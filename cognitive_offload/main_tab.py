"""Layout for the main "capture and start" tab.

Structured the way a shadcn dashboard is: a page header, a row of cards, and
a two-column body. The controls that matter for starting sit at the top of
the task card; the filtering machinery sits below it and folds away entirely
in Calm mode.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme
from .models import KIND_LABELS
from .queries import ALL_KINDS, SORT_ORDERS
from .theme import font, style_text, tokens
from .widgets import MomentumStrip, RowList


def build_main_tab(app, root: ttk.Frame) -> None:
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)

    _build_header(app, root)
    _build_top_row(app, root)
    _build_body(app, root)
    _build_footer(app, root)


def card(parent, title: str = "", description: str = "") -> tk.Frame:
    """A shadcn card: a bordered surface with optional title and description.

    The border is a 1px outer frame rather than a widget border, because
    clam's borders are bevelled and no amount of styling makes them flat.
    """
    outer = tk.Frame(parent, background=tokens().border, highlightthickness=0)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=14)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    outer.inner = inner
    if title:
        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
    if description:
        ttk.Label(inner, text=description, style="CardMuted.TLabel",
                  wraplength=440, justify="left").pack(anchor="w", pady=(1, 0))
    return outer


def _build_header(app, root: ttk.Frame) -> None:
    header = ttk.Frame(root, padding=(16, 14, 16, 6))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)

    left = ttk.Frame(header)
    left.grid(row=0, column=0, sticky="w")
    ttk.Label(left, text="Cognitive Offload", style="H1.TLabel").pack(anchor="w")
    ttk.Label(left, text="Get it out of your head, then start one small thing.",
              style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

    right = ttk.Frame(header)
    right.grid(row=0, column=1, sticky="e")
    app.theme_button = ttk.Button(right, text="Dark", style="SmOutline.TButton",
                                  command=app.toggle_theme)
    app.theme_button.pack(side="right")
    ttk.Checkbutton(right, text="Calm mode", variable=app.calm_var,
                    command=app.apply_calm_mode).pack(side="right", padx=(0, 12))
    ttk.Button(right, text="Shortcuts", style="SmGhost.TButton",
               command=app.show_shortcuts).pack(side="right", padx=(0, 6))

    path_row = ttk.Frame(header)
    path_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    app.path_label = ttk.Label(path_row, textvariable=app.path_var, style="Link.TLabel",
                               cursor="hand2")
    app.path_label.pack(side="left")
    app.path_label.bind("<Button-1>", lambda _e: app.copy_session_path())
    ttk.Button(path_row, text="Change folder", style="SmGhost.TButton",
               command=app.change_db_folder).pack(side="left", padx=(8, 0))
    app.header_extras = path_row


def _build_top_row(app, root: ttk.Frame) -> None:
    top = ttk.Frame(root, padding=(16, 8, 16, 0))
    top.grid(row=1, column=0, sticky="ew")
    top.columnconfigure(0, weight=3, uniform="top")
    top.columnconfigure(1, weight=2, uniform="top")

    _build_capture_card(app, top)
    _build_focus_card(app, top)


def _build_capture_card(app, top: ttk.Frame) -> None:
    outer = card(top, "Quick capture", "Anything in your head — it does not have to be tidy.")
    outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    body = outer.inner

    entry_row = ttk.Frame(body, style="Card.TFrame")
    entry_row.pack(fill="x", pady=(12, 8))
    entry_row.columnconfigure(0, weight=1)
    app.capture_entry = ttk.Entry(entry_row, font=font(theme.SIZE_LG))
    app.capture_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=3)
    app.capture_entry.bind("<Return>", lambda _e: app.add_task_from_capture())
    app.capture_entry.bind("<Control-Return>", lambda _e: app.add_note_from_capture())
    ttk.Button(entry_row, text="Add task", style="Default.TButton",
               command=app.add_task_from_capture).grid(row=0, column=1)
    ttk.Button(entry_row, text="To scratchpad", style="Outline.TButton",
               command=app.add_note_from_capture).grid(row=0, column=2, padx=(6, 0))

    ttk.Label(body, text="Enter files it as a task · Ctrl+Enter drops it in the scratchpad",
              style="CardMuted.TLabel").pack(anchor="w")


def _build_focus_card(app, top: ttk.Frame) -> None:
    outer = card(top, "Focus session")
    outer.grid(row=0, column=1, sticky="nsew")
    body = outer.inner

    app.focus_task_label = ttk.Label(
        body, textvariable=app.focus_task_var, style="CardMuted.TLabel",
        anchor="center", justify="center", wraplength=300,
    )
    app.focus_task_label.pack(fill="x", pady=(12, 0))

    app.timer_label = ttk.Label(body, text="15:00", style="Timer.TLabel", anchor="center")
    app.timer_label.pack(fill="x")

    app.timer_progress = ttk.Progressbar(body, mode="determinate", maximum=1000)
    app.timer_progress.pack(fill="x", pady=(2, 12))

    controls = ttk.Frame(body, style="Card.TFrame")
    controls.pack(fill="x")
    controls.columnconfigure(2, weight=1)
    controls.columnconfigure(3, weight=1)
    ttk.Label(controls, text="Min", style="CardMuted.TLabel").grid(row=0, column=0, padx=(0, 4))
    app.work_minutes = tk.IntVar(value=15)
    ttk.Spinbox(controls, from_=1, to=240, width=4, textvariable=app.work_minutes,
                command=app.on_timer_minutes_changed).grid(row=0, column=1, padx=(0, 8))
    app.timer_button = ttk.Button(controls, text="Start", style="SmDefault.TButton",
                                  command=app.toggle_timer)
    app.timer_button.grid(row=0, column=2, sticky="ew", padx=(0, 6))
    ttk.Button(controls, text="Reset", style="SmOutline.TButton",
               command=app.reset_timer).grid(row=0, column=3, sticky="ew", padx=(0, 6))
    ttk.Button(controls, text="Pop out", style="SmGhost.TButton",
               command=app.open_focus_window).grid(row=0, column=4)


def _build_body(app, root: ttk.Frame) -> None:
    body = ttk.Frame(root, padding=(16, 12, 16, 0))
    body.grid(row=2, column=0, sticky="nsew")
    body.columnconfigure(0, weight=3, uniform="cols")
    body.columnconfigure(1, weight=2, uniform="cols")
    body.rowconfigure(0, weight=1)

    _build_tasks_card(app, body)
    _build_scratchpad_card(app, body)


def _build_tasks_card(app, body: ttk.Frame) -> None:
    outer = card(body)
    outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    inner = outer.inner
    inner.columnconfigure(0, weight=1)
    inner.rowconfigure(4, weight=1)

    heading = ttk.Frame(inner, style="Card.TFrame")
    heading.grid(row=0, column=0, sticky="ew")
    ttk.Label(heading, text="Active stack", style="CardTitle.TLabel").pack(side="left")
    ttk.Label(heading, textvariable=app.counts_var, style="CardMuted.TLabel").pack(side="right")

    # The way in when the list itself is the thing you cannot face.
    start_row = ttk.Frame(inner, style="Card.TFrame")
    start_row.grid(row=1, column=0, sticky="ew", pady=(10, 10))
    ttk.Button(start_row, text="Where do I start?", style="Default.TButton",
               command=app.start_here).pack(side="left")
    ttk.Button(start_row, text="Focus on selected", style="Outline.TButton",
               command=app.focus_on_selected).pack(side="left", padx=(6, 0))
    app.due_label = ttk.Label(start_row, textvariable=app.due_var, style="CardMuted.TLabel",
                              cursor="hand2")
    app.due_label.pack(side="left", padx=(12, 0))
    app.due_label.bind("<Button-1>", lambda _e: app.show_booked())

    search_row = ttk.Frame(inner, style="Card.TFrame")
    search_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    search_row.columnconfigure(0, weight=1)
    app.search_entry = ttk.Entry(search_row, textvariable=app.search_var)
    app.search_entry.grid(row=0, column=0, sticky="ew")
    app.search_entry.bind("<KeyRelease>", lambda _e: app.refresh_tasks())
    app.search_entry.bind("<Escape>", lambda _e: app.clear_search())
    ttk.Button(search_row, text="Clear", style="SmGhost.TButton",
               command=app.clear_search).grid(row=0, column=1, padx=(6, 0))
    app.search_row = search_row

    filters = ttk.Frame(inner, style="Card.TFrame")
    filters.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    kind_combo = ttk.Combobox(
        filters, textvariable=app.kind_filter_var,
        values=[ALL_KINDS] + [label for key, label in KIND_LABELS.items() if key],
        width=12, state="readonly",
    )
    kind_combo.pack(side="left", padx=(0, 6))
    kind_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())

    app.tag_filter_combo = ttk.Combobox(filters, textvariable=app.tag_filter_var,
                                        width=9, state="readonly")
    app.tag_filter_combo.pack(side="left", padx=(0, 6))
    app.tag_filter_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())

    sort_combo = ttk.Combobox(filters, textvariable=app.sort_var, values=list(SORT_ORDERS),
                              width=10, state="readonly")
    sort_combo.pack(side="left")
    sort_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())
    ttk.Checkbutton(filters, text="Show done", variable=app.show_done_var,
                    style="Card.TCheckbutton", command=app.refresh_tasks).pack(
        side="left", padx=(8, 0))
    app.filter_row = filters

    app.task_list = RowList(
        inner,
        on_activate=app.edit_selected_details,
        on_toggle=app.toggle_selected_done,
        on_delete=app.delete_selected,
        on_select=app.on_task_selection_changed,
        empty_text="Nothing here. Capture a thought above — or take the win and stop.",
    )
    app.task_list.grid(row=4, column=0, sticky="nsew")

    toolbar = ttk.Frame(inner, style="Card.TFrame")
    toolbar.grid(row=5, column=0, sticky="ew", pady=(8, 0))
    for column in range(4):
        toolbar.columnconfigure(column, weight=1, uniform="tools")
    rows = [
        [("Done", app.toggle_selected_done, "SmOutline.TButton"),
         ("Priority", app.toggle_selected_priority, "SmOutline.TButton"),
         ("Tag", app.tag_selected, "SmOutline.TButton"),
         ("Edit", app.edit_selected_details, "SmOutline.TButton")],
        [("Move to top", app.promote_selected, "SmGhost.TButton"),
         ("To matrix", app.send_selected_to_matrix, "SmGhost.TButton"),
         ("Delete", app.delete_selected, "SmDestructive.TButton")],
    ]
    for row_index, row in enumerate(rows):
        for column, (label, command, style) in enumerate(row):
            ttk.Button(toolbar, text=label, style=style, command=command).grid(
                row=row_index, column=column, sticky="ew", padx=(0, 4), pady=(0, 4))
    app.task_toolbar = toolbar

    ttk.Button(inner, text="Clear completed", style="SmGhost.TButton",
               command=app.clear_completed).grid(row=6, column=0, sticky="w", pady=(6, 0))


def _build_scratchpad_card(app, body: ttk.Frame) -> None:
    outer = card(body)
    outer.grid(row=0, column=1, sticky="nsew")
    inner = outer.inner
    inner.columnconfigure(0, weight=1)
    inner.rowconfigure(2, weight=1)

    heading = ttk.Frame(inner, style="Card.TFrame")
    heading.grid(row=0, column=0, columnspan=2, sticky="ew")
    ttk.Label(heading, text="Scratchpad", style="CardTitle.TLabel").pack(side="left")
    ttk.Label(heading, text="saved with the session", style="CardMuted.TLabel").pack(side="right")

    buttons = ttk.Frame(inner, style="Card.TFrame")
    buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 8))
    ttk.Button(buttons, text="Line → task", style="SmOutline.TButton",
               command=app.send_scratch_line_to_tasks).pack(side="left", padx=(0, 4))
    ttk.Button(buttons, text="All → tasks", style="SmGhost.TButton",
               command=app.brain_dump_into_tasks).pack(side="left", padx=(0, 4))
    ttk.Button(buttons, text="Clear", style="SmDestructive.TButton",
               command=app.clear_notes).pack(side="left")

    app.note_text = tk.Text(inner, wrap="word", height=16, undo=True, maxundo=200)
    style_text(app.note_text)
    app.note_text.grid(row=2, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(inner, orient="vertical", command=app.note_text.yview)
    scroll.grid(row=2, column=1, sticky="ns")
    app.note_text.configure(yscrollcommand=scroll.set)
    app.note_text.bind("<<Modified>>", app.on_scratchpad_modified)


def _build_footer(app, root: ttk.Frame) -> None:
    footer = ttk.Frame(root, padding=(16, 10, 16, 12))
    footer.grid(row=3, column=0, sticky="ew")

    for label, command in (("Save", app.save_state), ("Open", app.load_state_dialog),
                           ("Export", app.export_state), ("Undo", app.undo)):
        ttk.Button(footer, text=label, style="SmGhost.TButton", command=command).pack(
            side="left", padx=(0, 4))

    ttk.Label(footer, textvariable=app.status_var, style="Muted.TLabel").pack(side="right")
    ttk.Label(footer, textvariable=app.momentum_var, style="Muted.TLabel").pack(
        side="right", padx=(0, 14))
    app.momentum_strip = MomentumStrip(footer, days=14, on_hover=app.on_momentum_hover,
                                       surface="background")
    app.momentum_strip.pack(side="right", padx=(0, 10))
