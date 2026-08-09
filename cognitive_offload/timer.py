"""The focus/break clock as a pure state machine.

This class owns the app's honesty guarantees for a time-blind user:

* never invent minutes — ``bank_early`` refuses when the block already
  logged itself or never started;
* never credit a break as focus — expiry reports the mode that ended,
  exactly once, and resets to focus;
* never let a stale total make a fresh clock look two-thirds run — the
  plain-start path refreshes total and remaining together.

No tkinter, and no wall clock of its own: every method takes ``now`` (a
monotonic timestamp), so tests drive time by hand. The Tk ``after`` loop,
labels, dialogs and the session log all stay in the controller.
"""

from __future__ import annotations

import math

FOCUS = "focus"
BREAK = "break"
CLOSING_SECONDS = 120


class FocusTimer:
    def __init__(self, fallback_minutes: int = 15):
        self.mode = FOCUS
        self.running = False
        self.total = max(1, fallback_minutes) * 60
        self.remaining = self.total
        self.banked = False
        self.deadline = 0.0

    # -- lifecycle -----------------------------------------------------
    def start(self, now: float, minutes: int | None = None, mode: str = FOCUS,
              fallback_minutes: int = 15) -> bool:
        """Begin or resume. False when a block is already running.

        ``minutes`` given = a fresh block. Without it, a spent or
        inconsistent clock is refreshed (a fresh block again — including
        clearing ``banked``, which belongs to the previous block); a paused
        one resumes untouched.
        """
        if self.running:
            return False
        if minutes is not None:
            self.mode = mode
            self.total = max(1, minutes) * 60
            self.remaining = self.total
            self.banked = False
        elif self.remaining <= 0 or self.remaining > self.total:
            self.total = max(1, fallback_minutes) * 60
            self.remaining = self.total
            self.banked = False
        self.deadline = now + self.remaining
        self.running = True
        return True

    def pause(self, now: float) -> bool:
        """Stop the clock without judgement. False when nothing was running."""
        if not self.running:
            return False
        self.remaining = max(0, int(round(self.deadline - now)))
        self.running = False
        return True

    def tick(self, now: float, allow_finish: bool = True) -> str:
        """Advance the clock. Returns the mode that just expired, or "".

        ``allow_finish=False`` holds an expired block at 00:00 without
        finishing it (used while a modal dialog holds the grab): the block
        completes on the first tick after permission returns.
        """
        if not self.running:
            return ""
        raw = self.deadline - now
        self.remaining = max(0, int(math.ceil(raw)))
        if raw > 0 or not allow_finish:
            return ""
        expired = self.mode
        self.banked = True
        self.running = False
        self.remaining = 0
        self.mode = FOCUS
        return expired

    def reset(self, fallback_minutes: int) -> None:
        self.running = False
        self.mode = FOCUS
        self.total = max(1, fallback_minutes) * 60
        self.remaining = self.total
        self.banked = False

    # -- adjustments ---------------------------------------------------
    def set_length_if_idle(self, minutes: int) -> bool:
        """Follow the spinbox only when genuinely idle.

        A paused block also has ``running == False``, but it holds elapsed
        minutes worth banking — a stray arrow-click must not wipe them.
        """
        mid_block = 0 < self.remaining < self.total
        if self.running or mid_block:
            return False
        self.total = max(1, minutes) * 60
        self.remaining = self.total
        return True

    def bank_early(self, fallback_minutes: int) -> tuple[str, int] | None:
        """Stop now, keeping the minutes actually done.

        None when there is nothing to bank: the block already logged
        itself, or never started — logging then would invent minutes.
        Returns ``(mode_that_ended, elapsed_minutes)``.
        """
        if self.banked or (not self.running and self.remaining >= self.total):
            return None
        elapsed = max(1, round((self.total - self.remaining) / 60))
        mode, self.mode = self.mode, FOCUS
        if mode == BREAK:
            self.total = max(1, fallback_minutes) * 60
        self.running = False
        self.remaining = self.total
        return (mode, elapsed)

    def minutes_for_natural_finish(self) -> int:
        return max(1, round(self.total / 60))

    # -- read-only views -----------------------------------------------
    @property
    def elapsed(self) -> int:
        return max(0, self.total - self.remaining)

    @property
    def fraction(self) -> float:
        return self.elapsed / self.total if self.total else 0.0

    @property
    def closing_in(self) -> bool:
        """The last two minutes of a running focus block."""
        return (self.mode == FOCUS and self.running
                and 0 < self.remaining <= CLOSING_SECONDS)
