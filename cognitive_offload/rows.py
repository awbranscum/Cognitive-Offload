"""How a task renders as a list row — shared between the two tabs.

The badge and subtitle logic used to be copy-pasted between the main list
and the matrix quadrants, so any wording change had to be made twice and
drift would mean the same task reading differently on the two tabs. Both
builders now feed from the same helpers. UI-free: imports no tkinter.
"""

from __future__ import annotations

from .models import Task, humanize_date, kind_label
from .queries import SORT_ORDERS
from .widgets import Badge, Row


def _shared_badges(item) -> list[Badge]:
    """Badges every open task shows, main list or matrix alike."""
    badges = []
    if item.kind:
        badges.append(Badge(kind_label(item.kind).split(" ")[0].lower(), item.kind))
    if item.is_ready:
        badges.append(Badge("ready", "ready"))
    if item.scheduled_for:
        # An overdue booking is a nudge, not a telling-off.
        badges.append(Badge(
            "today" if item.is_due()
            else f"booked {humanize_date(item.scheduled_for)}",
            "today" if item.is_due() else "booked",
        ))
    if item.estimate_minutes:
        badges.append(Badge(f"~{item.estimate_minutes} min", "estimate"))
    return badges


def task_row(task: Task) -> Row:
    """A task as a list row: title, first step underneath, badges alongside."""
    badges = []
    if task.done:
        badges.append(Badge("done", "done"))
    else:
        if task.pinned:
            badges.append(Badge("pinned", "pinned"))
        badges.extend(_shared_badges(task))
    badges.extend(Badge(f"#{tag}", "tag") for tag in task.tags)

    if task.done and task.completed_at:
        subtitle = f"done {task.completed_at}"
    elif task.first_step:
        subtitle = f"→ {task.first_step}"
    elif task.description.strip():
        subtitle = task.description.strip().splitlines()[0][:80]
    else:
        subtitle = ""

    return Row(id=task.id, title=task.text, subtitle=subtitle, badges=badges,
               done=task.done, flagged=bool(task.priority))


def matrix_row(task) -> Row:
    badges = _shared_badges(task)
    subtitle = f"→ {task.first_step}" if task.first_step else (
        task.content.strip().splitlines()[0][:80] if task.content.strip() else ""
    )
    return Row(id=task.id, title=task.title, subtitle=subtitle, badges=badges,
               marker="·")


def focus_caption(task: Task | None, first_step: str) -> str:
    if task is None:
        return f"Free focus — {first_step}" if first_step else "Free focus"
    return f"{task.text}\n→ {first_step}" if first_step else task.text


def sort_label(order: str) -> str:
    for label, key in SORT_ORDERS.items():
        if key == order:
            return label
    return "Priority"
