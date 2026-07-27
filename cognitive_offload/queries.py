"""Filtering and sorting of the task list.

Pure functions over lists of :class:`~cognitive_offload.models.Task`; the UI
only ever renders whatever ``visible_tasks`` returns.
"""

from __future__ import annotations

from .models import Task

# Label shown in the combobox -> internal sort key.
SORT_ORDERS: dict[str, str] = {
    "Priority": "priority",
    "Created": "created",
    "Alphabetical": "alpha",
    "Completed": "completed",
}
DEFAULT_SORT = "priority"


def filter_tasks(
    tasks: list[Task],
    search: str = "",
    tag: str | None = None,
    show_done: bool = True,
) -> list[Task]:
    result = list(tasks)
    search = (search or "").strip()
    if search:
        result = [t for t in result if t.matches(search)]
    tag = (tag or "").strip().lower()
    if tag:
        result = [t for t in result if tag in t.tags]
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
    return sorted(items, key=lambda t: (t.done, -t.priority, _descending(t.created_at)))


def _descending(value: str) -> tuple[int, ...]:
    """Sort key that reverses a timestamp string without reversing the tuple."""
    return tuple(-ord(ch) for ch in value)


def visible_tasks(
    tasks: list[Task],
    search: str = "",
    tag: str | None = None,
    order: str = DEFAULT_SORT,
    show_done: bool = True,
) -> list[Task]:
    return sort_tasks(filter_tasks(tasks, search, tag, show_done), order)


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
