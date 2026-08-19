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
from .presenter import NOTHING_HERE
from .queries import ALL_KINDS, SORT_ORDERS
from .theme import font, px, style_text, tokens
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
                  wraplength=px(inner, 440), justify="left").pack(anchor="w", pady=(1, 0))
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
    ttk.Button(right, text="Shortcuts", style="SmPageGhost.TButton",
               command=app.show_shortcuts).pack(side="right", padx=(0, 6))

    path_row = ttk.Frame(header)
    path_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    app.path_label = ttk.Label(path_row, textvariable=app.path_var, style="Link.TLabel",
                               cursor="hand2")
    app.path_label.pack(side="left")
    app.path_label.bind("<Button-1>", lambda _e: app.copy_session_path())
    ttk.Button(path_row, text="Change folder", style="SmPageGhost.TButton",
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
    # "new", not "nsew": stretched to the focus card's height, the capture
    # card was mostly a blank slab — dead space where the task list wants
    # to be.
    outer.grid(row=0, column=0, sticky="new", padx=(0, 10))
    body = outer.inner

    entry_row = ttk.Frame(body, style="Card.TFrame")
    entry_row.pack(fill="x", pady=(8, 6))
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
        anchor="center", justify="center", wraplength=px(body, 300),
    )
    app.focus_task_label.pack(fill="x", pady=(6, 0))

    app.timer_label = ttk.Label(body, text="15:00", style="Timer.TLabel", anchor="center")
    app.timer_label.pack(fill="x")

    app.timer_progress = ttk.Progressbar(body, mode="determinate", maximum=1000)
    app.timer_progress.pack(fill="x", pady=(2, 2))
    ttk.Label(body, textvariable=app.finish_var, style="CardMuted.TLabel",
              anchor="center").pack(fill="x", pady=(0, 6))

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
    body = ttk.Frame(root, padding=(16, 8, 16, 0))
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
    # The list flexes. The minsize only binds when the window is squeezed,
    # and there it is a trade against the toolbar below: 55 keeps one task
    # row AND the whole toolbar inside the card at the window's minimum
    # size with a session running (the worst legitimate state). Grid does
    # not shrink fixed rows — whatever exceeds the card is clipped, so the
    # floor budget has to actually add up.
    inner.rowconfigure(4, weight=1, minsize=55)

    heading = ttk.Frame(inner, style="Card.TFrame")
    heading.grid(row=0, column=0, sticky="ew")
    ttk.Label(heading, text="Active stack", style="CardTitle.TLabel").pack(side="left")
    ttk.Label(heading, textvariable=app.counts_var, style="CardMuted.TLabel").pack(side="right")
    # Sits by the counts rather than in the button row, which runs out of width.
    app.today_label = ttk.Label(heading, textvariable=app.today_var, style="DoneToday.TLabel",
                                cursor="hand2")
    app.today_label.pack(side="right", padx=(0, 12))
    app.today_label.bind("<Button-1>", lambda _e: app.show_today())

    # Named without being asked: opening the app and being told what to start
    # is one decision instead of two. The 1px border makes the app's single
    # most important element read as one contained unit instead of floating
    # loose between the counts and the search box. app.next_frame is the
    # OUTER frame — refresh_next_up grid_remove()s it whole.
    app.next_frame = tk.Frame(inner, background=tokens().border, highlightthickness=0)
    app.next_frame.grid(row=1, column=0, sticky="ew", pady=(8, 6))
    next_inner = ttk.Frame(app.next_frame, style="Card.TFrame", padding=8)
    next_inner.pack(fill="both", expand=True, padx=1, pady=1)
    next_inner.columnconfigure(0, weight=1)
    app.next_frame.inner = next_inner  # picked up by the theme toggle's border walk

    next_text = ttk.Frame(next_inner, style="Card.TFrame")
    next_text.grid(row=0, column=0, sticky="ew")
    ttk.Label(next_text, text="NEXT UP", style="CardMuted.TLabel").pack(anchor="w")
    # Wraplength follows the column's real width: a fixed number wider
    # than the column makes long titles clip mid-word instead of wrapping
    # — at the window's minimum size the column is ~290px, not 380.
    for var, style_name in ((app.next_title_var, "H2.TLabel"),
                            (app.next_step_var, "CardMuted.TLabel")):
        label = ttk.Label(next_text, textvariable=var, style=style_name,
                          wraplength=380, justify="left")
        label.pack(anchor="w", fill="x")
        label.bind("<Configure>",
                   lambda e: e.widget.configure(wraplength=max(120, e.width)))

    next_buttons = ttk.Frame(next_inner, style="Card.TFrame")
    next_buttons.grid(row=0, column=1, sticky="e", padx=(10, 0))
    ttk.Button(next_buttons, text="Start this", style="Default.TButton",
               command=app.start_next).pack(anchor="e")
    # "Not that one" walks the list; "Not today" excuses the task until
    # tomorrow. The difference matters when the same dreaded task greets
    # you at every launch. Side by side, not stacked: the two escape
    # hatches are peers, and a third button-height here is what pushed
    # the toolbar out of the card at the window's minimum size.
    declines = ttk.Frame(next_buttons, style="Card.TFrame")
    declines.pack(anchor="e", pady=(4, 0))
    ttk.Button(declines, text="Not that one", style="SmGhost.TButton",
               command=app.skip_next).pack(side="left")
    ttk.Button(declines, text="Not today", style="SmGhost.TButton",
               command=app.snooze_next).pack(side="left", padx=(4, 0))

    # The way in when even that is too much of a decision.
    start_row = ttk.Frame(inner, style="Card.TFrame")
    start_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    ttk.Button(start_row, text="Where do I start?", style="Default.TButton",
               command=app.start_here).pack(side="left")
    # Kept in `needs_selection` so they can be greyed while they cannot act:
    # a control that looks live and does nothing is a decision that pays
    # nothing, and this screen used to offer fourteen of them at once.
    app.needs_selection = []
    focus_button = ttk.Button(start_row, text="Focus on selected",
                              style="Outline.TButton",
                              command=app.focus_on_selected)
    focus_button.pack(side="left", padx=(6, 0))
    app.needs_selection.append(focus_button)
    # Done lives here, not in the toolbar: Calm mode hides the toolbar, and
    # hiding the primary verb while keeping Save/Open/Export is backwards.
    done_button = ttk.Button(start_row, text="Done", style="Outline.TButton",
                             command=app.toggle_selected_done)
    done_button.pack(side="left", padx=(6, 0))
    app.needs_selection.append(done_button)
    app.due_label = ttk.Label(start_row, textvariable=app.due_var, style="CardMuted.TLabel",
                              cursor="hand2")
    app.due_label.pack(side="left", padx=(12, 0))
    app.due_label.bind("<Button-1>", lambda _e: app.show_booked())

    # One row for search AND filters: two separate rows cost the task list
    # a whole visible task, and the list is the point of this card.
    filters = ttk.Frame(inner, style="Card.TFrame")
    filters.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    # minsize: the entry flexes, but search must never collapse to nothing
    # at narrow widths — it did, at the window's own minimum size.
    filters.columnconfigure(0, weight=1, minsize=110)
    app.search_entry = ttk.Entry(filters, textvariable=app.search_var)
    app.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    app.search_entry.bind("<KeyRelease>", lambda _e: app.refresh_tasks())
    app.search_entry.bind("<Escape>", lambda _e: app.clear_search() or "break")
    ttk.Button(filters, text="Clear", style="SmGhost.TButton",
               command=app.clear_search).grid(row=0, column=1, padx=(0, 8))

    kind_combo = ttk.Combobox(
        filters, textvariable=app.kind_filter_var,
        values=[ALL_KINDS] + [label for key, label in KIND_LABELS.items() if key],
        width=10, state="readonly",
    )
    kind_combo.grid(row=0, column=2, padx=(0, 4))
    kind_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())

    app.tag_filter_combo = ttk.Combobox(filters, textvariable=app.tag_filter_var,
                                        width=8, state="readonly")
    app.tag_filter_combo.grid(row=0, column=3, padx=(0, 4))
    app.tag_filter_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())

    sort_combo = ttk.Combobox(filters, textvariable=app.sort_var, values=list(SORT_ORDERS),
                              width=9, state="readonly")
    sort_combo.grid(row=0, column=4)
    sort_combo.bind("<<ComboboxSelected>>", lambda _e: app.refresh_tasks())
    ttk.Checkbutton(filters, text="Show done", variable=app.show_done_var,
                    style="Card.TCheckbutton", command=app.refresh_tasks).grid(
        row=0, column=5, padx=(8, 0))
    # Both names survive the merge: calm mode and the tests reach for each.
    app.filter_row = filters
    app.search_row = filters

    app.task_list = RowList(
        inner,
        on_activate=app.edit_selected_details,
        on_toggle=app.toggle_selected_done,
        on_delete=app.delete_selected,
        on_select=app.on_task_selection_changed,
        # The same constant the presenter hands back on every refresh — two
        # copies of one sentence is the drift this branch exists to stop.
        empty_text=NOTHING_HERE,
    )
    app.task_list.grid(row=4, column=0, sticky="nsew")

    # One row, not two: the second row was what clipped off the bottom of
    # the card whenever a running session made the focus card taller.
    toolbar = ttk.Frame(inner, style="Card.TFrame")
    toolbar.grid(row=5, column=0, sticky="ew", pady=(8, 0))
    buttons = [
        ("Priority", app.toggle_selected_priority, "SmOutline.TButton"),
        ("Tag", app.tag_selected, "SmOutline.TButton"),
        ("Edit", app.edit_selected_details, "SmOutline.TButton"),
        ("Pin", app.promote_selected, "SmGhost.TButton"),
        ("To matrix", app.send_selected_to_matrix, "SmGhost.TButton"),
        ("Delete", app.delete_selected, "SmDestructive.TButton"),
        ("Clear done", app.clear_completed, "SmGhost.TButton"),
    ]
    # No uniform group: it would force every column as wide as "Clear
    # done", and seven of those don't fit the card at the window's
    # minimum size. Each column floors at its own label instead.
    for column, (label, command, style) in enumerate(buttons):
        toolbar.columnconfigure(column, weight=1)
        button = ttk.Button(toolbar, text=label, style=style, command=command)
        button.grid(row=0, column=column, sticky="ew",
                    padx=(0, 3) if column < len(buttons) - 1 else 0)
        # "Clear done" acts on the list, not on a selection, so it answers to
        # a different question and is tracked separately.
        if label == "Clear done":
            app.needs_done_task = button
        else:
            app.needs_selection.append(button)
    app.task_toolbar = toolbar


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
        ttk.Button(footer, text=label, style="SmPageGhost.TButton", command=command).pack(
            side="left", padx=(0, 4))

    ttk.Label(footer, textvariable=app.status_var, style="Muted.TLabel").pack(side="right")
    momentum_label = ttk.Label(footer, textvariable=app.momentum_var,
                               style="Muted.TLabel", cursor="hand2")
    momentum_label.bind("<Button-1>", lambda _e: app.show_week())
    momentum_label.pack(
        side="right", padx=(0, 14))
    app.momentum_strip = MomentumStrip(footer, days=14, on_hover=app.on_momentum_hover,
                                       surface="background")
    # The strip is the teaser; the click is the receipts.
    app.momentum_strip.configure(cursor="hand2")
    app.momentum_strip.bind("<Button-1>", lambda _e: app.show_week())
    app.momentum_strip.pack(side="right", padx=(0, 10))
