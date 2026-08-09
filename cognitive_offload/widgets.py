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


# Badge texts are a small closed set ("admin", "ready", "#work", dates), so
# measuring each one once is enough. Building a Tcl font object per badge per
# draw was the bulk of the cost of rendering a long list.
_TEXT_WIDTHS: dict[tuple, int] = {}
_FONTS: dict[tuple, object] = {}


def _mix(base: str, other: str, amount: float) -> str:
    """Blend two hex colours, for surfaces the token set does not cover."""
    def parts(value):
        value = value.lstrip("#")
        return [int(value[i:i + 2], 16) for i in (0, 2, 4)]

    a, b = parts(base), parts(other)
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


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
        # Keyed by interpreter as well as font: a Font object belongs to the Tk
        # instance that made it, and the app can be constructed more than once
        # in a process.
        interp = self.tk.interpaddr()
        key = (interp, self._font, text)
        cached = _TEXT_WIDTHS.get(key)
        if cached is not None:
            return cached
        from tkinter import font as tkfont

        try:
            measurer = _FONTS.get((interp, self._font))
            if measurer is None:
                measurer = _FONTS[(interp, self._font)] = tkfont.Font(root=self, font=self._font)
            width = measurer.measure(text)
        except tk.TclError:
            return 7 * len(text)  # no Tk available; good enough to lay out
        _TEXT_WIDTHS[key] = width
        return width

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
        self._pool: list[dict] = []
        self._selected: set[int] = set()
        self._hovered: int | None = None
        self._anchor: int | None = None
        self._row_tag = f"rowlist{id(self)}"

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

        self._empty_label = tk.Label(self.inner, justify="left", anchor="w",
                                     font=font(theme.SIZE_SM), padx=14, pady=16)
        self._bind_row_events()
        self.restyle()

    # -- theming -------------------------------------------------------
    def _bg(self) -> str:
        return self._surface or tokens().card

    def set_surface(self, colour: str | None) -> None:
        self._surface = colour
        self.restyle()

    def restyle(self) -> None:
        t = tokens()
        # Tk reserves the highlight border whether or not the widget has focus,
        # so a thickness of 2 shows keyboard focus without shifting the layout.
        self.canvas.configure(background=self._bg(), highlightthickness=2,
                              highlightbackground=t.border, highlightcolor=t.ring)
        self.inner.configure(background=self._bg())
        self._empty_label.configure(background=self._bg(), foreground=t.muted_foreground)
        self.render()

    # -- data ----------------------------------------------------------
    def set_rows(self, rows: list[Row], keep_selection: bool = True) -> None:
        selected_ids = {self._rows[i].id for i in self._selected if i < len(self._rows)} \
            if keep_selection else set()
        shrank = len(rows) < len(self._rows)
        self._rows = list(rows)
        self._selected = {i for i, row in enumerate(self._rows) if row.id in selected_ids}
        self._anchor = min(self._selected) if self._selected else None
        self.render()
        if shrank:
            # Otherwise the view stays parked past the end of the new list and
            # a search that matches shows an empty panel.
            self.canvas.yview_moveto(0)

    def render(self) -> None:
        """Refill the pooled row widgets rather than rebuilding them.

        Creating a Tk widget is expensive (~0.5ms), and a row is six of them.
        Destroying and recreating the list on every keystroke of a search made
        a 300-task list take about a second per letter, which punishes exactly
        the user this app tells to capture everything.
        """
        self._empty_label.pack_forget()
        for index, row in enumerate(self._rows):
            self._apply_row(self._ensure_row(index), index, row)
        for spare in self._pool[len(self._rows):]:
            if spare["visible"]:
                spare["frame"].pack_forget()
                spare["separator"].pack_forget()
                spare["visible"] = False

        if not self._rows:
            self._empty_label.configure(text=self._empty_text, background=self._bg(),
                                        foreground=tokens().muted_foreground)
            self._empty_label.pack(fill="x")
            return
        self._paint_selection()

    def _ensure_row(self, index: int) -> dict:
        """Return the pooled widgets for a row, building them the first time."""
        while len(self._pool) <= index:
            self._pool.append(self._build_row())
        cell = self._pool[index]
        if not cell["visible"]:
            # Re-packed in ascending order, and every lower index is still
            # packed, so rows always land back in the right place.
            cell["frame"].pack(fill="x")
            cell["separator"].pack(fill="x")
            cell["visible"] = True
        return cell

    def _build_row(self) -> dict:
        bg = self._bg()
        frame = tk.Frame(self.inner, background=bg, padx=self.ROW_PAD_X, pady=self.ROW_PAD_Y,
                         highlightthickness=0)
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)

        mark = tk.Label(frame, background=bg, font=font(theme.SIZE_BASE), width=2)
        mark.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 8))
        title = tk.Label(frame, background=bg, anchor="w", justify="left")
        title.grid(row=0, column=1, sticky="w")
        badges = BadgeStrip(frame, [], background=bg)
        badges.grid(row=0, column=2, sticky="e", padx=(8, 0))
        subtitle = tk.Label(frame, background=bg, font=font(theme.SIZE_SM),
                            anchor="w", justify="left")
        subtitle.grid(row=1, column=1, columnspan=2, sticky="w")
        separator = tk.Frame(self.inner, height=1, background=tokens().border)
        separator.pack(fill="x")

        cells = [frame, mark, title, badges, subtitle]
        for widget in cells:
            # One shared bindtag instead of nine bindings per widget: at 300
            # rows that was ~14k bind calls per refresh.
            widget.bindtags((self._row_tag,) + widget.bindtags())
        return {"frame": frame, "mark": mark, "title": title, "badges": badges,
                "subtitle": subtitle, "separator": separator, "cells": cells,
                "visible": True}

    def _apply_row(self, cell: dict, index: int, row: Row) -> None:
        t = tokens()
        bg = self._bg()
        for widget in cell["cells"]:
            widget._row_index = index  # read back by the shared bindtag handlers

        marker = row.marker or ("✓" if row.done else ("●" if row.flagged else "○"))
        cell["mark"].configure(
            text=marker, background=bg,
            # The marker is the fastest pre-attentive read of row state; in
            # t.border it sat at 1.4:1 — a reserved column of nothing. The
            # glyph shape carries the open/done distinction.
            foreground=t.destructive if row.flagged and not row.done
            else t.muted_foreground,
        )
        cell["title"].configure(
            text=row.title, background=bg,
            foreground=t.muted_foreground if row.done else t.card_foreground,
            font=font(theme.SIZE_BASE, "normal" if row.done else "bold"),
        )
        cell["badges"].set_badges(row.badges, background=bg)
        if row.badges:
            cell["badges"].grid()
        else:
            cell["badges"].grid_remove()
        cell["subtitle"].configure(text=row.subtitle, background=bg,
                                   foreground=t.muted_foreground)
        if row.subtitle:
            cell["subtitle"].grid()
        else:
            cell["subtitle"].grid_remove()
        cell["separator"].configure(background=t.border)

    def _bind_row_events(self) -> None:
        """Bind the row interactions once, on a tag shared by every row widget."""
        def index_of(event):
            return getattr(event.widget, "_row_index", None)

        def on_click(event, toggle=False, extend=False):
            index = index_of(event)
            return None if index is None else self._click(index, event, toggle, extend)

        self.bind_class(self._row_tag, "<Button-1>", on_click)
        self.bind_class(self._row_tag, "<Control-Button-1>",
                        lambda e: on_click(e, toggle=True))
        self.bind_class(self._row_tag, "<Shift-Button-1>",
                        lambda e: on_click(e, extend=True))
        self.bind_class(self._row_tag, "<Double-Button-1>",
                        lambda e: self._double(index_of(e)) if index_of(e) is not None else None)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_class(self._row_tag, sequence, self._on_wheel)
        self.bind_class(self._row_tag, "<Enter>",
                        lambda e: self._hover(index_of(e), True) if index_of(e) is not None else None)
        self.bind_class(self._row_tag, "<Leave>",
                        lambda e: self._hover(index_of(e), False) if index_of(e) is not None else None)

    # -- selection -----------------------------------------------------
    def _row_widgets(self, index: int):
        if 0 <= index < len(self._rows) and index < len(self._pool):
            cell = self._pool[index]
            return cell["frame"], cell["cells"]
        return None, []

    def _selected_bg(self) -> str:
        """Selection colour with enough contrast against *this* surface.

        The quadrant lists sit on their own tints, where the shared selected
        token is nearly invisible.
        """
        t = tokens()
        if self._surface is None:
            return t.selected
        return _mix(self._surface, t.foreground, 0.16 if t.name == "light" else 0.24)

    def _paint_selection(self) -> None:
        for index in range(len(self._rows)):
            if index in self._selected:
                colour = self._selected_bg()
            elif index == self._hovered:
                # The pointer hasn't moved just because the list repainted:
                # without this, every keystroke of a search dropped the
                # hover highlight.
                colour = self._hover_colour()
            else:
                colour = self._bg()
            self._paint_row(index, colour)

    def _paint_row(self, index: int, colour: str) -> None:
        frame, widgets = self._row_widgets(index)
        if frame is None:
            return
        for widget in widgets:
            try:
                widget.configure(background=colour)
            except tk.TclError:
                pass

    def _hover_colour(self) -> str:
        return tokens().hover if self._surface is None else _mix(
            self._surface, tokens().foreground, 0.06)

    def _hover(self, index: int, entering: bool) -> None:
        if index >= len(self._rows):
            return
        if entering:
            self._hovered = index
        elif self._hovered == index:
            self._hovered = None
        if index in self._selected:
            return
        self._paint_row(index, self._hover_colour() if entering else self._bg())

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
        # Space toggles done where rows have a done state. The matrix has none,
        # so it stays inert; Return and double click still activate.
        self._fire(self._on_toggle)
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


    def curselection(self) -> tuple:
        return tuple(sorted(i for i in self._selected if i < len(self._rows)))

    def _index(self, value) -> int:
        """Coerce a Listbox-style index ('end' or an int) into a valid row."""
        if isinstance(value, str):
            value = len(self._rows) - 1 if value.startswith("end") else int(value)
        return max(0, min(len(self._rows) - 1, int(value)))

    def selection_set(self, first, last=None) -> None:
        if not self._rows:
            return
        first = self._index(first)
        last = first if last is None else self._index(last)
        self._selected.update(range(min(first, last), max(first, last) + 1))
        self._anchor = first
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


# Neutral by design: never "distraction", never an instruction to focus.
PARK_HINT = "Something else on your mind? Park it here."
PARK_DONE = "Parked in the scratchpad. Back to it."


class FocusWindow(tk.Toplevel):
    """A small always-on-top window holding only the timer and the first step.

    During a session the rest of the app is noise, and a countdown you cannot
    see is a countdown you lose track of. This stays visible over whatever you
    are actually working in.
    """

    def __init__(self, master, on_pause=None, on_done=None, on_close=None, on_park=None):
        super().__init__(master)
        self._on_pause = on_pause
        self._on_done = on_done
        self._on_close = on_close
        self._on_park = on_park
        self.title("Focus")
        self.resizable(False, False)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self._pause())

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
        self.time_label = ttk.Label(body, textvariable=self.time_var,
                                    style="Timer.TLabel", anchor="center")
        self.time_label.pack(fill="x")
        self._closing = False

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

        # An intrusive thought mid-block should cost two seconds, not a trip
        # back to the main window. Parking never touches the timer.
        park = ttk.Frame(body, style="Card.TFrame")
        park.pack(fill="x", pady=(12, 0))
        park.columnconfigure(0, weight=1)
        self.park_entry = ttk.Entry(park)
        self.park_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.park_entry.bind("<Return>", lambda _e: self._park() or "break")
        self.park_entry.bind("<Escape>", lambda _e: self._clear_park() or "break")
        ttk.Button(park, text="Park", style="SmGhost.TButton",
                   command=self._park).grid(row=0, column=1)
        self.park_var = tk.StringVar(value=PARK_HINT)
        ttk.Label(body, textvariable=self.park_var, style="CardMuted.TLabel",
                  anchor="center", wraplength=280, justify="center").pack(fill="x", pady=(4, 0))

        self.pause_button.focus_set()
        self.update_idletasks()
        self.geometry(f"320x{max(210, self.winfo_reqheight())}")

    def restyle(self) -> None:
        """Follow a theme switch instead of being closed mid-session."""
        try:
            self.configure(background=tokens().card)
        except tk.TclError:
            pass

    def update_session(self, task: str, step: str, time_text: str, fraction: float,
                       running: bool, closing: bool = False) -> None:
        self.task_var.set(task or "Free focus")
        if closing:
            # The last two minutes: a soft landing, not an ambush. Amber,
            # never red — a heads-up is not an alarm.
            self.step_var.set("a good moment to find a stopping point")
        else:
            self.step_var.set(f"→ {step}" if step else "")
        self.time_var.set(time_text)
        if closing != self._closing:
            self._closing = closing
            try:
                self.time_label.configure(
                    foreground=tokens().warning if closing else "")
            except tk.TclError:
                pass
        self.progress["value"] = int(max(0.0, min(1.0, fraction)) * 1000)
        self.pause_button.configure(text="Pause" if running else "Resume")

    def _pause(self):
        if self._on_pause:
            self._on_pause()

    def _park(self):
        text = self.park_entry.get().strip()
        if not text:
            return  # an empty Enter is a no-op: no dialog, no beep
        self.park_entry.delete(0, tk.END)
        if self._on_park:
            self._on_park(text)
        self.park_var.set(PARK_DONE)
        self.after(4000, lambda: self.park_var.set(PARK_HINT))

    def _clear_park(self):
        self.park_entry.delete(0, tk.END)

    def _done(self):
        if self._on_done:
            self._on_done()

    def close(self):
        if self._on_close:
            self._on_close()
        self.destroy()
