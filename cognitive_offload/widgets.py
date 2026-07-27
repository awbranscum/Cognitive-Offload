"""Custom widgets: shadcn-style badges, a rich row list, and the momentum strip.

The task list used to be a ``tk.Listbox``, which can only draw one line of
plain text per row. Everything about a task — is it ready to start, how does
it feel, is it booked — had to be crammed into that string. These widgets
give each task a real row: a title, its first step underneath, and badges,
so the important parts are visible at a glance instead of parsed out of a
sentence.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk

from . import theme
from .theme import RADIUS_PILL, font, rounded_rect, tokens


@dataclass
class Badge:
    text: str
    variant: str = "tag"  # key into Tokens.badges


@dataclass
class Row:
    """One entry in a :class:`RowList`."""

    id: str
    title: str
    subtitle: str = ""
    badges: list = field(default_factory=list)
    done: bool = False
    flagged: bool = False
    marker: str = ""  # optional leading glyph override

    def as_text(self) -> str:
        """Flat text of the whole row (used by tests and accessibility)."""
        parts = [self.title]
        parts.extend(badge.text for badge in self.badges)
        if self.subtitle:
            parts.append(self.subtitle)
        return "  ".join(parts)


class BadgeStrip(tk.Canvas):
    """A row of small rounded pills, drawn on a canvas.

    ttk has no pill widget and no rounded corners, but a canvas does both,
    and badges are small enough that drawing them by hand is cheap.
    """

    PAD_X, PAD_Y, GAP = 7, 3, 5

    def __init__(self, master, badges: list[Badge], background: str, **kwargs):
        self._badges = badges
        self._background = background
        self._font = font(theme.SIZE_XS, "bold")
        super().__init__(master, highlightthickness=0, borderwidth=0,
                         background=background, height=18, **kwargs)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def set_badges(self, badges: list[Badge], background: str | None = None) -> None:
        self._badges = badges
        if background:
            self._background = background
            self.configure(background=background)
        self._draw()

    def _text_width(self, text: str) -> int:
        from tkinter import font as tkfont

        try:
            return tkfont.Font(font=self._font).measure(text)
        except tk.TclError:
            return 7 * len(text)

    def _draw(self) -> None:
        self.delete("all")
        palette = tokens().badges
        x = 0
        height = 17
        for badge in self._badges:
            fill, fg = palette.get(badge.variant, palette["tag"])
            width = self._text_width(badge.text) + 2 * self.PAD_X
            rounded_rect(self, x, 1, x + width, height, RADIUS_PILL, fill=fill, outline="")
            self.create_text(x + width / 2, (height + 1) / 2, text=badge.text,
                             fill=fg, font=self._font)
            x += width + self.GAP
        self.configure(width=max(1, x))


class RowList(ttk.Frame):
    """Scrollable list of rich rows with Listbox-compatible selection.

    Exposes ``size`` / ``get`` / ``curselection`` / ``selection_set`` /
    ``selection_clear`` / ``see`` so it can stand in for the ``tk.Listbox``
    it replaced without rewriting every caller.
    """

    ROW_PAD_X, ROW_PAD_Y = 10, 7

    def __init__(self, master, on_activate=None, on_select=None, on_delete=None,
                 on_toggle=None, empty_text="Nothing here yet.", surface=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_activate = on_activate
        self._on_select = on_select
        self._on_delete = on_delete
        self._on_toggle = on_toggle
        self._empty_text = empty_text
        self._surface = surface  # None -> card colour
        self._rows: list[Row] = []
        self._row_frames: list[tk.Frame] = []
        self._selected: set[int] = set()
        self._anchor: int | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, highlightthickness=1, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.inner = tk.Frame(self.canvas, borderwidth=0, highlightthickness=0)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        for widget in (self.canvas, self.inner):
            widget.bind("<MouseWheel>", self._on_wheel)
            widget.bind("<Button-4>", self._on_wheel)
            widget.bind("<Button-5>", self._on_wheel)

        self.canvas.configure(takefocus=True)
        self.canvas.bind("<Up>", lambda _e: self._move(-1))
        self.canvas.bind("<Down>", lambda _e: self._move(1))
        self.canvas.bind("<space>", self._activate_toggle)
        self.canvas.bind("<Return>", lambda _e: self._fire(self._on_activate))
        self.canvas.bind("<Delete>", lambda _e: self._fire(self._on_delete))
        self.canvas.bind("<Button-1>", lambda _e: self.canvas.focus_set())

        self.restyle()

    # -- theming -------------------------------------------------------
    def _bg(self) -> str:
        return self._surface or tokens().card

    def set_surface(self, colour: str | None) -> None:
        self._surface = colour
        self.restyle()

    def restyle(self) -> None:
        t = tokens()
        self.canvas.configure(background=self._bg(), highlightbackground=t.border,
                              highlightcolor=t.border)
        self.inner.configure(background=self._bg())
        self.render()

    # -- data ----------------------------------------------------------
    def set_rows(self, rows: list[Row], keep_selection: bool = True) -> None:
        selected_ids = {self._rows[i].id for i in self._selected if i < len(self._rows)} \
            if keep_selection else set()
        self._rows = list(rows)
        self._selected = {i for i, row in enumerate(self._rows) if row.id in selected_ids}
        self._anchor = min(self._selected) if self._selected else None
        self.render()

    def render(self) -> None:
        for frame in self._row_frames:
            frame.destroy()
        self._row_frames = []
        t = tokens()

        if not self._rows:
            empty = tk.Label(self.inner, text=self._empty_text, background=self._bg(),
                             foreground=t.muted_foreground, font=font(theme.SIZE_SM),
                             justify="left", anchor="w", padx=14, pady=16)
            empty.pack(fill="x")
            self._row_frames.append(empty)
            return

        for index, row in enumerate(self._rows):
            self._row_frames.append(self._build_row(index, row))
        self._paint_selection()

    def _build_row(self, index: int, row: Row) -> tk.Frame:
        t = tokens()
        bg = self._bg()
        frame = tk.Frame(self.inner, background=bg, padx=self.ROW_PAD_X, pady=self.ROW_PAD_Y,
                         highlightthickness=0)
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)

        marker = row.marker or ("✓" if row.done else ("●" if row.flagged else "○"))
        colour = t.muted_foreground if row.done else (t.destructive if row.flagged else t.border)
        mark = tk.Label(frame, text=marker, background=bg, foreground=colour,
                        font=font(theme.SIZE_BASE), width=2)
        mark.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))

        title = tk.Label(
            frame, text=row.title, background=bg,
            foreground=t.muted_foreground if row.done else t.card_foreground,
            font=font(theme.SIZE_BASE, "normal" if row.done else "bold"),
            anchor="w", justify="left",
        )
        title.grid(row=0, column=1, sticky="w")

        widgets = [frame, mark, title]

        if row.badges:
            strip = BadgeStrip(frame, row.badges, background=bg)
            strip.grid(row=0, column=2, sticky="e", padx=(8, 0))
            widgets.append(strip)

        if row.subtitle:
            subtitle = tk.Label(frame, text=row.subtitle, background=bg,
                                foreground=t.muted_foreground, font=font(theme.SIZE_SM),
                                anchor="w", justify="left")
            subtitle.grid(row=1, column=1, columnspan=2, sticky="w")
            widgets.append(subtitle)

        separator = tk.Frame(self.inner, height=1, background=t.border)
        separator.pack(fill="x")
        self._row_frames.append(separator)

        for widget in widgets:
            widget.bind("<Button-1>", lambda e, i=index: self._click(i, e))
            widget.bind("<Control-Button-1>", lambda e, i=index: self._click(i, e, toggle=True))
            widget.bind("<Shift-Button-1>", lambda e, i=index: self._click(i, e, extend=True))
            widget.bind("<Double-Button-1>", lambda _e, i=index: self._double(i))
            widget.bind("<MouseWheel>", self._on_wheel)
            widget.bind("<Button-4>", self._on_wheel)
            widget.bind("<Button-5>", self._on_wheel)
            widget.bind("<Enter>", lambda _e, i=index: self._hover(i, True))
            widget.bind("<Leave>", lambda _e, i=index: self._hover(i, False))
        frame._cell_widgets = widgets  # noqa: SLF001 - used by _paint_selection
        return frame

    # -- selection -----------------------------------------------------
    def _row_widgets(self, index: int):
        frames = [f for f in self._row_frames if getattr(f, "_cell_widgets", None)]
        if index < len(frames):
            return frames[index], frames[index]._cell_widgets
        return None, []

    def _paint_selection(self) -> None:
        t = tokens()
        for index in range(len(self._rows)):
            colour = t.selected if index in self._selected else self._bg()
            self._paint_row(index, colour)

    def _paint_row(self, index: int, colour: str) -> None:
        frame, widgets = self._row_widgets(index)
        if frame is None:
            return
        frame.configure(background=colour)
        for widget in widgets:
            try:
                widget.configure(background=colour)
            except tk.TclError:
                pass

    def _hover(self, index: int, entering: bool) -> None:
        if index in self._selected:
            return
        self._paint_row(index, tokens().hover if entering else self._bg())

    def _click(self, index: int, _event=None, toggle: bool = False, extend: bool = False):
        self.canvas.focus_set()
        if toggle:
            self._selected.symmetric_difference_update({index})
            self._anchor = index
        elif extend and self._anchor is not None:
            low, high = sorted((self._anchor, index))
            self._selected = set(range(low, high + 1))
        else:
            self._selected = {index}
            self._anchor = index
        self._paint_selection()
        if self._on_select:
            self._on_select()
        return "break"

    def _double(self, index: int):
        self._click(index)
        self._fire(self._on_activate)
        return "break"

    def _activate_toggle(self, _event=None):
        self._fire(self._on_toggle or self._on_activate)
        return "break"

    def _fire(self, callback):
        if callback:
            callback()
        return "break"

    def _move(self, delta: int):
        if not self._rows:
            return "break"
        current = min(self._selected) if self._selected else -1
        target = max(0, min(len(self._rows) - 1, current + delta))
        self._selected = {target}
        self._anchor = target
        self._paint_selection()
        self.see(target)
        if self._on_select:
            self._on_select()
        return "break"

    # -- Listbox-compatible surface ------------------------------------
    def size(self) -> int:
        return len(self._rows)

    def get(self, index: int) -> str:
        return self._rows[index].as_text() if 0 <= index < len(self._rows) else ""

    def row(self, index: int) -> Row | None:
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def curselection(self) -> tuple:
        return tuple(sorted(i for i in self._selected if i < len(self._rows)))

    def selection_set(self, first, last=None) -> None:
        last = first if last is None else last
        self._selected.update(range(int(first), int(last) + 1))
        self._anchor = int(first)
        self._paint_selection()

    def selection_clear(self, _first=None, _last=None) -> None:
        self._selected.clear()
        self._paint_selection()

    def see(self, index: int) -> None:
        frame, _ = self._row_widgets(index)
        if frame is None:
            return
        self.canvas.update_idletasks()
        top = frame.winfo_y()
        height = frame.winfo_height()
        total = max(1, self.inner.winfo_height())
        view_top = self.canvas.canvasy(0)
        view_height = self.canvas.winfo_height()
        if top < view_top:
            self.canvas.yview_moveto(top / total)
        elif top + height > view_top + view_height:
            self.canvas.yview_moveto(max(0, (top + height - view_height) / total))

    def focus_list(self) -> None:
        self.canvas.focus_set()

    # -- scrolling -----------------------------------------------------
    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")
        return "break"


class MomentumStrip(tk.Canvas):
    """A row of squares, one per day, shaded by sessions completed.

    The visible feedback loop: short sessions are easier to keep doing when
    you can see the ones you already did. ``on_hover`` is called with a
    description of the day under the pointer, and ``""`` when it leaves.
    """

    def __init__(self, master, days: int = 14, cell: int = 13, gap: int = 4, on_hover=None,
                 surface: str = "card", **kwargs):
        self.days = days
        self.cell = cell
        self.gap = gap
        self._on_hover = on_hover
        self._surface = surface
        self._counts: list[tuple[str, int]] = []
        super().__init__(master, width=days * (cell + gap), height=cell + 2,
                         highlightthickness=0, borderwidth=0,
                         background=self._bg(), **kwargs)
        self.bind("<Leave>", lambda _e: self._report(""))

    def _bg(self) -> str:
        t = tokens()
        return t.background if self._surface == "background" else t.card

    def _levels(self) -> list[str]:
        t = tokens()
        # Empty days are simply empty: never red, never a broken streak.
        if t.name == "dark":
            return ["#232327", "#243b55", "#2f5c86", "#3f83bd", "#60a5fa"]
        return ["#ebebef", "#dbe7f6", "#b6cef0", "#7ba7e0", "#3b82f6"]

    def render(self, counts: list[tuple[str, int]] | None = None) -> None:
        if counts is not None:
            self._counts = counts
        self.configure(background=self._bg())
        self.delete("all")
        levels = self._levels()
        for index, (day, count) in enumerate(self._counts[-self.days:]):
            x = index * (self.cell + self.gap)
            rect = rounded_rect(self, x, 1, x + self.cell, self.cell + 1, 3,
                                fill=levels[min(count, len(levels) - 1)], outline="")
            label = "no sessions" if count == 0 else f"{count} session{'s' if count != 1 else ''}"
            self.tag_bind(rect, "<Enter>", self._hover(f"{day}: {label}"))

    def _hover(self, text: str):
        return lambda _event=None: self._report(text)

    def _report(self, text: str) -> None:
        if self._on_hover is not None:
            self._on_hover(text)


class FocusWindow(tk.Toplevel):
    """A small always-on-top window holding only the timer and the first step.

    During a session the rest of the app is noise, and a countdown you cannot
    see is a countdown you lose track of. This stays visible over whatever you
    are actually working in.
    """

    def __init__(self, master, on_pause=None, on_done=None, on_close=None):
        super().__init__(master)
        self._on_pause = on_pause
        self._on_done = on_done
        self._on_close = on_close
        self.title("Focus")
        self.resizable(False, False)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.close)

        t = tokens()
        self.configure(background=t.card)
        body = ttk.Frame(self, style="Card.TFrame", padding=18)
        body.pack(fill="both", expand=True)

        self.task_var = tk.StringVar(value="")
        self.step_var = tk.StringVar(value="")
        self.time_var = tk.StringVar(value="00:00")

        ttk.Label(body, textvariable=self.task_var, style="Lead.TLabel",
                  wraplength=280, justify="center", anchor="center").pack(fill="x")
        ttk.Label(body, textvariable=self.step_var, style="CardMuted.TLabel",
                  wraplength=280, justify="center", anchor="center").pack(fill="x", pady=(2, 6))
        ttk.Label(body, textvariable=self.time_var, style="Timer.TLabel",
                  anchor="center").pack(fill="x")

        self.progress = ttk.Progressbar(body, mode="determinate", maximum=1000)
        self.progress.pack(fill="x", pady=(4, 12))

        row = ttk.Frame(body, style="Card.TFrame")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        self.pause_button = ttk.Button(row, text="Pause", style="SmOutline.TButton",
                                       command=self._pause)
        self.pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(row, text="Done early", style="SmGhost.TButton",
                   command=self._done).grid(row=0, column=1, sticky="ew")

        self.update_idletasks()
        self.geometry(f"320x{max(210, self.winfo_reqheight())}")

    def update_session(self, task: str, step: str, time_text: str, fraction: float,
                       running: bool) -> None:
        self.task_var.set(task or "Free focus")
        self.step_var.set(f"→ {step}" if step else "")
        self.time_var.set(time_text)
        self.progress["value"] = int(max(0.0, min(1.0, fraction)) * 1000)
        self.pause_button.configure(text="Pause" if running else "Resume")

    def _pause(self):
        if self._on_pause:
            self._on_pause()

    def _done(self):
        if self._on_done:
            self._on_done()

    def close(self):
        if self._on_close:
            self._on_close()
        self.destroy()
