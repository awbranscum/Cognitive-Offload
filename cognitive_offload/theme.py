"""Colours and ttk styles.

Kept in one place so the two tabs cannot drift apart visually (the old matrix
tab hard-coded its own background colours on plain ``tk`` widgets, which only
lined up with the rest of the app by accident).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTE = {
    "bg": "#f5f6f8",
    "card": "#ffffff",
    "text": "#1f2430",
    "muted": "#5b6472",
    "accent": "#2f6fd0",
    "accent_soft": "#e8f0fc",
    "danger": "#c0392b",
    "done": "#8a94a3",
    "border": "#d8dce3",
    "select": "#dce8fb",
}

QUADRANT_COLORS = {
    "do_first": "#fdecec",
    "schedule": "#e9efff",
    "delegate": "#fdf6e3",
    "eliminate": "#f0f1f3",
}

FONT = "Helvetica"
BASE_FONT = (FONT, 10)
BOLD_FONT = (FONT, 10, "bold")
MONO_FONT = ("Consolas", 10)


def apply_theme(root: tk.Misc) -> None:
    style = ttk.Style(root)
    for theme in ("clam", "alt", "default"):
        try:
            style.theme_use(theme)
            break
        except tk.TclError:
            continue

    bg, card, text, muted = PALETTE["bg"], PALETTE["card"], PALETTE["text"], PALETTE["muted"]
    accent, border = PALETTE["accent"], PALETTE["border"]

    root.configure(background=bg)

    style.configure(".", background=bg, foreground=text, font=BASE_FONT)
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card, relief="flat")
    style.configure("TLabel", background=bg, foreground=text)
    style.configure("Header.TLabel", font=(FONT, 17, "bold"), background=bg)
    style.configure("Sub.TLabel", font=(FONT, 9), background=bg, foreground=muted)
    style.configure("Hint.TLabel", font=(FONT, 9), background=bg, foreground=muted)
    style.configure("Link.TLabel", background=bg, foreground=accent)
    style.configure("Timer.TLabel", font=(FONT, 26, "bold"), background=bg, foreground=text)
    style.configure("Quadrant.TLabel", font=(FONT, 13, "bold"), background=bg)

    style.configure("TButton", padding=(10, 5))
    style.map(
        "TButton",
        background=[("active", PALETTE["accent_soft"])],
        foreground=[("disabled", muted)],
    )
    style.configure("Accent.TButton", padding=(12, 5), foreground="#ffffff", background=accent)
    style.map("Accent.TButton", background=[("active", "#255ab0"), ("disabled", border)])
    style.configure("Danger.TButton", padding=(10, 5), foreground=PALETTE["danger"])
    style.configure("Toolbar.TButton", padding=(8, 4))

    style.configure("TLabelframe", background=bg, bordercolor=border, relief="solid", borderwidth=1)
    style.configure("Card.TLabelframe", background=bg, padding=10, bordercolor=border)
    style.configure("Card.TLabelframe.Label", background=bg, foreground=muted, font=BOLD_FONT)

    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 7), font=BASE_FONT)
    style.map(
        "TNotebook.Tab",
        background=[("selected", card)],
        foreground=[("selected", accent)],
    )

    style.configure("TEntry", fieldbackground=card, bordercolor=border, padding=4)
    style.configure("TCombobox", fieldbackground=card, padding=3)
    style.configure("TCheckbutton", background=bg)
    style.configure("TRadiobutton", background=bg)
    style.configure("TSpinbox", fieldbackground=card, padding=3)
    style.configure("Vertical.TScrollbar", background=bg, troughcolor=bg, bordercolor=border)


def style_listbox(listbox: tk.Listbox, background: str | None = None) -> None:
    """Apply the palette to a classic ``tk.Listbox`` (ttk has no equivalent)."""
    listbox.configure(
        background=background or PALETTE["card"],
        foreground=PALETTE["text"],
        selectbackground=PALETTE["select"],
        selectforeground=PALETTE["text"],
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
        borderwidth=0,
        activestyle="none",
        font=BASE_FONT,
    )


def style_text(widget: tk.Text) -> None:
    widget.configure(
        background=PALETTE["card"],
        foreground=PALETTE["text"],
        insertbackground=PALETTE["text"],
        selectbackground=PALETTE["select"],
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
        borderwidth=0,
        padx=6,
        pady=6,
        font=BASE_FONT,
    )
