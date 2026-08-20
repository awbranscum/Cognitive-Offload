"""The application controller: wires the model, the stores and the two tabs."""

from __future__ import annotations

import contextlib
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_TITLE, __version__
from .dialogs import (
    HandoffDialog,
    HandoffDoneDialog,
    PromptDialog,
    QuadrantDialog,
    SessionEndDialog,
    ShortcutsDialog,
    StartFocusDialog,
    StartHereDialog,
    TaskEditorDialog,
    WeekReviewDialog,
)
from .main_tab import build_main_tab
from .matrix_tab import build_matrix_tab
from . import handoff, presenter
from .models import (
    KIND_KEY_BY_LABEL,
    Task,
    humanize_date,
    now_stamp,
    parse_date_input,
    today_iso,
)
from .queries import (
    ALL_KINDS,
    DEFAULT_SORT,
    SORT_ORDERS,
    all_tags,
    rank_for_starting,
    split_lines,
)
from .sessions import DEFAULT_BREAK_MINUTES, SessionLog
from .storage import (
    CATEGORY_KEYS,
    Config,
    InstanceLock,
    MatrixStore,
    NotASessionError,
    StateStore,
    StorageError,
    category_label,
    display_path,
)
from .rows import (
    focus_caption,
    matrix_row,
    plan_place,
    sort_label,
    step_with_place,
)
from .theme import apply_theme, px, style_text, tokens
from .timer import FocusTimer
from .undo import UndoStack
from .widgets import FocusWindow

ALL_TAGS = "(all)"
AUTOSAVE_SECONDS = 30
# Said at the end of a session. Deliberately flat and factual: the point is
# that the time is banked, not that you have been a good boy.

def window_bounds(screen: tuple, design: tuple, floor: tuple,
                  margin: tuple) -> tuple:
    """Opening size and minimum size for a screen of this size.

    Pure, so the interesting cases can be tested without one X display per
    resolution — which is why the bug it fixes survived so long: every test
    ran on a screen big enough to hide it.

    Returns ``(opening, minimum)``. Both are capped by the room the screen
    leaves after ``margin`` (a title bar and a taskbar). When the screen
    cannot show even the floor, **the screen wins**: a control clipped by a
    few pixels is still readable and still clickable, while a control below
    the bottom edge of a window that refuses to shrink is neither.
    """
    room = tuple(max(1, s - m) for s, m in zip(screen, margin))
    return (tuple(min(d, r) for d, r in zip(design, room)),
            tuple(min(f, r) for f, r in zip(floor, room)))


class CognitiveOffloadApp(tk.Tk):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.title(f"{APP_TITLE} {__version__}")
        self._fit_to_screen()

        self.config_store = config or Config().load()
        self.state_store = StateStore(self.config_store.state_file)
        self.matrix = MatrixStore(self.config_store.matrix_db_path)
        self.session_log = SessionLog(self.config_store.sessions_file).load()

        self.tasks: list[Task] = []
        self._visible: list[Task] = []
        self._matrix_cache: dict[str, list] = {key: [] for key in CATEGORY_KEYS}
        self._undo_stack = UndoStack()
        self._dirty = False
        self._autosave_blocked = False
        self._autosave_complained = False
        self._suppress_scratch_event = False
        self._status_token = 0
        self._status_before_hover: str | None = None
        self._autosave_job = None
        self._parked_this_session: list[str] = []
        self._timer_job = None
        self.timer = FocusTimer(self.config_store.focus_minutes)
        self._focus_task_id: str | None = None
        self._session_count = 0
        self._focus_window: FocusWindow | None = None
        # Tasks finished and then cleared away; keeps "N done today" honest
        # after a tidy-up instead of resetting the day to zero.
        self.completed_log: list[dict] = []
        # Steps ticked off, with the day they were ticked. `Task.steps_done`
        # is a cursor and keeps no history, so this is the ONLY record that a
        # step was ever finished — and the week review's whole job is being
        # the record.
        self.steps_log: list[dict] = []
        self._day = None
        # Which suggestion the "Next up" strip is showing; "Not that one"
        # walks it forward.
        self._next_offset = 0
        self._next_task_id: str | None = None

        # Tk variables have to exist before the tabs that bind to them.
        self.search_var = tk.StringVar()
        self.tag_filter_var = tk.StringVar(value=ALL_TAGS)
        self.kind_filter_var = tk.StringVar(value=ALL_KINDS)
        self.sort_var = tk.StringVar(value=sort_label(self.config_store.sort_order))
        self.show_done_var = tk.BooleanVar(value=self.config_store.show_done)
        self.status_var = tk.StringVar(value="Ready.")
        self.counts_var = tk.StringVar(value="")
        self.focus_task_var = tk.StringVar(value=self.IDLE_CAPTION)
        self._next_up_shown = False
        #: set the first time Ctrl+F is pressed, and never unset — see
        #: `focus_search`.
        self._filter_row_requested = False
        self.momentum_var = tk.StringVar(value="")
        self.due_var = tk.StringVar(value="")
        self.today_var = tk.StringVar(value="")
        self.finish_var = tk.StringVar(value="")
        self.next_title_var = tk.StringVar(value="")
        self.next_step_var = tk.StringVar(value="")
        self.path_var = tk.StringVar(value="")
        self.matrix_path_var = tk.StringVar(value="")
        self.calm_var = tk.BooleanVar(value=self.config_store.calm_mode)

        self.theme_name = self.config_store.theme
        apply_theme(self, self.theme_name)
        self._ui_ready = False
        self._build_ui()
        self._bind_shortcuts()
        self.apply_calm_mode()
        self._ui_ready = True

        self._ensure_folders()
        self.aborted = False
        self._instance_lock = InstanceLock(self.config_store.db_path)
        if not self._claim_instance_lock(self._instance_lock):
            self.aborted = True
            self.destroy()
            return
        self.load_state(initial=True)
        self.refresh_matrix()
        self.refresh_momentum()
        self._update_timer_label()
        self._schedule_autosave()
        if self.config_store.first_run:
            # Said once, on the only launch where the app can know nobody has
            # seen it before. Calm mode hiding controls silently would be a
            # trap; one flat sentence that names the way out is not.
            self.set_status("Calm mode is on — fewer controls to begin with. "
                            "Untick it above for filters and task tools.")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _claim_instance_lock(self, lock: InstanceLock) -> bool:
        """Acquire the folder lock, or ask whether to take it over.

        Two copies autosaving the same file silently overwrite each other's
        work every 30 seconds — double-clicking run.bat twice, or reopening
        a window that was just lost behind others, is exactly the slip this
        guards against.

        The question asked depends on what is actually known. Since the lock
        started being held by the operating system, a copy that crashed is
        claimed silently and never reaches here — so a refusal now usually
        means a copy really is running, and saying "that is safe if the other
        one crashed" would be talking the person into the exact loss the
        warning is about. That reassurance is kept only where it is still
        true: a folder that cannot do locking at all.
        """
        if lock.acquire():
            return True
        if lock.uncertain:
            title = "Already running?"
            body = (
                f"Another copy of Cognitive Offload looks open with this "
                f"session folder ({lock.holder()}).\n\n"
                "This folder cannot say for certain — some network and synced "
                "folders cannot — so this may be a leftover from a copy that "
                "closed badly.\n\n"
                "Two copies would silently overwrite each other's saves. Open "
                "here anyway? (That is safe if the other copy crashed or was "
                "force-closed.)"
            )
        else:
            title = "Already open"
            body = (
                f"Cognitive Offload is already open with this session folder "
                f"({lock.holder()}).\n\n"
                "Both copies save to the same file every thirty seconds, so "
                "whichever you type in second quietly undoes the other.\n\n"
                "The window you want is already open — switch to it. Open a "
                "second copy here anyway?"
            )
        if messagebox.askyesno(title, body):
            lock.takeover()
            return True
        return False

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _fit_to_screen(self) -> None:
        """Open at the designed size, but never bigger than the screen.

        Both numbers used to be absolute, and neither was ever compared to
        the screen. The window opened 880 tall with a floor of 790 — so on a
        1366x768 laptop it opened 113px past the bottom edge and **could not
        be resized to fit**, because 790 is itself taller than 768. Thirteen
        controls sat off-screen: the whole task toolbar, the whole footer
        including Undo, the status bar (where most of what this app says is
        actually said), and the momentum strip — which with its label is the
        only way into the week review.

        The floors below are measured against the layout rather than chosen.
        In the worst legitimate state — a running session with a NEXT UP
        title and first step that each wrap — nothing overflows its card down
        to 1100x670, so 1120x700 keeps 20-30px of clearance. The old floor
        was 1160x790: about right on width, and ~110px taller than the layout
        needs, which is the whole of the bug on a 768px screen.

        The width number came out of a second measurement, because the first
        one used ``reqwidth > width`` and reported 930 — a widget can be
        given exactly the width it asked for and still sit past its card's
        right edge, which is what "Show done" does at 1060.

        When the screen cannot show even that, the screen wins. A button
        clipped by a few pixels is still readable and still clickable; a
        button below the bottom edge of an unresizable window is neither.
        """
        (width, height), floor = window_bounds(
            screen=(self.winfo_screenwidth(), self.winfo_screenheight()),
            design=(px(self, 1240), px(self, 880)),
            floor=(px(self, 1120), px(self, 700)),
            # Room for a title bar and a taskbar. Generous rather than exact:
            # guessing 20px too small costs a little space, guessing 20px too
            # large puts the footer — and Undo with it — under the taskbar.
            margin=(px(self, 16), px(self, 72)),
        )
        self.geometry(f"{width}x{height}")
        self.minsize(*floor)

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="  Cognitive Offload  ")
        build_main_tab(self, self.main_frame)

        self.matrix_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.matrix_frame, text="  Eisenhower Matrix  ")
        build_matrix_tab(self, self.matrix_frame)

    def _bind_shortcuts(self) -> None:
        # (sequence, handler, works_while_typing, shows_the_tasks_tab).
        #
        # Ctrl+P/T/D/N/O/B/Z all have default meanings inside Text and Entry
        # widgets, so those shortcuts step aside whenever a text widget has
        # focus.
        #
        # The fourth column is the one that matters on the other tab. These
        # are installed with `bind_all`, so every one of them fires whichever
        # tab is in front — and with the Eisenhower tab up, Ctrl+P changed the
        # priority of a task on the hidden list, Ctrl+Up pinned one, Ctrl+D
        # opened the editor on one, and Ctrl+B emptied the scratchpad you
        # could not see into tasks you could not see. This app's one rule is
        # that it never changes something you are not looking at.
        #
        # `focus_capture` and `focus_search` already did the right thing by
        # selecting the tasks tab themselves; the column makes that the rule
        # rather than two functions' private habit. Ctrl+Z is deliberately
        # NOT marked: undo also reverses matrix changes, and yanking someone
        # to the other tab to undo what they did on this one is the same
        # crime facing the other way.
        bindings = [
            ("<Control-s>", lambda: self.save_state(), True, False),
            ("<Control-f>", lambda: self.focus_search(), True, True),
            ("<Control-Key-1>", lambda: self.notebook.select(0), True, False),
            ("<Control-Key-2>", lambda: self.notebook.select(1), True, False),
            ("<F1>", lambda: self.show_shortcuts(), True, False),
            ("<Escape>", lambda: self.stop_timer(), True, False),
            ("<Control-o>", lambda: self.load_state_dialog(), False, False),
            ("<Control-n>", lambda: self.focus_capture(), False, True),
            ("<Control-b>", lambda: self.brain_dump_into_tasks(), False, True),
            ("<Control-p>", lambda: self.toggle_selected_priority(), False, True),
            ("<Control-t>", lambda: self.tag_selected(), False, True),
            ("<Control-d>", lambda: self.edit_selected_details(), False, True),
            ("<Control-m>", lambda: self.send_selected_to_matrix(), False, True),
            ("<Control-z>", lambda: self.undo(), False, False),
            ("<Control-Up>", lambda: self.promote_selected(), False, True),
            ("<Control-g>", lambda: self.start_here(), False, True),
            ("<Control-r>", lambda: self.focus_on_selected(), False, True),
        ]
        for sequence, handler, while_typing, shows_tasks in bindings:
            self.bind_all(sequence,
                          self._shortcut(handler, while_typing, shows_tasks))

    def _shortcut(self, handler, while_typing: bool, shows_tasks: bool = False):
        def wrapper(_event=None):
            if not while_typing and self._typing():
                return None  # let the widget's own binding win
            if shows_tasks:
                # Before, not after: the point is to be looking at the thing
                # when it changes, not to be shown the aftermath.
                self.notebook.select(0)
            handler()
            return "break"

        return wrapper

    def _typing(self) -> bool:
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            return False
        return isinstance(focused, (tk.Text, tk.Entry, ttk.Entry, ttk.Combobox, ttk.Spinbox))

    def _ensure_folders(self) -> None:
        try:
            self.config_store.db_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Folder error", f"Could not use {self.config_store.db_path}:\n{exc}")
        try:
            self.matrix.ensure()
        except StorageError as exc:
            messagebox.showerror("Folder error", str(exc))

    # ------------------------------------------------------------------
    # status / refresh
    # ------------------------------------------------------------------
    def set_status(self, message: str) -> None:
        self._status_token += 1
        token = self._status_token
        self.status_var.set(message)
        self.after(6000, lambda: self._clear_status(token))

    def hold_status(self, message: str) -> None:
        """Contextual text that should stay put, not a transient message.

        Bumping the token stops an in-flight clear from an earlier
        ``set_status`` matching and wiping it six seconds later.
        """
        self._status_token += 1
        self.status_var.set(message)

    def _clear_status(self, token: int) -> None:
        if token == self._status_token:
            self.status_var.set("Ready.")

    def mark_dirty(self) -> None:
        self._dirty = True

    def refresh_all(self) -> None:
        self.refresh_tasks()
        self.path_var.set(display_path(self.state_store.path))
        self.matrix_path_var.set(display_path(self.matrix.root))

    def copy_session_path(self) -> None:
        """The label only shows a shortened path, so make the full one reachable."""
        self.clipboard_clear()
        self.clipboard_append(str(self.state_store.path))
        self.set_status(f"Copied path: {self.state_store.path}")

    def refresh_tasks(self, keep_selection: bool = True) -> None:
        self._refresh_tag_choices()
        view = presenter.task_list_view(
            self.tasks,
            search=self.search_var.get(),
            tag=self._active_tag(),
            order=SORT_ORDERS.get(self.sort_var.get(), DEFAULT_SORT),
            show_done=self.show_done_var.get(),
            kind=self._active_kind(),
            completed_log=self.completed_log,
            steps_log=self.steps_log,
        )
        self._visible = view.visible

        # Before set_rows, so an empty list paints the right sentence the
        # first time rather than the wrong one for a frame.
        self.task_list.set_empty_text(view.empty_text)
        # set_rows already restores the selection by row id, which is the same
        # matching this used to do by hand - once per selected row, each time
        # repainting every row.
        self.task_list.set_rows(view.rows, keep_selection=keep_selection)
        self.counts_var.set(view.summary)
        # The row set just changed, so what the actions can act on has too.
        self.sync_action_availability()
        self.sync_filter_row()
        self.refresh_next_up()
        # An empty ``done_today_text`` is the presenter's decision that today
        # has nothing to say, not a missing value. Hide the whole pill rather
        # than just blanking it: the tinted DoneToday style paints its padded
        # background even for an empty label, and an empty green box is a
        # 0-done scoreboard in pill form.
        if view.done_today_text:
            self.today_var.set(view.done_today_text)
            if not self.today_label.winfo_manager():
                self.today_label.pack(side="right", padx=(0, 12))
        else:
            self.today_var.set("")
            self.today_label.pack_forget()
        self.refresh_due()

    def refresh_next_up(self) -> None:
        """Name the next thing without being asked.

        Opening the app and being told what to start is the difference between
        one decision and two. "Where do I start?" is still there for when the
        answer needs to match how you feel; this is the default.
        """
        # While a block is open on a task (running, or paused partway),
        # the box either names a different task or — if there is nothing
        # else — hides, rather than pitching the session you are already
        # in. Once the block ends the task is suggestible again: "another
        # round when you're ready" and the suggestion may rightly agree.
        exclude = self._focus_task_id if self.timer.open_block else None
        view = presenter.next_up_view(self.tasks, offset=self._next_offset,
                                      warm=self.session_log.recent_task_ids(),
                                      exclude=exclude)
        if view is None:
            self._next_task_id = None
            self._next_up_shown = False
            self.next_title_var.set("")
            self.next_step_var.set("")
            if getattr(self, "next_frame", None) is not None:
                self.next_frame.grid_remove()
            return

        self._next_task_id = view.task_id
        # Tracked rather than read back off the widget: a withdrawn window
        # reports every widget unmapped, so asking `winfo_ismapped` would make
        # anything keyed on this quietly never fire.
        self._next_up_shown = getattr(self, "next_frame", None) is None
        self.next_title_var.set(view.title)
        self.next_step_var.set(view.step)
        if getattr(self, "next_frame", None) is not None:
            # While a focus block actually runs, the strip steps out of
            # sight. Leaving it up put the largest button on the window —
            # "Start this", on a different task — in front of someone
            # sixty seconds into the block they fought to begin, and
            # clicking it raised a "drop it and start a new one?" question
            # the app had invented for itself. A pause is different: that
            # is exactly when "what should I do instead?" is fair, so this
            # tests the running clock, not open_block.
            #
            # The vars above stay populated on purpose, so Ctrl-driven
            # start_next still behaves normally — the soliciting button
            # goes away, the deliberate keystroke does not.
            if self._timer_running and self._timer_mode == "focus":
                self.next_frame.grid_remove()
                self._next_up_shown = False
            else:
                self.next_frame.grid()
                self._next_up_shown = True

    def next_task(self) -> Task | None:
        return next((t for t in self.tasks if t.id == self._next_task_id), None)

    def start_next(self) -> None:
        """One click from opening the app to being underway."""
        task = self.next_task()
        if task is None:
            self.set_status("Nothing open. That is a fine place to be.")
            return
        self._next_offset = 0
        self._select_task(task)
        self.begin_focus(task)

    def snooze_next(self) -> None:
        """Not today. The task keeps its place on the list; the suggestion
        slot stops being guarded by something you cannot face right now.

        Repeated forced contact with a dreaded task does not build willpower
        — it builds avoidance of the whole app. One day, no badge, no
        counter, silent expiry."""
        task = self.next_task()
        if task is None:
            return
        from datetime import date, timedelta

        self.push_undo("not today")
        task.snoozed_until = (date.today() + timedelta(days=1)).isoformat()
        self.mark_dirty()
        self._next_offset = 0
        self.refresh_next_up()
        self.set_status("Okay — it will come back tomorrow.")

    def skip_next(self) -> None:
        """Not that one. Walk to the next suggestion, wrapping around."""
        # Count the pool the suggestion actually draws from — the same
        # filters as suggest_tasks (done and snoozed drop out; mid-session
        # the in-focus task is excluded). Counting raw open tasks
        # overcounted and made the walk silently go nowhere.
        excluded = self._focus_task_id if self.timer.open_block else None
        pool = len(rank_for_starting([t for t in self.tasks if t.id != excluded]))
        if pool <= 1:
            self.set_status("That is the only thing open."
                            if excluded is None else
                            "That is the only thing open besides what you're on.")
            return
        self._next_offset = (self._next_offset + 1) % pool
        self.refresh_next_up()

    def _refresh_tag_choices(self) -> None:
        tags = all_tags(self.tasks)
        self.tag_filter_combo["values"] = [ALL_TAGS] + tags
        if self.tag_filter_var.get() not in ([ALL_TAGS] + tags):
            self.tag_filter_var.set(ALL_TAGS)

    def _active_tag(self) -> str | None:
        value = self.tag_filter_var.get()
        return None if value in ("", ALL_TAGS) else value

    def _active_kind(self) -> str | None:
        label = self.kind_filter_var.get()
        if label in ("", ALL_KINDS):
            return None
        return KIND_KEY_BY_LABEL.get(label) or None

    def clear_kind_filter(self) -> None:
        self.kind_filter_var.set(ALL_KINDS)
        self.refresh_tasks()

    def any_filter_active(self) -> bool:
        """Is anything currently narrowing the list?

        Read by the rule below, and deliberately generous: "Show done" being
        off hides finished tasks, which is narrowing even though nobody thinks
        of it as a filter.
        """
        return bool(self.search_var.get().strip()
                    or self._active_tag()
                    or self._active_kind()
                    or not self.show_done_var.get())

    def sync_filter_row(self) -> None:
        """The filter row appears when there is something to filter.

        On a first run it was six live controls — a search box, Clear, three
        dropdowns and "Show done" — narrowing an empty list, on the screen a
        new person meets first. Nothing there can do anything until a task
        exists, and a control that cannot act is still a thing to read and
        decide about.

        It obeys the rule calm mode already wrote down: **never hide a control
        that is still filtering the list**, because a shorter list with no
        visible reason why is worse than the clutter. So an active filter
        keeps the row up even with nothing left to show — that is exactly when
        you need to see the filter in order to clear it. And Ctrl+F pins it
        for the session, because a shortcut whose whole job is to put the
        cursor in that box must not leave the box hidden. Calm mode still
        wins over all three.
        """
        row = getattr(self, "filter_row", None)
        if row is None or self.calm_var.get():
            return
        if self.tasks or self.any_filter_active() or self._filter_row_requested:
            row.grid()
        else:
            row.grid_remove()

    def clear_search(self) -> None:
        self.search_var.set("")
        self.refresh_tasks()

    def clear_tag_filter(self) -> None:
        self.tag_filter_var.set(ALL_TAGS)
        self.refresh_tasks()

    def focus_search(self) -> None:
        self.notebook.select(0)
        if self.calm_var.get():
            # Searching needs the search box back; asking for it is consent.
            self.calm_var.set(False)
            self.apply_calm_mode()
        # And asking for it is also consent to keep it, even with nothing to
        # search yet: a shortcut that puts the cursor somewhere invisible is
        # a shortcut that appears not to work. Sticky for the session on
        # purpose — the alternative is a box that comes and goes under you.
        self._filter_row_requested = True
        self.sync_filter_row()
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def focus_capture(self) -> None:
        self.notebook.select(0)
        self.capture_entry.focus_set()

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self).show()

    # ------------------------------------------------------------------
    # selection helpers
    # ------------------------------------------------------------------
    def selected_tasks(self) -> list[Task]:
        """Tasks behind the current listbox selection, in display order."""
        return [self._visible[i] for i in self.task_list.curselection() if i < len(self._visible)]

    def _require_selection(self, verb: str) -> list[Task]:
        tasks = self.selected_tasks()
        if not tasks:
            self.set_status(f"Select a task first to {verb}.")
        return tasks

    def sync_action_availability(self) -> None:
        """Grey the controls that cannot act yet.

        First run offered thirty-two clickable things, and about half of them
        could do nothing at all: every task action needs a selection, and
        there were no tasks. For this audience each control is a small
        decision — "is this for me? what does it do?" — and an inert one is a
        decision that pays nothing back. The only way to learn a button was
        not for you was to press it and be told so.

        Greying rather than hiding, deliberately: nothing moves, the row
        keeps its shape, and the moment you select a task seven buttons come
        on at once. That correlation teaches what they apply to without a
        sentence and without a failed click.
        """
        state = "normal" if self.selected_tasks() else "disabled"
        for button in getattr(self, "needs_selection", ()):
            button.state(["!disabled"] if state == "normal" else ["disabled"])
        clearable = any(t.done for t in self.tasks)
        button = getattr(self, "needs_done_task", None)
        if button is not None:
            button.state(["!disabled"] if clearable else ["disabled"])

    def on_task_selection_changed(self) -> None:
        self.sync_action_availability()
        tasks = self.selected_tasks()
        if len(tasks) == 1:
            task = tasks[0]
            details = task.text
            if task.tags:
                details += f"  ·  tags: {', '.join(task.tags)}"
            if task.description.strip():
                first_line = task.description.strip().splitlines()[0]
                details += f"  ·  {first_line[:60]}"
            self.hold_status(details[:160])
        elif len(tasks) > 1:
            self.hold_status(f"{len(tasks)} tasks selected.")

    # ------------------------------------------------------------------
    # undo
    # ------------------------------------------------------------------
    def push_undo(self, label: str) -> None:
        self._undo_stack.push(label, [t.copy() for t in self.tasks],
                              self.steps_log)

    def _advance(self, item) -> bool:
        """Tick the current step off, recording it on the way past.

        Recorded only when the cursor actually moves. It used to be written
        first and unconditionally, and `advance_step` refuses at the end of a
        plan — the model's invariant is `first_step == steps[steps_done]`, so
        the cursor may never pass the last step. Ticking "Done" on the last
        step therefore logged a finished step and changed nothing, every
        time it was pressed: three ticks put the same step in the week review
        three times, and inflated the "N done today" count with it.

        Padding the record is not a smaller sin than losing it. That screen
        exists because "I did nothing this week" is a distortion, and it can
        only correct one by being true.
        """
        finished = (getattr(item, "first_step", "") or "").strip()
        if not item.advance_step():
            return False
        # After the move, so `first_step` is now the NEXT step — the one just
        # completed has to be carried across by hand.
        self.record_step_done(item, step=finished)
        return True

    #: what the focus card says when nothing is running and there is nothing
    #: to remember either. Three places used to spell it out; one of them is
    #: now the fallback for the other two.
    IDLE_CAPTION = "Nothing picked yet"

    def set_idle_focus_caption(self) -> None:
        """Fill the idle focus card with what you were last doing.

        The slot said "Nothing picked yet" — three words of dead text in the
        most prominent place on the screen, at the exact moment someone is
        trying to remember what they were on. Replacing dead text costs no
        pixels, which is the only kind of addition this screen can afford
        after v3.48.0 spent a release taking things off it.
        """
        self.focus_task_var.set(
            presenter.resume_line(
                self.session_log, self.steps_log, self.tasks,
                shown_as_next=self._next_task_id if self._next_up_shown else "")
            or self.IDLE_CAPTION)

    def record_step_done(self, item, step: str = "") -> None:
        """Write down a step that has been ticked off.

        Called from all three places that advance a plan, because three
        hand-written copies of this is precisely the shape of bug the last
        four releases have been fixing. Undo is handled by the stack, which
        snapshots the log alongside the tasks — Ctrl+Z must not put the
        cursor back and leave the evidence behind.

        ``step`` is passed explicitly by `_advance`, which reads it before
        moving the cursor: afterwards `first_step` names the *next* step, and
        a log that recorded that would name the wrong one every time.
        """
        step = (step or getattr(item, "first_step", "") or "").strip()
        if not step:
            return
        self.steps_log.append({
            "step": step,
            "task": getattr(item, "text", None) or getattr(item, "title", "") or "",
            # The id as well as the title: the title is what the week review
            # shows, and the id is what "what was I doing?" joins on. Matching
            # on a title that the person has since reworded would quietly
            # drop the one line that answers the question.
            "task_id": getattr(item, "id", "") or "",
            "done_at": now_stamp(),
        })
        self.mark_dirty()

    def attach_undo(self, restore) -> None:
        """Give the pending undo entry a side effect to run as well.

        Moving a task between the list and the matrix touches two stores;
        restoring only the task list would leave the task in both places, or
        in neither.
        """
        self._undo_stack.attach(restore)

    def undo(self) -> None:
        entry = self._undo_stack.pop()
        if entry is None:
            self.set_status("Nothing to undo.")
            return
        self.tasks = entry.snapshot
        # Before `restore`, so a flow that captured the log itself — the
        # matrix editor pushes AFTER its writes, so its snapshot already has
        # the new entry in it — gets the last word.
        self.steps_log = list(entry.steps_log)
        if entry.restore is not None:
            try:
                entry.restore()
            except StorageError as exc:
                messagebox.showerror("Undo failed", str(exc))
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Undid: {entry.label}.")

    # ------------------------------------------------------------------
    # capture / task commands
    # ------------------------------------------------------------------
    def _add_tasks(self, texts: list[str], status: str) -> int:
        texts = [t for t in texts if t.strip()]
        if not texts:
            return 0
        self.push_undo("add")
        for text in texts:
            self.tasks.insert(0, Task(text=text.strip()))
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        # {lines} is already pluralised; {count} is the bare number, kept for
        # a caller that wants to phrase it differently. A template with
        # neither is passed through untouched.
        self.set_status(status.format(count=len(texts),
                                      lines=presenter.plural(len(texts), "line")))
        return len(texts)

    def add_task_from_capture(self) -> None:
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.capture_entry.delete(0, tk.END)
        self._add_tasks([text], "Captured as task.")


    def add_note_from_capture(self) -> None:
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.capture_entry.delete(0, tk.END)
        self.append_scratchpad(text, stamped=True)
        self.set_status("Captured in scratchpad.")

    def toggle_selected_done(self) -> None:
        tasks = self._require_selection("mark it done")
        if not tasks:
            return
        self.push_undo("toggle done")
        target = not all(t.done for t in tasks)
        booked = []
        for task in tasks:
            # Take the next round before marking this one done, so the new
            # booking is worked out from the date this one was actually for.
            following = task.next_instance() if target and not task.done else None
            task.set_done(target)
            if following is not None:
                booked.append(following)
        self.tasks.extend(booked)
        self.refresh_tasks()
        self.mark_dirty()
        word = "done" if target else "open"
        status = f"Marked {presenter.plural(len(tasks), 'task')} {word}."
        # Said once, as a fact: the thing you just finished has not been taken
        # away from you and you do not have to remember to put it back. Each
        # tail is its own `status =` rather than a `+=` — an augmented
        # assignment is invisible to the wording snapshot, so these two
        # sentences would have shipped watched by nothing.
        if len(booked) == 1:
            # A colon, not "booked for": humanize_date returns both weekdays
            # ("Sat") and durations ("in 9 days"), and every preposition that
            # fits one is wrong for the other. Seen only by running the app —
            # "Next one booked for in 9 days." passes every test there is.
            status = (f"{status} Next one: "
                      f"{humanize_date(booked[0].scheduled_for)}.")
        elif booked:
            status = (f"{status} "
                      f"{presenter.plural(len(booked), 'repeat')} booked again.")
        self.set_status(status)

    def toggle_selected_priority(self) -> None:
        tasks = self._require_selection("change its priority")
        if not tasks:
            return
        self.push_undo("toggle priority")
        target = 0 if all(t.priority for t in tasks) else 1
        for task in tasks:
            task.priority = target
        self.refresh_tasks()
        self.mark_dirty()
        self.set_status(f"{'Flagged' if target else 'Unflagged'} {presenter.plural(len(tasks), 'task')}.")

    def tag_selected(self) -> None:
        tasks = self._require_selection("tag it")
        if not tasks:
            return
        with self._ask_over_focus():
            tag = PromptDialog(self, "Add tag", "Tag name", hint="Lower-cased automatically.",
                               ok_text="Add").show()
        if not tag:
            return
        self.push_undo("add tag")
        changed = sum(1 for task in tasks if task.add_tag(tag))
        self.refresh_tasks()
        self.mark_dirty()
        self.set_status(f"Tagged {presenter.plural(changed, 'task')} with '{tag.strip().lower()}'.")

    def edit_selected_details(self) -> None:
        tasks = self.selected_tasks()
        if len(tasks) != 1:
            self.set_status("Select exactly one task to edit.")
            return
        task = tasks[0]
        result = TaskEditorDialog(
            self,
            title=task.text,
            content=task.description,
            tags=task.tags,
            first_step=task.first_step,
            kind=task.kind,
            scheduled_for=task.scheduled_for,
            estimate_minutes=task.estimate_minutes,
            repeat=task.repeat,
            snoozed_until=task.snoozed_until,
            handed_to=task.handed_to,
            follow_up_on=task.follow_up_on,
            rest_of_plan=task.rest_of_plan,
            window_title="Edit task",
            with_tags=True,
        ).show()
        if not result:
            return
        self.push_undo("edit task")
        task.text = result["title"]
        task.description = result["content"]
        task.tags = result["tags"]
        # set_current_step rather than a plain assignment: on a task with a
        # plan the step box IS the current line of it, and writing only to
        # first_step would leave the two disagreeing until the next load
        # silently reverted the edit.
        task.set_current_step(result["first_step"])
        task.set_rest(result.get("rest_of_plan", task.rest_of_plan))
        advanced = bool(result.get("step_done")) and self._advance(task)
        task.kind = result["kind"]
        task.scheduled_for = result["scheduled_for"]
        task.estimate_minutes = result.get("estimate_minutes", task.estimate_minutes)
        task.repeat = result.get("repeat", task.repeat)
        if result.get("clear_snooze"):
            task.snoozed_until = ""
        if result.get("take_back"):
            task.handed_to = task.handed_off_on = task.follow_up_on = ""
        waiting_on = result.get("waiting_on", "")
        if waiting_on:
            task.handed_to = waiting_on
            task.handed_off_on = today_iso()
            task.follow_up_on = result.get("check_back", "")
        self.refresh_tasks()
        self.mark_dirty()
        if waiting_on:
            self.set_status(f"Waiting on {waiting_on}. Ctrl+Z undoes it.")
        elif advanced:
            # Says what is next, not how many are left: a count of what
            # remains is a debt, and the next step is a way in.
            self.set_status(f"Next: {task.first_step}")
        else:
            self.set_status("Task updated.")

    def promote_selected(self) -> None:
        """Pin the selection above everything open (or unpin it again).

        The old version reordered ``self.tasks`` and reported success, but
        every sort order immediately re-sorted the list by task fields, so
        nothing visibly moved — a control that claims success and does
        nothing teaches the user to distrust the app. A pin is a real field:
        it survives re-sorts, saves, and restarts.
        """
        tasks = self._require_selection("pin it")
        if not tasks:
            return
        self.push_undo("pin")
        pin = not all(t.pinned for t in tasks)
        for task in tasks:
            task.pinned = pin
        self.refresh_tasks()
        self.mark_dirty()
        count = len(tasks)
        if not pin:
            self.set_status(f"Unpinned {presenter.plural(count, 'task')}.")
        elif SORT_ORDERS.get(self.sort_var.get(), DEFAULT_SORT) == "priority":
            self.set_status(f"Pinned {presenter.plural(count, 'task')} to the top.")
        else:
            # Under other sort orders the pin holds but doesn't reorder;
            # saying otherwise would be the same lie in a new costume.
            # "shows" agreed with nothing once the count was pluralised
            # properly; naming what shows fixes it for one task and for six.
            self.set_status(
                f"Pinned {presenter.plural(count, 'task')} — pinned tasks sit at the "
                "top under Priority sort."
            )

    def delete_selected(self) -> None:
        tasks = self._require_selection("delete it")
        if not tasks:
            return
        if len(tasks) > 1 and not messagebox.askyesno(
            "Delete tasks", f"Delete {len(tasks)} selected tasks?"
        ):
            return
        self.push_undo("delete")
        for task in tasks:
            self.tasks.remove(task)
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Deleted {presenter.plural(len(tasks), 'task')}. Ctrl+Z undoes it.")

    def clear_completed(self) -> None:
        done = [t for t in self.tasks if t.done]
        if not done:
            self.set_status("No completed tasks to clear.")
            return
        if not messagebox.askyesno("Clear completed", f"Remove {presenter.plural(len(done), 'completed task')}?"):
            return
        self.push_undo("clear completed")
        previous_log = list(self.completed_log)
        self.completed_log.extend(
            {"text": t.text, "completed_at": t.completed_at or now_stamp()} for t in done
        )
        self.attach_undo(lambda entries=previous_log: setattr(self, "completed_log", entries))
        self.tasks = [t for t in self.tasks if not t.done]
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Cleared {presenter.plural(len(done), 'completed task')}.")

    # ------------------------------------------------------------------
    # scratchpad
    # ------------------------------------------------------------------
    def scratchpad_text(self) -> str:
        return self.note_text.get("1.0", "end-1c")

    def set_scratchpad(self, text: str) -> None:
        self._suppress_scratch_event = True
        try:
            self.note_text.delete("1.0", tk.END)
            if text:
                self.note_text.insert("1.0", text)
            self.note_text.edit_reset()
            self.note_text.edit_modified(False)
        finally:
            self._suppress_scratch_event = False

    def append_scratchpad(self, text: str, stamped: bool = False) -> None:
        line = f"[{now_stamp()}] {text}" if stamped else text
        current = self.scratchpad_text()
        prefix = "" if not current or current.endswith("\n") else "\n"
        self.note_text.insert(tk.END, f"{prefix}{line}\n")
        self.note_text.see(tk.END)
        self.mark_dirty()

    def on_scratchpad_modified(self, _event=None) -> None:
        if self._suppress_scratch_event:
            return
        if self.note_text.edit_modified():
            self.note_text.edit_modified(False)
            self.mark_dirty()

    def send_scratch_line_to_tasks(self) -> None:
        try:
            raw = self.note_text.get("sel.first", "sel.last")
            span = ("sel.first", "sel.last")
        except tk.TclError:
            raw = self.note_text.get("insert linestart", "insert lineend")
            span = ("insert linestart", "insert lineend +1c")  # eat the newline
        lines = split_lines(raw)
        if not lines:
            self.set_status("Nothing on that line to turn into a task.")
            return
        previous = self.scratchpad_text()
        if self._add_tasks(lines, "Sent {lines} to the task list."):
            # A move, as the arrow on the button says: the line leaves the
            # pad — it is a commitment now, not a maybe — and Ctrl+Z brings
            # the pad and the list back together. Copying-but-saying-"sent"
            # also let the same line become a task twice.
            self.attach_undo(lambda text=previous: self.set_scratchpad(text))
            self.note_text.delete(*span)

    def brain_dump_into_tasks(self) -> None:
        lines = split_lines(self.scratchpad_text())
        if not lines:
            self.set_status("The scratchpad is empty.")
            return
        if len(lines) > 5 and not messagebox.askyesno(
            "Brain dump", f"Create {len(lines)} tasks from the scratchpad?"
        ):
            return
        previous = self.scratchpad_text()
        if self._add_tasks(lines, "Moved {lines} into tasks."):
            # "Moved" now means moved: every non-blank line became a task,
            # so the pad empties instead of inviting a duplicate dump.
            self.attach_undo(lambda text=previous: self.set_scratchpad(text))
            self.set_scratchpad("")

    def clear_notes(self) -> None:
        if not self.scratchpad_text().strip():
            return
        if not messagebox.askyesno("Clear scratchpad", "Clear everything in the scratchpad?"):
            return
        previous = self.scratchpad_text()
        self.push_undo("clear scratchpad")
        self.attach_undo(lambda text=previous: self.set_scratchpad(text))
        self.set_scratchpad("")
        self.mark_dirty()
        self.set_status("Scratchpad cleared.")

    # ------------------------------------------------------------------
    # matrix
    # ------------------------------------------------------------------
    def refresh_matrix(self) -> None:
        if not self.matrix.root.exists():
            # Four silently empty quadrants read as catastrophic data loss;
            # a moved or unmounted folder deserves its actual name.
            self.hold_status(
                f"Matrix folder is missing: {display_path(self.matrix.root)} "
                "(moved or unmounted?). Showing empty quadrants; nothing "
                "will be written until it is back."
            )
        unreadable = []
        loaded: dict[str, list] = {}
        for key in CATEGORY_KEYS:
            try:
                tasks = self.matrix.list(key)
            except (OSError, StorageError) as exc:
                tasks = []
                unreadable.append(f"{category_label(key)}: {exc}")
            loaded[key] = tasks
            self._matrix_cache[key] = tasks
            self.matrix_lists[key].set_rows([matrix_row(t) for t in tasks])
            # The row set just changed, so what the buttons can act on has too
            # — a rebuilt list drops the selection without firing on_select.
            self.sync_matrix_action_availability(key)
        # A quadrant that could not be read shows as empty, which is why the
        # status line above names the folder: an empty tab must never be the
        # only evidence that something is wrong.
        for index, quadrant in enumerate(presenter.matrix_view(loaded).quadrants):
            self.matrix_count_labels[quadrant.key].config(text=quadrant.count)
            self.matrix_notebook.tab(index, text=quadrant.tab)
        self.matrix_path_var.set(display_path(self.matrix.root))
        self.refresh_due()
        if unreadable:
            # An empty quadrant and an unreadable one look identical; say which.
            self.set_status("Could not read " + "; ".join(unreadable))

    def sync_matrix_action_availability(self, category: str) -> None:
        """Grey the quadrant's controls that cannot act yet.

        The same argument as ``sync_action_availability`` on the other tab,
        which this had gone without: an inert control is still a small
        decision — "is this for me?" — and the only way to learn the answer
        was to press it and be told "Select a task to…".

        Three questions, not one. Most buttons need a selection. "Copy all to
        tasks" needs the quadrant to have anything in it. And "Take it back"
        needs the selected task to actually be **out** with someone, which is
        the state that button exists to end — offering it on a task that is
        not waiting is offering to undo something that never happened.
        """
        selected = self._selected_matrix_tasks(category)

        def apply(buttons, enabled):
            for button in buttons:
                button.state(["!disabled"] if enabled else ["disabled"])

        apply(getattr(self, "matrix_needs_selection", {}).get(category, ()),
              bool(selected))
        apply(getattr(self, "matrix_needs_rows", {}).get(category, ()),
              bool(self._matrix_cache.get(category)))
        apply(getattr(self, "matrix_needs_waiting", {}).get(category, ()),
              any(t.is_waiting() for t in selected))

    def _selected_matrix_tasks(self, category: str) -> list:
        cached = self._matrix_cache.get(category, [])
        return [cached[i] for i in self.matrix_lists[category].curselection() if i < len(cached)]

    def add_matrix_task(self, category: str) -> None:
        result = TaskEditorDialog(
            self, window_title=f"New task – {category_label(category)}"
        ).show()
        if not result:
            return
        try:
            created = self.matrix.create(category, result["title"], result["content"])
            created.first_step = result["first_step"]
            created.set_rest(result.get("rest_of_plan", []))
            # step_done cannot be set on a task that did not exist a moment
            # ago: the dialog draws no checkbox with nothing to move on from.
            created.kind = result["kind"]
            # The dialog offers a guess and a repeat, so it has to keep them.
            # It did not: a new quadrant task filled in as "about 25 minutes,
            # every week" arrived with neither, and nothing said so — the
            # worst shape a data loss can take, because the person watched
            # themselves type it.
            created.estimate_minutes = result.get("estimate_minutes", 0)
            created.repeat = result.get("repeat", "")
            if result.get("waiting_on"):
                created.handed_to = result["waiting_on"]
                created.handed_off_on = today_iso()
                created.follow_up_on = result.get("check_back", "")
            # set_scheduled writes the record, so everything above rides with it.
            self.matrix.set_scheduled(created, result["scheduled_for"])
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._undo_matrix_change("add to the matrix", [], [created.id])
        self.refresh_matrix()
        self.set_status(f"Added to {category_label(category)}.")

    def edit_matrix_task(self, category: str) -> None:
        tasks = self._selected_matrix_tasks(category)
        if len(tasks) != 1:
            self.set_status("Select exactly one task to edit.")
            return
        task = tasks[0]
        result = TaskEditorDialog(
            self,
            title=task.title,
            content=task.content,
            first_step=task.first_step,
            kind=task.kind,
            scheduled_for=task.scheduled_for,
            estimate_minutes=task.estimate_minutes,
            # A quadrant task carries these too — it can arrive from the main
            # list already repeating, already excused, already out with
            # someone. Leaving them out did not hide them, it MISREPORTED
            # them: the dialog said "Does not repeat" about a task wearing a
            # weekly badge two inches away, and offered no way out of a wait
            # anywhere but Delegate, where the button lives.
            repeat=task.repeat,
            snoozed_until=task.snoozed_until,
            handed_to=task.handed_to,
            follow_up_on=task.follow_up_on,
            rest_of_plan=task.rest_of_plan,
            window_title="Edit matrix task",
        ).show()
        if not result:
            return
        # Taken before the writes below, which change the task in place and
        # can rename its file.
        before = [task.copy()]
        # Captured here because this flow registers its undo entry AFTER the
        # writes, so by then the log already holds whatever the edit added.
        steps_before = list(self.steps_log)
        waiting_on = result.get("waiting_on", "")
        try:
            task.set_current_step(result["first_step"])
            task.set_rest(result.get("rest_of_plan", task.rest_of_plan))
            advanced = bool(result.get("step_done")) and self._advance(task)
            task.kind = result["kind"]
            task.scheduled_for = result["scheduled_for"]
            task.estimate_minutes = result.get("estimate_minutes", task.estimate_minutes)
            task.repeat = result.get("repeat", task.repeat)
            if result.get("clear_snooze"):
                task.snoozed_until = ""
            if result.get("take_back"):
                task.handed_to = task.handed_off_on = task.follow_up_on = ""
            if waiting_on:
                task.handed_to = waiting_on
                task.handed_off_on = today_iso()
                task.follow_up_on = result.get("check_back", "")
            # One write, not five: `update` persists the whole record, so
            # every field above rides along with the title and the content.
            self.matrix.update(task, result["title"], result["content"])
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._undo_matrix_change("edit matrix task", before, [task.id],
                                 steps_before=steps_before)
        self.refresh_matrix()
        if waiting_on:
            self.set_status(f"Waiting on {waiting_on}. Ctrl+Z undoes it.")
        elif advanced:
            self.set_status(f"Next: {task.first_step}")
        else:
            self.set_status("Matrix task updated.")

    def hand_off_matrix_task(self, category: str) -> None:
        """Write a brief for an agent, and mark the task as waiting.

        Nothing is sent: a file is written and a command goes on the
        clipboard. The person is still the one who starts the agent, which is
        the only version of this that is safe to ship — a brief written in
        thirty seconds by someone mid-thought should be readable before
        anything acts on it.
        """
        tasks = self._selected_matrix_tasks(category)
        if len(tasks) != 1:
            self.set_status("Select exactly one task to hand over.")
            return
        task = tasks[0]
        result = HandoffDialog(
            self, task.title, target_key=self.config_store.handoff_target,
            follow_up_days=handoff.DEFAULT_FOLLOW_UP_DAYS,
        ).show()
        if not result:
            return
        target = handoff.target_for(result["target"])
        brief = handoff.build_brief(task, note=result["note"])
        try:
            path = handoff.write_brief(self.config_store.handoff_root, target, brief)
        except OSError as exc:
            messagebox.showerror(
                "Could not write the brief",
                f"{exc}\n\nNothing was handed over and the task is unchanged.",
            )
            return
        command = handoff.command_for(
            target, path, self.config_store.handoff_commands.get(target.key, ""))
        self._copy_to_clipboard(command)

        before = [task.copy()]
        handed_on = today_iso()
        # Who had it a moment ago. Newest-holder-wins is the right behaviour;
        # doing it in silence is not — before the editor could mark a wait,
        # the only way to reach this was to hand an agent's task to another
        # agent, and now anyone you were waiting on can be replaced by a
        # click that never mentions them.
        previous = task.handed_to
        try:
            self.matrix.set_handoff(
                task, target.label, handed_on,
                handoff.follow_up_date(handed_on, result["follow_up_days"]),
            )
        except StorageError as exc:
            # The brief is already written, so say what did happen rather
            # than implying the whole thing failed.
            messagebox.showerror(
                "Handed over, but not recorded",
                f"The brief was written to {path}, but the task could not be "
                f"marked as waiting: {exc}",
            )
            return
        self.config_store.handoff_target = target.key
        self._undo_matrix_change("hand a task over", before, [task.id])
        self.refresh_matrix()
        HandoffDoneDialog(self, target, path, command).show()
        if previous and previous != target.label:
            self.set_status(f"Was out with {previous}; now out with "
                            f"{target.label}. Ctrl+Z undoes it.")
        else:
            self.set_status(f"Handed to {target.label}. Ctrl+Z undoes it.")

    def take_back_matrix_task(self, category: str) -> None:
        """Clear the waiting mark. Not a failure, and never described as one."""
        tasks = [t for t in self._selected_matrix_tasks(category) if t.is_waiting()]
        if not tasks:
            self.set_status("Select a task that is out with someone.")
            return
        before = [task.copy() for task in tasks]
        try:
            for task in tasks:
                self.matrix.set_handoff(task, "", "", "")
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._undo_matrix_change("take a task back", before, [t.id for t in tasks])
        self.refresh_matrix()
        self.set_status("Back with you. Ctrl+Z undoes it.")

    def _copy_to_clipboard(self, text: str) -> bool:
        """Tk owns the clipboard while the app runs — no subprocess needed."""
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            return True
        except tk.TclError:
            return False

    def delete_matrix_tasks(self, category: str) -> None:
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to delete.")
            return
        # Confirm for a batch only, which is what the task list has always
        # done. Asking about every single delete made sense while the matrix
        # had no undo and the dialog was the only protection; since it gained
        # one, the question guards nothing that Ctrl+Z does not, and costs a
        # decision every time. Deleting one thing here is now exactly as
        # cheap, and as recoverable, as deleting one thing in the list.
        if len(tasks) > 1 and not messagebox.askyesno(
            "Delete", f"Delete {presenter.plural(len(tasks), 'task')}?"
        ):
            return
        before = [task.copy() for task in tasks]
        done = 0
        try:
            for task in tasks:
                self.matrix.delete(task)
                done += 1
        except StorageError as exc:
            messagebox.showerror("Delete failed", str(exc))
        if done:
            self._undo_matrix_change("delete from the matrix", before,
                                     [t.id for t in tasks])
        self.refresh_matrix()
        # _batch_status deliberately leaves the sentence unfinished so each
        # caller can add its own tail; this one forgot the full stop and read
        # "Deleted 1 matrix task Ctrl+Z undoes it." right beside a task list
        # that gets it right.
        self.set_status(presenter.batch_status("Deleted", done, len(tasks), "matrix task")
                        + "." + (" Ctrl+Z undoes it." if done else ""))

    def move_matrix_tasks(self, category: str) -> None:
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to move.")
            return
        destination = QuadrantDialog(
            self, count=len(tasks), initial=category, window_title="Move between quadrants"
        ).show()
        if not destination or destination == category:
            return
        before = [task.copy() for task in tasks]
        done = 0
        try:
            for task in tasks:
                self.matrix.move(task, destination)
                done += 1
        except StorageError as exc:
            messagebox.showerror("Move failed", str(exc))
        if done:
            self._undo_matrix_change("move between quadrants", before,
                                     [t.id for t in tasks])
        self.refresh_matrix()
        self.set_status(
            presenter.batch_status("Moved", done, len(tasks), "task")
            + f" to {category_label(destination)}."
        )

    def _import_matrix_tasks(self, tasks: list, undo_label: str) -> list[Task]:
        """Move matrix tasks onto the main stack; returns the imported Tasks.

        Shared by "Send to tasks" and "Focus on this". Delete-first: if the
        file cannot be removed, the task must not appear on the main list
        too — a duplicate in both stores is the README's "never in both
        places" promise broken by an I/O error.
        """
        self.push_undo(undo_label)
        imported: list[Task] = []
        restored: list = []
        for task in tasks:
            try:
                self.matrix.delete(task)
            except StorageError as exc:
                messagebox.showerror("Move failed", str(exc))
                break
            main_task = task.to_task()
            self.tasks.insert(0, main_task)
            imported.append(main_task)
            restored.append(task)
        self.attach_undo(lambda items=restored: self._restore_matrix_tasks(items))
        self.refresh_matrix()
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        return imported

    def matrix_to_tasks(self, category: str) -> None:
        """Move the selected matrix tasks back onto the main stack."""
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to send to the task list.")
            return
        moved = self._import_matrix_tasks(tasks, "import from matrix")
        self.set_status(f"Moved {presenter.plural(len(moved), 'task')} to the main list.")
        self.notebook.select(0)

    def focus_matrix_task(self, category: str) -> None:
        """One click from a quadrant to a running session.

        Booking a time is what makes Schedule work happen — but on the
        booked day the start machinery (warm-up, timer, hand-off) used to be
        unreachable from here: send to tasks, switch tab, find it, Ctrl+R.
        Four steps of self-administration is exactly what does not happen
        at 9am.
        """
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to start.")
            return
        imported = self._import_matrix_tasks(tasks[:1], "start from matrix")
        if not imported:
            return
        self.notebook.select(0)
        self._select_task(imported[0])
        self.begin_focus(imported[0])

    def copy_matrix_to_tasks(self, category: str) -> None:
        """Copy every task in the quadrant to the main list, leaving the files alone."""
        tasks = list(self._matrix_cache.get(category, []))
        if not tasks:
            self.set_status(f"{category_label(category)} is empty.")
            return
        if not messagebox.askyesno(
            "Copy to tasks", f"Copy {presenter.plural(len(tasks), 'task')} from {category_label(category)}?"
        ):
            return
        self.push_undo("copy from matrix")
        for task in tasks:
            self.tasks.insert(0, task.to_task())
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Copied {presenter.plural(len(tasks), 'task')} to the main list.")
        self.notebook.select(0)

    def send_selected_to_matrix(self) -> None:
        tasks = self._require_selection("send it to the matrix")
        if not tasks:
            return
        destination = QuadrantDialog(self, count=len(tasks)).show()
        if not destination:
            return
        self.push_undo("send to matrix")
        moved = 0
        created: list = []
        failed = False
        for task in tasks:
            try:
                created.append(self.matrix.add_from_task(destination, task))
            except StorageError as exc:
                messagebox.showerror("Move failed", str(exc))
                failed = True
                break
            self.tasks.remove(task)
            moved += 1
        # Capture ids, not objects: the file may be renamed or moved to
        # another quadrant before the undo fires, and a captured object's
        # path would then be stale — the delete would silently miss.
        self.attach_undo(
            lambda ids=[t.id for t in created]: self._remove_matrix_tasks_by_id(ids))
        self.refresh_tasks(keep_selection=False)
        self.refresh_matrix()
        self.mark_dirty()
        # Say what actually happened, not what was asked for.
        self.set_status(
            f"Moved {moved} of {presenter.plural(len(tasks), 'task')} to {category_label(destination)}."
            if failed else
            f"Moved {presenter.plural(moved, 'task')} to {category_label(destination)}."
        )
        self.notebook.select(1)
        # Land on the quadrant the tasks actually went to, with the new rows
        # selected — a task that visibly vanishes right after an action is a
        # small jolt of doubt every time, and doubt is what breaks trust in
        # the offload.
        self.matrix_notebook.select(CATEGORY_KEYS.index(destination))
        created_ids = {t.id for t in created}
        listing = self.matrix_lists.get(destination)
        if listing is not None:
            listing.selection_clear(0, tk.END)
            for index, task in enumerate(self._matrix_cache.get(destination, [])):
                if task.id in created_ids:
                    listing.selection_set(index)

    # ------------------------------------------------------------------
    # appearance
    # ------------------------------------------------------------------
    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.theme_name == "light" else "light")

    def set_theme(self, name: str) -> None:
        """Re-skin every widget. Dark is not decoration here — a bright slab of
        white at 11pm is its own barrier to sitting down and starting."""
        self.theme_name = name
        self.config_store.theme = name
        apply_theme(self, name)
        self.theme_button.configure(text="Light" if name == "dark" else "Dark")
        style_text(self.note_text)
        for widget in self._themable_frames():
            widget.configure(background=tokens().border)
        self.task_list.restyle()
        for key, listing in self.matrix_lists.items():
            listing.set_surface(tokens().quadrants.get(key))
        self.refresh_tasks()
        self.refresh_matrix()
        self.refresh_momentum()
        if self._focus_window is not None:
            self._focus_window.restyle()
        self.set_status(f"{name.title()} theme.")

    def _themable_frames(self) -> list:
        """Card borders are plain frames, so they need recolouring by hand."""
        found = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Frame) and getattr(child, "inner", None) is not None:
                    found.append(child)
                walk(child)

        walk(self)
        return found

    def apply_calm_mode(self) -> None:
        """Hide everything that is not needed to capture or to start.

        Filters, sort, the toolbar and the file paths are all useful and all
        noise. Calm mode is one click to a screen with a capture box, a list,
        and the button that starts something.
        """
        calm = bool(self.calm_var.get())
        self.config_store.calm_mode = calm
        if calm:
            # Never hide a control that is still filtering the list: a shorter
            # list with no visible reason why is worse than the clutter.
            self.search_var.set("")
            self.tag_filter_var.set(ALL_TAGS)
            self.kind_filter_var.set(ALL_KINDS)
            self.show_done_var.set(True)
        for widget in (self.filter_row, self.task_toolbar, self.header_extras, self.search_row):
            if calm:
                widget.grid_remove()
            else:
                widget.grid()
        self.refresh_tasks()
        if self._ui_ready:
            self.set_status("Calm mode on — the extras are hidden, not gone." if calm
                            else "Calm mode off.")

    # ------------------------------------------------------------------
    # starting: the part that actually hurts
    # ------------------------------------------------------------------
    def start_here(self) -> None:
        """Pick something to start, when picking is the thing you can't do."""
        open_tasks = [t for t in self.tasks if not t.done]
        if not open_tasks:
            self.set_status("Nothing open. That is a fine place to be.")
            return
        chosen = StartHereDialog(self, self.tasks,
                                 warm=self.session_log.recent_task_ids()).show()
        if chosen is None:
            return
        self._select_task(chosen)
        self.begin_focus(chosen)

    def focus_on_selected(self) -> None:
        tasks = self.selected_tasks()
        if len(tasks) > 1:
            self.set_status("Pick one task to focus on — one at a time is the point.")
            return
        self.begin_focus(tasks[0] if tasks else None)

    def begin_focus(self, task: Task | None) -> None:
        """Warm-up ladder, then run the session."""
        if self._timer_running:
            current = self._focus_task()
            # The same rounding the timer banks with, so the number in the
            # question is the number that gets logged — and the old floor
            # division said "0 minutes" for a block that would still bank
            # one. The wording itself lives in presenter.
            elapsed = max(1, round(
                (self._timer_total - self._timer_remaining) / 60))
            question = presenter.replace_running_question(
                elapsed, mode=self._timer_mode,
                task_text=current.text if current else "")
            with self._ask_over_focus():
                if not messagebox.askyesno("Something is already running", question):
                    return

        with self._ask_over_focus():
            result = StartFocusDialog(
                self,
                task_text=task.text if task else "",
                first_step=task.first_step if task else "",
                place=plan_place(task) if task else "",
                minutes=self.config_store.focus_minutes,
                warmup_steps=self.config_store.warmup_steps,
                show_warmup=self.config_store.show_warmup,
                estimate_minutes=task.estimate_minutes if task else 0,
                popout=self.config_store.popout_on_start,
            ).show()
        if not result:
            return  # nothing torn down: the running block is still running

        banked = None
        replaced = None
        if self.timer.open_block:
            # open_block, not _timer_running: a block PAUSED partway is the
            # other realistic way to arrive here — you stopped, thought
            # better of it, and picked something smaller — and those
            # minutes were being dropped. (The guard in the branch above
            # stays on _timer_running deliberately: that one raises a
            # yes/no modal, and asking it of someone who merely paused
            # would put a decision exactly where it hurts.)
            #
            # Only now is the replacement certain. Bank what was actually done
            # rather than dropping those minutes on the floor — silently: the
            # old block's end dialog in the middle of starting a new one is a
            # decision at the wrong moment, and its break option used to
            # swallow the session being started.
            replaced = self._focus_task()
            banked = self.finish_session_early(interactive=False)

        if task is not None and result["first_step"] and result["first_step"] != task.first_step:
            # Naming the first move is worth keeping even if the session dies.
            self.push_undo("set first step")
            # set_current_step, not a plain assignment: on a task with a plan
            # the first step IS the current line of it, and writing only to
            # `first_step` left the two disagreeing — which `_fix_steps`
            # silently reverted on the next load, so the rename survived
            # until the app was closed. The editor and the session-end dialog
            # were fixed for this; this fourth site was missed.
            task.set_current_step(result["first_step"])
            self.refresh_tasks()
            self.mark_dirty()

        if result.get("warmup_done"):
            steps = result["warmup_done"]
            self.set_status(f"{steps} warm-up step{'s' if steps != 1 else ''} done. Starting.")
        self._focus_task_id = task.id if task else None
        self.focus_task_var.set(
            focus_caption(task, result["first_step"], plan_place(task)))
        self.config_store.focus_minutes = result["minutes"]
        self.work_minutes.set(result["minutes"])
        # The rituals stick: ladder edits, ladder visibility, the pop-out
        # preference and the session length all persist — after the minutes
        # are in, so the saved default doesn't lag a session behind.
        if result.get("warmup_steps") is not None:
            self.config_store.warmup_steps = result["warmup_steps"]
        if "show_warmup" in result:
            self.config_store.show_warmup = bool(result["show_warmup"])
        if "popout" in result:
            self.config_store.popout_on_start = bool(result["popout"])
        self._save_config()
        self.start_timer(minutes=result["minutes"], mode="focus")
        if result.get("popout"):
            # Time blindness: the person least likely to notice the timer is
            # missing is the one who needed it. No remembered click.
            self.open_focus_window()
        if banked:
            # start_timer just overwrote the bank notice; the evidence of the
            # minutes already done should not vanish the moment they land.
            name = f' on "{replaced.text}"' if replaced else ""
            self.set_status(
                f"{banked} min banked{name}. Only the first step matters."
            )

    def _select_task(self, task: Task) -> None:
        """Make a task the current listbox selection, clearing filters if needed."""
        if task not in self._visible:
            self.search_var.set("")
            self.tag_filter_var.set(ALL_TAGS)
            self.kind_filter_var.set(ALL_KINDS)
            self.show_done_var.set(True)
            self.refresh_tasks(keep_selection=False)
        self.task_list.selection_clear(0, tk.END)
        for index, candidate in enumerate(self._visible):
            if candidate.id == task.id:
                self.task_list.selection_set(index)
                self.task_list.see(index)
                break
        # Selecting from code does not fire the widget's own callback, so the
        # actions would stay greyed over a visibly selected row — reachable
        # by clicking the "booked for today" banner.
        self.sync_action_availability()

    def _focus_task(self) -> Task | None:
        if not self._focus_task_id:
            return None
        return next((t for t in self.tasks if t.id == self._focus_task_id), None)

    def open_focus_window(self) -> None:
        """A small always-on-top companion so the countdown stays visible."""
        if self._focus_window is not None:
            try:
                self._focus_window.lift()
                return
            except tk.TclError:
                self._focus_window = None
        self._focus_window = FocusWindow(
            self,
            on_pause=self.toggle_timer,
            on_done=self.finish_session_early,
            on_close=self._forget_focus_window,
            on_park=self.park_thought,
        )
        self._sync_focus_window()

    @contextlib.contextmanager
    def _ask_over_focus(self):
        """Ask where the user is actually looking.

        Drops the pop-out's always-on-top for the duration of a dialog, so the
        question cannot end up hidden behind it.
        """
        window = self._focus_window
        lowered = False
        if window is not None:
            try:
                window.attributes("-topmost", False)
                lowered = True
            except tk.TclError:
                pass
        try:
            yield
        finally:
            if lowered and self._focus_window is window:
                try:
                    window.attributes("-topmost", True)
                except tk.TclError:
                    pass

    def park_thought(self, text: str) -> None:
        """Catch a mid-session thought without ending the session.

        It goes to the scratchpad rather than the task list on purpose: the
        list is a commitment, and deciding is what you are trying not to do
        right now.
        """
        self.append_scratchpad(text, stamped=True)
        self._parked_this_session.append(text)
        self.set_status("Parked in the scratchpad.")

    def _forget_focus_window(self) -> None:
        self._focus_window = None

    def _sync_focus_window(self) -> None:
        if self._focus_window is None:
            return
        task = self._focus_task()
        minutes, seconds = divmod(max(0, self._timer_remaining), 60)
        elapsed = max(0, self._timer_total - self._timer_remaining)
        try:
            self._focus_window.update_session(
                "Break — step away" if self._timer_mode == "break"
                else (task.text if task else ""),
                # With the place, like every other surface that names a step.
                # The pop-out is the one that is up *while you work*, where
                # "of 3" is the difference between a step and a step in
                # something finite.
                step_with_place(task.first_step, plan_place(task))
                if task and self._timer_mode == "focus" else "",
                f"{minutes:02d}:{seconds:02d}",
                elapsed / self._timer_total if self._timer_total else 0,
                self._timer_running,
                closing=self._closing_in(),
            )
        except tk.TclError:
            self._focus_window = None

    def _closing_in(self) -> bool:
        """The last two minutes of a running focus block."""
        return self.timer.closing_in

    def finish_session_early(self, interactive: bool = True) -> int | None:
        """Stop now and keep the minutes you actually did.

        ``interactive=False`` banks the minutes with a status line and no
        end-of-session dialog — used when the block is being replaced by a
        new one, where opening the old block's full end ceremony mid-start
        is a decision forced at exactly the wrong moment (and choosing
        "take a break" there used to swallow the new session entirely).

        Returns the banked focus minutes, or None when nothing was logged
        (never started, already banked, or the block was a break).
        """
        banked = self.timer.bank_early(self._minutes())
        if banked is None:
            # Nothing left to bank: the block either already logged itself, or
            # never started. Logging here would invent minutes.
            return None
        mode, elapsed = banked
        self._stop_ticking()
        self.timer_button.config(text="Start")
        self._update_timer_label()
        if mode == "break":
            self.set_status("Break ended.")
            self.refresh_next_up()  # the break block just closed
            return None
        if interactive:
            self._finish_session(elapsed)
        else:
            self._bank_session(elapsed)
        return elapsed

    def _restore_matrix_tasks(self, tasks: list) -> None:
        for task in tasks:
            self.matrix.restore(task)
        self.refresh_matrix()

    def _remove_matrix_tasks(self, tasks: list) -> None:
        for task in tasks:
            self.matrix.delete(task)
        self.refresh_matrix()

    def _revert_matrix_tasks(self, before: list, ids: list) -> None:
        """Put the matrix back: drop what is there now, write back what was.

        One shape covers adding, editing, moving, booking and deleting,
        because every one of them is the same sentence — *these ids ended up
        in some state, and this is the state they were in before*. An add has
        nothing to write back; a delete has nothing to drop.

        Dropping first matters for edits and moves: both can rename the file,
        so writing the old copy without removing the new one would show the
        task twice.
        """
        self._remove_matrix_tasks_by_id(ids)
        for task in before:
            self.matrix.restore(task)
        self.refresh_matrix()

    def _undo_matrix_change(self, label: str, before: list, ids: list,
                            steps_before: list | None = None) -> None:
        """Register a matrix change with the same undo stack as everything else.

        Without this the stack simply did not hear about matrix work, so the
        next Ctrl+Z popped an older, unrelated entry: the deleted task stayed
        deleted and a change the user was not thinking about was reverted
        instead.
        """
        self.push_undo(label)

        def restore(before=before, ids=ids, steps=steps_before):
            if steps is not None:
                self.steps_log = list(steps)
            self._revert_matrix_tasks(before, ids)

        self.attach_undo(restore)

    def _remove_matrix_tasks_by_id(self, ids: list) -> None:
        """Delete matrix tasks by id, resolved fresh from disk."""
        wanted = set(ids)
        for category in CATEGORY_KEYS:
            for task in self.matrix.list(category):
                if task.id in wanted:
                    self.matrix.delete(task)
        self.refresh_matrix()

    def refresh_momentum(self) -> None:
        self.momentum_strip.render(self.session_log.counts_by_day(14))
        self.momentum_var.set(self.session_log.summary())

    def on_momentum_hover(self, text: str) -> None:
        """Show the day under the pointer, and restore the status line after."""
        if text:
            if self._status_before_hover is None:
                self._status_before_hover = self.status_var.get()
            self.hold_status(text)
        elif self._status_before_hover is not None:
            self.hold_status(self._status_before_hover)
            self._status_before_hover = None

    def _bank_session(self, minutes: int) -> None:
        """Log the minutes; no dialog, no ceremony."""
        task = self._focus_task()
        self.session_log.record(minutes=minutes, task=task.text if task else "",
                                task_id=task.id if task else "")
        self._session_banked = True
        self._session_count += 1
        self.refresh_momentum()
        note = ""
        if self.session_log.write_failed:
            note = " (couldn't write the session log — the day strip may forget this one)"
        self.set_status(
            f"{minutes} min banked" + (f' on "{task.text}"' if task else "") + "." + note
        )

    def _finish_session(self, minutes: int) -> None:
        """Log a completed focus block and offer the break."""
        task = self._focus_task()
        self._bank_session(minutes)

        message = presenter.done_message(self._session_count, minutes)
        self.set_status(message)
        self.bell()

        next_step = ""
        parked = len(self._parked_this_session)
        with self._ask_over_focus():
            if task is not None:
                answer = SessionEndDialog(self, message, task.text,
                                          self.config_store.break_minutes,
                                          first_step=task.first_step,
                                          parked=parked,
                                          rest_of_plan=task.rest_of_plan,
                                          place=plan_place(task)).show() or {}
                choice = answer.get("choice", "carry_on")
                next_step = answer.get("next_step", "")
                step_done = bool(answer.get("step_done"))
            else:
                step_done = False
                choice = "break" if messagebox.askyesno(
                    "Session finished",
                    presenter.break_offer(message, self.config_store.break_minutes),
                ) else "carry_on"

        if task is not None and choice != "done" and (next_step or step_done):
            # Tomorrow's start is already written, while it is still obvious.
            self.push_undo("hand off")
            # Reword first, then move on — the same order as the task editor,
            # because the dialog now asks the same question it does: the box
            # holds what THIS step says, not a description of the next one.
            # The old blank field conflated the two, so on a task with a plan
            # the honest answer overwrote the wrong line.
            if next_step:
                task.set_current_step(next_step)
            if step_done:
                self._advance(task)
            self.refresh_tasks()
            self.mark_dirty()

        if choice == "done" and task is not None:
            self.push_undo("finish task")
            task.set_done(True)
            self.refresh_tasks()
            self.mark_dirty()
            self.set_status(presenter.finished_message(
                minutes, task.estimate_minutes,
                self.session_log.minutes_for_task(task.id)))
            self._focus_task_id = None
            self.focus_task_var.set(presenter.focus_caption_done(minutes))
            self._sync_focus_window()
        if choice == "break":
            self.start_timer(minutes=self.config_store.break_minutes, mode="break")
        elif choice != "done":
            self.focus_task_var.set(presenter.focus_caption_more(minutes))
        if parked:
            # Attention is free now: put the parked lines on screen instead
            # of relying on the user remembering to scroll a growing pad.
            self.note_text.see(tk.END)
        # The block is over (or a break block began): either way the
        # suggestion box's exclusion just changed.
        self.refresh_next_up()

    def _finish_break(self) -> None:
        self.focus_task_var.set(presenter.BREAK_OVER_CAPTION)
        self.set_status("Break finished.")
        self.bell()
        task = self._focus_task()
        self._focus_task_id = None  # the block it belonged to is over
        self.refresh_next_up()
        with self._ask_over_focus():
            again = messagebox.askyesno("Break over", "Start another focus session?")
        if again:
            self.begin_focus(task)

    # ------------------------------------------------------------------
    # booked time (the Schedule quadrant is where this matters)
    # ------------------------------------------------------------------
    def _due_today(self) -> "presenter.DueView":
        """Today's bookings, from the one place that counts them."""
        return presenter.due_view(self.tasks,
                                  self._matrix_cache.get("schedule", []))

    def refresh_due(self) -> None:
        # Counts what is booked for today itself. A banner claiming seven
        # things are due today when five were booked weeks ago is a number
        # the user can check, and checking it is what makes them stop
        # trusting the booking feature entirely. Missed bookings keep their
        # place in the list and their weight in the ranking; they simply
        # stop being counted as today.
        self.due_var.set(self._due_today().text)

    def show_today(self) -> None:
        """What you actually finished today, plus the minutes you focused."""
        view = presenter.today_view(self.tasks, self.completed_log,
                                    self.session_log, steps_log=self.steps_log)
        if not view.body:
            return
        with self._ask_over_focus():
            messagebox.showinfo("Today", view.body)

    def show_week(self) -> None:
        """The last seven days, as evidence — only the days that had anything."""
        view = presenter.week_view(self.tasks, self.completed_log,
                                   self.session_log, steps_log=self.steps_log)
        with self._ask_over_focus():
            WeekReviewDialog(self, view.days, view.total_sessions,
                             view.total_minutes).show()

    def show_booked(self) -> None:
        # The banner counts today's bookings, so its click must land on one
        # of them. Following due_tasks here selected the OLDEST booking —
        # so the most confident gesture in the feature took you to a task
        # from two months ago.
        view = self._due_today()
        if view.tasks:
            self._select_task(view.tasks[0])
            self.set_status(f"Booked for today: {view.tasks[0].text}")
            return
        booked = view.scheduled
        if booked:
            self.notebook.select(1)
            self.matrix_notebook.select(CATEGORY_KEYS.index("schedule"))
            # Put the eye on the booked rows, not just the right tab — and
            # "Focus on this" is one click away from here.
            listing = self.matrix_lists.get("schedule")
            if listing is not None:
                listing.selection_clear(0, tk.END)
                # Highlight exactly the rows the banner counted, by identity,
                # rather than asking "is this today?" a second time here.
                # Two answers to that question is how the count and the click
                # drifted apart in the first place.
                counted = {id(t) for t in booked}
                for index, task in enumerate(self._matrix_cache.get("schedule", [])):
                    if id(task) in counted:
                        listing.selection_set(index)
            self.set_status(f"Booked in Schedule: {booked[0].title}")

    def book_matrix_time(self, category: str) -> None:
        """Give an important-but-not-urgent task the deadline it never had."""
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to book a time for.")
            return
        with self._ask_over_focus():
            answer = PromptDialog(
                self, "Book a time", "When will you actually do this?",
                initial=tasks[0].scheduled_for,
                hint="today / tomorrow / a weekday / 2026-08-01 — blank clears it",
                ok_text="Book",
            ).show()
        if answer is None:
            return
        when = parse_date_input(answer)
        if when is None:
            messagebox.showwarning(
                "Date not understood",
                "Try 'today', 'tomorrow', a weekday, or a date like 2026-08-01.",
            )
            return
        before = [task.copy() for task in tasks]
        done = 0
        try:
            for task in tasks:
                self.matrix.set_scheduled(task, when)
                done += 1
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
        if done:
            self._undo_matrix_change("book a time", before,
                                     [t.id for t in tasks])
        self.refresh_matrix()
        human = humanize_date(when) if when else ""
        spoken = f"for {human} ({when})" if human and human != when else f"for {when}"
        self.set_status(
            (presenter.batch_status("Booked", done, len(tasks), "task") + f" {spoken}.") if when
            else (presenter.batch_status("Cleared the booking on", done, len(tasks), "task") + ".")
        )

    # ------------------------------------------------------------------
    # timer
    # ------------------------------------------------------------------
    # Delegating views onto the FocusTimer state machine. They exist as the
    # documented test seam (the UI tests reach into the clock to fake time
    # passing) and so long-standing internal reads keep working; new code
    # should talk to self.timer directly.
    @property
    def _timer_running(self) -> bool:
        return self.timer.running

    @_timer_running.setter
    def _timer_running(self, value: bool) -> None:
        self.timer.running = bool(value)

    @property
    def _timer_total(self) -> int:
        return self.timer.total

    @_timer_total.setter
    def _timer_total(self, value: int) -> None:
        self.timer.total = value

    @property
    def _timer_remaining(self) -> int:
        return self.timer.remaining

    @_timer_remaining.setter
    def _timer_remaining(self, value: int) -> None:
        self.timer.remaining = value

    @property
    def _timer_mode(self) -> str:
        return self.timer.mode

    @_timer_mode.setter
    def _timer_mode(self, value: str) -> None:
        self.timer.mode = value

    @property
    def _timer_deadline(self) -> float:
        return self.timer.deadline

    @_timer_deadline.setter
    def _timer_deadline(self, value: float) -> None:
        self.timer.deadline = value

    @property
    def _session_banked(self) -> bool:
        return self.timer.banked

    @_session_banked.setter
    def _session_banked(self, value: bool) -> None:
        self.timer.banked = bool(value)

    def toggle_timer(self) -> None:
        if self._timer_running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self, minutes: int | None = None, mode: str = "focus") -> None:
        if not self.timer.start(time.monotonic(), minutes=minutes, mode=mode,
                                fallback_minutes=self._minutes()):
            return
        if minutes is not None and mode == "focus":
            # Only after the machine accepted the start: a refused start
            # must not clear the running block's parked thoughts.
            self._parked_this_session = []
        self.timer_button.config(text="Pause")
        if self.timer.mode == "break":
            self.focus_task_var.set("Break — step away from the screen.")
        # A block just opened: the suggestion box stops pitching the task
        # the block is on (every start path funnels through here — the
        # dialog flow sets _focus_task_id before calling).
        self.refresh_next_up()
        self._tick_timer()
        self.set_status(
            "Break started." if self.timer.mode == "break"
            else f"{self.timer.remaining // 60} minutes. Only the first step matters."
        )

    def pause_timer(self) -> None:
        if not self.timer.pause(time.monotonic()):
            return
        self._stop_ticking()
        self.timer_button.config(text="Resume")
        self._update_timer_label()  # also syncs the pop-out's button and clock
        # Pausing is not failing; say so plainly.
        self.set_status("Paused. Pick it up whenever.")

    def stop_timer(self) -> None:
        if not self._timer_running:
            return
        self.pause_timer()

    def reset_timer(self) -> None:
        # Bank first, while the task is still known — clearing the id below
        # would leave the record with no name on it.
        #
        # Quitting mid-block already keeps your minutes, and so does "Done
        # early". Reset did not, which credited the person who closed the
        # laptop and quietly charged the person who tidied up before
        # stopping. On an empty-tank afternoon those four minutes are the
        # only evidence the day produced anything, and Reset is exactly the
        # button that person reaches for. It banks nothing when there is
        # nothing to bank: an untouched timer, a break, or a block that
        # already logged itself all return None here.
        banked = self.finish_session_early(interactive=False)
        self._stop_ticking()
        self._focus_task_id = None
        self.set_idle_focus_caption()
        self.timer.reset(self._minutes())
        self.timer_button.config(text="Start")
        self._update_timer_label()
        self.refresh_next_up()
        if not banked:
            # Leave the "N min banked" line standing when there was one:
            # it is the evidence, and "Timer reset." would bury it.
            self.set_status("Timer reset.")

    def on_timer_minutes_changed(self) -> None:
        if self.timer.set_length_if_idle(self._minutes()):
            self._update_timer_label()

    def _minutes(self) -> int:
        try:
            return max(1, min(240, int(self.work_minutes.get())))
        except (tk.TclError, ValueError):
            self.work_minutes.set(self.config_store.focus_minutes)
            return self.config_store.focus_minutes

    def _stop_ticking(self) -> None:
        self._timer_running = False
        if self._timer_job is not None:
            try:
                self.after_cancel(self._timer_job)
            except tk.TclError:
                pass
            self._timer_job = None

    def _tick_timer(self) -> None:
        if not self.timer.running:
            return
        # allow_finish=False while a modal dialog holds the grab: finishing
        # would put the end-of-session dialog on top of it and Tk would hand
        # the grab back to nobody when it closed, leaving the "modal" editor
        # open over a mutable main window. The clock holds at 00:00 and the
        # block completes on the first tick after the dialog closes.
        expired = self.timer.tick(time.monotonic(),
                                  allow_finish=self.grab_current() is None)
        self._update_timer_label()
        if expired:
            minutes = self.timer.minutes_for_natural_finish()
            self._stop_ticking()
            self.timer_button.config(text="Start")
            self._update_timer_label()
            if expired == "break":
                self._finish_break()
            else:
                self._finish_session(minutes)
            return
        self._timer_job = self.after(250, self._tick_timer)

    def _update_timer_label(self) -> None:
        view = presenter.timer_view(
            self._timer_remaining, self._timer_total,
            mode=self._timer_mode, running=self._timer_running,
            closing=self._closing_in(),
        )
        self.timer_label.config(text=view.clock)
        self.finish_var.set(view.ends)
        # A visible bar of time left is easier to feel than digits alone.
        self.timer_progress["value"] = int(min(1.0, view.fraction) * 1000)
        self._sync_focus_window()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def load_state(self, initial: bool = False) -> None:
        try:
            data = self.state_store.load()
        except NotASessionError as exc:
            # The file is fine, it just belongs to something else. Leave it
            # exactly where it is and refuse to write anywhere near it.
            self._autosave_blocked = True
            messagebox.showerror(
                "Load failed",
                f"{exc}\n\nAuto-save is off for this session so the file is not "
                f"overwritten. Choose a different session folder, or move the "
                f"file out of the way first.",
            )
            return
        except StorageError as exc:
            data = self._recover_state(exc)
            if data is None:
                return
        self._autosave_blocked = False
        dropped = data.get("dropped", 0)
        if dropped:
            # The amputation must never become permanent silently: autosave
            # stays off until an explicit Save — the user's informed consent
            # to the loss — or a re-load that reads clean.
            self._autosave_blocked = True
            plural = "s" if dropped != 1 else ""
            messagebox.showwarning(
                "Some records were unreadable",
                f"{dropped} task record{plural} in "
                f"{self.state_store.path.name} couldn't be read and "
                f"{'were' if dropped != 1 else 'was'} left out.\n\n"
                "Auto-save is off so the file stays untouched for now. "
                "Saving (Ctrl+S) accepts the loss; Export a copy first if "
                "you want to look at the original.",
            )
        self._apply_state(data)
        if not initial:
            self.set_status(f"Loaded {self.state_store.path}")
        elif self.tasks:
            self.set_status(f"Loaded {presenter.plural(len(self.tasks), 'task')}.")

    def _recover_state(self, exc: StorageError) -> dict | None:
        """The session file is unreadable. Make that survivable.

        The old behaviour was the worst of all worlds: it advised an explicit
        Save, whose once-per-run backup copied the corrupt file over the last
        good ``.bak`` and then wrote the empty in-memory session over the
        data — the app's own advice destroyed both copies. Now the bad file
        is set aside first, so nothing that happens afterwards can lose it,
        and the backup is offered instead of sacrificed.
        """
        spoiled = self.state_store.quarantine()
        if spoiled is None:
            # Could not move it aside (read-only folder?). Fall back to the
            # cautious old stance: touch nothing, save nothing.
            self._autosave_blocked = True
            messagebox.showerror(
                "Load failed",
                f"{exc}\n\nThe file could not be moved aside either, so "
                f"auto-save is off for this session and nothing will be "
                f"overwritten.",
            )
            return None
        intro = (f"{exc}\n\nThe unreadable file was set aside as "
                 f"{spoiled.name}, so nothing is lost.")
        backup = self.state_store.backup_path
        if backup.exists():
            with self._ask_over_focus():
                restore = messagebox.askyesno(
                    "Load failed",
                    intro + f"\n\nRestore the previous session from "
                            f"{backup.name} now?",
                )
            if restore:
                if self.state_store.restore_backup():
                    try:
                        return self.state_store.load()
                    except StorageError as exc2:
                        self._autosave_blocked = True
                        messagebox.showerror(
                            "Load failed",
                            f"The backup could not be read either: {exc2}",
                        )
                        return None
                messagebox.showerror(
                    "Load failed",
                    f"Could not copy {backup.name} back into place. It is "
                    f"still there, untouched.",
                )
                self._autosave_blocked = True
                return None
            # Declined: start fresh, but keep the .bak exactly as it is —
            # the once-per-run backup must not replace it with an empty file.
            self.state_store.preserve_backup()
        else:
            messagebox.showinfo(
                "Load failed",
                intro + "\n\nThere is no backup next to it, so this session "
                        "starts empty. The set-aside file is untouched.",
            )
        self.set_status(f"Started fresh. The unreadable file is kept as {spoiled.name}.")
        return {"tasks": [], "scratchpad": "", "timer_minutes": 15,
                "completed_log": [], "steps_log": []}

    def _apply_state(self, data: dict) -> None:
        self.tasks = data["tasks"]
        self.completed_log = list(data.get("completed_log") or [])
        self.steps_log = list(data.get("steps_log") or [])
        self.set_scratchpad(data["scratchpad"])
        self.work_minutes.set(data["timer_minutes"])
        self._stop_ticking()
        self._timer_mode = "focus"
        self._session_banked = False
        # Both halves, or a stale total turns a 5-minute clock into a
        # two-thirds-full progress bar and a 15-minute log entry.
        self._timer_total = data["timer_minutes"] * 60
        self._timer_remaining = self._timer_total
        if self._focus_task_id and not any(t.id == self._focus_task_id for t in data["tasks"]):
            self._focus_task_id = None
            self.focus_task_var.set(self.IDLE_CAPTION)
        self._undo_stack.clear()
        self._dirty = False
        self.refresh_all()
        self._update_timer_label()
        if not self._focus_task_id:
            # After the logs are loaded, not before: this reads them.
            self.set_idle_focus_caption()

    def save_state(self, silent: bool = False) -> bool:
        try:
            self.state_store.save(self.tasks, self.scratchpad_text(), self._minutes(),
                                  self.completed_log, self.steps_log)
        except StorageError as exc:
            if not silent:
                messagebox.showerror("Save failed", str(exc))
            return False
        self._dirty = False
        self._autosave_complained = False  # a working save clears the warning
        # An explicit, successful save is informed consent: whatever the
        # block was protecting has now been overwritten deliberately.
        self._autosave_blocked = False
        if not silent:
            self.set_status(f"Saved to {self.state_store.path}")
        return True

    def load_state_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open session",
            initialdir=str(self.config_store.db_path),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        if self._dirty and not messagebox.askyesno(
            "Unsaved changes", "Discard the unsaved changes in this session?"
        ):
            return
        store = StateStore(Path(path))
        try:
            data = store.load()
        except StorageError as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        # Keep working in the file that was opened, rather than silently
        # writing it back over the previous session.
        self.state_store.set_path(Path(path))
        self._autosave_blocked = False
        dropped = data.get("dropped", 0)
        if dropped:
            # Same consent rule as startup: an opened file with unreadable
            # records must not be lossily rewritten by the next autosave.
            self._autosave_blocked = True
            plural = "s" if dropped != 1 else ""
            messagebox.showwarning(
                "Some records were unreadable",
                f"{dropped} task record{plural} in {Path(path).name} couldn't "
                f"be read and {'were' if dropped != 1 else 'was'} left out.\n\n"
                "Auto-save is off so the file stays untouched for now. "
                "Saving (Ctrl+S) accepts the loss.",
            )
        self._apply_state(data)
        self.set_status(f"Working in {Path(path).name}")

    def export_state(self) -> bool:
        """Write a copy anywhere. True only when a copy actually landed."""
        path = filedialog.asksaveasfilename(
            title="Export session",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return False
        try:
            StateStore(Path(path)).save(self.tasks, self.scratchpad_text(), self._minutes(),
                                        self.completed_log, self.steps_log)
        except StorageError as exc:
            messagebox.showerror("Export failed", str(exc))
            return False
        self.set_status(f"Exported to {Path(path).name}")
        return True

    def change_db_folder(self) -> None:
        # Titled, because there are two "Change folder" buttons in this app —
        # one here for your tasks and sessions, one in the matrix tab for the
        # quadrant files. On screen each sits beside the path it changes, but
        # the picker covers that, so the title is the only thing left saying
        # which folder you are about to move.
        new_path = filedialog.askdirectory(
            title="Choose the session folder",
            initialdir=str(self.config_store.db_path))
        if not new_path:
            return
        if self._dirty and not self.save_state(silent=True):
            if not messagebox.askyesno(
                "Change folder",
                f"Could not save to {self.state_store.path}.\n\n"
                "Switch folders anyway and lose the unsaved changes?",
            ):
                return
        new_lock = InstanceLock(Path(new_path))
        if not self._claim_instance_lock(new_lock):
            self.set_status("Kept the current session folder.")
            return
        self._instance_lock.release()
        self._instance_lock = new_lock
        self.config_store.db_path = Path(new_path)
        self.state_store.set_path(self.config_store.state_file)
        self.session_log.set_path(self.config_store.sessions_file)
        self.session_log.load()
        self._ensure_folders()
        self._save_config()
        self.load_state(initial=True)
        self.refresh_momentum()
        self.set_status(f"Session folder: {self.config_store.db_path}")

    def change_matrix_db_folder(self) -> None:
        new_path = filedialog.askdirectory(
            title="Choose the matrix folder",
            initialdir=str(self.matrix.root))
        if not new_path:
            return
        self.config_store.matrix_db_path = Path(new_path)
        self.matrix.set_root(self.config_store.matrix_db_path)
        self._ensure_folders()
        self._save_config()
        self.refresh_matrix()
        self.set_status(f"Matrix folder: {self.matrix.root}")

    def _save_config(self) -> None:
        self.config_store.focus_minutes = self._minutes()
        self.config_store.show_done = bool(self.show_done_var.get())
        self.config_store.sort_order = SORT_ORDERS.get(self.sort_var.get(), DEFAULT_SORT)
        self.config_store.break_minutes = self.config_store.break_minutes or DEFAULT_BREAK_MINUTES
        self.config_store.theme = self.theme_name
        self.config_store.calm_mode = bool(self.calm_var.get())
        try:
            self.config_store.save()
        except StorageError as exc:
            self.set_status(str(exc))

    # ------------------------------------------------------------------
    # autosave / shutdown
    # ------------------------------------------------------------------
    def _schedule_autosave(self) -> None:
        self._autosave_job = self.after(AUTOSAVE_SECONDS * 1000, self._autosave)

    def _roll_over_the_day(self) -> None:
        today = today_iso()
        if self._day is None:
            self._day = today
        elif today != self._day:
            self._day = today
            self.refresh_tasks()  # yesterday's "done today" is not today's
            self.refresh_momentum()  # ...and neither is its session summary

    def _autosave(self) -> None:
        self._roll_over_the_day()
        if self.config_store.autosave and self._dirty and not self._autosave_blocked:
            if self.save_state(silent=True):
                self.set_status("Auto-saved.")
            elif not self._autosave_complained:
                # Say it once, calmly, and keep saying nothing while it stays
                # broken — the user needs the fact, not a nag every 30s. The
                # old behaviour was worse than either: hours of silent
                # failure discovered only at quit.
                self._autosave_complained = True
                self.hold_status(
                    "Couldn't auto-save — disk full, or the folder "
                    "unavailable? Your work is only in this window for now: "
                    "try Save, or Export a copy somewhere safe."
                )
        self._schedule_autosave()

    def on_close(self) -> None:
        if self._dirty and not self.save_state(silent=True):
            choice = messagebox.askyesnocancel(
                "Save failed",
                "Saving to the session folder failed.\n\n"
                "Save a copy somewhere else before quitting?\n\n"
                "(“No” quits without saving. “Cancel” stays here.)",
            )
            if choice is None:
                return
            if choice and not self.export_state():
                return  # no copy was written; don't quit on a failed rescue
        # Past every cancel point, so a cancelled quit keeps its running
        # block. Bank an open focus block's minutes silently: closing the
        # lid mid-block without ceremony is a normal end of day, and the
        # evidence of the time must not depend on doing it properly.
        # (No-ops for breaks and never-started blocks; writes to the
        # session log's own file, separate from the state just saved.)
        self.finish_session_early(interactive=False)
        self._save_config()
        self._instance_lock.release()
        self._stop_ticking()
        if self._focus_window is not None:
            self._focus_window.close()
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except tk.TclError:
                pass
        self.destroy()




def main() -> None:
    app = CognitiveOffloadApp()
    if not app.aborted:
        app.mainloop()
