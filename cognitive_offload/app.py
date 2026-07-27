"""The application controller: wires the model, the stores and the two tabs."""

from __future__ import annotations

import contextlib
import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_TITLE, __version__
from .dialogs import (
    QuadrantDialog,
    SessionEndDialog,
    ShortcutsDialog,
    StartFocusDialog,
    StartHereDialog,
    TaskEditorDialog,
)
from .main_tab import build_main_tab
from .matrix_tab import build_matrix_tab
from .models import KIND_LABELS, Task, kind_label, now_stamp, parse_date_input
from .queries import (
    ALL_KINDS,
    DEFAULT_SORT,
    SORT_ORDERS,
    all_tags,
    counts,
    done_today,
    due_tasks,
    split_lines,
    visible_tasks,
)
from .sessions import DEFAULT_BREAK_MINUTES, SessionLog
from .storage import (
    CATEGORY_KEYS,
    Config,
    MatrixStore,
    StateStore,
    StorageError,
    category_label,
    display_path,
)
from .theme import apply_theme, style_text, tokens
from .widgets import Badge, FocusWindow, Row

ALL_TAGS = "(all)"
AUTOSAVE_SECONDS = 30
UNDO_LIMIT = 30

# Said at the end of a session. Deliberately flat and factual: the point is
# that the time is banked, not that you have been a good boy.
DONE_MESSAGES = [
    "That's {minutes} minutes on it. Banked.",
    "{minutes} minutes done — that counts, however it went.",
    "Session finished. The hard part was starting, and you did that.",
]


class CognitiveOffloadApp(tk.Tk):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.title(f"{APP_TITLE} {__version__}")
        self.geometry("1240x880")
        self.minsize(1020, 700)

        self.config_store = config or Config().load()
        self.state_store = StateStore(self.config_store.state_file)
        self.matrix = MatrixStore(self.config_store.matrix_db_path)
        self.session_log = SessionLog(self.config_store.sessions_file).load()

        self.tasks: list[Task] = []
        self._visible: list[Task] = []
        self._matrix_cache: dict[str, list] = {key: [] for key in CATEGORY_KEYS}
        self._undo_stack: list[tuple[str, list[Task]]] = []
        self._dirty = False
        self._autosave_blocked = False
        self._suppress_scratch_event = False
        self._status_token = 0
        self._status_before_hover: str | None = None
        self._autosave_job = None
        self._timer_job = None
        self._timer_running = False
        self._timer_total = self.config_store.focus_minutes * 60
        self._timer_remaining = self._timer_total
        self._timer_deadline = 0.0
        self._timer_mode = "focus"  # or "break"
        self._focus_task_id: str | None = None
        self._session_count = 0
        self._focus_window: FocusWindow | None = None

        # Tk variables have to exist before the tabs that bind to them.
        self.search_var = tk.StringVar()
        self.tag_filter_var = tk.StringVar(value=ALL_TAGS)
        self.kind_filter_var = tk.StringVar(value=ALL_KINDS)
        self.sort_var = tk.StringVar(value=_sort_label(self.config_store.sort_order))
        self.show_done_var = tk.BooleanVar(value=self.config_store.show_done)
        self.status_var = tk.StringVar(value="Ready.")
        self.counts_var = tk.StringVar(value="")
        self.focus_task_var = tk.StringVar(value="Nothing picked yet")
        self.momentum_var = tk.StringVar(value="")
        self.due_var = tk.StringVar(value="")
        self.today_var = tk.StringVar(value="")
        self.finish_var = tk.StringVar(value="")
        self.path_var = tk.StringVar(value="")
        self.matrix_path_var = tk.StringVar(value="")
        self.calm_var = tk.BooleanVar(value=self.config_store.calm_mode)

        self.theme_name = self.config_store.theme
        apply_theme(self, self.theme_name)
        self._build_ui()
        self._bind_shortcuts()
        self.apply_calm_mode()

        self._ensure_folders()
        self.load_state(initial=True)
        self.refresh_matrix()
        self.refresh_momentum()
        self._update_timer_label()
        self._schedule_autosave()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
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
        # (sequence, handler, works_while_typing). Ctrl+P/T/D/N/O/B/Z all have
        # default meanings inside Text and Entry widgets, so those shortcuts
        # step aside whenever a text widget has focus.
        bindings = [
            ("<Control-s>", lambda: self.save_state(), True),
            ("<Control-f>", lambda: self.focus_search(), True),
            ("<Control-Key-1>", lambda: self.notebook.select(0), True),
            ("<Control-Key-2>", lambda: self.notebook.select(1), True),
            ("<F1>", lambda: self.show_shortcuts(), True),
            ("<Escape>", lambda: self.stop_timer(), True),
            ("<Control-o>", lambda: self.load_state_dialog(), False),
            ("<Control-n>", lambda: self.focus_capture(), False),
            ("<Control-b>", lambda: self.brain_dump_into_tasks(), False),
            ("<Control-p>", lambda: self.toggle_selected_priority(), False),
            ("<Control-t>", lambda: self.tag_selected(), False),
            ("<Control-d>", lambda: self.edit_selected_details(), False),
            ("<Control-m>", lambda: self.send_selected_to_matrix(), False),
            ("<Control-z>", lambda: self.undo(), False),
            ("<Control-Up>", lambda: self.promote_selected(), False),
            ("<Control-g>", lambda: self.start_here(), False),
            ("<Control-r>", lambda: self.focus_on_selected(), False),
        ]
        for sequence, handler, while_typing in bindings:
            self.bind_all(sequence, self._shortcut(handler, while_typing))

    def _shortcut(self, handler, while_typing: bool):
        def wrapper(_event=None):
            if not while_typing and self._typing():
                return None  # let the widget's own binding win
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
        self._visible = visible_tasks(
            self.tasks,
            search=self.search_var.get(),
            tag=self._active_tag(),
            order=SORT_ORDERS.get(self.sort_var.get(), DEFAULT_SORT),
            show_done=self.show_done_var.get(),
            kind=self._active_kind(),
        )

        # set_rows already restores the selection by row id, which is the same
        # matching this used to do by hand - once per selected row, each time
        # repainting every row.
        self.task_list.set_rows([_task_row(t) for t in self._visible],
                                keep_selection=keep_selection)

        open_count, done_count, flagged = counts(self.tasks)
        hidden = len(self.tasks) - len(self._visible)
        summary = f"{open_count} open · {done_count} done"
        if flagged:
            summary += f" · {flagged} flagged"
        if hidden > 0:
            summary += f" · {hidden} hidden"
        self.counts_var.set(summary)
        finished = len(done_today(self.tasks))
        # Only ever shown when there is something to show: "0 done today" is
        # the kind of scoreboard this app is meant not to keep.
        self.today_var.set(f"{finished} done today →" if finished else "")
        self.refresh_due()

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
        return next((key for key, name in KIND_LABELS.items() if name == label and key), None)

    def clear_kind_filter(self) -> None:
        self.kind_filter_var.set(ALL_KINDS)
        self.refresh_tasks()

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

    def on_task_selection_changed(self) -> None:
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
        self._undo_stack.append((label, [t.copy() for t in self.tasks]))
        del self._undo_stack[:-UNDO_LIMIT]

    def undo(self) -> None:
        if not self._undo_stack:
            self.set_status("Nothing to undo.")
            return
        label, snapshot = self._undo_stack.pop()
        self.tasks = snapshot
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Undid: {label}.")

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
        self.set_status(status.format(count=len(texts)))
        return len(texts)

    def add_task_from_capture(self) -> None:
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.capture_entry.delete(0, tk.END)
        self._add_tasks([text], "Captured as task.")

    def add_task_direct(self) -> None:
        """Kept as an alias for quick capture: one obvious way to add a task."""
        self.add_task_from_capture()

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
        for task in tasks:
            task.set_done(target)
        self.refresh_tasks()
        self.mark_dirty()
        word = "done" if target else "open"
        self.set_status(f"Marked {len(tasks)} task(s) {word}.")

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
        self.set_status(f"{'Flagged' if target else 'Unflagged'} {len(tasks)} task(s).")

    def tag_selected(self) -> None:
        tasks = self._require_selection("tag it")
        if not tasks:
            return
        tag = simpledialog.askstring("Add tag", "Tag name:", parent=self)
        if not tag or not tag.strip():
            return
        self.push_undo("add tag")
        changed = sum(1 for task in tasks if task.add_tag(tag))
        self.refresh_tasks()
        self.mark_dirty()
        self.set_status(f"Tagged {changed} task(s) with '{tag.strip().lower()}'.")

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
            window_title="Edit task",
            with_tags=True,
        ).show()
        if not result:
            return
        self.push_undo("edit task")
        task.text = result["title"]
        task.description = result["content"]
        task.tags = result["tags"]
        task.first_step = result["first_step"]
        task.kind = result["kind"]
        task.scheduled_for = result["scheduled_for"]
        self.refresh_tasks()
        self.mark_dirty()
        self.set_status("Task updated.")

    def promote_selected(self) -> None:
        tasks = self._require_selection("move it to the top")
        if not tasks:
            return
        self.push_undo("move to top")
        for task in reversed(tasks):
            self.tasks.remove(task)
            self.tasks.insert(0, task)
        self.refresh_tasks()
        self.mark_dirty()
        self.set_status(f"Moved {len(tasks)} task(s) to the top.")

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
        self.set_status(f"Deleted {len(tasks)} task(s). Ctrl+Z undoes it.")

    def clear_completed(self) -> None:
        done = [t for t in self.tasks if t.done]
        if not done:
            self.set_status("No completed tasks to clear.")
            return
        if not messagebox.askyesno("Clear completed", f"Remove {len(done)} completed task(s)?"):
            return
        self.push_undo("clear completed")
        self.tasks = [t for t in self.tasks if not t.done]
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Cleared {len(done)} completed task(s).")

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
        except tk.TclError:
            raw = self.note_text.get("insert linestart", "insert lineend")
        lines = split_lines(raw)
        if not lines:
            self.set_status("Nothing on that line to turn into a task.")
            return
        self._add_tasks(lines, "Sent {count} line(s) to the task list.")

    def brain_dump_into_tasks(self) -> None:
        lines = split_lines(self.scratchpad_text())
        if not lines:
            self.set_status("The scratchpad is empty.")
            return
        if len(lines) > 5 and not messagebox.askyesno(
            "Brain dump", f"Create {len(lines)} tasks from the scratchpad?"
        ):
            return
        self._add_tasks(lines, "Moved {count} line(s) into tasks.")

    def clear_notes(self) -> None:
        if not self.scratchpad_text().strip():
            return
        if not messagebox.askyesno("Clear scratchpad", "Clear everything in the scratchpad?"):
            return
        self.set_scratchpad("")
        self.mark_dirty()
        self.set_status("Scratchpad cleared.")

    # ------------------------------------------------------------------
    # matrix
    # ------------------------------------------------------------------
    def refresh_matrix(self) -> None:
        for index, key in enumerate(CATEGORY_KEYS):
            try:
                tasks = self.matrix.list(key)
            except (OSError, StorageError):
                tasks = []
            self._matrix_cache[key] = tasks
            self.matrix_lists[key].set_rows([_matrix_row(t) for t in tasks],
                                            keep_selection=False)
            self.matrix_count_labels[key].config(
                text=f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}"
            )
            suffix = f" ({len(tasks)})" if tasks else ""
            self.matrix_notebook.tab(index, text=f"{category_label(key)}{suffix}")
        self.matrix_path_var.set(display_path(self.matrix.root))
        self.refresh_due()

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
            created.kind = result["kind"]
            self.matrix.set_scheduled(created, result["scheduled_for"])
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
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
            window_title="Edit matrix task",
        ).show()
        if not result:
            return
        try:
            task.first_step = result["first_step"]
            task.kind = result["kind"]
            task.scheduled_for = result["scheduled_for"]
            self.matrix.update(task, result["title"], result["content"])
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.refresh_matrix()
        self.set_status("Matrix task updated.")

    def delete_matrix_tasks(self, category: str) -> None:
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to delete.")
            return
        label = tasks[0].title if len(tasks) == 1 else f"{len(tasks)} tasks"
        if not messagebox.askyesno("Delete", f"Delete {label}?"):
            return
        try:
            for task in tasks:
                self.matrix.delete(task)
        except StorageError as exc:
            messagebox.showerror("Delete failed", str(exc))
        self.refresh_matrix()
        self.set_status(f"Deleted {len(tasks)} matrix task(s).")

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
        try:
            for task in tasks:
                self.matrix.move(task, destination)
        except StorageError as exc:
            messagebox.showerror("Move failed", str(exc))
        self.refresh_matrix()
        self.set_status(f"Moved {len(tasks)} task(s) to {category_label(destination)}.")

    def matrix_to_tasks(self, category: str) -> None:
        """Move the selected matrix tasks back onto the main stack."""
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to send to the task list.")
            return
        self.push_undo("import from matrix")
        moved = 0
        for task in tasks:
            self.tasks.insert(0, task.to_task())
            try:
                self.matrix.delete(task)
            except StorageError as exc:
                messagebox.showerror("Move failed", str(exc))
                break
            moved += 1
        self.refresh_matrix()
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Moved {moved} task(s) to the main list.")
        self.notebook.select(0)

    def copy_matrix_to_tasks(self, category: str) -> None:
        """Copy every task in the quadrant to the main list, leaving the files alone."""
        tasks = list(self._matrix_cache.get(category, []))
        if not tasks:
            self.set_status(f"{category_label(category)} is empty.")
            return
        if not messagebox.askyesno(
            "Copy to tasks", f"Copy {len(tasks)} task(s) from {category_label(category)}?"
        ):
            return
        self.push_undo("copy from matrix")
        for task in tasks:
            self.tasks.insert(0, task.to_task())
        self.refresh_tasks(keep_selection=False)
        self.mark_dirty()
        self.set_status(f"Copied {len(tasks)} task(s) to the main list.")
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
        for task in tasks:
            try:
                self.matrix.add_from_task(destination, task)
            except StorageError as exc:
                messagebox.showerror("Move failed", str(exc))
                break
            self.tasks.remove(task)
            moved += 1
        self.refresh_tasks(keep_selection=False)
        self.refresh_matrix()
        self.mark_dirty()
        self.set_status(f"Moved {moved} task(s) to {category_label(destination)}.")
        self.notebook.select(1)

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
        for widget in (self.filter_row, self.task_toolbar, self.header_extras, self.search_row):
            if calm:
                widget.grid_remove()
            else:
                widget.grid()
        self.refresh_tasks()
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
        chosen = StartHereDialog(self, self.tasks).show()
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
        if self._timer_running and self._timer_mode == "focus":
            # Losing track that a block is already running is the exact failure
            # mode this app exists for, so say so instead of silently
            # mis-crediting the log.
            current = self._focus_task()
            name = f'"{current.text}"' if current else "the current block"
            if not messagebox.askyesno(
                "A session is already running",
                f"You are {self._timer_remaining // 60} minutes into {name}.\n\n"
                "Drop it and start a new one?",
            ):
                return
            self._stop_ticking()
            self._timer_remaining = self._timer_total
        result = StartFocusDialog(
            self,
            task_text=task.text if task else "",
            first_step=task.first_step if task else "",
            minutes=self.config_store.focus_minutes,
            warmup_steps=self.config_store.warmup_steps,
            show_warmup=self.config_store.show_warmup,
        ).show()
        if not result:
            return

        if task is not None and result["first_step"] and result["first_step"] != task.first_step:
            # Naming the first move is worth keeping even if the session dies.
            self.push_undo("set first step")
            task.first_step = result["first_step"]
            self.refresh_tasks()
            self.mark_dirty()

        self._focus_task_id = task.id if task else None
        self.focus_task_var.set(_focus_caption(task, result["first_step"]))
        self.config_store.focus_minutes = result["minutes"]
        self.work_minutes.set(result["minutes"])
        self.start_timer(minutes=result["minutes"], mode="focus")

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
                task.first_step if task and self._timer_mode == "focus" else "",
                f"{minutes:02d}:{seconds:02d}",
                elapsed / self._timer_total if self._timer_total else 0,
                self._timer_running,
            )
        except tk.TclError:
            self._focus_window = None

    def finish_session_early(self) -> None:
        """Stop now and keep the minutes you actually did."""
        if not self._timer_running and (
            self._timer_remaining <= 0 or self._timer_remaining >= self._timer_total
        ):
            # Nothing left to bank: the block either already logged itself on
            # expiry, or never started. Logging here would invent minutes.
            return
        elapsed = max(1, round((self._timer_total - self._timer_remaining) / 60))
        self._stop_ticking()
        mode, self._timer_mode = self._timer_mode, "focus"
        self._timer_remaining = self._timer_total
        self.timer_button.config(text="Start")
        self._update_timer_label()
        if mode == "break":
            self.set_status("Break ended.")
            return
        self._finish_session(elapsed)

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

    def _finish_session(self, minutes: int) -> None:
        """Log a completed focus block and offer the break."""
        task = self._focus_task()
        self.session_log.record(minutes=minutes, task=task.text if task else "")
        self._session_count += 1
        self.refresh_momentum()

        message = DONE_MESSAGES[self._session_count % len(DONE_MESSAGES)].format(minutes=minutes)
        self.set_status(message)
        self.bell()

        with self._ask_over_focus():
            if task is not None:
                choice = SessionEndDialog(self, message, task.text,
                                          self.config_store.break_minutes).show()
            else:
                choice = "break" if messagebox.askyesno(
                    "Session finished",
                    f"{message}\n\nTake a {self.config_store.break_minutes}-minute break now?",
                ) else "carry_on"

        if choice == "done" and task is not None:
            self.push_undo("finish task")
            task.set_done(True)
            self.refresh_tasks()
            self.mark_dirty()
            self.set_status(f"{minutes} min, and it's finished. Nice.")
            self._focus_task_id = None
        if choice in ("break", "done_break"):
            self.start_timer(minutes=self.config_store.break_minutes, mode="break")
        elif choice != "done":
            self.focus_task_var.set(
                f"{minutes} min logged. Another round when you're ready."
            )

    def _finish_break(self) -> None:
        self.focus_task_var.set("Break over. One more small block?")
        self.set_status("Break finished.")
        self.bell()
        task = self._focus_task()
        self._focus_task_id = None  # the block it belonged to is over
        with self._ask_over_focus():
            again = messagebox.askyesno("Break over", "Start another focus session?")
        if again:
            self.begin_focus(task)

    # ------------------------------------------------------------------
    # booked time (the Schedule quadrant is where this matters)
    # ------------------------------------------------------------------
    def refresh_due(self) -> None:
        due = due_tasks(self.tasks)
        booked = [t for t in self._matrix_cache.get("schedule", []) if t.is_due()]
        total = len(due) + len(booked)
        if total:
            self.due_var.set(f"{total} booked for today →")
        else:
            self.due_var.set("")

    def show_today(self) -> None:
        """What you actually finished today, plus the minutes you focused."""
        finished = done_today(self.tasks)
        if not finished:
            return
        lines = [f"·  {t.text}" for t in finished]
        minutes = self.session_log.minutes_today()
        sessions = self.session_log.count_today()
        footer = ""
        if sessions:
            footer = (f"\n\nPlus {sessions} focus session"
                      f"{'s' if sessions != 1 else ''} — {minutes} minutes.")
        with self._ask_over_focus():
            messagebox.showinfo(
                "Today",
                "Finished today:\n\n" + "\n".join(lines) + footer,
            )

    def show_booked(self) -> None:
        due = due_tasks(self.tasks)
        if due:
            self._select_task(due[0])
            self.set_status(f"Booked for today: {due[0].text}")
            return
        booked = [t for t in self._matrix_cache.get("schedule", []) if t.is_due()]
        if booked:
            self.notebook.select(1)
            self.matrix_notebook.select(1)
            self.set_status(f"Booked in Schedule: {booked[0].title}")

    def book_matrix_time(self, category: str) -> None:
        """Give an important-but-not-urgent task the deadline it never had."""
        tasks = self._selected_matrix_tasks(category)
        if not tasks:
            self.set_status("Select a task to book a time for.")
            return
        answer = simpledialog.askstring(
            "Book a time",
            "When will you actually do this?\n"
            "today / tomorrow / a weekday / 2026-08-01  (blank clears it)",
            parent=self,
            initialvalue=tasks[0].scheduled_for,
        )
        if answer is None:
            return
        when = parse_date_input(answer)
        if when is None:
            messagebox.showwarning(
                "Date not understood",
                "Try 'today', 'tomorrow', a weekday, or a date like 2026-08-01.",
            )
            return
        try:
            for task in tasks:
                self.matrix.set_scheduled(task, when)
        except StorageError as exc:
            messagebox.showerror("Save failed", str(exc))
        self.refresh_matrix()
        self.set_status(
            f"Booked {len(tasks)} task(s) for {when}." if when
            else f"Cleared the booking on {len(tasks)} task(s)."
        )

    # ------------------------------------------------------------------
    # timer
    # ------------------------------------------------------------------
    def toggle_timer(self) -> None:
        if self._timer_running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self, minutes: int | None = None, mode: str = "focus") -> None:
        if self._timer_running:
            return
        if minutes is not None:
            self._timer_mode = mode
            self._timer_total = max(1, minutes) * 60
            self._timer_remaining = self._timer_total
        elif self._timer_remaining <= 0:
            self._timer_total = self._minutes() * 60
            self._timer_remaining = self._timer_total
        # Track a wall-clock deadline so the countdown cannot drift.
        self._timer_deadline = time.monotonic() + self._timer_remaining
        self._timer_running = True
        self.timer_button.config(text="Pause")
        if self._timer_mode == "break":
            self.focus_task_var.set("Break — step away from the screen.")
        self._tick_timer()
        self.set_status(
            "Break started." if self._timer_mode == "break"
            else f"{self._timer_remaining // 60} minutes. Only the first step matters."
        )

    def pause_timer(self) -> None:
        if not self._timer_running:
            return
        self._timer_remaining = max(0, int(round(self._timer_deadline - time.monotonic())))
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
        self._stop_ticking()
        self._focus_task_id = None
        self.focus_task_var.set("Nothing picked yet")
        self._timer_mode = "focus"
        self._timer_total = self._minutes() * 60
        self._timer_remaining = self._timer_total
        self.timer_button.config(text="Start")
        self._update_timer_label()
        self.set_status("Timer reset.")

    def on_timer_minutes_changed(self) -> None:
        if not self._timer_running:
            self._timer_total = self._minutes() * 60
            self._timer_remaining = self._timer_total
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
        if not self._timer_running:
            return
        remaining = self._timer_deadline - time.monotonic()
        self._timer_remaining = max(0, int(math.ceil(remaining)))
        self._update_timer_label()
        if remaining <= 0:
            mode = self._timer_mode
            minutes = max(1, round(self._timer_total / 60))
            self._stop_ticking()
            self._timer_remaining = 0
            self._timer_mode = "focus"
            self.timer_button.config(text="Start")
            self._update_timer_label()
            if mode == "break":
                self._finish_break()
            else:
                self._finish_session(minutes)
            return
        self._timer_job = self.after(250, self._tick_timer)

    def _update_timer_label(self) -> None:
        minutes, seconds = divmod(max(0, self._timer_remaining), 60)
        self.timer_label.config(text=f"{minutes:02d}:{seconds:02d}")
        # "ends 15:42" is anchorable in a way "22:00 left" is not, which is the
        # whole difficulty with time blindness.
        if self._timer_running and self._timer_remaining > 0:
            ends = time.localtime(time.time() + self._timer_remaining)
            self.finish_var.set(("break ends " if self._timer_mode == "break" else "ends ")
                                + time.strftime("%H:%M", ends))
        else:
            self.finish_var.set("")
        # A visible bar of time left is easier to feel than digits alone.
        elapsed = max(0, self._timer_total - self._timer_remaining)
        fraction = elapsed / self._timer_total if self._timer_total else 0
        self.timer_progress["value"] = int(min(1.0, fraction) * 1000)
        self._sync_focus_window()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def load_state(self, initial: bool = False) -> None:
        try:
            data = self.state_store.load()
        except StorageError as exc:
            # Don't let autosave overwrite a file we failed to read - the user
            # may still be able to recover it (or the .bak next to it) by hand.
            self._autosave_blocked = True
            messagebox.showerror(
                "Load failed",
                f"{exc}\n\nAuto-save is off for this session so the existing file "
                f"is not overwritten. Use Save explicitly to replace it.",
            )
            return
        self._autosave_blocked = False
        self._apply_state(data)
        if not initial:
            self.set_status(f"Loaded {self.state_store.path}")
        elif self.tasks:
            self.set_status(f"Loaded {len(self.tasks)} task(s).")

    def _apply_state(self, data: dict) -> None:
        self.tasks = data["tasks"]
        self.set_scratchpad(data["scratchpad"])
        self.work_minutes.set(data["timer_minutes"])
        self._timer_remaining = data["timer_minutes"] * 60
        self._undo_stack.clear()
        self._dirty = False
        self.refresh_all()
        self._update_timer_label()

    def save_state(self, silent: bool = False) -> bool:
        try:
            self.state_store.save(self.tasks, self.scratchpad_text(), self._minutes())
        except StorageError as exc:
            if not silent:
                messagebox.showerror("Save failed", str(exc))
            return False
        self._dirty = False
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
        self._apply_state(data)
        self.set_status(f"Loaded {Path(path).name}")

    def export_state(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export session",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            StateStore(Path(path)).save(self.tasks, self.scratchpad_text(), self._minutes())
        except StorageError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        self.set_status(f"Exported to {Path(path).name}")

    def change_db_folder(self) -> None:
        new_path = filedialog.askdirectory(initialdir=str(self.config_store.db_path))
        if not new_path:
            return
        if self._dirty:
            self.save_state(silent=True)
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
        new_path = filedialog.askdirectory(initialdir=str(self.matrix.root))
        if not new_path:
            return
        self.config_store.matrix_db_path = Path(new_path)
        self.matrix.set_root(self.config_store.matrix_db_path)
        self._ensure_folders()
        self._save_config()
        self.refresh_matrix()
        self.set_status(f"Matrix folder: {self.matrix.root}")

    def _save_config(self) -> None:
        self.config_store.timer_minutes = self._minutes()
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

    def _autosave(self) -> None:
        if self.config_store.autosave and self._dirty and not self._autosave_blocked:
            if self.save_state(silent=True):
                self.set_status("Auto-saved.")
        self._schedule_autosave()

    def on_close(self) -> None:
        if self._dirty and not self.save_state(silent=True):
            if not messagebox.askyesno("Quit", "Saving failed. Quit and lose the changes?"):
                return
        self._save_config()
        self._stop_ticking()
        if self._focus_window is not None:
            self._focus_window.close()
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except tk.TclError:
                pass
        self.destroy()


def _task_row(task: Task) -> Row:
    """A task as a list row: title, first step underneath, badges alongside."""
    badges = []
    if task.done:
        badges.append(Badge("done", "done"))
    else:
        if task.kind:
            badges.append(Badge(kind_label(task.kind).split(" ")[0].lower(), task.kind))
        if task.is_ready:
            badges.append(Badge("ready", "ready"))
        if task.scheduled_for:
            badges.append(Badge(
                "today" if task.is_due() else f"booked {task.scheduled_for}",
                "today" if task.is_due() else "booked",
            ))
    badges.extend(Badge(f"#{tag}", "tag") for tag in task.tags)

    if task.done and task.completed_at:
        subtitle = f"done {task.completed_at}"
    elif task.first_step:
        subtitle = f"→ {task.first_step}"
    elif task.description.strip():
        subtitle = task.description.strip().splitlines()[0][:80]
    else:
        subtitle = ""

    return Row(id=task.id, title=task.text, subtitle=subtitle, badges=badges,
               done=task.done, flagged=bool(task.priority))


def _matrix_row(task) -> Row:
    badges = []
    if task.kind:
        badges.append(Badge(kind_label(task.kind).split(" ")[0].lower(), task.kind))
    if task.is_ready:
        badges.append(Badge("ready", "ready"))
    if task.scheduled_for:
        # An overdue booking is a nudge, not a telling-off.
        badges.append(Badge(
            "today" if task.is_due() else f"booked {task.scheduled_for}",
            "today" if task.is_due() else "booked",
        ))
    subtitle = f"→ {task.first_step}" if task.first_step else (
        task.content.strip().splitlines()[0][:80] if task.content.strip() else ""
    )
    return Row(id=task.id, title=task.title, subtitle=subtitle, badges=badges, marker="·")


def _focus_caption(task: Task | None, first_step: str) -> str:
    if task is None:
        return f"Free focus — {first_step}" if first_step else "Free focus"
    return f"{task.text}\n→ {first_step}" if first_step else task.text


def _sort_label(order: str) -> str:
    for label, key in SORT_ORDERS.items():
        if key == order:
            return label
    return "Priority"


def main() -> None:
    app = CognitiveOffloadApp()
    app.mainloop()
