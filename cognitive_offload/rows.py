"""How a task renders as a list row — shared between the two tabs.

The badge and subtitle logic used to be copy-pasted between the main list
and the matrix quadrants, so any wording change had to be made twice and
drift would mean the same task reading differently on the two tabs. Both
builders now feed from the same helpers.

This module decides what a row *says*; it never draws one. It imports no
UI toolkit, so a front-end on any platform can reuse these decisions
instead of re-deriving which tasks read as "ready" — which is exactly why
a task's badges stay identical wherever it appears.
"""

from __future__ import annotations

from .models import Task, humanize_date, kind_label, today_iso
from .queries import SORT_ORDERS
from .viewmodels import Badge, Row


def _shared_badges(item) -> list[Badge]:
    """Badges every open task shows, main list or matrix alike."""
    badges = []
    if item.kind:
        badges.append(Badge(kind_label(item.kind).split(" ")[0].lower(), item.kind))
    if item.is_ready:
        badges.append(Badge("ready", "ready"))
    if item.scheduled_for:
        # An overdue booking is a nudge, not a telling-off — so a missed
        # booking says when it was for, in the same quiet tone a future one
        # uses. It must not say "today": twelve rows all claiming today
        # when two of them are today makes the badge carry no information,
        # and the honest response to that is to disbelieve all of them.
        booked_today = item.scheduled_for == today_iso()
        badges.append(Badge(
            "today" if booked_today
            else f"booked {humanize_date(item.scheduled_for)}",
            "today" if booked_today else "booked",
        ))
    if item.estimate_minutes:
        badges.append(Badge(f"~{item.estimate_minutes} min", "estimate"))
    return badges


def _step_or_summary(first_step: str, body: str) -> str:
    """The line under a task title, in one place for both tabs.

    This module's whole reason for existing is that these two subtitles were
    copy-pasted; the drift then arrived exactly as predicted, when the matrix
    copy moved inside a conditional and fell off the wording snapshot while
    the identical string in the main list kept it looking covered.
    """
    if first_step:
        return f"→ {first_step}"
    body = (body or "").strip()
    return body.splitlines()[0][:80] if body else ""


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
    else:
        subtitle = _step_or_summary(task.first_step, task.description)

    return Row(id=task.id, title=task.text, subtitle=subtitle, badges=badges,
               done=task.done, flagged=bool(task.priority))


def waiting_line(task, on: str | None = None) -> str:
    """One line for a task that is out with an agent, or "" if it is not.

    States a fact and asks nothing. A handoff that has not come back is not
    a failure — most of them are simply not due to be looked at yet, and the
    ones that are get a badge rather than a scolding.
    """
    handed_to = (getattr(task, "handed_to", "") or "").strip()
    handed_on = (getattr(task, "handed_off_on", "") or "").strip()
    if not handed_to and not handed_on:
        return ""
    on = on or today_iso()
    line = f"Waiting on {handed_to or 'an agent'}"
    if handed_on:
        line += f" since {humanize_date(handed_on, on)}"
    follow_up = (getattr(task, "follow_up_on", "") or "").strip()
    if follow_up:
        line += f" · check back {humanize_date(follow_up, on)}"
    return line


def matrix_row(task) -> Row:
    badges = _shared_badges(task)
    waiting = waiting_line(task)
    if waiting:
        # "check back" rather than "overdue" or "late": the task went out on
        # purpose and the date arriving is information, not a verdict. It
        # leads the badges because it is the one thing about this row that
        # is not about you.
        badges.insert(0, Badge(
            "check back" if task.is_due_back() else "waiting", "booked"))
    # The waiting line wins the subtitle. The first step belongs to whoever
    # has the task now, and showing it here would read as something still
    # sitting on your own plate.
    subtitle = waiting or _step_or_summary(task.first_step, task.content)
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
