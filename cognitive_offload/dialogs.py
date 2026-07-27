"""Modal dialogs.

All of them share :class:`ModalDialog`, which handles centring on the parent,
Escape/Return handling and the grab/wait dance - previously each dialog did a
slightly different (and slightly broken) version of that.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .models import KIND_UNSET, TASK_KINDS, Task, parse_date_input
from .queries import suggest_tasks
from .storage import CATEGORIES, CATEGORY_KEYS
from .theme import SIZE_BASE, SIZE_LG, SIZE_SM, font, style_text, tokens


class ModalDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.result = None
        self._parent = parent
        self.title(title)
        self.configure(background=tokens().background)
        self.transient(parent.winfo_toplevel())
        if size:
            self.minsize(*size)
            self.geometry(f"{size[0]}x{size[1]}")
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        # "or \"break\"" stops the global Escape binding from also pausing a
        # running session behind the dialog.
        self.bind("<Escape>", lambda _e: self.cancel() or "break")

    def button_row(self, ok_text: str = "OK") -> ttk.Frame:
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(10, 0))
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
        window_title: str = "Task",
        with_tags: bool = False,
    ):
        super().__init__(parent, window_title, size=(520, 520))
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
            wraplength=470,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(0, 10))
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
        ttk.Label(row, text="today / tomorrow / fri / 2026-08-01", style="Muted.TLabel").pack(
            side="left", padx=(6, 0)
        )

        ttk.Label(self.body, text="Details").pack(anchor="w")
        self.content_text = tk.Text(self.body, height=8, wrap="word", undo=True)
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

    def collect(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Title required", "The title cannot be empty.", parent=self)
            self.title_entry.focus_set()
            return None
        scheduled = parse_date_input(self.date_entry.get())
        if scheduled is None:
            messagebox.showwarning(
                "Date not understood",
                "Try 'today', 'tomorrow', a weekday, or a date like 2026-08-01.",
                parent=self,
            )
            self.date_entry.focus_set()
            return None
        label_to_key = {label: key for key, label in KIND_CHOICES}
        result = {
            "title": title,
            "content": self.content_text.get("1.0", "end").strip(),
            "first_step": self.step_entry.get().strip(),
            "kind": label_to_key.get(self.kind_var.get(), KIND_UNSET),
            "scheduled_for": scheduled,
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

    def __init__(self, parent: tk.Misc, tasks: list[Task]):
        super().__init__(parent, "Where do I start?", size=(560, 460))
        self._tasks = tasks
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
            wraplength=510,
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
        ttk.Button(controls, text="Cancel", style="Ghost.TButton", command=self.cancel).pack(side="right")
        ttk.Button(controls, text="Start on this", style="Default.TButton", command=self.ok).pack(
            side="right", padx=(0, 8)
        )

        self._refresh()

    def _refresh(self) -> None:
        for child in self.choices.winfo_children():
            child.destroy()
        self._suggestions = suggest_tasks(
            self._tasks, kind=self.kind_var.get() or None, limit=3, offset=self._offset
        )
        if not self._suggestions:
            ttk.Label(
                self.choices,
                text="Nothing open in that shape. Try 'Anything', or capture "
                     "something new — an empty list is allowed.",
                style="Muted.TLabel",
                wraplength=510,
                justify="left",
            ).pack(anchor="w", pady=6)
            self.choice_var.set("")
            return

        self.choice_var.set(self._suggestions[0].id)
        for task in self._suggestions:
            frame = ttk.Frame(self.choices)
            frame.pack(fill="x", pady=4)
            ttk.Radiobutton(
                frame, text=task.text, value=task.id, variable=self.choice_var
            ).pack(anchor="w")
            detail = task.first_step or "No first step yet — you'll be asked for one."
            ttk.Label(
                frame, text=f"    → {detail}", style="Muted.TLabel", wraplength=490, justify="left"
            ).pack(anchor="w")

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
    ):
        super().__init__(parent, "Start a focus session", size=(520, 460))

        ttk.Label(self.body, text="Working on", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(
            self.body,
            text=task_text or "Free focus (no task selected)",
            font=font(SIZE_LG, "bold"),
            wraplength=470,
            justify="left",
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
        if show_warmup and warmup_steps:
            ttk.Label(self.body, text="Warm-up ladder", font=font(SIZE_BASE, "bold")).pack(
                anchor="w"
            )
            ttk.Label(
                self.body,
                text="Step down towards the task instead of leaping at it. "
                     "Tick what you've done — skipping them is fine too.",
                style="Muted.TLabel",
                wraplength=470,
                justify="left",
            ).pack(anchor="w", pady=(2, 6))
            for step in warmup_steps:
                var = tk.BooleanVar(value=False)
                self.warmup_vars.append(var)
                ttk.Checkbutton(self.body, text=step, variable=var).pack(anchor="w", pady=1)

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

    def collect(self):
        try:
            minutes = max(1, min(120, int(self.minutes_var.get())))
        except (tk.TclError, ValueError):
            minutes = 15
        return {
            "minutes": minutes,
            "first_step": self.step_entry.get().strip(),
            "warmup_done": sum(1 for var in self.warmup_vars if var.get()),
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
        ttk.Label(self.body, text=prompt, wraplength=360, justify="left").pack(anchor="w")
        self.entry = ttk.Entry(self.body, width=42)
        self.entry.pack(fill="x", pady=(8, 0))
        self.entry.insert(0, initial)
        self.entry.select_range(0, "end")
        if hint:
            ttk.Label(self.body, text=hint, style="Muted.TLabel",
                      wraplength=360, justify="left").pack(anchor="w", pady=(4, 0))
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

    def __init__(self, parent: tk.Misc, message: str, task_text: str, break_minutes: int = 5):
        super().__init__(parent, "Session finished")
        self.resizable(False, False)
        ttk.Label(self.body, text=message, font=font(SIZE_LG, "bold"),
                  wraplength=380, justify="left").pack(anchor="w")
        ttk.Label(self.body, text=task_text, style="Muted.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", pady=(6, 14))

        first = None
        for label, value, style in (
            ("It's finished — mark it done", "done", "Default.TButton"),
            (f"Not yet — take {break_minutes} minutes", "break", "Outline.TButton"),
            ("Not yet — keep going", "carry_on", "Ghost.TButton"),
        ):
            button = ttk.Button(self.body, text=label, style=style,
                                command=lambda v=value: self._choose(v))
            button.pack(fill="x", pady=2)
            first = first or button
        if first is not None:
            first.focus_set()
            self.bind("<Return>", lambda _e: self._choose("done"))

    def _choose(self, value: str) -> None:
        self.result = value
        self.destroy()

    def cancel(self, _event=None):
        # Closing the window is "no answer", which means carry on.
        self.result = "carry_on"
        self.destroy()


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
            ("Double click / Ctrl+D", "Edit details"),
            ("Space", "Toggle done"),
            ("Up / Down", "Move through the list"),
            ("Delete", "Delete selected"),
            ("Ctrl+P", "Toggle high priority"),
            ("Ctrl+T", "Add a tag"),
            ("Ctrl+Up", "Move to top"),
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
                ttk.Label(grid, text=keys, style="Muted.TLabel", font=font(SIZE_SM, "bold")).grid(
                    row=row, column=0, sticky="w", padx=(0, 12)
                )
                ttk.Label(grid, text=description, style="Muted.TLabel").grid(
                    row=row, column=1, sticky="w"
                )
        ttk.Button(self.body, text="Close", style="Outline.TButton", command=self.cancel).pack(anchor="e", pady=(14, 0))
