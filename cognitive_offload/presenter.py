"""What the app says, decided without a screen to say it on.

Every function here takes plain data and returns a plain description of what
should appear. Nothing in this module knows whether the thing displaying it is
a desktop window, a phone, or a test. The tkinter controller reads its widget
variables, hands the values over, and writes the answers back into widgets — it
makes no decisions of its own in between.

That split is the point. The rules that make this app what it is live here: a
day with nothing finished shows no counter rather than a zero, the banner and
the click behind it are computed once so they cannot disagree, an empty week is
omitted instead of listed. A second front-end reuses all of it unchanged, and
cannot accidentally reimplement it differently.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import today_iso
from .queries import (
    DEFAULT_SORT,
    completed_titles_today,
    counts,
    scheduled_today,
    suggest_tasks,
    visible_tasks,
)
from .rows import task_row
from .storage import category_label
from .viewmodels import Row


@dataclass
class TimerView:
    """What the clock says: the digits, the line under them, the bar."""

    clock: str = "00:00"
    ends: str = ""
    fraction: float = 0.0


@dataclass
class TaskListView:
    """The task list and the line of counters under it."""

    visible: list = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    summary: str = ""
    done_today: int = 0
    done_today_text: str = ""


@dataclass
class NextUpView:
    """The one task the app names without being asked."""

    task_id: str
    title: str
    step: str


@dataclass
class DueView:
    """Today's bookings: the banner text, and the tasks it is counting."""

    total: int = 0
    text: str = ""
    tasks: list = field(default_factory=list)
    scheduled: list = field(default_factory=list)


@dataclass
class TodayView:
    """What you finished today. Empty ``body`` means: say nothing at all."""

    titles: list = field(default_factory=list)
    sessions: int = 0
    minutes: int = 0
    body: str = ""


@dataclass
class WeekDay:
    label: str
    sessions: int
    minutes: int
    titles: list = field(default_factory=list)


@dataclass
class WeekView:
    days: list = field(default_factory=list)
    total_sessions: int = 0
    total_minutes: int = 0


@dataclass
class MatrixQuadrant:
    """One quadrant's words: the tab it sits behind, and its count line."""

    key: str = ""
    tab: str = ""
    count: str = ""


@dataclass
class MatrixView:
    quadrants: list = field(default_factory=list)


def plural(count: int, noun: str) -> str:
    """``1 task`` / ``3 tasks`` — never ``1 task(s)``.

    In an app whose whole difference is that the words were written for a
    person, "1 task(s)" reads like output from a machine that did not care
    enough to look.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def batch_status(verb: str, done: int, total: int, noun: str) -> str:
    """Report what actually happened, not what was asked for.

    Deliberately leaves the sentence unfinished: callers add their own tail
    (" to Schedule.", " Ctrl+Z undoes it.") and the full stop that goes with
    it.
    """
    if done == total:
        return f"{verb} {plural(done, noun)}"
    return f"{verb} {done} of {total} {noun}s — the rest failed"


# Rotated so the same sentence does not arrive every time. The words stay
# level on purpose: a block that went badly earns the same acknowledgement as
# one that went well, because the app is not scoring the work.
DONE_MESSAGES = (
    "That's {minutes} minutes on it. Banked.",
    "{minutes} minutes done — that counts, however it went.",
    "Session finished. The hard part was starting, and you did that.",
)


def done_message(session_count: int, minutes: int) -> str:
    """What the app says when a block ends.

    ``session_count`` is the count *after* this session was banked, which is
    why the first block of a run gets the second sentence. That is not a bug
    to tidy: changing it would move which line every person meets first, and
    no snapshot of the wording would notice, because all three still exist.
    """
    return DONE_MESSAGES[session_count % len(DONE_MESSAGES)].format(minutes=minutes)


def break_offer(message: str, break_minutes: int) -> str:
    """The plain question asked when a block ends with no task attached."""
    return f"{message}\n\nTake a {break_minutes}-minute break now?"


def quadrant_tab(label: str, count: int) -> str:
    """A quadrant tab: its name, and its count only when there is one.

    A returned sentence rather than an inline expression on purpose. Built
    inline as ``tab=...`` it was invisible to the wording snapshot — the
    keyword is not one the extractor watches — so this string fell off the
    net the moment it moved out of the controller, and the entry count did
    not notice because fifty-five others arrived in the same commit.
    """
    return f"{label} ({count})" if count else label


def matrix_view(tasks_by_key: dict) -> MatrixView:
    """The four quadrants' labels, decided without a screen.

    Carries a rule that was previously buried in a refresh method and
    tested nowhere: **an empty quadrant shows no number at all**, not
    "(0)". Same reason the day counter is hidden rather than zeroed and the
    momentum line says "No sessions yet today" — a zero on a tab you have
    not opened yet reads as a score, and four of them read as a verdict on
    the whole week.

    The count line under the list is different: you are already inside that
    quadrant, looking at an empty list, so "0 tasks" is a plain description
    of what you can see rather than a number following you around.
    """
    view = MatrixView()
    for key, tasks in tasks_by_key.items():
        view.quadrants.append(MatrixQuadrant(
            key=key,
            tab=quadrant_tab(category_label(key), len(tasks)),
            count=plural(len(tasks), "task"),
        ))
    return view


def momentum_view(sessions_today: int, minutes_today: int) -> str:
    """The line under the fourteen-day strip.

    A day with nothing on it says "No sessions yet today" rather than
    "0 sessions today · 0 min". The zero is the shaming version: it reads
    as a score you are losing, and it is the first thing you see on the
    morning you most need not to be told that. "Yet" says the day is still
    open, which is true.

    The wording lived on SessionLog, in a module the wording snapshot does
    not read — two sentences a person meets every session, watched by
    nothing. Moving it here put them under the net.
    """
    if sessions_today == 0:
        return "No sessions yet today"
    return f"{plural(sessions_today, 'session')} today · {minutes_today} min"


def replace_running_question(elapsed: int, *, mode: str = "focus",
                             task_text: str = "") -> str:
    """What is asked before a running block is swapped for another one.

    Losing track that a block is already running is the exact failure mode
    this app exists for, so it says so rather than silently mis-crediting
    the log.

    The focus wording once said "Drop it and start a new one?" — which
    stopped being true when replacing a block started banking its minutes.
    Telling someone they are about to lose the eight minutes they managed is
    the fear that pins them inside a block they cannot work in, and it is
    the opposite of what actually happens. ``elapsed`` is rounded by the
    caller with the same arithmetic the timer banks with: a promise about
    "those minutes" is worth nothing if it names a different figure.
    """
    if mode == "break":
        return "A break is running.\n\nEnd it and start a session now?"
    name = f'"{task_text}"' if task_text else "the current block"
    return (
        f"You are {plural(elapsed, 'minute')} into {name}.\n\n"
        "Those minutes are kept, not lost — starting something "
        "else banks them.\n\n"
        "Start something else instead?"
    )


def finished_message(minutes: int, estimate: int = 0, actual: int = 0) -> str:
    """Finishing the task itself, plus the guess-versus-actual line.

    Calibration, not a mark: time-sense only improves when the guess meets
    the actual number somewhere visible and quiet.
    """
    text = f"{minutes} min, and it's finished. Nice."
    if estimate and actual:
        text += (f" You guessed ~{estimate} min; "
                 f"it took about {actual} across your sessions.")
    return text


def focus_caption_done(minutes: int) -> str:
    return f"{minutes} min logged, and that one is done."


def focus_caption_more(minutes: int) -> str:
    return f"{minutes} min logged. Another round when you're ready."


BREAK_OVER_CAPTION = "Break over. One more small block?"


def timer_view(remaining: int, total: int, *, mode: str = "focus",
               running: bool = False, closing: bool = False,
               now: float | None = None) -> TimerView:
    """The countdown, and the line that says where it lands on the clock.

    ``now`` is a parameter rather than a call to the clock inside, which is
    what finally makes this testable. Both of the interesting branches — the
    block that ends after midnight, and the soft landing near the end — used
    to be reachable only by building a real window at the right time of day,
    so in practice neither was covered anywhere that runs headless.
    """
    minutes, seconds = divmod(max(0, remaining), 60)
    view = TimerView(clock=f"{minutes:02d}:{seconds:02d}")
    elapsed = max(0, total - remaining)
    view.fraction = elapsed / total if total else 0.0
    if not (running and remaining > 0):
        return view

    # "ends 15:42" is anchorable in a way "22:00 left" is not, which is the
    # whole difficulty with time blindness.
    stamp = time.time() if now is None else now
    ends = time.localtime(stamp + remaining)
    line = ("break ends " if mode == "break" else "ends ") + \
        time.strftime("%H:%M", ends)
    if time.localtime(stamp)[:3] != ends[:3]:
        # A clock time you cannot place on a day is exactly the ambiguity
        # this line exists to remove.
        line += " tomorrow"
    if closing:
        # A soft landing: the transition costs less when it is announced,
        # and a chosen stopping point is what makes the hand-off question
        # answerable.
        line += " · a good moment to find a stopping point"
    view.ends = line
    return view


def task_list_view(
    tasks: list,
    *,
    search: str = "",
    tag: str | None = None,
    order: str = DEFAULT_SORT,
    show_done: bool = True,
    kind: str | None = None,
    completed_log: list | None = None,
) -> TaskListView:
    """The visible rows, plus the counters that describe what was left out."""
    visible = visible_tasks(
        tasks, search=search, tag=tag, order=order, show_done=show_done, kind=kind
    )
    open_count, done_count, flagged = counts(tasks)
    summary = f"{open_count} open · {done_count} done"
    if flagged:
        summary += f" · {flagged} flagged"
    hidden = len(tasks) - len(visible)
    if hidden > 0:
        summary += f" · {hidden} hidden"

    finished = len(completed_titles_today(tasks, completed_log))
    # A day with nothing finished says nothing. "0 done today" is the kind of
    # scoreboard this app exists not to keep, so the empty string here is a
    # decision, not a missing value — the caller hides the pill on it.
    return TaskListView(
        visible=visible,
        rows=[task_row(t) for t in visible],
        summary=summary,
        done_today=finished,
        done_today_text=f"{finished} done today →" if finished else "",
    )


def next_up_view(
    tasks: list,
    *,
    offset: int = 0,
    warm: set | None = None,
    exclude: str | None = None,
) -> NextUpView | None:
    """The next thing to start, or ``None`` when there is nothing to name."""
    suggestions = suggest_tasks(
        tasks, limit=1, offset=offset, warm=warm, exclude=exclude
    )
    if not suggestions:
        return None
    task = suggestions[0]
    return NextUpView(
        task_id=task.id,
        title=task.text,
        step=f"→ {task.first_step}" if task.first_step
        else "no first step yet — you'll be asked",
    )


def due_view(tasks: list, scheduled: list | None = None,
             on: str | None = None) -> DueView:
    """Today's bookings, counted once.

    The banner and the click behind it used to compute this separately, and
    drifted: the banner counted bookings for today while the click selected the
    oldest overdue task, so the most confident gesture in the feature landed on
    something from two months ago. One function means they cannot disagree
    again.
    """
    day = on or today_iso()
    due = scheduled_today(tasks, on=day)
    booked = [t for t in (scheduled or []) if t.scheduled_for == day]
    total = len(due) + len(booked)
    return DueView(
        total=total,
        text=f"{total} booked for today →" if total else "",
        tasks=due,
        scheduled=booked,
    )


def today_view(tasks: list, completed_log: list | None = None,
               session_log=None, on: str | None = None) -> TodayView:
    """What you finished today, plus the minutes you focused."""
    day = on or today_iso()
    titles = completed_titles_today(tasks, completed_log, on=day)
    sessions = len(session_log.on_day(day)) if session_log is not None else 0
    minutes = (sum(s.minutes for s in session_log.on_day(day))
               if session_log is not None else 0)
    if not titles:
        return TodayView(titles=[], sessions=sessions, minutes=minutes, body="")
    footer = ""
    if sessions:
        footer = (f"\n\nPlus {sessions} focus session"
                  f"{'s' if sessions != 1 else ''} — {minutes} minutes.")
    body = "Finished today:\n\n" + "\n".join(f"·  {t}" for t in titles) + footer
    return TodayView(titles=titles, sessions=sessions, minutes=minutes, body=body)


def week_view(tasks: list, completed_log: list | None = None,
              session_log=None, today: date | None = None) -> WeekView:
    """The last seven days as evidence — only the days that had something.

    A day you did nothing is skipped rather than listed with a zero beside it.
    A week review that reads as a row of noughts is a week review nobody opens
    twice.
    """
    today = today or date.today()
    days: list[WeekDay] = []
    total_sessions = 0
    total_minutes = 0
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        iso = day.isoformat()
        sessions = session_log.on_day(iso) if session_log is not None else []
        titles = completed_titles_today(tasks, completed_log, on=iso)
        if not sessions and not titles:
            continue
        minutes = sum(s.minutes for s in sessions)
        total_sessions += len(sessions)
        total_minutes += minutes
        if offset == 0:
            label = "Today"
        elif offset == 1:
            label = "Yesterday"
        else:
            label = day.strftime("%A")
        days.append(WeekDay(label=label, sessions=len(sessions),
                            minutes=minutes, titles=titles))
    return WeekView(days=days, total_sessions=total_sessions,
                    total_minutes=total_minutes)
