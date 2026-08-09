"""The undo stack, UI-free.

Ctrl+Z is what makes every destructive action in the app low-stakes — an
impulsive delete never costs anything. That safety net used to be ~30 lines
of in-place list mutation inside the controller, typed as 2-tuples while the
code appended mutable 3-lists so a later ``attach`` could add a side effect.
A small real class makes the entry shape explicit and testable headless.
"""

from __future__ import annotations

from typing import Callable

UNDO_LIMIT = 30


class UndoEntry:
    __slots__ = ("label", "snapshot", "restore")

    def __init__(self, label: str, snapshot: list):
        self.label = label
        self.snapshot = snapshot
        self.restore: Callable[[], None] | None = None


class UndoStack:
    """Snapshots of the task list, each optionally paired with a callable
    that undoes a matching side effect in another store (the matrix)."""

    def __init__(self, limit: int = UNDO_LIMIT):
        self._entries: list[UndoEntry] = []
        self._limit = max(1, limit)

    def push(self, label: str, snapshot: list) -> None:
        self._entries.append(UndoEntry(label, snapshot))
        del self._entries[:-self._limit]

    def attach(self, restore: Callable[[], None]) -> None:
        """Give the most recent entry a side effect to run on undo.

        Moving a task between the list and the matrix touches two stores;
        undoing only one half would leave the task in both places or
        neither.
        """
        if self._entries:
            self._entries[-1].restore = restore

    def pop(self) -> UndoEntry | None:
        return self._entries.pop() if self._entries else None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)
