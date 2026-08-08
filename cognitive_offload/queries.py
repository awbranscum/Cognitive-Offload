"""Filtering and sorting of the task list.

Pure functions over lists of :class:`~cognitive_offload.models.Task`; the UI
only ever renders whatever ``visible_tasks`` returns.
"""

from __future__ import annotations

from .models import KIND_UNSET, Task, today_iso

# Label shown in the combobox -> internal sort key.
SORT_ORDERS: dict[str, str] = {
    "Priority": "priority",
    "Created": "created",
    "Alphabetical": "alpha",
    "Completed": "completed",
}
DEFAULT_SORT = "priority"
ALL_KINDS = "(any feel)"


def filter_tasks(
    tasks: list[Task],
    search: str = "",
    tag: str | None = None,
    show_done: bool = True,
    kind: str | None = None,
) -> list[Task]:
    result = list(tasks)
    search = (search or "").strip()
    if search:
        result = [t for t in result if t.matches(search)]
    tag = (tag or "").strip().lower()
    if tag:
        result = [t for t in result if tag in t.tags]
    if kind:
        result = [t for t in result if t.kind == kind]
    if not show_done:
        result = [t for t in result if not t.done]
    return result


def sort_tasks(tasks: list[Task], order: str = DEFAULT_SORT) -> list[Task]:
    """Return a new list ordered by ``order``.

    ``priority`` keeps open work at the top: unfinished before finished, then
    flagged before unflagged, then newest first.
    """
    items = list(tasks)
    if order == "created":
        return sorted(items, key=lambda t: t.created_at, reverse=True)
    if order == "alpha":
        return sorted(items, key=lambda t: (t.done, t.text.casefold()))
    if order == "completed":
        # Most recently completed first, then everything still open.
        return sorted(items, key=lambda t: (not t.done, _descending(t.completed_at or "")))
    return sorted(items, key=lambda t: (
        t.done, -int(t.pinned), -t.priority, _descending(t.created_at)))


def _descending(value: str) -> tuple[int, ...]:
    """Sort key that reverses a timestamp string without reversing the tuple."""
    return tuple(-ord(ch) for ch in value)


def visible_tasks(
    tasks: list[Task],
    search: str = "",
    tag: str | None = None,
    order: str = DEFAULT_SORT,
    show_done: bool = True,
    kind: str | None = None,
) -> list[Task]:
    return sort_tasks(filter_tasks(tasks, search, tag, show_done, kind), order)


def all_tags(tasks: list[Task]) -> list[str]:
    tags: set[str] = set()
    for task in tasks:
        tags.update(task.tags)
    return sorted(tags)


def counts(tasks: list[Task]) -> tuple[int, int, int]:
    """(open, done, flagged-and-open) counters for the status bar."""
    done = sum(1 for t in tasks if t.done)
    flagged = sum(1 for t in tasks if t.priority and not t.done)
    return len(tasks) - done, done, flagged


def done_today(tasks: list[Task], on: str | None = None) -> list[Task]:
    """What you finished today, most recent last.

    The app records ``completed_at`` but never showed it back, so the only
    number on screen was how much was left. This is the other half.
    """
    on = on or today_iso()
    finished = [t for t in tasks if t.done and (t.completed_at or "")[:10] == on]
    return sorted(finished, key=lambda t: t.completed_at or "")


def completed_titles_today(tasks: list[Task], log: list | None = None,
                           on: str | None = None) -> list[str]:
    """Everything finished today: still on the list, or cleared away since.

    Tidying up should not delete the answer to "what did I get done today".
    """
    on = on or today_iso()
    titles = [t.text for t in done_today(tasks, on)]
    for entry in log or []:
        if str(entry.get("completed_at", ""))[:10] == on and entry.get("text") not in titles:
            titles.append(entry["text"])
    return titles


def due_tasks(tasks: list[Task], on: str | None = None) -> list[Task]:
    """Open tasks with a booked time of today or earlier, soonest first."""
    on = on or today_iso()
    due = [t for t in tasks if not t.done and t.is_due(on)]
    return sorted(due, key=lambda t: t.scheduled_for)


def rank_for_starting(tasks: list[Task], kind: str | None = None, on: str | None = None) -> list[Task]:
    """Order open tasks by how easy they are to *start*, best first.

    Knowing what matters most is not the problem; getting moving is. So this
    ranks by the things that lower the activation energy rather than by
    importance:

    * a task that already names its first step is far easier to begin;
    * a booked time that has arrived is the whole point of booking it;
    * a flagged task still beats an unflagged one, all else being equal.

    ``kind`` narrows the list to work that feels a particular way. Tasks with
    no kind set always stay in the running - being unsorted should never make
    a task invisible.
    """
    on = on or today_iso()
    candidates = [t for t in tasks if not t.done]
    if kind:
        candidates = [t for t in candidates if t.kind == kind or t.kind == KIND_UNSET]

    def score(task: Task) -> tuple:
        return (
            -(3 if task.is_ready else 0)
            - (3 if task.is_due(on) else 0)
            - (2 if task.priority else 0)
            # A pinned task the app never suggests becomes a guilt fixture:
            # always at the top of the list, never the thing you are invited
            # to start. Same weight as the flag, still below a written first
            # step or an arrived booking.
            - (2 if task.pinned else 0)
            - (1 if kind and task.kind == kind else 0)
            # Captured today: it is the thing currently on your mind, and the
            # age tiebreak below would otherwise bury it under everything old.
            - (1 if task.created_at[:10] == on else 0),
            task.created_at,  # older first: it has waited long enough
            task.text.casefold(),
        )

    return sorted(candidates, key=score)


def suggest_tasks(
    tasks: list[Task],
    kind: str | None = None,
    limit: int = 3,
    offset: int = 0,
    on: str | None = None,
) -> list[Task]:
    """A short shortlist. Long lists are the thing that causes the freeze."""
    ranked = rank_for_starting(tasks, kind, on)
    if not ranked:
        return []
    limit = max(1, limit)
    start = offset % len(ranked)
    # Wrap around so "show me others" keeps cycling instead of dead-ending.
    doubled = ranked + ranked
    return doubled[start:start + limit][:len(ranked)]


def split_lines(raw: str) -> list[str]:
    """Split a scratchpad blob into task-sized lines.

    Strips bullet/checkbox decoration and any ``[timestamp]`` prefix added by
    quick capture, and drops blank lines.
    """
    lines: list[str] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        line = line.lstrip("-*•+ \t")
        for marker in ("[ ] ", "[x] ", "[X] "):
            if line.startswith(marker):
                line = line[len(marker):]
        if line.startswith("[") and "] " in line:
            head, _, tail = line.partition("] ")
            # Only treat it as a timestamp prefix, not as real content.
            if head[1:].replace("-", "").replace(":", "").replace(" ", "").isdigit():
                line = tail
        line = line.strip()
        if line:
            lines.append(line)
    return lines
