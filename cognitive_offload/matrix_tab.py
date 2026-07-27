"""Layout for the Eisenhower matrix tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .storage import CATEGORIES, CATEGORY_KEYS
from .theme import QUADRANT_COLORS, style_listbox


def build_matrix_tab(app, root: ttk.Frame) -> None:
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    header = ttk.Frame(root, padding=(12, 10, 12, 0))
    header.grid(row=0, column=0, sticky="ew")
    ttk.Label(header, text="Eisenhower Matrix", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text="Sort by urgency and importance. Each quadrant is a folder of task files on disk.",
        style="Sub.TLabel",
    ).pack(anchor="w", pady=(2, 8))

    db_row = ttk.Frame(header)
    db_row.pack(fill="x", pady=(0, 6))
    ttk.Label(db_row, text="Matrix folder:", style="Sub.TLabel").pack(side="left")
    app.matrix_path_label = ttk.Label(db_row, text="", style="Link.TLabel")
    app.matrix_path_label.pack(side="left", padx=(6, 10))
    ttk.Button(db_row, text="Change folder", style="Toolbar.TButton",
               command=app.change_matrix_db_folder).pack(side="left")
    ttk.Button(db_row, text="Refresh", style="Toolbar.TButton",
               command=app.refresh_matrix).pack(side="left", padx=(4, 0))
    ttk.Button(db_row, text="← Back to tasks", style="Toolbar.TButton",
               command=lambda: app.notebook.select(0)).pack(side="right")

    app.matrix_notebook = ttk.Notebook(root)
    app.matrix_notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    app.matrix_lists = {}
    app.matrix_count_labels = {}

    for key in CATEGORY_KEYS:
        _build_quadrant(app, key)


def _build_quadrant(app, key: str) -> None:
    _, short_label, long_label = CATEGORIES[key]
    frame = ttk.Frame(app.matrix_notebook, padding=10)
    app.matrix_notebook.add(frame, text=short_label)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(1, weight=1)

    title_row = ttk.Frame(frame)
    title_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
    ttk.Label(title_row, text=long_label, style="Quadrant.TLabel").pack(side="left")
    count_label = ttk.Label(title_row, text="", style="Sub.TLabel")
    count_label.pack(side="left", padx=(10, 0))
    app.matrix_count_labels[key] = count_label

    buttons = ttk.Frame(frame)
    buttons.grid(row=1, column=0, sticky="nw", padx=(0, 10))
    actions = [
        ("Add", lambda k=key: app.add_matrix_task(k), "Accent.TButton"),
        ("Edit", lambda k=key: app.edit_matrix_task(k), "TButton"),
        ("Move to…", lambda k=key: app.move_matrix_tasks(k), "TButton"),
        ("→ Tasks", lambda k=key: app.matrix_to_tasks(k), "TButton"),
        ("Copy all → tasks", lambda k=key: app.copy_matrix_to_tasks(k), "TButton"),
        ("Delete", lambda k=key: app.delete_matrix_tasks(k), "Danger.TButton"),
    ]
    for text, command, style in actions:
        ttk.Button(buttons, text=text, style=style, command=command).pack(fill="x", pady=2)

    listbox = tk.Listbox(frame, height=18, selectmode=tk.EXTENDED, exportselection=False)
    style_listbox(listbox, background=QUADRANT_COLORS.get(key))
    listbox.grid(row=1, column=1, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
    scroll.grid(row=1, column=2, sticky="ns")
    listbox.configure(yscrollcommand=scroll.set)

    listbox.bind("<Double-Button-1>", lambda _e, k=key: app.edit_matrix_task(k))
    listbox.bind("<Return>", lambda _e, k=key: app.edit_matrix_task(k))
    listbox.bind("<Delete>", lambda _e, k=key: app.delete_matrix_tasks(k))

    ttk.Label(
        frame,
        text="Double click to edit · Delete removes · multi-select works with Shift/Ctrl",
        style="Hint.TLabel",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

    app.matrix_lists[key] = listbox
