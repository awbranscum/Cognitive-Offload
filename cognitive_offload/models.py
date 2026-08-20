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


# Fields that belong to the round they were set in, not to the task itself,
# and so are reset when a repeat books its next round. Everything else on a
# Task is setup you did once and should carry forward.
#
# A mapping rather than a list of names because not everything here resets to
# "": how far down the plan you got is a number, and blanking it would have
# put a string where an int belongs — the sort of thing a list of names
# cannot even express, let alone catch.
PER_ROUND_FIELDS: dict = {
    "snoozed_until": "",
    "handed_to": "",
    "handed_off_on": "",
    "follow_up_on": "",
    # The plan carries forward; your place in it does not. Next week's bins
    # start at the first step again, which is the whole point of a routine.
    "steps_done": 0,
}


def as_records(value) -> list:
    """The records in a field that is meant to hold a list of them.

    Anything that is not a list or tuple is **not** a short list — it is an
    unreadable field, and this returns nothing for it. Two bugs came from
    iterating the raw value instead. A string was walked character by
    character, so ``"tasks": "nope"`` was reported to the person as *"4 task
    records couldn't be read"* — a loss count invented out of a string's
    length, in an app whose whole promise is telling the truth about their
    stuff. And a number is not iterable at all, so ``"tasks": 42`` raised a
    TypeError out of the loader, past every StorageError the recovery code
    catches, and the app did not open.

    The two model coercions below have always done this. The store loaders
    did not, which is the whole distance between "your file is damaged, here
    is what I saved" and a traceback.
    """
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_steps(value) -> list[str]:
    """Coerce whatever was in the file into a list of non-empty steps."""
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return []
    return [text for text in (_as_str(v).strip() for v in value) if text]


def _fix_steps(item) -> None:
    """Hold the one invariant this feature rests on.

    ``first_step`` has forty-seven readers across seven modules and is what
    ``is_ready`` — and so the whole "what should I start?" ranking — is built
    on. Adding a plan must not add a *second* answer to "what next", so a
    task with steps defines ``first_step`` as ``steps[steps_done]`` and this
    is the only place that says so. Self-healing on load: a hand-edited file
    whose first_step has drifted from its plan is put back rather than
    believed.
    """
    item.steps = _as_steps(item.steps)
    if len(item.steps) <= 1:
        # A plan of one step is just a first step, which the app already has
        # a field, a badge and a whole vocabulary for. Two ways to say the
        # same thing is how they drift — and a row reading "step 1 of 1" is
        # the drift arriving. Reachable by deleting the only other step, not
        # just by hand-editing a file.
        if item.steps:
            item.first_step = item.steps[0]
        item.steps = []
        item.steps_done = 0
        return
    try:
        cursor = int(item.steps_done)
    except (TypeError, ValueError):
        cursor = 0
    item.steps_done = max(0, min(cursor, len(item.steps) - 1))
    item.first_step = item.steps[item.steps_done]


def _rest_of_plan(item) -> list[str]:
    """The steps after the one you are on. What the editor shows and edits.

    The current step is NOT in this list, and that is the whole reason the
    editor can hold both without them fighting: the step box owns one line,
    the plan box owns the rest, and neither can overwrite the other's.
    """
    if not item.steps:
        return []
    return list(item.steps[item.steps_done + 1:])


def _set_rest(item, rest) -> None:
    """Replace everything after the current step, keeping your place.

    Rewriting what is left to do must not throw away the fact that you have
    already done three of them, so the head of the plan — up to and including
    the step you are on — is kept exactly as it was.
    """
    rest = _as_steps(rest)
    if item.steps:
        head = list(item.steps[:item.steps_done + 1])
    else:
        head = [item.first_step] if item.first_step else []
    item.steps = head + rest
    _fix_steps(item)


def _set_current_step(item, text: str) -> None:
    """Reword what you are about to do, wherever it happens to be stored.

    Without this, editing the step box on a task that has a plan would write
    to ``first_step`` alone and the two would disagree until the next load
    silently reverted it.
    """
    text = _as_str(text).strip()
    item.first_step = text
    if item.steps and 0 <= item.steps_done < len(item.steps):
        item.steps[item.steps_done] = text
        if not text:
            # An emptied step is a removed step, not a blank one sitting in
            # the middle of the plan.
            del item.steps[item.steps_done]
            _fix_steps(item)


def _advance_step(item) -> bool:
    """Tick this step off and move to the next. False when there is no next.

    Deliberately a cursor rather than a pop: the plan describes the task, so
    a repeating task has to be able to hand the *whole* plan to its next
    round. Steps consumed destructively could not.
    """
    if not item.steps or item.steps_done >= len(item.steps) - 1:
        return False
    item.steps_done += 1
    item.first_step = item.steps[item.steps_done]
    return True


def _steps_left(item) -> int:
    """How many steps come after this one. 0 when there is no plan."""
    if not item.steps:
        return 0
    return max(0, len(item.steps) - item.steps_done - 1)


def _is_waiting(item) -> bool:
    """Out with someone (or something) else, and not back yet.

    A free function rather than a method on each model, because both tabs ask
    it and two copies of a predicate is how the two tabs' answers drift apart
    — which is the bug this whole area exists to stop.
    """
    return bool(getattr(item, "handed_to", "") or getattr(item, "handed_off_on", ""))


def snooze_is_live(snoozed_until: str, on: str | None = None) -> bool:
    """Is this "not today" date still in the future?

    Takes the date rather than the task, because the task editor holds the
    value as a plain string and had written the comparison out for itself.
    That inline copy is how the rule ends up with two answers.
    """
    value = (snoozed_until or "").strip()
    return bool(value) and value > (on or today_iso())


def _is_snoozed(item, on: str | None = None) -> bool:
    """Put down until a later day — "not today", and still not today.

    The rule lived inline in ``rank_for_starting`` while it had one reader.
    It has two now, and the second one is the focus card, which sits ABOVE
    the slot that rule protects: two copies of this predicate would let the
    most prominent thing on the screen go on naming a task the list itself
    had agreed to stop naming.
    """
    return snooze_is_live(getattr(item, "snoozed_until", ""), on)


def _is_put_down(item, on: str | None = None) -> bool:
    """True when you have deliberately set this task aside for now.

    Snoozed, or out with someone and not due back. Both mean the same thing
    to anything that would otherwise tell you to get on with it: **not now**,
    decided by you, and the app does not get to reopen the question.
    """
    return _is_snoozed(item, on) or (_is_waiting(item) and not _is_due_back(item, on))


def _is_due_back(item, on: str | None = None) -> bool:
    """Inclusive of the past, exactly like ``is_due``: a follow-up you missed
    still deserves a route back rather than silently expiring."""
    follow_up = getattr(item, "follow_up_on", "")
    if not _is_waiting(item) or not follow_up:
        return False
    return follow_up <= (on or today_iso())


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
    # Who has it, since when, and when it comes back. These live on both
    # models: a task handed to an agent and then moved to the main list used
    # to arrive with no trace of the handoff at all, which is exactly the
    # disappearance the feature exists to prevent.
    handed_to: str = ""
    handed_off_on: str = ""
    follow_up_on: str = ""
    # The rest of the plan, and how far down it you are. "Write the report"
    # is a wall; "open last year's, copy the headings, fill in the numbers"
    # is three things you can start. The task used to hold exactly ONE step,
    # so the moment it was done the task was a blank wall again and every
    # transition charged a fresh decision — the one thing this app's own
    # design rules say not to charge for.
    #
    # `steps_done` is a cursor, not a tick list: see _advance_step.
    steps: list[str] = field(default_factory=list)
    steps_done: int = 0

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
        # Last, because it can rewrite first_step and needs the coercions
        # above to have run first.
        _fix_steps(self)

    # -- the plan ------------------------------------------------------
    @property
    def rest_of_plan(self) -> list[str]:
        return _rest_of_plan(self)

    def set_rest(self, rest) -> None:
        _set_rest(self, rest)

    def set_current_step(self, text: str) -> None:
        _set_current_step(self, text)

    def advance_step(self) -> bool:
        return _advance_step(self)

    @property
    def steps_left(self) -> int:
        return _steps_left(self)

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

    def is_waiting(self) -> bool:
        return _is_waiting(self)

    def is_snoozed(self, on: str | None = None) -> bool:
        return _is_snoozed(self, on)

    def is_put_down(self, on: str | None = None) -> bool:
        return _is_put_down(self, on)

    def is_due_back(self, on: str | None = None) -> bool:
        return _is_due_back(self, on)

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
        # would silently excuse the next one too. The handoff marks are the
        # same shape and were missed when they were added: the next round
        # arrived already claiming to be out with an agent that had never
        # been given it, and every round after that inherited the claim.
        # `tests/test_repeat_rounds` now classifies every field so the next
        # one added has to be decided rather than silently inherited.
        for field_name, blank in PER_ROUND_FIELDS.items():
            setattr(nxt, field_name, blank)
        # The resets happen after construction, so the plan invariant has to
        # be restored by hand: a round that starts at step one must say the
        # first step, not the last one the previous round reached.
        _fix_steps(nxt)
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
        """Case-insensitive search across everything the person wrote.

        Including **every step of the plan**, not just the one you are on.
        A step is something you typed, and this app says out loud that a task
        stays "in every search" and that hiding one is the thing it will not
        do — so searching for a step and getting nothing back is not a small
        gap, it is the search box teaching you to distrust it.
        """
        term = term.strip().lower()
        if not term:
            return True
        haystack = (self.text, self.description, self.first_step, *self.steps)
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
            "handed_to": self.handed_to,
            "handed_off_on": self.handed_off_on,
            "follow_up_on": self.follow_up_on,
            "steps": list(self.steps),
            "steps_done": self.steps_done,
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
            handed_to=_as_str(data.get("handed_to")),
            handed_off_on=_as_str(data.get("handed_off_on")),
            follow_up_on=_as_str(data.get("follow_up_on")),
            steps=_as_steps(data.get("steps")),
            steps_done=data.get("steps_done", 0),
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
    # Inert in a quadrant — the matrix has no "done" to trigger the next
    # round, and nothing here reads a snooze — but both are carried so a trip
    # through the matrix does not quietly strip them off a task.
    repeat: str = ""
    snoozed_until: str = ""
    # The plan, and how far down it you are — same meaning as on Task, and
    # carried for the same reason the handoff marks are: a task broken down
    # on the main list must not arrive here as a wall again.
    steps: list[str] = field(default_factory=list)
    steps_done: int = 0
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
        self.repeat = self.repeat if self.repeat in REPEATS else ""
        _fix_steps(self)

    # -- the plan ------------------------------------------------------
    @property
    def rest_of_plan(self) -> list[str]:
        return _rest_of_plan(self)

    def set_rest(self, rest) -> None:
        _set_rest(self, rest)

    def set_current_step(self, text: str) -> None:
        _set_current_step(self, text)

    def advance_step(self) -> bool:
        return _advance_step(self)

    @property
    def steps_left(self) -> int:
        return _steps_left(self)

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
            "repeat": self.repeat,
            "snoozed_until": self.snoozed_until,
            "steps": list(self.steps),
            "steps_done": self.steps_done,
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
            repeat=_as_str(data.get("repeat")),
            snoozed_until=_as_str(data.get("snoozed_until")),
            steps=_as_steps(data.get("steps")),
            steps_done=data.get("steps_done", 0),
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
        return _is_waiting(self)

    def is_snoozed(self, on: str | None = None) -> bool:
        return _is_snoozed(self, on)

    def is_put_down(self, on: str | None = None) -> bool:
        return _is_put_down(self, on)

    def is_due_back(self, on: str | None = None) -> bool:
        return _is_due_back(self, on)

    def to_task(self) -> Task:
        """Convert back into a main-list task.

        Carries everything the two models share, including the handoff marks
        — a task out with an agent used to arrive here with no trace of that
        at all, which is the disappearance the handoff exists to prevent,
        walked in through a different door.

        Four things deliberately do not cross, and ``tests/test_conversions``
        holds the list with a reason for each: the id and ``created_at``
        (a move makes a new record), and ``done``/``completed_at`` (a
        quadrant has no finished state to come back from).
        """
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
            repeat=self.repeat,
            snoozed_until=self.snoozed_until,
            handed_to=self.handed_to,
            handed_off_on=self.handed_off_on,
            follow_up_on=self.follow_up_on,
            steps=list(self.steps),
            steps_done=self.steps_done,
        )
