"""Small custom widgets."""

from __future__ import annotations

import tkinter as tk

from .theme import PALETTE

# Empty days are simply empty - never red, never a broken streak.
_LEVELS = ["#e9ecf1", "#cfe0f8", "#9dc0f0", "#5b93e0", "#2f6fd0"]


class MomentumStrip(tk.Canvas):
    """A row of squares, one per day, shaded by sessions completed.

    This is the visible feedback loop: short sessions are easier to keep doing
    when you can see the ones you already did. ``on_hover`` (if given) is
    called with a description of the day under the pointer, and with ``""``
    when the pointer leaves.
    """

    def __init__(self, master, days: int = 14, cell: int = 13, gap: int = 3, on_hover=None, **kwargs):
        self.days = days
        self.cell = cell
        self.gap = gap
        self._on_hover = on_hover
        super().__init__(
            master,
            width=days * (cell + gap),
            height=cell + 2,
            highlightthickness=0,
            background=PALETTE["bg"],
            **kwargs,
        )
        self.bind("<Leave>", lambda _e: self._report(""))

    def render(self, counts: list[tuple[str, int]]) -> None:
        """``counts`` is ``[(day, sessions), ...]``, oldest first."""
        self.delete("all")
        for index, (day, count) in enumerate(counts[-self.days:]):
            x = index * (self.cell + self.gap)
            rect = self.create_rectangle(
                x, 1, x + self.cell, self.cell + 1,
                fill=_LEVELS[min(count, len(_LEVELS) - 1)], outline="",
            )
            label = "no sessions" if count == 0 else f"{count} session{'s' if count != 1 else ''}"
            self.tag_bind(rect, "<Enter>", self._hover(f"{day}: {label}"))

    def _hover(self, text: str):
        return lambda _event=None: self._report(text)

    def _report(self, text: str) -> None:
        if self._on_hover is not None:
            self._on_hover(text)
