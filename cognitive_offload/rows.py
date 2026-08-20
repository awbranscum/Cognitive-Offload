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

from .models import Task, humanize_date, kind_label, repeat_label, today_iso
from .queries import SORT_ORDERS
from .viewmodels import Badge, Row


def _shared_badges(item) -> list[Badge]:
    """Badges every open task shows, main list or matrix alike."""
    badges = []
    if waiting_line(item):
        # Leads, because it is the one thing about this row that is not about
        # you. "check back" rather than "overdue" or "late": the task went out
        # on purpose and the date arriving is information, not a verdict.
        badges.append(Badge(
            "check back" if item.is_due_back() else "waiting", "booked"))
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
    if getattr(item, "repeat", ""):
        # Without this a repeating task is indistinguishable from a one-off,
        # and the reasonable thing to do with a finished one-off is delete it
        # — taking the recurrence with it.
        badges.append(Badge(repeat_label(item.repeat).lower(), "repeat"))
    return badges


def _step_or_summary(item, body: str) -> str:
    """The line under a task title, in one place for both tabs.

    This module's whole reason for existing is that these two subtitles were
    copy-pasted; the drift then arrived exactly as predicted, when the matrix
    copy moved inside a conditional and fell off the wording snapshot while
    the identical string in the main list kept it looking covered.

    A task with a plan says where in it you are. That is the whole visible
    difference between a task and a wall: "step 2 of 5" is evidence you are
    part-way through something, on the row, without opening anything. It
    counts what exists, never what is missing, and it appears only when
    there is a plan to be part-way through.
    """
    first_step = getattr(item, "first_step", "")
    if first_step:
        return f"→ {step_with_place(first_step, plan_place(item))}"
    body = (body or "").strip()
    return body.splitlines()[0][:80] if body else ""


def plan_place(item) -> str:
    """"step 2 of 4", or "" for a task with no plan.

    Said in one place because two screens say it now — the row and the
    session-end dialog — and this module exists precisely because the last
    sentence that lived in two places drifted.

    `if steps:` and not `len(steps) > 1:` — the model collapses a plan of one
    back into a plain first step, so the longer test could never tell a
    different story. A branch no fixture can reach is a branch nothing can
    check.
    """
    steps = getattr(item, "steps", None) or []
    if not steps:
        return ""
    return f"step {getattr(item, 'steps_done', 0) + 1} of {len(steps)}"


def step_with_place(first_step: str, place: str) -> str:
    """``"copy the headings across · step 2 of 3"``, or just the step.

    One composer, because three surfaces say this sentence — the row, the
    focus card, and the pop-out — and the pop-out had been saying only half
    of it. `focus_caption`'s own docstring promised the pop-out was covered;
    the pop-out passed `first_step` raw and never asked for the place. Two
    copies of a sentence is how a third comes to be missing.
    """
    return f"{first_step} · {place}" if first_step and place else first_step


def _subtitle(item, body: str) -> str:
    """What sits under the title, wherever the task is shown.

    The waiting line wins: the first step belongs to whoever has the task
    now, and showing it would read as something still on your own plate.
    """
    return waiting_line(item) or _step_or_summary(item, body)


#: A ceiling on what a row *draws*, not on what a task *keeps*.
#:
#: Row height grows about 0.43px per character with nothing stopping it: a
#: 1000-character paste made a row 437px tall — taller than the whole visible
#: list at the window's floor — a 4000-character one 1729px, and 8000
#: characters took the X server's pixmap allocation down with the app. The
#: same growth on the NEXT UP strip put 694px of title where a 696px window
#: was, pushing "Where do I start?", the filters and the list off the bottom.
#:
#: Three hundred is a guard rail rather than a policy. The longest title
#: anyone has typed in this project's own fixtures is 138 characters, so this
#: never touches something a person wrote; it catches the paragraph pasted out
#: of an email, which is a thing this app openly invites ("Anything in your
#: head — it does not have to be tidy"). Nothing is lost: the full text is
#: stored, reloaded byte-identical, searched, and shown in the editor.
#:
#: Whether ordinary titles should wrap or ellipsize is a different question
#: and still an open one. This is not it.
TITLE_LIMIT = 300


def short(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, on a word boundary where one is
    near enough to the end that using it does not throw away half the line.

    Lives here rather than in the presenter because two callers now want it
    and the presenter imports this module, not the other way round.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    space = cut.rfind(" ")
    if space >= limit - 12:
        cut = cut[:space].rstrip()
    return cut + "\u2026"


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
        subtitle = _subtitle(task, task.description)

    return Row(id=task.id, title=short(task.text, TITLE_LIMIT),
               subtitle=subtitle, badges=badges,
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
    return Row(id=task.id, title=short(task.title, TITLE_LIMIT),
               subtitle=_subtitle(task, task.content),
               badges=_shared_badges(task), marker="·")


def focus_caption(task: Task | None, first_step: str, place: str = "") -> str:
    """What the focus card and the pop-out say you are on.

    ``place`` is "step 2 of 4" and only ever appears on a task that has a
    plan. During a session it is the one thing about the plan worth showing:
    not what is coming — that is a decision for later and this screen is
    deliberately light — but where you are in it.
    """
    if task is None:
        return f"Free focus — {first_step}" if first_step else "Free focus"
    if not first_step:
        return task.text
    return f"{task.text}\n→ {step_with_place(first_step, place)}"


def sort_label(order: str) -> str:
    for label, key in SORT_ORDERS.items():
        if key == order:
            return label
    return "Priority"
