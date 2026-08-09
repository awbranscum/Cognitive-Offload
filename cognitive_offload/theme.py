"""Design tokens and ttk styles, ported from shadcn/ui's zinc theme.

shadcn is a React/Tailwind library, so none of its code can be used here
directly. What carries over is the system: the same token names and colour
values, the same radius and type scale, and the same component variants
(default / secondary / outline / ghost / destructive). The result is a
tkinter app that reads like a shadcn page rather than a 1997 Tk dialog.

Everything is driven by :class:`Tokens`, so light and dark are the same code
with different values.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import font as tkfont
from tkinter import ttk

RADIUS_PILL = 999  # shadcn badges are fully rounded


@dataclass(frozen=True)
class Tokens:
    """The shadcn CSS custom properties, as hex."""

    name: str
    background: str        # the page
    foreground: str
    card: str              # raised surfaces
    card_foreground: str
    muted: str
    muted_foreground: str
    border: str
    input: str
    primary: str
    primary_foreground: str
    secondary: str
    secondary_foreground: str
    accent: str
    accent_foreground: str
    destructive: str
    destructive_foreground: str
    ring: str
    success: str
    warning: str
    selected: str          # selected row
    hover: str             # hovered row
    quadrants: dict = field(default_factory=dict)
    badges: dict = field(default_factory=dict)


# zinc, --radius 0.5rem. Page sits on muted so white cards read as raised.
LIGHT = Tokens(
    name="light",
    background="#f4f4f5",
    foreground="#09090b",
    card="#ffffff",
    card_foreground="#09090b",
    muted="#f4f4f5",
    muted_foreground="#63636b",  # 5.4:1 on the page, 6.0:1 on a card
    border="#d9d9de",
    input="#d4d4d8",
    primary="#18181b",
    primary_foreground="#fafafa",
    secondary="#f4f4f5",
    secondary_foreground="#18181b",
    accent="#f4f4f5",
    accent_foreground="#18181b",
    destructive="#dc2626",
    destructive_foreground="#fafafa",
    ring="#18181b",  # shadcn zinc's own ring; 17.7:1 on card, a real ring
    success="#15803d",
    warning="#b45309",
    selected="#dbe6f5",  # visible against the card and every quadrant tint
    hover="#f1f1f3",
    quadrants={
        "do_first": "#fef2f2",
        "schedule": "#eff6ff",
        "delegate": "#fefce8",
        "eliminate": "#fafafa",
    },
    badges={
        "urgent": ("#fee2e2", "#b91c1c"),
        "deadline": ("#ffedd5", "#c2410c"),
        "admin": ("#e0e7ff", "#4338ca"),
        "creative": ("#dcfce7", "#15803d"),
        "ready": ("#f4f4f5", "#3f3f46"),
        "booked": ("#fef3c7", "#92400e"),
        "today": ("#fde68a", "#78350f"),
        "tag": ("#f4f4f5", "#71717a"),
        "done": ("#f4f4f5", "#64646c"),  # 5.3:1; was 2.3:1 and unreadable
        "pinned": ("#e0f2fe", "#075985"),  # sky pair, 6.6:1
        "estimate": ("#f4f4f5", "#71717a"),  # same quiet pair as "tag":
        # a guess is information, not a signal.
    },
)

DARK = Tokens(
    name="dark",
    background="#09090b",
    foreground="#fafafa",
    card="#141417",
    card_foreground="#fafafa",
    muted="#27272a",
    muted_foreground="#a1a1aa",
    border="#2c2c31",
    input="#3f3f46",
    primary="#fafafa",
    primary_foreground="#18181b",
    secondary="#27272a",
    secondary_foreground="#fafafa",
    accent="#27272a",
    accent_foreground="#fafafa",
    destructive="#f87171",
    destructive_foreground="#1c1917",
    ring="#d4d4d8",  # 12.4:1 on the dark card
    success="#4ade80",
    warning="#fbbf24",
    selected="#2c3542",
    hover="#1f1f24",
    quadrants={
        "do_first": "#241618",
        "schedule": "#121c2b",
        "delegate": "#231f12",
        "eliminate": "#1a1a1d",
    },
    badges={
        "urgent": ("#3f1d1d", "#fca5a5"),
        "deadline": ("#3a2712", "#fdba74"),
        "admin": ("#1e1b4b", "#a5b4fc"),
        "creative": ("#14321f", "#86efac"),
        "ready": ("#27272a", "#d4d4d8"),
        "booked": ("#3a2f12", "#fcd34d"),
        "today": ("#4a3a12", "#fde68a"),
        "tag": ("#27272a", "#a1a1aa"),
        "done": ("#27272a", "#9a9aa2"),  # 5.3:1; was 3.1:1
        "pinned": ("#0c2f42", "#7dd3fc"),  # sky pair, 8.4:1
        "estimate": ("#27272a", "#a1a1aa"),  # same quiet pair as "tag"
    },
)

THEMES = {"light": LIGHT, "dark": DARK}

_current: Tokens = LIGHT
_family: str = "Helvetica"

# shadcn's type scale, in Tk point sizes.
SIZE_XS, SIZE_SM, SIZE_BASE, SIZE_LG, SIZE_XL, SIZE_2XL, SIZE_TIMER = 8, 9, 10, 12, 15, 19, 34


def tokens() -> Tokens:
    return _current


def font(size: int = SIZE_BASE, weight: str = "normal") -> tuple:
    return (_family, size, weight)


def _pick_family(root: tk.Misc) -> str:
    """Closest available match to shadcn's Inter stack."""
    try:
        available = {name.lower(): name for name in tkfont.families(root)}
    except tk.TclError:
        return "Helvetica"
    for wanted in ("Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans",
                   "Liberation Sans", "Helvetica", "Arial"):
        if wanted.lower() in available:
            return available[wanted.lower()]
    return "Helvetica"


def apply_theme(root: tk.Misc, name: str = "light") -> Tokens:
    """Install the ttk styles for a theme and remember it as current."""
    global _current, _family
    _current = THEMES.get(name, LIGHT)
    t = _current
    _family = _pick_family(root)

    style = ttk.Style(root)
    for base in ("clam", "alt", "default"):
        try:
            style.theme_use(base)
            break
        except tk.TclError:
            continue

    root.configure(background=t.background)

    # Flat everything: clam's bevels are what make Tk look dated, and they are
    # drawn with lightcolor/darkcolor, so matching them to the fill kills them.
    style.configure(
        ".",
        background=t.background,
        foreground=t.foreground,
        fieldbackground=t.card,
        bordercolor=t.border,
        lightcolor=t.background,
        darkcolor=t.background,
        troughcolor=t.muted,
        focuscolor=t.ring,
        font=font(),
        relief="flat",
        borderwidth=0,
    )

    style.configure("TFrame", background=t.background)
    style.configure("Card.TFrame", background=t.card)
    style.configure("Muted.TFrame", background=t.muted)

    style.configure("TLabel", background=t.background, foreground=t.foreground, font=font())
    style.configure("Card.TLabel", background=t.card, foreground=t.card_foreground, font=font())
    style.configure("H1.TLabel", background=t.background, foreground=t.foreground,
                    font=font(SIZE_2XL, "bold"))
    style.configure("H2.TLabel", background=t.card, foreground=t.card_foreground,
                    font=font(SIZE_LG, "bold"))
    style.configure("CardTitle.TLabel", background=t.card, foreground=t.card_foreground,
                    font=font(SIZE_BASE, "bold"))
    style.configure("Muted.TLabel", background=t.background, foreground=t.muted_foreground,
                    font=font(SIZE_SM))
    style.configure("CardMuted.TLabel", background=t.card, foreground=t.muted_foreground,
                    font=font(SIZE_SM))
    style.configure("Timer.TLabel", background=t.card, foreground=t.card_foreground,
                    font=font(SIZE_TIMER, "bold"))
    style.configure("Lead.TLabel", background=t.card, foreground=t.card_foreground,
                    font=font(SIZE_LG, "bold"))
    style.configure("Link.TLabel", background=t.background, foreground=t.muted_foreground,
                    font=font(SIZE_SM))
    # The day's positive evidence — the non-shaming replacement for streaks —
    # should not be typographically identical to the bookkeeping counts
    # beside it. A quiet success tint, no scoreboard for what's missing.
    style.configure("DoneToday.TLabel",
                    background=t.badges["creative"][0],
                    foreground=t.badges["creative"][1],
                    padding=(8, 2), font=font(SIZE_SM, "bold"))

    _button_variants(style, t)

    style.configure("TEntry", fieldbackground=t.card, foreground=t.foreground,
                    bordercolor=t.input, insertcolor=t.foreground, padding=6, relief="flat",
                    selectbackground=t.selected, selectforeground=t.foreground)
    style.map("TEntry", bordercolor=[("focus", t.ring)])
    style.configure("TCombobox", fieldbackground=t.card, background=t.card,
                    foreground=t.foreground, bordercolor=t.input, arrowcolor=t.muted_foreground,
                    padding=4, relief="flat",
                    selectbackground=t.selected, selectforeground=t.foreground)
    style.map("TCombobox",
              fieldbackground=[("disabled", t.muted), ("readonly", t.card)],
              foreground=[("disabled", t.muted_foreground)],
              background=[("readonly", t.card)],
              bordercolor=[("focus", t.ring)])
    style.configure("TSpinbox", fieldbackground=t.card, foreground=t.foreground,
                    bordercolor=t.input, arrowcolor=t.muted_foreground, padding=4, relief="flat")
    # The spinbox sets the session length — the one place a keyboard user
    # must not lose the focus ring.
    style.map("TSpinbox",
              bordercolor=[("focus", t.ring)],
              fieldbackground=[("disabled", t.muted)],
              foreground=[("disabled", t.muted_foreground)])
    style.map("TEntry",
              fieldbackground=[("disabled", t.muted)],
              foreground=[("disabled", t.muted_foreground)])

    for suffix, bg in (("TCheckbutton", t.background), ("Card.TCheckbutton", t.card)):
        style.configure(suffix, background=bg, foreground=t.foreground,
                        indicatorcolor=t.card, indicatorbackground=t.card,
                        indicatorforeground=t.primary_foreground,
                        upperbordercolor=t.input, lowerbordercolor=t.input,
                        font=font(SIZE_SM))
        style.map(
            suffix,
            background=[("active", bg)],
            # Tick and indicator must move together, or the mark is drawn in
            # the foreground colour on top of a same-coloured box.
            indicatorcolor=[("selected", t.primary), ("disabled", t.muted)],
            indicatorforeground=[("selected", t.primary_foreground)],
            upperbordercolor=[("selected", t.primary)],
            lowerbordercolor=[("selected", t.primary)],
        )
    # Dialog bodies sit on the page background, not on a card.
    for suffix, bg in (("TRadiobutton", t.background), ("Card.TRadiobutton", t.card)):
        style.configure(suffix, background=bg, foreground=t.foreground, font=font(),
                        indicatorcolor=t.card, indicatorbackground=t.card,
                        upperbordercolor=t.input, lowerbordercolor=t.input)
        style.map(suffix, background=[("active", bg)],
                  indicatorcolor=[("selected", t.primary)],
                  upperbordercolor=[("selected", t.primary)],
                  lowerbordercolor=[("selected", t.primary)])

    # Tabs, shadcn style: a muted pill container, the active tab a raised card.
    style.configure("TNotebook", background=t.background, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", background=t.muted, foreground=t.muted_foreground,
                    padding=(16, 8), borderwidth=0, font=font(SIZE_BASE, "bold"))
    style.map("TNotebook.Tab",
              # Selected first — first matching state wins — then hover:
              # the cheapest possible "this is clickable" signal.
              background=[("selected", t.card), ("active", t.accent)],
              foreground=[("selected", t.foreground), ("active", t.foreground)],
              expand=[("selected", (0, 0, 0, 0))])

    style.configure("TProgressbar", background=t.primary, troughcolor=t.muted,
                    bordercolor=t.muted, lightcolor=t.primary, darkcolor=t.primary,
                    thickness=6)
    style.configure("Vertical.TScrollbar", background=t.border, troughcolor=t.card,
                    bordercolor=t.card, arrowcolor=t.muted_foreground, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", t.muted_foreground)])
    style.configure("TSeparator", background=t.border)

    # The combobox popdown is a plain Tk listbox living in its own toplevel,
    # so ttk styles never reach it - without this it stays white-on-white in
    # dark mode.
    root.option_add("*TCombobox*Listbox.background", t.card)
    root.option_add("*TCombobox*Listbox.foreground", t.foreground)
    root.option_add("*TCombobox*Listbox.selectBackground", t.selected)
    root.option_add("*TCombobox*Listbox.selectForeground", t.foreground)
    root.option_add("*TCombobox*Listbox.font", font())
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.highlightThickness", 1)
    root.option_add("*TCombobox*Listbox.highlightBackground", t.border)

    return t


def _button_variants(style: ttk.Style, t: Tokens) -> None:
    """The shadcn button variants, each in a default and a compact size."""

    def variant(name: str, bg: str, fg: str, hover_bg: str, hover_fg: str,
                border: str, width: int = 0) -> None:
        for suffix, padding, size in (("", (14, 8), SIZE_BASE), ("Sm", (10, 5), SIZE_SM)):
            full = f"{suffix}{name}" if suffix else name
            style.configure(
                full,
                background=bg, foreground=fg, bordercolor=border,
                lightcolor=bg, darkcolor=bg,
                borderwidth=width,
                # clam only paints a border for a non-flat relief, so the
                # outline variants would otherwise read as bare text.
                relief="solid" if width else "flat",
                font=font(size, "bold"), padding=padding,
            )
            style.map(
                full,
                background=[("active", hover_bg), ("disabled", t.muted)],
                foreground=[("active", hover_fg), ("disabled", t.muted_foreground)],
                lightcolor=[("active", hover_bg)], darkcolor=[("active", hover_bg)],
                bordercolor=[("active", t.ring)],
            )

    variant("TButton", t.secondary, t.secondary_foreground, t.accent, t.accent_foreground, t.border)
    variant("Default.TButton", t.primary, t.primary_foreground,
            t.foreground, t.primary_foreground, t.primary)
    variant("Secondary.TButton", t.secondary, t.secondary_foreground,
            t.accent, t.accent_foreground, t.border)
    variant("Outline.TButton", t.card, t.foreground, t.accent, t.accent_foreground, t.border, 1)
    variant("Ghost.TButton", t.card, t.muted_foreground, t.accent, t.foreground, t.card)
    # Same variant, for the ones that sit on the page rather than on a card.
    variant("PageGhost.TButton", t.background, t.muted_foreground,
            t.accent, t.foreground, t.background)
    variant("Destructive.TButton", t.card, t.destructive,
            t.destructive, t.destructive_foreground, t.border, 1)


def style_text(widget: tk.Text, muted: bool = False) -> None:
    t = _current
    widget.configure(
        background=t.card,
        foreground=t.muted_foreground if muted else t.card_foreground,
        insertbackground=t.foreground,
        selectbackground=t.selected,
        selectforeground=t.foreground,
        highlightthickness=1,
        highlightbackground=t.border,
        highlightcolor=t.ring,
        borderwidth=0,
        padx=10,
        pady=8,
        font=font(),
    )



def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """A rounded rectangle as a smoothed polygon (Tk has no native one)."""
    radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=12, **kwargs)
