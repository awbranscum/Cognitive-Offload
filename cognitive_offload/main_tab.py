"""Layout for the main "capture and triage" tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .models import KIND_LABELS
from .queries import ALL_KINDS, SORT_ORDERS
from .theme import PALETTE, style_listbox, style_text
from .widgets import MomentumStrip


def build_main_tab(app, root: ttk.Frame) -> None:
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)

    _build_header(app, root)
    _build_top_row(app, root)
    _build_body(app, root)
    _build_footer(app, root)


def _build_header(app, root: ttk.Frame) -> None:
    header = ttk.Frame(root, padding=(12, 10, 12, 0))
    header.grid(row=0, column=0, sticky="ew")

    ttk.Label(header, text="Cognitive Offload", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text="A second brain: capture it, sort it, and keep the active stack visible.",
        style="Sub.TLabel",
    ).pack(anchor="w", pady=(2, 8))

    db_row = ttk.Frame(header)
    db_row.pack(fill="x", pady=(0, 6))
    # Right-hand widgets are packed first so a long path can never push them
    # off the edge of the window.
    ttk.Button(db_row, text="Shortcuts", style="Toolbar.TButton",
               command=app.show_shortcuts).pack(side="right")
    ttk.Button(db_row, text="Change folder", style="Toolbar.TButton",
               command=app.change_db_folder).pack(side="right", padx=(0, 6))
    ttk.Label(db_row, text="Session file:", style="Sub.TLabel").pack(side="left")
    app.path_label = ttk.Label(db_row, text="", style="Link.TLabel", cursor="hand2")
    app.path_label.pack(side="left", padx=(6, 10))
    app.path_label.bind("<Button-1>", lambda _e: app.copy_session_path())


def _build_top_row(app, root: ttk.Frame) -> None:
    top = ttk.Frame(root, padding=(12, 0))
    top.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    top.columnconfigure(0, weight=3)
    top.columnconfigure(1, weight=1)

    capture = ttk.Labelframe(top, text="Quick capture", style="Card.TLabelframe")
    capture.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    capture.columnconfigure(0, weight=1)

    app.capture_entry = ttk.Entry(capture, font=("Helvetica", 11))
    app.capture_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 4))
    app.capture_entry.bind("<Return>", lambda _e: app.add_task_from_capture())
    app.capture_entry.bind("<Control-Return>", lambda _e: app.add_note_from_capture())

    ttk.Button(capture, text="→ Task", style="Accent.TButton",
               command=app.add_task_from_capture).grid(row=0, column=1, padx=(0, 6))
    ttk.Button(capture, text="→ Scratchpad",
               command=app.add_note_from_capture).grid(row=0, column=2)
    ttk.Label(
        capture,
        text="Enter adds a task · Ctrl+Enter drops it in the scratchpad",
        style="Hint.TLabel",
    ).grid(row=1, column=0, columnspan=3, sticky="w")

    timer = ttk.Labelframe(top, text="Focus session", style="Card.TLabelframe")
    timer.grid(row=0, column=1, sticky="nsew")
    for col in range(4):
        timer.columnconfigure(col, weight=1)

    app.focus_task_label = ttk.Label(
        timer, textvariable=app.focus_task_var, style="Hint.TLabel", anchor="center",
        wraplength=260, justify="center",
    )
    app.focus_task_label.grid(row=0, column=0, columnspan=4, sticky="ew")

    app.timer_label = ttk.Label(timer, text="15:00", style="Timer.TLabel", anchor="center")
    app.timer_label.grid(row=1, column=0, columnspan=4, sticky="ew")

    app.timer_progress = ttk.Progressbar(timer, mode="determinate", maximum=1000)
    app.timer_progress.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 6))

    app.work_minutes = tk.IntVar(value=15)
    ttk.Label(timer, text="Min").grid(row=3, column=0, sticky="e", padx=(0, 4))
    ttk.Spinbox(timer, from_=1, to=240, width=4, textvariable=app.work_minutes,
                command=app.on_timer_minutes_changed).grid(row=3, column=1, sticky="w")
    app.timer_button = ttk.Button(timer, text="Start", style="Accent.TButton",
                                  command=app.toggle_timer)
    app.timer_button.grid(row=3, column=2, padx=4, sticky="ew")
    ttk.Button(timer, text="Reset", command=app.reset_timer).grid(row=3, column=3, sticky="ew")

    momentum = ttk.Frame(timer)
    momentum.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
    app.momentum_strip = MomentumStrip(momentum, days=14, on_hover=app.on_momentum_hover)
    app.momentum_strip.pack(side="left")
    ttk.Label(momentum, textvariable=app.momentum_var, style="Hint.TLabel").pack(
        side="left", padx=(8, 0)
    )


def _build_body(app, root: ttk.Frame) -> None:
    body = ttk.Frame(root, padding=(12, 0))
    body.grid(row=2, column=0, sticky="nsew")
    body.columnconfigure(0, weight=3, uniform="cols")
    body.columnconfigure(1, weight=2, uniform="cols")
    body.rowconfigure(0, weight=1)

    _build_tasks_card(app, body)
    _build_scratchpad_card(app, body)


def _build_tasks_card(app, body: ttk.Frame) -> None:
    card = ttk.Labelframe(body, text="Tasks / active stack", style="Card.TLabelframe")
    card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    card.columnconfigure(0, weight=1)
    card.rowconfigure(4, weight=1)

    # The most important button on the screen: the way in when the list
    # itself is the thing you cannot face.
    start_row = ttk.Frame(card)
    start_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Button(
        start_row, text="Where do I start?", style="Accent.TButton", command=app.start_here
    ).pack(side="left")
    ttk.Button(
        start_row, text="Focus on selected", command=app.focus_on_selected
    ).pack(side="left", padx=(6, 0))
    app.due_label = ttk.Label(start_row, textvariable=app.due_var, style="Hint.TLabel",
                              cursor="hand2")
    app.due_label.pack(side="left", padx=(12, 0))
    app.due_label.bind("<Button-1>", lambda _e: app.show_booked())

    search_row = ttk.Frame(card)
    search_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    ttk.Label(search_row, text="Search").pack(side="left", padx=(0, 6))
    app.search_entry = ttk.Entry(search_row, textvariable=app.search_var)
    app.search_entry.pack(side="left", fill="x", expand=True)
    app.search_entry.bind("<KeyRelease>", lambda _e: app.refresh_tasks())
    app.search_entry.bind("<Escape>", lambda _e: app.clear_search())
    ttk.Button(search_row, text="Clear", style="Toolbar.TButton",
               command=app.clear_search).pack(side="left", padx=(6, 0))

    filter_row = ttk.Frame(card)
    filter_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    ttk.Label(filter_row, text="Tag").pack(side="left", padx=(0, 4))
    app.tag_filter_combo = ttk.Combobox(
        filter_row, textvariable=app.tag_filter_var, width=12, state="readonly"
    )
    app.tag_filter_combo.pack(side="left")
    app.tag_filter_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())
    ttk.Button(filter_row, text="All tags", style="Toolbar.TButton",
               command=app.clear_tag_filter).pack(side="left", padx=(4, 12))

    ttk.Label(filter_row, text="Feels like").pack(side="left", padx=(0, 4))
    kind_combo = ttk.Combobox(
        filter_row,
        textvariable=app.kind_filter_var,
        values=[ALL_KINDS] + [label for key, label in KIND_LABELS.items() if key],
        width=14,
        state="readonly",
    )
    kind_combo.pack(side="left", padx=(0, 12))
    kind_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())

    ttk.Label(filter_row, text="Sort").pack(side="left", padx=(0, 4))
    sort_combo = ttk.Combobox(
        filter_row, textvariable=app.sort_var, values=list(SORT_ORDERS), width=12, state="readonly"
    )
    sort_combo.pack(side="left")
    sort_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())
    ttk.Checkbutton(
        filter_row, text="Show done", variable=app.show_done_var, command=app.refresh_tasks
    ).pack(side="left", padx=(12, 0))

    # Two rows of equal-width buttons: a single row clipped its last entries
    # as soon as the window was anything less than very wide.
    toolbar = ttk.Frame(card)
    toolbar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    rows = [
        [("Done", app.toggle_selected_done),
         ("Priority", app.toggle_selected_priority),
         ("Tag", app.tag_selected),
         ("Details", app.edit_selected_details)],
        [("Move to top", app.promote_selected),
         ("To matrix", app.send_selected_to_matrix),
         ("Delete", app.delete_selected)],
    ]
    for column in range(4):
        toolbar.columnconfigure(column, weight=1, uniform="tools")
    for row_index, row in enumerate(rows):
        for column, (label, command) in enumerate(row):
            style = "Danger.TButton" if label == "Delete" else "Toolbar.TButton"
            ttk.Button(toolbar, text=label, style=style, command=command).grid(
                row=row_index, column=column, sticky="ew", padx=(0, 4), pady=(0, 4)
            )

    app.task_list = tk.Listbox(card, height=14, selectmode=tk.EXTENDED, exportselection=False)
    style_listbox(app.task_list)
    app.task_list.grid(row=4, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(card, orient="vertical", command=app.task_list.yview)
    scroll.grid(row=4, column=1, sticky="ns")
    app.task_list.configure(yscrollcommand=scroll.set)

    def toggle_done_key(_event):
        app.toggle_selected_done()
        return "break"  # stop the listbox from also scrolling

    app.task_list.bind("<Double-Button-1>", lambda _e: app.toggle_selected_done())
    app.task_list.bind("<space>", toggle_done_key)
    app.task_list.bind("<Return>", lambda _e: app.edit_selected_details())
    app.task_list.bind("<Delete>", lambda _e: app.delete_selected())
    app.task_list.bind("<<ListboxSelect>>", lambda _e: app.on_task_selection_changed())

    entry_row = ttk.Frame(card)
    entry_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    entry_row.columnconfigure(0, weight=1)
    app.task_entry = ttk.Entry(entry_row)
    app.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    app.task_entry.bind("<Return>", lambda _e: app.add_task_direct())
    ttk.Button(entry_row, text="Add task", command=app.add_task_direct).grid(row=0, column=1)
    ttk.Button(entry_row, text="Clear done", style="Toolbar.TButton",
               command=app.clear_completed).grid(row=0, column=2, padx=(6, 0))


def _build_scratchpad_card(app, body: ttk.Frame) -> None:
    card = ttk.Labelframe(body, text="Scratchpad / working note", style="Card.TLabelframe")
    card.grid(row=0, column=1, sticky="nsew")
    card.columnconfigure(0, weight=1)
    card.rowconfigure(1, weight=1)

    buttons = ttk.Frame(card)
    buttons.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    ttk.Button(buttons, text="Line → task", style="Toolbar.TButton",
               command=app.send_scratch_line_to_tasks).pack(side="left", padx=(0, 4))
    ttk.Button(buttons, text="All → tasks", style="Toolbar.TButton",
               command=app.brain_dump_into_tasks).pack(side="left", padx=(0, 4))
    ttk.Button(buttons, text="Clear", style="Danger.TButton",
               command=app.clear_notes).pack(side="left")

    app.note_text = tk.Text(card, wrap="word", height=18, undo=True, maxundo=200)
    style_text(app.note_text)
    app.note_text.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(card, orient="vertical", command=app.note_text.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    app.note_text.configure(yscrollcommand=scroll.set)
    app.note_text.bind("<<Modified>>", app.on_scratchpad_modified)

    ttk.Label(
        card,
        text="Typed notes are saved with the session. 'Line → task' uses the selection "
             "or the line under the cursor.",
        style="Hint.TLabel",
        wraplength=320,
        justify="left",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))


def _build_footer(app, root: ttk.Frame) -> None:
    footer = ttk.Frame(root, padding=(12, 8, 12, 10))
    footer.grid(row=3, column=0, sticky="ew")

    ttk.Button(footer, text="Save", style="Toolbar.TButton",
               command=app.save_state).pack(side="left", padx=(0, 4))
    ttk.Button(footer, text="Open…", style="Toolbar.TButton",
               command=app.load_state_dialog).pack(side="left", padx=(0, 4))
    ttk.Button(footer, text="Export…", style="Toolbar.TButton",
               command=app.export_state).pack(side="left", padx=(0, 4))
    ttk.Button(footer, text="Undo", style="Toolbar.TButton",
               command=app.undo).pack(side="left")

    ttk.Label(footer, textvariable=app.status_var, style="Sub.TLabel").pack(side="right")
    ttk.Label(footer, textvariable=app.counts_var, style="Sub.TLabel").pack(
        side="right", padx=(0, 14)
    )

    separator = tk.Frame(root, height=1, background=PALETTE["border"])
    separator.grid(row=3, column=0, sticky="new")
