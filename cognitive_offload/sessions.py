"""The focus-session log.

Short sessions work partly because they close a loop you can see. This keeps
the record of finished sessions so the app can show that evidence back to you.

Deliberately non-punitive: it counts what you *did*, never what you missed,
and there is no streak to break. A quiet day is just a quiet day.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import DATE_FORMAT, TIMESTAMP_FORMAT, now_stamp, today_iso

# Enough history for the momentum strip and a year of looking back, while
# keeping the file small.
MAX_SESSIONS = 2000
DEFAULT_FOCUS_MINUTES = 15
DEFAULT_BREAK_MINUTES = 5


@dataclass
class FocusSession:
    minutes: int
    task: str = ""
    started_at: str = field(default_factory=now_stamp)
    completed: bool = True
    # Which task the block was on (Task.id) — what makes "the thing you
    # worked on yesterday" findable again tomorrow.
    task_id: str = ""

    @property
    def day(self) -> str:
        return self.started_at[:10]

    def to_dict(self) -> dict:
        record = {
            "started_at": self.started_at,
            "minutes": int(self.minutes),
            "task": self.task,
            "completed": bool(self.completed),
        }
        if self.task_id:
            record["task_id"] = self.task_id
        return record

    @classmethod
    def from_dict(cls, data: dict) -> "FocusSession":
        started = data.get("started_at")
        try:
            minutes = int(data.get("minutes", 0))
        except (TypeError, ValueError):
            minutes = 0
        return cls(
            minutes=max(0, minutes),
            task=data.get("task") if isinstance(data.get("task"), str) else "",
            started_at=started if isinstance(started, str) else now_stamp(),
            completed=bool(data.get("completed", True)),
            task_id=data.get("task_id") if isinstance(data.get("task_id"), str) else "",
        )


class SessionLog:
    """Append-only-ish list of finished sessions, stored next to the session file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.sessions: list[FocusSession] = []
        self.write_failed = False  # did the most recent record() reach disk?

    def set_path(self, path: Path) -> None:
        self.path = Path(path)
        self.sessions = []

    def load(self) -> "SessionLog":
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            self.sessions = []
            return self
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # A damaged log is not worth interrupting anyone over, but it
            # should not be silently overwritten by tonight's first session
            # either - park it next door first.
            self.sessions = []
            self._quarantine()
            return self
        records = data.get("sessions") if isinstance(data, dict) else data
        self.sessions = [
            FocusSession.from_dict(r) for r in (records or []) if isinstance(r, dict)
        ]
        return self

    def _quarantine(self) -> None:
        """Move an unreadable log aside so the next save cannot destroy it."""
        spoiled = self.path.with_suffix(self.path.suffix + ".corrupt")
        try:
            if self.path.exists() and not spoiled.exists():
                self.path.replace(spoiled)
        except OSError:
            pass

    def save(self) -> None:
        from .storage import write_json  # imported here to avoid a cycle

        self.sessions = self.sessions[-MAX_SESSIONS:]
        write_json(self.path, {"sessions": [s.to_dict() for s in self.sessions]}, indent=1)

    def record(self, minutes: int, task: str = "", completed: bool = True,
               task_id: str = "") -> FocusSession:
        session = FocusSession(minutes=minutes, task=task, completed=completed,
                               task_id=task_id)
        self.sessions.append(session)
        try:
            self.save()
            self.write_failed = False
        except OSError:
            # Losing a log entry must never cost you the session itself —
            # but the caller may want to mention it happened.
            self.write_failed = True
        return session

    # -- reporting -----------------------------------------------------
    def on_day(self, day: str) -> list[FocusSession]:
        return [s for s in self.sessions if s.day == day and s.completed]

    def count_today(self) -> int:
        return len(self.on_day(today_iso()))

    def minutes_for_task(self, task_id: str) -> int:
        """Total completed focus minutes ever logged against one task."""
        if not task_id:
            return 0
        return sum(s.minutes for s in self.sessions
                   if s.completed and s.task_id == task_id)

    def recent_task_ids(self, days: int = 2, end: str | None = None) -> set:
        """Ids of tasks with a focus session in the last ``days`` days.

        A task worked on yesterday is warm — its context is half-loaded and
        its hand-off step freshly written — and far cheaper to re-enter than
        a cold start. The ranking uses this to resurface it.
        """
        last = _parse_day(end) if end else date.today()
        first = last - timedelta(days=max(0, days - 1))
        window = {(first + timedelta(days=i)).isoformat()
                  for i in range((last - first).days + 1)}
        return {s.task_id for s in self.sessions
                if s.task_id and s.day in window}

    def minutes_today(self) -> int:
        return sum(s.minutes for s in self.on_day(today_iso()))

    def counts_by_day(self, days: int = 14, end: str | None = None) -> list[tuple[str, int]]:
        """``[(YYYY-MM-DD, sessions), ...]`` oldest first, gaps included as 0."""
        last = _parse_day(end) if end else date.today()
        tally: dict[str, int] = {}
        for session in self.sessions:
            if session.completed:
                tally[session.day] = tally.get(session.day, 0) + 1
        span = max(1, days)
        return [
            (day.isoformat(), tally.get(day.isoformat(), 0))
            for day in (last - timedelta(days=offset) for offset in range(span - 1, -1, -1))
        ]

    def total_minutes(self, days: int = 7, end: str | None = None) -> int:
        recent = {day for day, _ in self.counts_by_day(days, end)}
        return sum(s.minutes for s in self.sessions if s.completed and s.day in recent)

    def summary(self) -> str:
        """One honest line for the status bar."""
        today = self.count_today()
        if today == 0:
            return "No sessions yet today"
        minutes = self.minutes_today()
        return f"{today} session{'s' if today != 1 else ''} today · {minutes} min"


def _parse_day(value: str) -> date:
    try:
        return datetime.strptime(value[:10], DATE_FORMAT).date()
    except (TypeError, ValueError):
        return date.today()


def parse_stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None
