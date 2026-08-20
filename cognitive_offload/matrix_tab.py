"""Layout for the Eisenhower matrix tab."""

from __future__ import annotations

from tkinter import ttk

from .main_tab import card
from .storage import CATEGORIES, CATEGORY_KEYS
from .theme import px, tokens
from .widgets import RowList

# What each quadrant is actually for. Schedule gets the longest note on
# purpose: important-but-not-urgent work is the stuff that quietly never
# happens, and booking a time is what turns it into something the brain will
# actually respond to.
QUADRANT_ADVICE = {
    "do_first": "Crises and real deadlines. Do these now.",
    "schedule": "The quadrant that decides how your year goes: goals, health, "
                "relationships, the slow important things. They have no deadline to "
                "make you start, so give them one — book a time on each.",
    "delegate": "Loud, but not yours. Hand off, batch, or shrink these — this is "
                "urgency borrowed from someone else's list.",
    "eliminate": "Not urgent, not important. Deleting these is progress, not "
                 "failure — a shorter list is easier to face.",
}


def build_matrix_tab(app, root: ttk.Frame) -> None:
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    header = ttk.Frame(root, padding=(16, 14, 16, 6))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)

    left = ttk.Frame(header)
    left.grid(row=0, column=0, sticky="w")
    ttk.Label(left, text="Eisenhower Matrix", style="H1.TLabel").pack(anchor="w")
    ttk.Label(left, text="Sort by urgency and importance. One quadrant at a time.",
              style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

    right = ttk.Frame(header)
    right.grid(row=0, column=1, sticky="e")
    ttk.Button(right, text="Back to tasks", style="SmOutline.TButton",
               command=lambda: app.notebook.select(0)).pack(side="right")
    ttk.Button(right, text="Refresh", style="SmPageGhost.TButton",
               command=app.refresh_matrix).pack(side="right", padx=(0, 6))

    app.matrix_notebook = ttk.Notebook(root)
    app.matrix_notebook.grid(row=1, column=0, sticky="nsew", padx=16, pady=(6, 6))

    # Under the quadrants, not above them. This was the third element on the
    # tab — a folder path and a button standing between the person and the
    # four boxes they came here for — which is the same demotion the tasks
    # tab got: where the file lives matters once, the quadrants matter every
    # time. Here there is no dead space to slip it into, so it goes to the
    # bottom, where chrome about the surface belongs.
    path_row = ttk.Frame(root, padding=(16, 0, 16, 12))
    path_row.grid(row=2, column=0, sticky="w")
    app.matrix_path_label = ttk.Label(path_row, textvariable=app.matrix_path_var,
                                      style="Link.TLabel")
    app.matrix_path_label.pack(side="left")
    ttk.Button(path_row, text="Change folder", style="SmPageGhost.TButton",
               command=app.change_matrix_db_folder).pack(side="left", padx=(8, 0))

    app.matrix_lists = {}
    app.matrix_count_labels = {}
    app.matrix_needs_selection = {}
    app.matrix_needs_rows = {}
    app.matrix_needs_waiting = {}
    for key in CATEGORY_KEYS:
        _build_quadrant(app, key)


def _build_quadrant(app, key: str) -> None:
    _, short_label, long_label = CATEGORIES[key]
    page = ttk.Frame(app.matrix_notebook, padding=12)
    app.matrix_notebook.add(page, text=short_label)
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)

    outer = card(page)
    outer.grid(row=0, column=0, sticky="nsew")
    inner = outer.inner
    inner.columnconfigure(1, weight=1)
    inner.rowconfigure(2, weight=1)

    heading = ttk.Frame(inner, style="Card.TFrame")
    heading.grid(row=0, column=0, columnspan=2, sticky="ew")
    ttk.Label(heading, text=long_label, style="H2.TLabel").pack(side="left")
    count = ttk.Label(heading, text="", style="CardMuted.TLabel")
    count.pack(side="left", padx=(10, 0))
    app.matrix_count_labels[key] = count

    ttk.Label(inner, text=QUADRANT_ADVICE[key], style="CardMuted.TLabel",
              wraplength=px(inner, 800), justify="left").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

    buttons = ttk.Frame(inner, style="Card.TFrame")
    buttons.grid(row=2, column=0, sticky="nw", padx=(0, 12))
    # Each quadrant's own verb is the primary button: booking in Schedule,
    # handing over in Delegate. "Delegate" is the quadrant most people cannot
    # use, because giving it to someone else needs a someone else — so the
    # button that supplies one leads, rather than sitting among the ghosts.
    # (label, command, style, what it needs before it can act). The last
    # column is stated here, beside the button, rather than in a set of label
    # strings somewhere else: a list of names keyed on other names is the
    # disease this codebase keeps curing, and renaming a button would have
    # quietly dropped it out of the greying.
    actions = [
        ("Add", lambda k=key: app.add_matrix_task(k),
         "Outline.TButton" if key in ("schedule", "delegate") else "Default.TButton",
         ""),
        ("Book a time", lambda k=key: app.book_matrix_time(k),
         "Default.TButton" if key == "schedule" else "Outline.TButton",
         "selection"),
        # The start machinery, reachable from the quadrant where booked work
        # lives — not four manual steps away on the other tab.
        ("Focus on this", lambda k=key: app.focus_matrix_task(k),
         "Outline.TButton", "selection"),
        ("Edit", lambda k=key: app.edit_matrix_task(k), "Ghost.TButton", "selection"),
        ("Move to…", lambda k=key: app.move_matrix_tasks(k), "Ghost.TButton", "selection"),
        ("Send to tasks", lambda k=key: app.matrix_to_tasks(k), "Ghost.TButton",
         "selection"),
        ("Copy all to tasks", lambda k=key: app.copy_matrix_to_tasks(k),
         "Ghost.TButton", "rows"),
        ("Delete", lambda k=key: app.delete_matrix_tasks(k), "Destructive.TButton",
         "selection"),
    ]
    if key == "delegate":
        actions[1:1] = [
            ("Hand off to an agent", lambda k=key: app.hand_off_matrix_task(k),
             "Default.TButton", "selection"),
            # Not just a selection: something has to be OUT with someone for
            # taking it back to mean anything.
            ("Take it back", lambda k=key: app.take_back_matrix_task(k),
             "Ghost.TButton", "waiting"),
        ]
    # The main tab has greyed its selection-dependent controls since the
    # first-run audit; this tab went on offering eleven live controls, four of
    # which answered a click with "Select a task to…". Learning that a button
    # was not for you by pressing it is exactly what
    # `sync_action_availability` exists to stop.
    groups = {"selection": app.matrix_needs_selection.setdefault(key, []),
              "rows": app.matrix_needs_rows.setdefault(key, []),
              "waiting": app.matrix_needs_waiting.setdefault(key, [])}
    for text, command, style, needs in actions:
        button = ttk.Button(buttons, text=text, style=style, command=command)
        button.pack(fill="x", pady=2)
        if needs:
            groups[needs].append(button)

    listing = RowList(
        inner,
        on_activate=lambda k=key: app.edit_matrix_task(k),
        on_select=lambda k=key: app.sync_matrix_action_availability(k),
        on_delete=lambda k=key: app.delete_matrix_tasks(k),
        empty_text="Empty. That is allowed.",
        surface=tokens().quadrants.get(key),
    )
    listing.grid(row=2, column=1, sticky="nsew")
    app.matrix_lists[key] = listing

    ttk.Label(inner, text="Double click to edit · Delete removes · Shift/Ctrl multi-selects",
              style="CardMuted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w",
                                             pady=(10, 0))
