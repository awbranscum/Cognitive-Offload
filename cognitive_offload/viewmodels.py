"""What a row shows, with no opinion about how it is drawn.

These are the types that cross the line between the app's brain and its
face. :mod:`rows` decides what a task should say — its title, the step
underneath, which badges it has earned — and hands back these plain
objects; a front-end then draws them however that platform draws things.
The tkinter :class:`~cognitive_offload.widgets.RowList` paints them on a
canvas. A phone front-end would paint the same objects a different way,
and would need none of this file changed to do it.

They live here rather than in ``widgets`` because that module imports
tkinter, and importing a GUI toolkit to learn that a task is flagged is
the kind of coupling that quietly decides what the app can ever run on.
Nothing in this file may import a UI toolkit — ``tests/test_portability``
enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Badge:
    """A small labelled pill. ``variant`` names a colour role, not a colour."""

    text: str
    variant: str = "tag"  # key into Tokens.badges


@dataclass
class Row:
    """One entry in a list: what to say about a task, not how to show it."""

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
