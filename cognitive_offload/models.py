"""Data model.

Everything here is pure Python with no tkinter import, so it can be unit
tested without a display.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

# How a task *feels* to start, which is what decides whether you can face it
# right now. Ordering matters: it is the order shown in the pickers.
TASK_KINDS: dict[str, str] = {
    "urgent": "Urgent sprint",
    "deadline": "Deadline sprint",
    "admin": "Admin sprint",
    "creative": "Creative / fun",
}
KIND_UNSET = ""
KIND_LABELS = {KIND_UNSET: "Unsorted", **TASK_KINDS}
# The one label→key map. It existed three times (app, dialogs, main_tab);
# adding a fifth kind meant touching files that never reference each other.
KIND_KEY_BY_LABEL = {label: key for key, label in KIND_LABELS.items()}


def now_stamp() -> str:
    """Current local time in the sortable format used throughout the app."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def new_id() -> str:
    return uuid.uuid4().hex


def today_iso() -> str:
    return date.today().isoformat()


def parse_date_input(text: str) -> str | None:
    """Turn what a person actually types into ``YYYY-MM-DD``.

    Accepts ``today``, ``tomorrow``, a weekday name (the next one), or an ISO
    date. Returns ``None`` if it cannot be understood, and ``""`` for empty
    input (meaning "no date").
    """
    text = (text or "").strip().lower()
    if not text:
        return ""
    today = date.today()
    if text in ("today", "now"):
        return today.isoformat()
    if text == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for index, name in enumerate(weekdays):
        if text == name or text == name[:3]:
            ahead = (index - today.weekday()) % 7 or 7
            return (today + timedelta(days=ahead)).isoformat()
    try:
        return datetime.strptime(text, DATE_FORMAT).date().isoformat()
    except ValueError:
        return None


def parse_estimate_input(text: str) -> int | None:
    """Turn what a person types into a minutes estimate, or ``None``.

    The field is labelled "About ⬚ minutes, at a guess" with the word
    *minutes* printed to the RIGHT of the box, so typing "20 mins" into it
    is the natural thing to do — and that was the input most reliably
    thrown away, along with "20m", "1h" and "~15". A guess that vanishes is
    worse than no field at all: ``estimate_minutes = 0`` means "no guess",
    so a discarded estimate is indistinguishable from a blank one, and the
    calibration line ("You guessed ~20 min; it took about 35") then never
    appears, with nothing to connect that silence to what was typed.

    Deliberately forgiving rather than strict, and deliberately silent on
    what it still cannot read. The dialog's own comment — "junk is just
    'no guess', never an error dialog" — is a decision worth keeping: an
    optional guess is not worth stopping someone with a modal. So this
    understands more instead of complaining more, which removes most of the
    loss without adding the dialog that was ruled out.

    Returns ``None`` for text it cannot read, so a caller can tell that
    apart from a real zero; the editor maps both to "no guess".
    """
    text = (text or "").strip().lower()
    if not text:
        return 0
    if text.startswith("~"):
        text = text[1:].strip()
    if text.startswith("about "):
        text = text[6:].strip()

    unit, factor = "", 1
    for suffix, scale in (("minutes", 1), ("minute", 1), ("mins", 1), ("min", 1),
                          ("hours", 60), ("hour", 60), ("hrs", 60), ("hr", 60),
                          ("m", 1), ("h", 60)):
        if text.endswith(suffix):
            unit, factor = suffix, scale
            break
    if unit:
        text = text[: -len(unit)].strip()
    if not text:
        return None  # a bare "mins" says no number at all

    try:
        amount = float(text)
    except ValueError:
        return None
    if amount < 0:
        return None
    # Same ceiling the store uses; a guess is a guess, not a workday plan.
    return max(0, min(480, round(amount * factor)))


def humanize_date(iso: str, on: str | None = None) -> str:
    """A date in the units a time-blind brain actually acts on.

    "2026-08-22" is flat data that needs deliberate date arithmetic —
    everything beyond now collapses into "not now". "Fri" and "in 12 days"
    are pre-computed temporal distance. The inverse of parse_date_input.
    """
    try:
        target = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    base = date.fromisoformat(on) if on else date.today()
    delta = (target - base).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if 2 <= delta <= 6:
        return target.strftime("%a")
    if 7 <= delta <= 14:
        return f"in {delta} days"
    if delta == -1:
        return "yesterday"
    if delta < 0:
        # A short, plain date — deliberately NOT the weekday form used for
        # the near future. "Thu" two days ahead is unambiguous; "Thu" in
        # the past could be four days ago or eleven, and a date you cannot
        # place is the thing this function exists to prevent. (%-d is not
        # available on Windows, and this app ships a run.bat.)
        #
        # The year is carried only when it differs, for the same reason.
        # Without it "22 Dec" on a task booked last year reads as the
        # *coming* December, especially beside a row saying "in 7 days" —
        # and a two-year-old booking was indistinguishable from a
        # two-week-old one. This app is built for people who keep tasks
        # around, so a stale booking is the ordinary case, not an edge.
        # Same-year dates stay short: "1 Aug" is already placeable.
        if target.year != base.year:
            return f"{target.day} {target.strftime('%b')} {target.year}"
        return f"{target.day} {target.strftime('%b')}"
    return iso  # far future stays a plain date


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, KIND_LABELS[KIND_UNSET])


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_str(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_minutes(value) -> int:
    """A minutes estimate: 0 (no guess) to 8 hours, junk becomes no guess."""
    try:
        return max(0, min(480, int(value)))
    except (TypeError, ValueError):
        return 0


def _as_tags(value) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    tags: list[str] = []
    for tag in value:
        if not isinstance(tag, str):
            continue
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


# key -> (label, how the next date is worked out). Deliberately small: a
# recurrence grammar with "every 3rd Tuesday" in it is a second app, and the
# things this audience actually loses are bins, meds, bills and standing
# appointments — all of which fit here.
REPEATS: dict[str, str] = {
    "": "Does not repeat",
    "daily": "Every day",
    "weekdays": "Every weekday",
    "weekly": "Every week",
    "fortnightly": "Every two weeks",
    "monthly": "Every month",
}
REPEAT_KEYS = tuple(REPEATS)
REPEAT_LABELS = tuple(REPEATS.values())
REPEAT_KEY_BY_LABEL = {label: key for key, label in REPEATS.items()}


def repeat_label(repeat: str) -> str:
    return REPEATS.get(repeat, REPEATS[""])


def next_occurrence(repeat: str, scheduled_for: str = "", on: str | None = None) -> str:
    """The next day a repeating task is wanted, or "" if it does not repeat.

    Two rules, and the second one is the whole reason this is a function
    rather than a line of arithmetic:

    **Never generate a backlog.** The next date is worked out from *today*
    whenever the booking has already passed. Miss the bins for a fortnight and
    you come back to one task asking about the next collection — not fourteen
    copies of a task you already feel bad about. A pile of overdue duplicates
    is the single most reliable way to make someone stop opening an app.

    **Keep the rhythm when you are on time.** If the booking is still ahead
    (you did it early), the next one is counted from the booking, so a
    Tuesday task stays a Tuesday task instead of drifting a day earlier every
    week.
    """
    if repeat not in REPEATS or not repeat:
        return ""
    from datetime import date, timedelta

    today = on or today_iso()
    try:
        base = date.fromisoformat(scheduled_for) if scheduled_for else None
    except ValueError:
        base = None
    try:
        floor = date.fromisoformat(today)
    except ValueError:
        floor = date.fromisoformat(today_iso())
    if base is None or base < floor:
        base = floor

    if repeat == "daily":
        return (base + timedelta(days=1)).isoformat()
    if repeat == "weekdays":
        nxt = base + timedelta(days=1)
        while nxt.weekday() >= 5:  # Saturday, Sunday
            nxt += timedelta(days=1)
        return nxt.isoformat()
    if repeat == "weekly":
        return (base + timedelta(days=7)).isoformat()
    if repeat == "fortnightly":
        return (base + timedelta(days=14)).isoformat()
    # monthly: the same day next month, pulled back to the last day of a
    # shorter one so the 31st does not silently skip February.
    year, month = base.year + (base.month // 12), base.month % 12 + 1
    import calendar

    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


@dataclass
class Task:
    """A single item on the active stack.

    ``id`` is what the UI uses to map a listbox row back to a task; relying on
    value equality breaks as soon as two tasks share the same text.
    """

    text: str
    done: bool = False
    created_at: str = field(default_factory=now_stamp)
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    completed_at: str | None = None
    description: str = ""
    id: str = field(default_factory=new_id)
    # The concrete two-minute action that gets you moving. Knowing what to do
    # is not the same as being able to start, and a vague task is much harder
    # to begin than a specific first move.
    first_step: str = ""
    # How the task feels to start (see TASK_KINDS), so you can pick work that
    # matches the state you are actually in.
    kind: str = KIND_UNSET
    scheduled_for: str = ""  # YYYY-MM-DD, or "" for unscheduled
    # Pinned tasks sort above everything open in the default order. This is
    # what "move to top" always promised: an anchor for the thing you are
    # afraid of losing track of, one that survives every re-sort.
    pinned: bool = False
    # "Not today": excused from NEXT UP / "Where do I start?" until this
    # date (YYYY-MM-DD, exclusive). Never filters the task list itself, has
    # no badge and no counter, and expires silently.
    snoozed_until: str = ""
    # "About how long?" in minutes; 0 means no guess. A written guess is
    # what makes time-sense calibrate: compared later with what the sessions
    # actually took — as data, never as a mark.
    estimate_minutes: int = 0
    # How often this comes back round (see REPEATS). Finishing a repeating
    # task completes *this* one and books the next, so the week review still
    # holds the evidence that you did it — a task that quietly reset its own
    # date would erase the record, which is the one thing that screen is for.
    repeat: str = ""

    def __post_init__(self) -> None:
        self.text = _as_str(self.text).strip()
        self.description = _as_str(self.description)
        self.tags = _as_tags(self.tags)
        self.priority = 1 if self.priority else 0
        self.done = _as_bool(self.done)
        self.pinned = _as_bool(self.pinned)
        self.snoozed_until = _as_str(self.snoozed_until).strip()
        self.estimate_minutes = _as_minutes(self.estimate_minutes)
        self.first_step = _as_str(self.first_step).strip()
        # An unknown repeat becomes "does not repeat" rather than an error:
        # same reason an unknown kind becomes Unsorted.
        self.repeat = self.repeat if self.repeat in REPEATS else ""
        self.kind = self.kind if self.kind in TASK_KINDS else KIND_UNSET
        self.scheduled_for = _as_str(self.scheduled_for).strip()
        if not self.created_at:
            self.created_at = now_stamp()
        if not self.done:
            self.completed_at = None

    @property
    def is_ready(self) -> bool:
        """True when the task already says how to begin."""
        return bool(self.first_step)

    def is_due(self, on: str | None = None) -> bool:
        """Scheduled for today or earlier (an overdue block is still due)."""
        if not self.scheduled_for:
            return False
        return self.scheduled_for <= (on or today_iso())

    # -- state changes -------------------------------------------------
    def set_done(self, done: bool) -> None:
        self.done = bool(done)
        self.completed_at = now_stamp() if self.done else None

    def next_instance(self, on: str | None = None) -> "Task | None":
        """The next round of a repeating task, or ``None`` if it does not.

        A fresh, open task rather than a reset of this one. Resetting would
        quietly delete the evidence that you did it, and the week review — the
        screen whose whole job is answering "I did nothing this week" — reads
        exactly that evidence. Doing the bins six weeks running should look
        like six things done, not like one task that is somehow never
        finished.
        """
        when = next_occurrence(self.repeat, self.scheduled_for, on)
        if not when:
            return None
        nxt = Task.from_dict(self.to_dict())
        nxt.id = new_id()
        nxt.created_at = now_stamp()
        nxt.done = False
        nxt.completed_at = None
        nxt.scheduled_for = when
        # A snooze belongs to the round it was taken in; carrying it forward
        # would silently excuse the next one too.
        nxt.snoozed_until = ""
        return nxt


    def add_tag(self, tag: str) -> bool:
        cleaned = tag.strip().lower()
        if not cleaned or cleaned in self.tags:
            return False
        self.tags.append(cleaned)
        return True

    def remove_tag(self, tag: str) -> bool:
        cleaned = tag.strip().lower()
        if cleaned not in self.tags:
            return False
        self.tags.remove(cleaned)
        return True

    def matches(self, term: str) -> bool:
        """Case-insensitive search across title, description and tags."""
        term = term.strip().lower()
        if not term:
            return True
        haystack = (self.text, self.description, self.first_step)
        if any(term in part.lower() for part in haystack):
            return True
        return any(term in tag for tag in self.tags)

    # -- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "created_at": self.created_at,
            "priority": self.priority,
            "tags": list(self.tags),
            "completed_at": self.completed_at,
            "description": self.description,
            "first_step": self.first_step,
            "kind": self.kind,
            "scheduled_for": self.scheduled_for,
            "pinned": self.pinned,
            "snoozed_until": self.snoozed_until,
            "estimate_minutes": self.estimate_minutes,
            "repeat": self.repeat,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Build a task from stored JSON, tolerating older/partial records."""
        if not isinstance(data, dict):
            raise ValueError("task record must be an object")
        completed_at = data.get("completed_at")
        return cls(
            text=_as_str(data.get("text")),
            done=_as_bool(data.get("done")),
            created_at=_as_str(data.get("created_at")),
            priority=1 if data.get("priority") else 0,
            tags=_as_tags(data.get("tags")),
            completed_at=completed_at if isinstance(completed_at, str) else None,
            description=_as_str(data.get("description")),
            id=_as_str(data.get("id")) or new_id(),
            first_step=_as_str(data.get("first_step")),
            kind=_as_str(data.get("kind")),
            scheduled_for=_as_str(data.get("scheduled_for")),
            pinned=_as_bool(data.get("pinned")),
            snoozed_until=_as_str(data.get("snoozed_until")),
            estimate_minutes=_as_minutes(data.get("estimate_minutes")),
            repeat=_as_str(data.get("repeat")),
        )

    def copy(self) -> "Task":
        return Task.from_dict(self.to_dict())


@dataclass
class Note:
    """A timestamped scratchpad line (kept for reading pre-2.0 save files)."""

    text: str
    created_at: str = field(default_factory=now_stamp)

    def to_dict(self) -> dict:
        return {"text": self.text, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            text=_as_str(data.get("text")),
            created_at=_as_str(data.get("created_at")) or now_stamp(),
        )

    def render(self) -> str:
        return f"[{self.created_at}] {self.text}" if self.created_at else self.text


@dataclass
class MatrixTask:
    """A task living in one of the four Eisenhower quadrants (one file each)."""

    title: str
    content: str = ""
    category: str = "do_first"
    created_at: str = field(default_factory=now_stamp)
    updated_at: str = field(default_factory=now_stamp)
    id: str = field(default_factory=new_id)
    first_step: str = ""
    kind: str = KIND_UNSET
    # Booking a time is what makes an important-but-not-urgent task actually
    # happen; without it the Schedule quadrant is where things go to be
    # forgotten.
    scheduled_for: str = ""
    tags: list[str] = field(default_factory=list)
    priority: int = 0
    pinned: bool = False
    estimate_minutes: int = 0
    # Handing a task to an agent and then forgetting it is not delegating, it
    # is losing it somewhere more respectable. These three are what make the
    # Delegate quadrant safe to actually use: who has it, since when, and the
    # day it comes back to you on its own.
    handed_to: str = ""
    handed_off_on: str = ""
    follow_up_on: str = ""
    # Absolute path of the backing file; assigned by the store, never stored.
    path: object = None

    def __post_init__(self) -> None:
        # Same coercion as Task: an unknown kind would otherwise render as a
        # badge with no colour and no meaning.
        self.kind = self.kind if self.kind in TASK_KINDS else KIND_UNSET
        self.tags = _as_tags(self.tags)
        self.priority = 1 if self.priority else 0
        self.pinned = _as_bool(self.pinned)
        self.estimate_minutes = _as_minutes(self.estimate_minutes)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "first_step": self.first_step,
            "kind": self.kind,
            "scheduled_for": self.scheduled_for,
            "tags": list(self.tags),
            "priority": self.priority,
            "pinned": self.pinned,
            "estimate_minutes": self.estimate_minutes,
            "handed_to": self.handed_to,
            "handed_off_on": self.handed_off_on,
            "follow_up_on": self.follow_up_on,
        }

    @classmethod
    def from_dict(cls, data: dict, category: str = "do_first") -> "MatrixTask":
        return cls(
            title=_as_str(data.get("title")).strip(),
            content=_as_str(data.get("content")),
            category=_as_str(data.get("category")) or category,
            created_at=_as_str(data.get("created_at")) or now_stamp(),
            updated_at=_as_str(data.get("updated_at")) or now_stamp(),
            id=_as_str(data.get("id")) or new_id(),
            first_step=_as_str(data.get("first_step")),
            kind=_as_str(data.get("kind")),
            scheduled_for=_as_str(data.get("scheduled_for")),
            tags=_as_tags(data.get("tags")),
            priority=1 if data.get("priority") else 0,
            pinned=_as_bool(data.get("pinned")),
            estimate_minutes=_as_minutes(data.get("estimate_minutes")),
            handed_to=_as_str(data.get("handed_to")),
            handed_off_on=_as_str(data.get("handed_off_on")),
            follow_up_on=_as_str(data.get("follow_up_on")),
        )

    def copy(self) -> "MatrixTask":
        """A detached duplicate, including the file it came from.

        ``path`` is carried across deliberately even though ``to_dict`` omits
        it: it is *where this task lives*, not part of what it says. An undo
        that wrote the old data to a freshly chosen filename would leave the
        task on screen twice.
        """
        clone = MatrixTask.from_dict(self.to_dict(), self.category)
        clone.path = self.path
        return clone

    @property
    def is_ready(self) -> bool:
        return bool(self.first_step)

    def is_due(self, on: str | None = None) -> bool:
        if not self.scheduled_for:
            return False
        return self.scheduled_for <= (on or today_iso())

    def is_waiting(self) -> bool:
        """Out with someone (or something) else, and not back yet."""
        return bool(self.handed_to or self.handed_off_on)

    def is_due_back(self, on: str | None = None) -> bool:
        """Inclusive of the past, exactly like ``is_due``: a follow-up you
        missed still deserves a route back rather than silently expiring."""
        if not self.is_waiting() or not self.follow_up_on:
            return False
        return self.follow_up_on <= (on or today_iso())

    def to_task(self) -> Task:
        """Convert back into a main-list task, keeping every field."""
        return Task(
            text=self.title,
            description=self.content,
            created_at=now_stamp(),
            first_step=self.first_step,
            kind=self.kind,
            scheduled_for=self.scheduled_for,
            tags=list(self.tags),
            priority=self.priority,
            pinned=self.pinned,
            estimate_minutes=self.estimate_minutes,
        )
