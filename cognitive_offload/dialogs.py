"""Modal dialogs.

All of them share :class:`ModalDialog`, which handles centring on the parent,
Escape/Return handling and the grab/wait dance - previously each dialog did a
slightly different (and slightly broken) version of that.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .models import (
    KIND_KEY_BY_LABEL,
    REPEAT_KEY_BY_LABEL,
    REPEAT_LABELS,
    KIND_UNSET,
    TASK_KINDS,
    Task,
    humanize_date,
    parse_date_input,
    parse_estimate_input,
    repeat_label,
    today_iso,
)
from .handoff import (
    DEFAULT_FOLLOW_UP_DAYS,
    TARGET_KEY_BY_LABEL,
    TARGET_KEYS,
    TARGET_LABELS,
    follow_up_date,
    target_for,
)
from .presenter import step_line
from .queries import split_lines, suggest_tasks
from .storage import CATEGORIES, CATEGORY_KEYS
from .theme import SIZE_BASE, SIZE_LG, SIZE_SM, font, px, style_text, tokens


class ModalDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, size: tuple | None = None):
        super().__init__(parent)
        self.result = None
        self._parent = parent
        self.title(title)
        self.configure(background=tokens().background)
        self.transient(parent.winfo_toplevel())
        self._fit_width = None
        if size:
            # Sizes are designed against 96 DPI; px() carries them to
            # HiDPI screens where the fonts inside have already grown.
            size = (px(self, size[0]), size[1] if size[1] is None else px(self, size[1]))
        if size and size[1] is None:
            # Width pinned, height to content (resolved in show(), once the
            # subclass has built its body): a fixed height is always wrong
            # for someone when the content varies — the warm-up ladder's
            # length is per-config — leaving a dead band or a cut-off.
            self.minsize(size[0], 1)
            self._fit_width = size[0]
        elif size:
            self.minsize(*size)
            self.geometry(f"{size[0]}x{size[1]}")
        # Opt-in ceiling for a dialog whose content has no natural bound.
        # Fitting to content is right until the content is taller than the
        # screen, at which point the controls at the bottom are simply gone
        # and the window cannot be resized to reach them.
        self._max_height = None
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        #: the frame packed directly on the window. A subclass may replace
        #: ``self.body`` with something nested (see TaskEditorDialog, which
        #: puts a scrolling canvas in between), and the button row still has
        #: to pack against the WINDOW rather than inside whatever that is.
        self._outer = self.body
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        # "or \"break\"" stops the global Escape binding from also pausing a
        # running session behind the dialog.
        self.bind("<Escape>", lambda _e: self.cancel() or "break")

    def _fit_to_content(self) -> None:
        """Grow to fit what was built, but never past the ceiling.

        Three copies of this geometry line had drifted into the file — the
        initial show, the suggestion refresh and the ladder editor — so a
        cap added to one would have missed the others.
        """
        if not self._fit_width:
            return
        height = self.winfo_reqheight()
        if self._max_height:
            height = min(height, self._max_height)
        self.geometry(f"{self._fit_width}x{height}")

    def button_row(self, ok_text: str = "OK") -> ttk.Frame:
        """The row that closes the dialog, packed so it cannot be dropped.

        Tk gives each slave its slab in pack order and squeezes what is left,
        so a row packed last inside an expanding body is the first thing to
        go when the window is shorter than its content — measured, the task
        editor's Save and Cancel were **not drawn at all** below 668px. The
        row is therefore packed against the bottom of the window *before* the
        body is re-packed to take the rest: whatever else has to give, the
        way out of the dialog does not.
        """
        row = ttk.Frame(self, padding=(12, 0, 12, 12))
        self._outer.pack_forget()
        row.pack(side="bottom", fill="x")
        self._outer.pack(fill="both", expand=True)
        ttk.Button(row, text="Cancel", style="Outline.TButton", command=self.cancel).pack(side="right")
        ttk.Button(row, text=ok_text, style="Default.TButton", command=self.ok).pack(
            side="right", padx=(0, 8)
        )
        return row

    def ok(self, _event=None):
        self.result = self.collect()
        if self.result is not None:
            self.destroy()

    def cancel(self, _event=None):
        self.result = None
        self.destroy()

    def collect(self):  # pragma: no cover - overridden
        return None

    def show(self):
        """Centre, make modal, and block until closed. Returns ``self.result``."""
        self.update_idletasks()
        self._fit_to_content()
        self._center()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return self.result

    def _center(self) -> None:
        top = self._parent.winfo_toplevel()
        try:
            width = self.winfo_width() or self.winfo_reqwidth()
            height = self.winfo_height() or self.winfo_reqheight()
            x = top.winfo_rootx() + max(0, (top.winfo_width() - width) // 2)
            y = top.winfo_rooty() + max(0, (top.winfo_height() - height) // 3)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass


KIND_CHOICES = [(KIND_UNSET, "Unsorted")] + list(TASK_KINDS.items())


class TaskEditorDialog(ModalDialog):
    """Edit a task: title, first step, feel, details, tags, booked time.

    Returns a dict so callers can pick out only the fields they use.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        first_step: str = "",
        kind: str = KIND_UNSET,
        scheduled_for: str = "",
        estimate_minutes: int = 0,
        repeat: str = "",
        snoozed_until: str = "",
        handed_to: str = "",
        follow_up_on: str = "",
        rest_of_plan: list[str] | None = None,
        window_title: str = "Task",
        with_tags: bool = False,
    ):
        # Width pinned, height fitted — the mechanism ModalDialog already
        # carries, and whose own comment says why: "a fixed height is always
        # wrong for someone when the content varies". This dialog varies more
        # than any other. It wanted 578px with a tag row and got 520, so
        # **Save and Cancel were simply not drawn**; the only way to keep an
        # edit was to know you could drag the window taller first. Every
        # optional row since — the excuse, the handoff, the wait — made it
        # worse.
        super().__init__(parent, window_title, size=(520, None))
        self._max_height = int(self.winfo_screenheight() * 0.8)
        self._make_scrollable()
        ttk.Label(self.body, text="Title").pack(anchor="w")
        self.title_entry = ttk.Entry(self.body)
        self.title_entry.pack(fill="x", pady=(2, 10))
        self.title_entry.insert(0, title)

        ttk.Label(self.body, text="Smallest next step").pack(anchor="w")
        self.step_entry = ttk.Entry(self.body)
        self.step_entry.pack(fill="x", pady=(2, 0))
        self.step_entry.insert(0, first_step)
        ttk.Label(
            self.body,
            text="The two-minute physical action that starts it — \"open the doc\", "
                 "\"find Dana's email\". This is the part that gets you moving.",
            style="Muted.TLabel",
            wraplength=px(self, 470),
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        # The plan, under the step it heads. The step box owns ONE line and
        # this owns the rest, so neither can overwrite the other's — which is
        # why the model keeps the current step out of `rest_of_plan` rather
        # than showing the whole list twice and picking a winner.
        rest = list(rest_of_plan or [])
        ttk.Label(self.body, text="The rest of the plan").pack(anchor="w")
        self.plan_text = tk.Text(self.body, height=3, wrap="word", undo=True)
        style_text(self.plan_text)
        # Not expand=True: pack squeezes the LATER slave when the window is
        # short, so making this one expand as well changed nothing except to
        # imply it shares the loss. It does not — see FINDING AR.
        self.plan_text.pack(fill="x", pady=(2, 0))
        self.plan_text.insert("1.0", "\n".join(rest))
        plan_hint = (
            "One step per line, in order. Optional — and only the top one has "
            "to be any good."
        )
        ttk.Label(self.body, text=plan_hint, style="Muted.TLabel",
                  wraplength=px(self, 470), justify="left").pack(
            anchor="w", pady=(2, 10))

        # Ticking a step off is the only thing that moves you down the plan,
        # and it lives here rather than on the list because it is a decision
        # about the task, not about the screen.
        self.step_done_var = None
        if rest:
            self.step_done_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                self.body,
                text=f"Done — move on to \"{rest[0]}\"",
                variable=self.step_done_var,
            ).pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Label(row, text="Feels like").pack(side="left")
        self.kind_var = tk.StringVar(value=dict(KIND_CHOICES).get(kind, "Unsorted"))
        ttk.Combobox(
            row,
            textvariable=self.kind_var,
            values=[label for _key, label in KIND_CHOICES],
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Booked for").pack(side="left")
        self.date_entry = ttk.Entry(row, width=14)
        self.date_entry.pack(side="left", padx=(6, 0))
        self.date_entry.insert(0, scheduled_for)
        # The estimate gets its own row — packed onto the row above it clips
        # off the dialog edge, the same trap the date hint fell into.
        estimate_row = ttk.Frame(self.body)
        estimate_row.pack(fill="x", pady=(6, 0))
        ttk.Label(estimate_row, text="About").pack(side="left")
        self.estimate_entry = ttk.Entry(estimate_row, width=5)
        self.estimate_entry.pack(side="left", padx=(6, 0))
        if estimate_minutes:
            self.estimate_entry.insert(0, str(estimate_minutes))
        ttk.Label(estimate_row, text="minutes, at a guess").pack(side="left", padx=(4, 0))
        ttk.Label(estimate_row, text="Repeats").pack(side="left", padx=(16, 0))
        self.repeat_var = tk.StringVar(value=repeat_label(repeat))
        ttk.Combobox(estimate_row, textvariable=self.repeat_var,
                     values=list(REPEAT_LABELS), state="readonly",
                     width=15).pack(side="left", padx=(6, 0))
        ttk.Label(
            self.body,
            text="Dates can be \"today\", \"tomorrow\", a weekday like \"fri\", "
                 "or 2026-08-01. The minutes are a guess, and a guess is "
                 "plenty — nothing holds you to it.",
            style="Muted.TLabel", wraplength=px(self, 470), justify="left",
        ).pack(anchor="w", pady=(2, 10))

        # The one exit from "Not today" besides waiting: visible only while
        # a snooze is actually in effect, and still no badge on the list.
        self.unsnooze_var = None
        if snoozed_until and snoozed_until > today_iso():
            self.unsnooze_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                self.body,
                text=f"Excused from suggestions until "
                     f"{humanize_date(snoozed_until)} — put it back in the "
                     f"running now",
                variable=self.unsnooze_var,
            ).pack(anchor="w", pady=(0, 10))

        # Two directions on one state, and never both on screen at once.
        #
        # The way OUT shipped first, and for a while it was the only half
        # that existed: the way IN was an agent handoff, reachable from one
        # quadrant of the other tab. So the whole waiting treatment — the
        # badge, the line under the title, the task quietly stepping out of
        # the suggestion slot until the day you said you would look again —
        # could only ever describe an AI agent, while most of what anyone is
        # actually waiting on is a person. Nothing in the model ever thought
        # so: `handed_to` is free text and always was.
        self.unwait_var = None
        self.waiting_entry = None
        self.check_back_entry = None
        if handed_to:
            self.unwait_var = tk.BooleanVar(value=False)
            waiting = f"Out with {handed_to}"
            if follow_up_on:
                waiting += f", checking back {humanize_date(follow_up_on)}"
            ttk.Checkbutton(
                self.body,
                text=f"{waiting} — take it back and do it yourself",
                variable=self.unwait_var,
            ).pack(anchor="w", pady=(0, 10))
        else:
            waiting_row = ttk.Frame(self.body)
            waiting_row.pack(fill="x")
            ttk.Label(waiting_row, text="Waiting on").pack(side="left")
            self.waiting_entry = ttk.Entry(waiting_row, width=18)
            self.waiting_entry.pack(side="left", padx=(6, 16))
            ttk.Label(waiting_row, text="check back").pack(side="left")
            self.check_back_entry = ttk.Entry(waiting_row, width=14)
            self.check_back_entry.pack(side="left", padx=(6, 0))
            waiting_hint = (
                "A person or an agent — anyone but you. It keeps its place "
                "in the list and in every search, and stops being offered as "
                "the next thing to start until the day you check back. "
                "Blank means three days from now."
            )
            ttk.Label(self.body, text=waiting_hint, style="Muted.TLabel",
                      wraplength=px(self, 470), justify="left").pack(
                anchor="w", pady=(2, 10))

        ttk.Label(self.body, text="Details").pack(anchor="w")
        # Six lines rather than eight: the plan box above took two, and the
        # details box was the more generously sized of the pair.
        self.content_text = tk.Text(self.body, height=6, wrap="word", undo=True)
        style_text(self.content_text)
        self.content_text.pack(fill="both", expand=True, pady=(2, 10))
        self.content_text.insert("1.0", content)

        self.tags_entry = None
        if with_tags:
            ttk.Label(self.body, text="Tags (comma separated)").pack(anchor="w")
            self.tags_entry = ttk.Entry(self.body)
            self.tags_entry.pack(fill="x", pady=(2, 0))
            self.tags_entry.insert(0, ", ".join(tags or []))

        self.button_row("Save")
        self.title_entry.focus_set()
        self.title_entry.bind("<Return>", lambda _e: self.step_entry.focus_set())

    def _make_scrollable(self) -> None:
        """Put a scrolling canvas between the window and the form.

        This dialog is the one that grows. It is already the tallest in the
        app and it gains a row every time a task learns something new, and
        the app supports a 1366x768 laptop on purpose — `_fit_to_screen`
        exists because the main window used to open 113px past the bottom of
        one. Measured on that screen the fullest editor wants 828px against a
        614px ceiling, and Tk's answer to a window shorter than its content
        is to stop placing widgets: at 614 the details box and the tag row
        were simply not drawn, at 520 nine controls were missing.

        A ceiling without a scrollbar is just a quieter version of the bug
        this dialog was fixed for one release ago. Content that fits looks
        exactly as it did — the canvas is sized to the form and the scrollbar
        stays hidden.
        """
        host = self.body
        self._canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0,
                                 background=tokens().background)
        self._vbar = ttk.Scrollbar(host, orient="vertical",
                                   command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._on_scrolled)
        self._canvas.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(self._canvas)
        self._form_window = self._canvas.create_window((0, 0), window=form,
                                                       anchor="nw")
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._form_window, width=e.width))
        form.bind("<Configure>", lambda _e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            # On the window, so the wheel works wherever the pointer is. Tk
            # puts the toplevel in every child's bindtags, so one binding
            # covers the lot.
            self.bind(sequence, self._on_wheel)
        # Same trick for focus: tabbing must not put the cursor in a box
        # that is scrolled out of sight.
        self.bind("<FocusIn>", lambda e: self._scroll_into_view(e.widget))
        # Everything built from here lands in the scrolling form instead.
        self.body = form

    def _on_scrolled(self, first: str, last: str) -> None:
        """Show the scrollbar only when there is something to scroll to."""
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._vbar.pack_forget()
        else:
            self._vbar.pack(side="right", fill="y")
        self._vbar.set(first, last)

    def _scrolls_itself(self, widget) -> bool:
        """Is the pointer over something that will handle the wheel itself?

        A ``Text``'s own class binding scrolls it and does **not** return
        "break", so the event carries on to the window binding as well —
        measured, one notch over the notes box moved the text AND slid the
        whole form by the same amount. Only true while the widget actually
        has somewhere to scroll: over a half-empty notes box the wheel
        should still move the form, or it dies in the middle of the dialog
        for no reason the person can see.
        """
        while widget is not None and widget is not self:
            if isinstance(widget, tk.Text):
                try:
                    first, last = widget.yview()
                except tk.TclError:
                    return False
                return not (first <= 0.0 and last >= 1.0)
            widget = getattr(widget, "master", None)
        return False

    def _on_wheel(self, event):
        if self._scrolls_itself(self.winfo_containing(event.x_root, event.y_root)):
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(delta, "units")

    def _scroll_into_view(self, widget) -> None:
        """Bring a widget that has just taken focus into the visible part.

        Tab moves focus by widget order, not by what is on screen, so on a
        window short enough to scroll it walked straight into the details
        box and the tag row while both were below the bottom edge — you type
        and nothing appears. Same arithmetic as `RowList.see`.

        Widgets outside the form are skipped, which is how Save and Cancel
        stay put: they are deliberately packed on the window, not in the
        scrolling area.
        """
        if widget is None:
            return
        inside = str(widget).startswith(f"{self.body}.")
        if not inside:
            return
        self.update_idletasks()
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + widget.winfo_height()
        room = self._canvas.winfo_height()
        total = max(1, self.body.winfo_height())
        seen_from = self._canvas.canvasy(0)
        if top < seen_from:
            self._canvas.yview_moveto(top / total)
        elif bottom > seen_from + room:
            self._canvas.yview_moveto(max(0.0, (bottom - room) / total))

    def _fit_to_content(self) -> None:
        """Ask for the height the form wants, then let the ceiling bite.

        The canvas is what stands between the window and the form, so it is
        the thing that has to *request* the form's full height — otherwise
        the window fits itself to a canvas of no particular size. Once the
        ceiling caps the window, the canvas is the widget that gives, and
        the scrollbar covers the difference.
        """
        self.update_idletasks()
        self._canvas.configure(height=self.body.winfo_reqheight())
        # Tk recomputes the window's requested height from its children in an
        # idle task, and the base class reads that number — so without this
        # the first fit sizes the window to the canvas's OLD height and only
        # a second call gets it right.
        self.update_idletasks()
        super()._fit_to_content()
        self.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _warn_about_date(self, entry) -> None:
        """One sentence, both date fields. Said twice it would drift once."""
        messagebox.showwarning(
            "Date not understood",
            "Try 'today', 'tomorrow', a weekday, or a date like 2026-08-01.",
            parent=self,
        )
        entry.focus_set()

    def collect(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Title required", "The title cannot be empty.", parent=self)
            self.title_entry.focus_set()
            return None
        scheduled = parse_date_input(self.date_entry.get())
        if scheduled is None:
            self._warn_about_date(self.date_entry)
            return None
        waiting_on = self.waiting_entry.get().strip() if self.waiting_entry else ""
        check_back = ""
        if waiting_on:
            check_back = parse_date_input(self.check_back_entry.get())
            if check_back is None:
                self._warn_about_date(self.check_back_entry)
                return None
            # Handing something over and then forgetting it is not delegating,
            # it is losing it somewhere more respectable. Every wait gets a
            # date, and the default is the one the agent handoff already uses.
            check_back = check_back or follow_up_date(today_iso())
        # "junk is just 'no guess', never an error dialog" — that decision
        # stands. What changed is how much counts as junk: "20 mins", "20m",
        # "1h" and "~15" all used to land here and vanish, which is the one
        # thing worse than refusing them, because a discarded guess reads
        # exactly like a blank field. parse_estimate_input understands them;
        # what it still cannot read remains a silent "no guess".
        estimate = parse_estimate_input(self.estimate_entry.get())
        if estimate is None:
            estimate = 0
        result = {
            "title": title,
            "content": self.content_text.get("1.0", "end").strip(),
            "first_step": self.step_entry.get().strip(),
            "kind": KIND_KEY_BY_LABEL.get(self.kind_var.get(), KIND_UNSET),
            "scheduled_for": scheduled,
            "estimate_minutes": estimate,
            "repeat": REPEAT_KEY_BY_LABEL.get(self.repeat_var.get(), ""),
            "clear_snooze": bool(self.unsnooze_var and self.unsnooze_var.get()),
            "take_back": bool(self.unwait_var and self.unwait_var.get()),
            "waiting_on": waiting_on,
            "check_back": check_back,
            # split_lines already strips bullets, checkboxes and the "[time]"
            # prefix quick capture adds, which is exactly what someone pastes
            # in here from a note they made earlier.
            "rest_of_plan": split_lines(self.plan_text.get("1.0", "end")),
            "step_done": bool(self.step_done_var and self.step_done_var.get()),
        }
        if self.tags_entry is not None:
            tags = [t.strip().lower() for t in self.tags_entry.get().split(",")]
            result["tags"] = [t for t in tags if t]
        return result


class StartHereDialog(ModalDialog):
    """"I don't know where to start."

    Asks how the next thing needs to *feel*, then offers a shortlist rather
    than the whole list - a long list is what causes the freeze in the first
    place.
    """

    def __init__(self, parent: tk.Misc, tasks: list[Task], warm: set | None = None):
        # Height to content: three suggestions or an empty-state line, never
        # a fixed 460px with a dead band above the buttons.
        super().__init__(parent, "Where do I start?", size=(560, None))
        self._tasks = tasks
        self._warm = warm
        self._offset = 0
        self._suggestions: list[Task] = []

        ttk.Label(
            self.body, text="What can you face right now?", font=font(SIZE_LG, "bold")
        ).pack(anchor="w")
        ttk.Label(
            self.body,
            text="Pick the shape of the work, not the most important thing. "
                 "Starting anything beats picking perfectly.",
            style="Muted.TLabel",
            wraplength=px(self, 510),
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        self.kind_var = tk.StringVar(value="")
        kinds = ttk.Frame(self.body)
        kinds.pack(fill="x", pady=(0, 10))
        options = [("Anything", "")] + [(label, key) for key, label in TASK_KINDS.items()]
        for column, (label, key) in enumerate(options):
            ttk.Radiobutton(
                kinds, text=label, value=key, variable=self.kind_var, command=self._refresh
            ).grid(row=column // 3, column=column % 3, sticky="w", padx=(0, 14), pady=2)

        self.choice_var = tk.StringVar(value="")
        self.choices = ttk.Frame(self.body)
        self.choices.pack(fill="both", expand=True)

        controls = ttk.Frame(self.body)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="Show me others", style="Outline.TButton", command=self._cycle).pack(side="left")
        ttk.Button(controls, text="Cancel", style="PageGhost.TButton",
                   command=self.cancel).pack(side="right")
        ttk.Button(controls, text="Start on this", style="Default.TButton", command=self.ok).pack(
            side="right", padx=(0, 8)
        )

        self._refresh()

    def _refresh(self) -> None:
        for child in self.choices.winfo_children():
            child.destroy()
        self._suggestions = suggest_tasks(
            self._tasks, kind=self.kind_var.get() or None, limit=3, offset=self._offset,
            warm=self._warm,
        )
        if not self._suggestions:
            ttk.Label(
                self.choices,
                text="Nothing open in that shape. Try 'Anything', or capture "
                     "something new — an empty list is allowed.",
                style="Muted.TLabel",
                wraplength=px(self, 510),
                justify="left",
            ).pack(anchor="w", pady=6)
            self.choice_var.set("")
        else:
            self.choice_var.set(self._suggestions[0].id)
            for task in self._suggestions:
                frame = ttk.Frame(self.choices)
                frame.pack(fill="x", pady=4)
                ttk.Radiobutton(
                    frame, text=task.text, value=task.id, variable=self.choice_var
                ).pack(anchor="w")
                detail = task.first_step or "No first step yet — you'll be asked for one."
                ttk.Label(
                    frame, text=f"    → {detail}", style="Muted.TLabel",
                    wraplength=px(self, 490), justify="left",
                ).pack(anchor="w")
        # The choice list's length just changed; follow it.
        self.update_idletasks()
        self._fit_to_content()

    def _cycle(self) -> None:
        self._offset += 3
        self._refresh()

    def collect(self):
        chosen = self.choice_var.get()
        for task in self._suggestions:
            if task.id == chosen:
                return task
        return None


class StartFocusDialog(ModalDialog):
    """The warm-up ladder plus the session length.

    The ladder is the "stepwise downshift": a couple of small moves between
    whatever you were doing and the task, so the jump is not straight from
    high stimulation to a cold start. Nothing here is required - the
    checkboxes are a prompt, not a gate.
    """

    def __init__(
        self,
        parent: tk.Misc,
        task_text: str = "",
        first_step: str = "",
        minutes: int = 15,
        warmup_steps: list[str] | None = None,
        show_warmup: bool = True,
        estimate_minutes: int = 0,
        popout: bool = False,
    ):
        super().__init__(parent, "Start a focus session", size=(520, None))

        ttk.Label(self.body, text="Working on", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(
            self.body,
            text=task_text or "Free focus (no task selected)",
            font=font(SIZE_LG, "bold"),
            wraplength=px(self, 470),
            justify="left",
        ).pack(anchor="w", pady=(0, 2 if estimate_minutes else 12))
        if estimate_minutes:
            # Display only — the session length below stays the user's call.
            ttk.Label(
                self.body,
                text=f"Your guess: about {estimate_minutes} min.",
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(0, 12))

        ttk.Label(self.body, text="First move").pack(anchor="w")
        self.step_entry = ttk.Entry(self.body)
        self.step_entry.pack(fill="x", pady=(2, 2))
        self.step_entry.insert(0, first_step)
        ttk.Label(
            self.body,
            text="Name the smallest physical action. You are only committing to this.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        self.warmup_vars: list[tk.BooleanVar] = []
        self._steps = list(warmup_steps or [])
        self._step_entries: list | None = None  # None = not editing
        self.ladder_frame = ttk.Frame(self.body)
        if show_warmup and warmup_steps:
            self.ladder_frame.pack(fill="x")
            self._build_ladder()

        # The rituals belong to the user, and this dialog is where the itch
        # occurs — not a hidden JSON file.
        self.show_warmup_var = tk.BooleanVar(value=show_warmup)
        ttk.Checkbutton(self.body, text="Show the warm-up ladder before sessions",
                        variable=self.show_warmup_var).pack(anchor="w", pady=(10, 0))
        self.popout_var = tk.BooleanVar(value=popout)
        ttk.Checkbutton(self.body, text="Keep the timer floating over my work",
                        variable=self.popout_var).pack(anchor="w", pady=(2, 0))

        length = ttk.Frame(self.body)
        length.pack(fill="x", pady=(14, 0))
        ttk.Label(length, text="Session length").pack(side="left")
        self.minutes_var = tk.IntVar(value=minutes)
        ttk.Spinbox(length, from_=1, to=120, width=5, textvariable=self.minutes_var).pack(
            side="left", padx=(8, 6)
        )
        ttk.Label(length, text="minutes", style="Muted.TLabel").pack(side="left")

        self.button_row("Start")
        self.step_entry.focus_set()
        self.bind("<Return>", self.ok)

    def _build_ladder(self) -> None:
        heading = ttk.Frame(self.ladder_frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="Warm-up ladder", font=font(SIZE_BASE, "bold")).pack(
            side="left")
        ttk.Button(heading, text="Edit steps…", style="SmPageGhost.TButton",
                   command=self._edit_steps).pack(side="left", padx=(8, 0))
        ttk.Label(
            self.ladder_frame,
            text="Step down towards the task instead of leaping at it. "
                 "Tick what you've done — skipping them is fine too.",
            style="Muted.TLabel",
            wraplength=px(self, 470),
            justify="left",
        ).pack(anchor="w", pady=(2, 6))
        for step in self._steps:
            var = tk.BooleanVar(value=False)
            self.warmup_vars.append(var)
            ttk.Checkbutton(self.ladder_frame, text=step, variable=var).pack(
                anchor="w", pady=1)

    def _edit_steps(self) -> None:
        """Swap the ladder for prefilled entries: a fixed ladder habituates
        within days, and steps tuned to the user's real downshift ritual
        keep reading as themselves."""
        if self._step_entries is not None:
            return
        for child in self.ladder_frame.winfo_children():
            child.destroy()
        self.warmup_vars = []
        ttk.Label(self.ladder_frame, text="Warm-up ladder",
                  font=font(SIZE_BASE, "bold")).pack(anchor="w")
        ttk.Label(
            self.ladder_frame,
            text="Your own downshift, in your own words. Blank lines are "
                 "dropped; the changes stick for future sessions.",
            style="Muted.TLabel", wraplength=px(self, 470), justify="left",
        ).pack(anchor="w", pady=(2, 6))
        self._step_entries = []
        for index in range(max(3, len(self._steps))):
            entry = ttk.Entry(self.ladder_frame)
            entry.pack(fill="x", pady=1)
            if index < len(self._steps):
                entry.insert(0, self._steps[index])
            self._step_entries.append(entry)
        self.update_idletasks()
        self._fit_to_content()

    def collect(self):
        try:
            minutes = max(1, min(120, int(self.minutes_var.get())))
        except (tk.TclError, ValueError):
            minutes = 15
        edited = None
        if self._step_entries is not None:
            edited = [e.get().strip() for e in self._step_entries if e.get().strip()]
        return {
            "minutes": minutes,
            "first_step": self.step_entry.get().strip(),
            "warmup_done": sum(1 for var in self.warmup_vars if var.get()),
            "warmup_steps": edited,  # None = untouched
            "show_warmup": bool(self.show_warmup_var.get()),
            "popout": bool(self.popout_var.get()),
        }


class QuadrantDialog(ModalDialog):
    """Pick one of the four Eisenhower quadrants."""

    def __init__(self, parent: tk.Misc, count: int = 1, initial: str = "do_first",
                 window_title: str = "Move to matrix"):
        super().__init__(parent, window_title, size=(360, 240))
        heading = "Move task to:" if count == 1 else f"Move {count} tasks to:"
        ttk.Label(self.body, text=heading, font=font(SIZE_BASE, "bold")).pack(anchor="w")

        self.choice = tk.StringVar(value=initial if initial in CATEGORIES else "do_first")
        for key in CATEGORY_KEYS:
            ttk.Radiobutton(
                self.body, text=CATEGORIES[key][2], variable=self.choice, value=key,
                style="TRadiobutton",
            ).pack(anchor="w", pady=3)

        self.button_row("Move")
        self.bind("<Return>", self.ok)

    def collect(self):
        return self.choice.get()


class PromptDialog(ModalDialog):
    """A themed one-line prompt, replacing ``simpledialog.askstring``."""

    def __init__(self, parent: tk.Misc, title: str, prompt: str, initial: str = "",
                 hint: str = "", ok_text: str = "OK"):
        super().__init__(parent, title)
        self.resizable(False, False)
        ttk.Label(self.body, text=prompt, wraplength=px(self, 360), justify="left").pack(anchor="w")
        self.entry = ttk.Entry(self.body, width=42)
        self.entry.pack(fill="x", pady=(8, 0))
        self.entry.insert(0, initial)
        self.entry.select_range(0, "end")
        if hint:
            ttk.Label(self.body, text=hint, style="Muted.TLabel",
                      wraplength=px(self, 360), justify="left").pack(anchor="w", pady=(4, 0))
        self.button_row(ok_text)
        self.entry.focus_set()
        self.bind("<Return>", self.ok)

    def collect(self):
        # "" is a valid answer (it clears a booking); None means cancelled,
        # and cancel() sets that without going through collect().
        return self.entry.get().strip()


class SessionEndDialog(ModalDialog):
    """What happens now the block is over.

    A session ends at the one moment the app knows something got worked on,
    and it used to ask only about a break — leaving the user to remember to go
    and tick the task off later, which is precisely the kind of remembering
    this app exists to take over.
    """

    def __init__(self, parent: tk.Misc, message: str, task_text: str, break_minutes: int = 5,
                 first_step: str = "", parked: int = 0,
                 rest_of_plan: list[str] | None = None, place: str = ""):
        super().__init__(parent, "Session finished")
        self.resizable(False, False)
        ttk.Label(self.body, text=message, font=font(SIZE_LG, "bold"),
                  wraplength=px(self, 380), justify="left").pack(anchor="w")
        ttk.Label(self.body, text=task_text, style="Muted.TLabel",
                  wraplength=px(self, 380), justify="left").pack(anchor="w", pady=(6, 12))
        if parked:
            # The second half of Park-it's contract: the thought comes back.
            # Session end is the transition moment the app already owns.
            plural = "s" if parked != 1 else ""
            ttk.Label(self.body,
                      text=f"{parked} thought{plural} parked in the scratchpad "
                           f"while you worked — safe there.",
                      style="Muted.TLabel", wraplength=px(self, 380),
                      justify="left").pack(anchor="w", pady=(0, 12))

        # The hand-off. Right now you know what comes next; tomorrow you will
        # be looking at a first step you already did. Optional, and skipping
        # it costs nothing.
        # A task with a plan is asked a different question, because on one
        # the honest answer is already written down. Two things can have
        # happened in the last fifteen minutes — you finished this step, or
        # you did not — and the old single blank field conflated them: it
        # invited a description of the NEXT step while the cursor was still
        # on this one, so typing the honest answer overwrote the wrong line.
        rest = list(rest_of_plan or [])
        self.step_done_var = None
        has_plan = bool(rest) or bool(place)
        if has_plan:
            ttk.Label(self.body, text="What does this step say now?").pack(anchor="w")
        else:
            ttk.Label(self.body,
                      text="Where does it pick up next time?").pack(anchor="w")
        self.next_entry = ttk.Entry(self.body, width=44)
        self.next_entry.pack(fill="x", pady=(4, 2))
        if has_plan:
            # Prefilled, so accepting it unchanged means exactly what it
            # looks like: nothing. A blank box at the tired end of a block is
            # a question; a filled one is a confirmation.
            self.next_entry.insert(0, first_step)
            if place:
                ttk.Label(self.body, text=place, style="Muted.TLabel",
                          wraplength=px(self, 380), justify="left").pack(anchor="w")
        elif first_step:
            ttk.Label(self.body, text=f"was: {first_step}", style="Muted.TLabel",
                      wraplength=px(self, 380), justify="left").pack(anchor="w")
        # Two hints, because the field means two different things. "Leave it
        # blank" is an invitation on an empty box and a lie on a filled one:
        # blanking a prefilled step changes nothing, so the sentence would be
        # offering an action that does not exist.
        hint = ("Change it if it needs changing — leaving it as it is is an "
                "answer." if has_plan
                else "Leave it blank if you would rather not decide now.")
        ttk.Label(self.body, text=hint, style="Muted.TLabel",
                  wraplength=px(self, 380), justify="left").pack(
            anchor="w", pady=(0, 14))
        if rest:
            self.step_done_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                self.body, text=f"Done — move on to \"{rest[0]}\"",
                variable=self.step_done_var,
            ).pack(anchor="w", pady=(0, 10))

        for label, value, style in (
            ("It's finished — mark it done", "done", "Default.TButton"),
            (f"Not yet — take {break_minutes} minutes", "break", "Outline.TButton"),
            # PageGhost, not Ghost: dialog bodies sit on the page background,
            # and the card-surface ghost renders as a white patch there.
            ("Not yet — keep going", "carry_on", "PageGhost.TButton"),
        ):
            button = ttk.Button(self.body, text=label, style=style,
                                command=lambda v=value: self._choose(v))
            button.pack(fill="x", pady=2)
        # Focus starts in the hand-off field, and Enter there means "keep the
        # step, carry on" — never "done". Typing a next step and hitting Enter
        # is the most ingrained habit on a text field, and having it declare
        # the task finished (discarding the step from NEXT UP's ranking) is
        # the opposite of what the user just said. Marking done takes a
        # deliberate Tab+Space or a click.
        self.next_entry.focus_set()
        # The dialog is built before it is mapped, and a focus_set that early
        # is dropped if the parent isn't viewable yet; re-assert it when the
        # window actually appears.
        self.bind("<Map>", lambda _e: self.next_entry.focus_set(), add=True)
        self.next_entry.bind("<Return>", self._keep_step)

    def _keep_step(self, _event=None):
        """Enter in the hand-off field: keep the step, carry on — never "done"."""
        self._choose("carry_on")

    def _choose(self, value: str) -> None:
        self.result = {
            "choice": value,
            "next_step": self.next_entry.get().strip(),
            "step_done": bool(self.step_done_var and self.step_done_var.get()),
        }
        self.destroy()

    def cancel(self, _event=None):
        # Closing the window is "no answer", which means carry on. Anything
        # already typed into the hand-off is still worth keeping.
        step = ""
        try:
            step = self.next_entry.get().strip()
        except tk.TclError:
            pass
        self.result = {"choice": "carry_on", "next_step": step,
                       "step_done": bool(self.step_done_var
                                         and self.step_done_var.get())}
        self.destroy()


class WeekReviewDialog(ModalDialog):
    """The week, in evidence.

    "I did nothing this week" is a distortion, and the correction is not
    motivation — it is the record. One line per day that HAD anything;
    days with nothing are simply omitted, never listed as zeros. It can
    only ever say what happened.
    """

    def __init__(self, parent: tk.Misc, days: list, total_sessions: int,
                 total_minutes: int):
        super().__init__(parent, "This week", size=(480, None))
        self.resizable(False, False)
        ttk.Label(self.body, text="This week, in evidence",
                  font=font(SIZE_LG, "bold")).pack(anchor="w")
        if not days:
            ttk.Label(
                self.body,
                text="A quiet week is just a quiet week — nothing here "
                     "counts against you. The strip fills in as sessions "
                     "happen.",
                style="Muted.TLabel", wraplength=px(self, 430), justify="left",
            ).pack(anchor="w", pady=(6, 0))
        # The days scroll; the total and the way out do not. A busy week of
        # long titles ran past the bottom of a 1366x768 screen, and what fell
        # off first was the totals line and the Close button — the single
        # most reassuring number this app produces, lost on exactly the week
        # that earned it, in a window that cannot be resized to reach it.
        self._max_height = int(self.winfo_screenheight() * 0.8)
        days_area = ttk.Frame(self.body)
        days_area.pack(fill="both", expand=True)
        canvas = tk.Canvas(days_area, highlightthickness=0, borderwidth=0,
                           background=tokens().background)
        canvas.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(days_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resized(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())
            # The scrollbar only appears when it has something to do; an
            # ordinary week should not grow furniture it does not need.
            needed = inner.winfo_reqheight() > canvas.winfo_height()
            if needed and not bar.winfo_ismapped():
                bar.pack(side="right", fill="y")
            elif not needed and bar.winfo_ismapped():
                bar.pack_forget()

        inner.bind("<Configure>", _resized)
        canvas.bind("<Configure>", _resized)
        for widget in (canvas, inner):
            widget.bind("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            widget.bind("<Button-4>", lambda _e: canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda _e: canvas.yview_scroll(1, "units"))

        for entry in days:
            line = entry.label
            if entry.sessions:
                plural = "s" if entry.sessions != 1 else ""
                line += (f" · {entry.sessions} session{plural}"
                         f" · {entry.minutes} min")
            ttk.Label(inner, text=line, font=font(SIZE_BASE, "bold")).pack(
                anchor="w", pady=(8, 0))
            for title in entry.titles:
                ttk.Label(inner, text=f"   ✓ {title}", style="Muted.TLabel",
                          wraplength=px(self, 410), justify="left").pack(anchor="w")
            # Steps use a different mark from finished tasks, because they
            # are different evidence: a task done and a step done should not
            # read as the same thing at a glance.
            for step, task in entry.steps:
                ttk.Label(inner, text=f"   · {step_line(step, task)}",
                          style="Muted.TLabel", wraplength=px(self, 410),
                          justify="left").pack(anchor="w")
        # Ask for exactly as much room as the days need, up to the ceiling.
        # Without this the canvas asks for nothing and even a quiet week
        # would scroll — trading one wrong answer for another.
        inner.update_idletasks()
        room = int(self.winfo_screenheight() * 0.8) - px(self, 160)
        canvas.configure(height=max(px(self, 80),
                                    min(inner.winfo_reqheight(), room)))

        # Named, because a test has to be able to ask where they ended up:
        # these two are precisely what used to fall off the bottom.
        self.totals_label = None
        if days:
            plural = "s" if total_sessions != 1 else ""
            self.totals_label = ttk.Label(
                self.body,
                text=f"{total_sessions} session{plural} · {total_minutes} "
                     f"minutes across the week.",
                style="Muted.TLabel",
            )
            self.totals_label.pack(anchor="w", pady=(12, 0))
        self.close_button = ttk.Button(self.body, text="Close",
                                       style="Outline.TButton",
                                       command=self.cancel)
        self.close_button.pack(anchor="e", pady=(14, 0))


class ShortcutsDialog(ModalDialog):
    """A cheat-sheet, so the shortcuts are actually discoverable."""

    SHORTCUTS = [
        ("Starting", [
            ("Ctrl+G", "Where do I start? — pick something"),
            ("Ctrl+R", "Focus session on the selected task"),
            ("Escape", "Pause the session"),
        ]),
        ("Capture", [
            ("Enter (capture box)", "Add as task"),
            ("Ctrl+Enter (capture box)", "Add to scratchpad"),
            ("Ctrl+N", "Focus the capture box"),
            ("Ctrl+B", "Send scratchpad lines to tasks"),
        ]),
        ("Tasks", [
            # Enter was bound from the start and listed nowhere. It is the
            # key a keyboard-first user reaches for, and the one editing
            # route that needs no chord to remember.
            ("Enter / Double click / Ctrl+D", "Edit details"),
            ("Space", "Toggle done"),
            ("Up / Down", "Move through the list"),
            ("Delete", "Delete selected"),
            ("Ctrl+P", "Toggle high priority"),
            ("Ctrl+T", "Add a tag"),
            ("Ctrl+Up", "Pin to the top (again to unpin)"),
            ("Ctrl+M", "Send selection to the matrix"),
            ("Ctrl+Z", "Undo the last change"),
            ("Ctrl+F", "Search"),
        ]),
        ("App", [
            ("Ctrl+S", "Save now"),
            ("Ctrl+O", "Open a saved session"),
            ("Ctrl+1 / Ctrl+2", "Switch tab"),
            ("Escape", "Pause the timer / close a dialog"),
            ("F1", "This help"),
        ]),
    ]

    def __init__(self, parent: tk.Misc):
        # No fixed size: the window sizes itself to the table so nothing is cut off.
        super().__init__(parent, "Keyboard shortcuts")
        self.resizable(False, False)
        for section, rows in self.SHORTCUTS:
            ttk.Label(self.body, text=section, font=font(SIZE_BASE + 1, "bold")).pack(
                anchor="w", pady=(8, 4)
            )
            grid = ttk.Frame(self.body)
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            for row, (keys, description) in enumerate(rows):
                # width pins every section's key column to the same edge —
                # four differently-ragged columns scan measurably slower.
                ttk.Label(grid, text=keys, style="Muted.TLabel",
                          font=font(SIZE_SM, "bold"), width=24).grid(
                    row=row, column=0, sticky="w", padx=(0, 12)
                )
                ttk.Label(grid, text=description, style="Muted.TLabel").grid(
                    row=row, column=1, sticky="w"
                )
        ttk.Button(self.body, text="Close", style="Outline.TButton", command=self.cancel).pack(anchor="e", pady=(14, 0))


class HandoffDialog(ModalDialog):
    """Hand a task to an agent, and say when it comes back.

    Delegate is the quadrant most people cannot use, because "give it to
    someone else" needs a someone else. This is that someone. The dialog asks
    for two things only — which agent, and anything you want to say about the
    task — and fills in the rest from what you already wrote down.

    The follow-up date is not optional and not a reminder to be dismissed: it
    is the difference between delegating a task and losing it.
    """

    def __init__(self, parent: tk.Misc, task_title: str, target_key: str = "",
                 follow_up_days: int = DEFAULT_FOLLOW_UP_DAYS):
        super().__init__(parent, "Hand this over", size=(520, None))
        ttk.Label(self.body, text="Handing over", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(self.body, text=task_title, wraplength=px(self, 470),
                  justify="left").pack(anchor="w", pady=(2, 12))

        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Label(row, text="To").pack(side="left")
        current = target_for(target_key)
        self.target_var = tk.StringVar(value=current.label)
        ttk.Combobox(row, textvariable=self.target_var, values=list(TARGET_LABELS),
                     state="readonly", width=18).pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Check back in").pack(side="left")
        self.days_entry = ttk.Entry(row, width=4)
        self.days_entry.pack(side="left", padx=(6, 0))
        self.days_entry.insert(0, str(follow_up_days))
        ttk.Label(row, text="days").pack(side="left", padx=(4, 0))

        ttk.Label(
            self.body,
            text="Nothing is sent anywhere. A brief is written to a file and "
                 "the command to run it goes on your clipboard — so you can "
                 "read it, change it, or not use it at all.",
            style="Muted.TLabel", wraplength=px(self, 470), justify="left",
        ).pack(anchor="w", pady=(8, 10))

        ttk.Label(self.body, text="Anything to say about it").pack(anchor="w")
        self.note_text = tk.Text(self.body, height=4, wrap="word")
        style_text(self.note_text)
        self.note_text.pack(fill="both", expand=True, pady=(2, 0))
        ttk.Label(
            self.body,
            text="Optional. The title, your details, the first step and the "
                 "booked date all go with it already.",
            style="Muted.TLabel", wraplength=px(self, 470), justify="left",
        ).pack(anchor="w", pady=(2, 0))

        self.button_row("Hand it over")

    def collect(self) -> dict:
        # An unreadable number of days is not worth a modal over: it falls
        # back to the default the same way an unreadable estimate becomes
        # "no guess". The task still gets a follow-up date, which is the part
        # that matters.
        try:
            days = int(self.days_entry.get().strip())
        except ValueError:
            days = DEFAULT_FOLLOW_UP_DAYS
        return {
            "target": TARGET_KEY_BY_LABEL.get(self.target_var.get(), "")
                      or TARGET_KEYS[0],
            "follow_up_days": max(1, min(days, 365)),
            "note": self.note_text.get("1.0", tk.END).strip(),
        }


class HandoffDoneDialog(ModalDialog):
    """Where the brief went and what to run — shown once, copyable.

    A status-bar line is the wrong place for a file path and a command: both
    are things you need to look at while doing something else, which is the
    exact moment this app's audience loses them.
    """

    def __init__(self, parent: tk.Misc, target, path, command: str):
        super().__init__(parent, "Handed over", size=(560, None))
        ttk.Label(self.body, text=f"Written for {target.label}",
                  style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(self.body, text=str(path), style="Muted.TLabel",
                  wraplength=px(self, 510), justify="left").pack(anchor="w", pady=(2, 12))

        ttk.Label(self.body, text="On your clipboard").pack(anchor="w")
        box = tk.Text(self.body, height=3, wrap="word")
        style_text(box)
        box.insert("1.0", command)
        box.configure(state="disabled")
        box.pack(fill="x", pady=(2, 10))

        ttk.Label(self.body, text=target.setup, style="Muted.TLabel",
                  wraplength=px(self, 510), justify="left").pack(anchor="w")
        ttk.Label(
            self.body,
            text="The task stays in Delegate, marked as waiting, until you "
                 "mark it done or take it back.",
            style="Muted.TLabel", wraplength=px(self, 510), justify="left",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(self.body, text="Close", style="Outline.TButton",
                   command=self.cancel).pack(anchor="e", pady=(14, 0))
