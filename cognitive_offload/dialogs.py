"""Modal dialogs.

All of them share :class:`ModalDialog`, which handles centring on the parent,
Escape/Return handling and the grab/wait dance - previously each dialog did a
slightly different (and slightly broken) version of that.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .storage import CATEGORIES, CATEGORY_KEYS
from .theme import PALETTE, style_text


class ModalDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.result = None
        self._parent = parent
        self.title(title)
        self.configure(background=PALETTE["bg"])
        self.transient(parent.winfo_toplevel())
        if size:
            self.minsize(*size)
            self.geometry(f"{size[0]}x{size[1]}")
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())

    def button_row(self, ok_text: str = "OK") -> ttk.Frame:
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(row, text=ok_text, style="Accent.TButton", command=self.ok).pack(
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


class TaskEditorDialog(ModalDialog):
    """Edit a title, a longer description and (optionally) tags."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        window_title: str = "Task",
        with_tags: bool = False,
    ):
        super().__init__(parent, window_title, size=(460, 380))
        ttk.Label(self.body, text="Title").pack(anchor="w")
        self.title_entry = ttk.Entry(self.body)
        self.title_entry.pack(fill="x", pady=(2, 10))
        self.title_entry.insert(0, title)

        ttk.Label(self.body, text="Details").pack(anchor="w")
        self.content_text = tk.Text(self.body, height=10, wrap="word", undo=True)
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
        self.title_entry.bind("<Return>", lambda _e: self.content_text.focus_set())

    def collect(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Title required", "The title cannot be empty.", parent=self)
            self.title_entry.focus_set()
            return None
        content = self.content_text.get("1.0", "end").strip()
        if self.tags_entry is None:
            return title, content
        tags = [t.strip().lower() for t in self.tags_entry.get().split(",")]
        return title, content, [t for t in tags if t]


class QuadrantDialog(ModalDialog):
    """Pick one of the four Eisenhower quadrants."""

    def __init__(self, parent: tk.Misc, count: int = 1, initial: str = "do_first",
                 window_title: str = "Move to matrix"):
        super().__init__(parent, window_title, size=(360, 240))
        heading = "Move task to:" if count == 1 else f"Move {count} tasks to:"
        ttk.Label(self.body, text=heading, font=("Helvetica", 10, "bold")).pack(anchor="w")

        self.choice = tk.StringVar(value=initial if initial in CATEGORIES else "do_first")
        for key in CATEGORY_KEYS:
            ttk.Radiobutton(
                self.body, text=CATEGORIES[key][2], variable=self.choice, value=key
            ).pack(anchor="w", pady=3)

        self.button_row("Move")
        self.bind("<Return>", self.ok)

    def collect(self):
        return self.choice.get()


class ShortcutsDialog(ModalDialog):
    """A cheat-sheet, so the shortcuts are actually discoverable."""

    SHORTCUTS = [
        ("Capture", [
            ("Enter (capture box)", "Add as task"),
            ("Ctrl+Enter (capture box)", "Add to scratchpad"),
            ("Ctrl+N", "Focus the capture box"),
            ("Ctrl+B", "Send scratchpad lines to tasks"),
        ]),
        ("Tasks", [
            ("Double click / Space", "Toggle done"),
            ("Delete", "Delete selected"),
            ("Ctrl+P", "Toggle high priority"),
            ("Ctrl+T", "Add a tag"),
            ("Ctrl+D", "Edit details"),
            ("Ctrl+Up", "Move to top"),
            ("Ctrl+M", "Send selection to the matrix"),
            ("Ctrl+Z", "Undo the last change"),
            ("Ctrl+F", "Search"),
        ]),
        ("App", [
            ("Ctrl+S", "Save now"),
            ("Ctrl+O", "Open a saved session"),
            ("Ctrl+1 / Ctrl+2", "Switch tab"),
            ("Escape", "Stop the timer / close a dialog"),
            ("F1", "This help"),
        ]),
    ]

    def __init__(self, parent: tk.Misc):
        # No fixed size: the window sizes itself to the table so nothing is cut off.
        super().__init__(parent, "Keyboard shortcuts")
        self.resizable(False, False)
        for section, rows in self.SHORTCUTS:
            ttk.Label(self.body, text=section, font=("Helvetica", 11, "bold")).pack(
                anchor="w", pady=(8, 4)
            )
            grid = ttk.Frame(self.body)
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            for row, (keys, description) in enumerate(rows):
                ttk.Label(grid, text=keys, foreground=PALETTE["accent"]).grid(
                    row=row, column=0, sticky="w", padx=(0, 12)
                )
                ttk.Label(grid, text=description, style="Sub.TLabel").grid(
                    row=row, column=1, sticky="w"
                )
        ttk.Button(self.body, text="Close", command=self.cancel).pack(anchor="e", pady=(14, 0))
