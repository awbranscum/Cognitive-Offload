"""The app's wording and counting, tested without a window.

Everything here used to live inside methods that also called ``.grid()``,
which meant the only way to check "does a day with nothing finished show a
zero?" was to build a Tk window and read a label. These are the same rules,
now testable in milliseconds and reusable by a front-end that has no ttk.
"""

import time
import unittest
from datetime import date, timedelta

from cognitive_offload import presenter
from cognitive_offload.models import Task, today_iso
from cognitive_offload.sessions import FocusSession, SessionLog


def make(text, **kwargs):
    return Task(text=text, **kwargs)


def log_with(*sessions):
    log = SessionLog.__new__(SessionLog)
    log.sessions = list(sessions)
    return log


def stamp(day, clock="09:00:00"):
    return f"{day} {clock}"


def at(hour, minute=0):
    """A wall-clock time today, as epoch seconds, in whatever zone we are in."""
    parts = list(time.localtime())
    parts[3], parts[4], parts[5] = hour, minute, 0
    parts[8] = -1  # let mktime work out DST rather than guessing
    return time.mktime(tuple(parts))


class TimerViewTests(unittest.TestCase):
    """The clock's words.

    Two of these branches could not be tested at all before: reaching them
    meant building a real window at the right time of day, so the soft
    landing and the after-midnight case were covered nowhere that runs
    headless — a named feature of the app with no test behind it.
    """

    def test_the_digits_count_down_in_minutes_and_seconds(self):
        self.assertEqual(presenter.timer_view(905, 1500).clock, "15:05")

    def test_a_finished_clock_does_not_go_negative(self):
        self.assertEqual(presenter.timer_view(-30, 1500).clock, "00:00")

    def test_a_stopped_timer_says_nothing_about_when_it_ends(self):
        self.assertEqual(presenter.timer_view(900, 1500, running=False).ends, "")

    def test_a_running_block_says_when_it_lands_on_the_clock(self):
        """"ends 09:20" is anchorable in a way "20:00 left" is not."""
        view = presenter.timer_view(1200, 1500, running=True, now=at(9, 0))
        self.assertEqual(view.ends, "ends 09:20")
        self.assertNotIn("tomorrow", view.ends, "a same-day block says no such thing")

    def test_a_break_says_so(self):
        view = presenter.timer_view(300, 300, mode="break", running=True,
                                    now=at(9, 0))
        self.assertEqual(view.ends, "break ends 09:05")

    def test_a_block_running_past_midnight_says_tomorrow(self):
        """A clock time you cannot place on a day is the ambiguity to remove."""
        view = presenter.timer_view(1200, 1500, running=True, now=at(23, 50))
        self.assertEqual(view.ends, "ends 00:10 tomorrow")

    def test_the_soft_landing_is_announced(self):
        view = presenter.timer_view(90, 1500, running=True, closing=True,
                                    now=at(9, 0))
        self.assertIn("a good moment to find a stopping point", view.ends)

    def test_the_soft_landing_is_absent_the_rest_of_the_time(self):
        view = presenter.timer_view(900, 1500, running=True, closing=False,
                                    now=at(9, 0))
        self.assertNotIn("stopping point", view.ends)

    def test_both_clauses_can_appear_together(self):
        view = presenter.timer_view(90, 1500, running=True, closing=True,
                                    now=at(23, 59))
        self.assertIn("tomorrow", view.ends)
        self.assertIn("stopping point", view.ends)

    def test_the_bar_tracks_how_much_is_done(self):
        self.assertAlmostEqual(presenter.timer_view(750, 1500).fraction, 0.5)
        self.assertEqual(presenter.timer_view(0, 0).fraction, 0.0,
                         "an untouched timer must not divide by zero")


class PluralTests(unittest.TestCase):
    def test_one_is_singular_and_everything_else_is_not(self):
        self.assertEqual(presenter.plural(1, "task"), "1 task")
        self.assertEqual(presenter.plural(3, "task"), "3 tasks")
        self.assertEqual(presenter.plural(0, "task"), "0 tasks")

    def test_a_batch_that_all_worked_just_says_so(self):
        self.assertEqual(presenter.batch_status("Deleted", 1, 1, "matrix task"),
                         "Deleted 1 matrix task")

    def test_a_partial_batch_reports_what_actually_happened(self):
        self.assertEqual(presenter.batch_status("Moved", 1, 3, "task"),
                         "Moved 1 of 3 tasks — the rest failed")

    def test_the_sentence_is_left_unfinished_for_the_caller(self):
        """Callers add their own tail and the full stop that goes with it."""
        self.assertFalse(
            presenter.batch_status("Deleted", 2, 2, "task").endswith("."))


class SessionEndWordingTests(unittest.TestCase):
    """What the app says when a block ends — the loaded moment."""

    def test_the_rotation_starts_where_the_counter_is(self):
        """The count passed in is post-banking, so a run opens on index 1.

        Pinned in app.py as behaviour too; here it is pinned as arithmetic,
        because the snapshot cannot see which of the three is chosen.
        """
        said = [presenter.done_message(n, 10) for n in (1, 2, 3, 4)]
        self.assertEqual(said, [
            "10 minutes done — that counts, however it went.",
            "Session finished. The hard part was starting, and you did that.",
            "That's 10 minutes on it. Banked.",
            "10 minutes done — that counts, however it went.",
        ])

    def test_no_finish_message_scores_the_work(self):
        """A block that went badly earns the same words as one that went well."""
        for n in range(len(presenter.DONE_MESSAGES)):
            said = presenter.done_message(n, 5).lower()
            for scold in ("only", "just", "should", "failed", "but "):
                self.assertNotIn(scold, said)

    def test_the_break_offer_carries_the_message_it_follows(self):
        offer = presenter.break_offer("5 minutes done.", 5)
        self.assertTrue(offer.startswith("5 minutes done."))
        self.assertIn("Take a 5-minute break now?", offer)

    def test_finishing_without_a_guess_says_nothing_about_guesses(self):
        self.assertEqual(presenter.finished_message(25),
                         "25 min, and it's finished. Nice.")

    def test_a_guess_and_an_actual_are_reported_side_by_side(self):
        said = presenter.finished_message(25, estimate=30, actual=25)
        self.assertIn("You guessed ~30 min", said)
        self.assertIn("about 25 across your sessions", said)

    def test_a_guess_with_nothing_logged_stays_quiet(self):
        """Half a comparison is worse than none — it would read as a verdict."""
        self.assertNotIn("guessed", presenter.finished_message(25, estimate=30,
                                                               actual=0))

    def test_the_captions_say_what_was_logged(self):
        self.assertEqual(presenter.focus_caption_done(15),
                         "15 min logged, and that one is done.")
        self.assertIn("Another round when you're ready",
                      presenter.focus_caption_more(15))
        self.assertEqual(presenter.BREAK_OVER_CAPTION,
                         "Break over. One more small block?")


class MomentumViewTests(unittest.TestCase):
    def test_an_empty_day_is_not_reported_as_a_zero(self):
        """The design rule, not the wording: no zero, and the day stays open."""
        text = presenter.momentum_view(0, 0)
        self.assertEqual(text, "No sessions yet today")
        self.assertNotIn("0", text)

    def test_one_session_is_singular(self):
        self.assertEqual(presenter.momentum_view(1, 15), "1 session today · 15 min")

    def test_more_than_one_is_plural(self):
        self.assertEqual(presenter.momentum_view(2, 30), "2 sessions today · 30 min")


class ReplaceRunningQuestionTests(unittest.TestCase):
    """Which question gets asked, which the wording snapshot cannot see.

    Both sentences exist in the module either way, so a swapped branch or a
    lost fallback would leave the snapshot byte-identical. That is what
    these pin.
    """

    def test_a_break_is_asked_about_as_a_break(self):
        text = presenter.replace_running_question(3, mode="break")
        self.assertEqual(text,
                         "A break is running.\n\nEnd it and start a session now?")
        self.assertNotIn("minutes are kept", text,
                         "a break has no banked minutes to promise about")

    def test_a_running_block_names_the_task_and_the_minutes(self):
        text = presenter.replace_running_question(8, task_text="write the letter")
        self.assertIn("You are 8 minutes into \"write the letter\".", text)
        self.assertIn("Start something else instead?", text)

    def test_the_promise_that_the_minutes_survive_is_made(self):
        """The whole point of the rewording. Losing it is a silent regression."""
        text = presenter.replace_running_question(8, task_text="a thing")
        self.assertIn("Those minutes are kept, not lost", text)
        self.assertNotIn("Drop it", text)

    def test_a_single_minute_is_singular(self):
        self.assertIn("You are 1 minute into",
                      presenter.replace_running_question(1, task_text="a thing"))

    def test_a_nameless_block_is_still_described(self):
        """An untitled block must not become 'You are 8 minutes into ""'."""
        self.assertIn("into the current block",
                      presenter.replace_running_question(8))


class TaskListViewTests(unittest.TestCase):
    def test_counts_open_done_and_flagged(self):
        tasks = [make("a"), make("b", priority=1), make("c")]
        tasks[2].set_done(True)
        view = presenter.task_list_view(tasks)
        self.assertEqual(view.summary, "2 open · 1 done · 1 flagged")

    def test_hidden_tasks_are_counted_so_the_list_never_lies(self):
        tasks = [make("shown"), make("gone")]
        tasks[1].set_done(True)
        view = presenter.task_list_view(tasks, show_done=False)
        self.assertIn("1 hidden", view.summary)
        self.assertEqual([r.title for r in view.rows], ["shown"])

    def test_a_day_with_nothing_finished_says_nothing(self):
        """Not "0 done today" — the app keeps no scoreboard to lose."""
        view = presenter.task_list_view([make("still open")])
        self.assertEqual(view.done_today, 0)
        self.assertEqual(view.done_today_text, "")

    def test_finishing_something_earns_the_pill(self):
        task = make("done thing")
        task.set_done(True)
        view = presenter.task_list_view([task])
        self.assertEqual(view.done_today_text, "1 done today →")

    def test_rows_line_up_with_the_tasks_behind_them(self):
        tasks = [make("first"), make("second")]
        view = presenter.task_list_view(tasks, order="created")
        self.assertEqual([r.id for r in view.rows], [t.id for t in view.visible])

    def test_a_cleared_away_task_still_counts_as_finished_today(self):
        log = [{"text": "tidied up", "completed_at": f"{today_iso()} 10:00:00"}]
        view = presenter.task_list_view([], completed_log=log)
        self.assertEqual(view.done_today_text, "1 done today →")


class NextUpViewTests(unittest.TestCase):
    def test_nothing_to_suggest_is_none_not_an_empty_card(self):
        self.assertIsNone(presenter.next_up_view([]))

    def test_a_task_without_a_first_step_promises_to_ask(self):
        view = presenter.next_up_view([make("vague thing")])
        self.assertEqual(view.title, "vague thing")
        self.assertIn("you'll be asked", view.step)

    def test_a_first_step_is_shown_as_the_arrow_line(self):
        view = presenter.next_up_view([make("call", first_step="find the number")])
        self.assertEqual(view.step, "→ find the number")

    def test_the_open_block_task_is_never_suggested_back(self):
        here = make("in progress")
        there = make("something else")
        view = presenter.next_up_view([here, there], exclude=here.id)
        self.assertEqual(view.task_id, there.id)

    def test_excluding_the_only_task_leaves_nothing_to_name(self):
        only = make("the one thing")
        self.assertIsNone(presenter.next_up_view([only], exclude=only.id))


class DueViewTests(unittest.TestCase):
    def test_a_booking_for_today_is_counted(self):
        view = presenter.due_view([make("dentist", scheduled_for=today_iso())])
        self.assertEqual(view.total, 1)
        self.assertEqual(view.text, "1 booked for today →")

    def test_a_missed_booking_is_not_called_today(self):
        """It keeps its place in the list; it stops claiming to be today."""
        stale = (date.today() - timedelta(days=40)).isoformat()
        view = presenter.due_view([make("old", scheduled_for=stale)])
        self.assertEqual(view.total, 0)
        self.assertEqual(view.text, "")

    def test_nothing_booked_shows_no_banner(self):
        self.assertEqual(presenter.due_view([make("unscheduled")]).text, "")

    def test_the_banner_and_the_click_see_the_same_tasks(self):
        """The count and the task the click lands on come from one call.

        These were computed separately once, and drifted: the banner counted
        today's bookings while the click selected the oldest overdue task.
        """
        stale = (date.today() - timedelta(days=40)).isoformat()
        old = make("two months ago", scheduled_for=stale)
        now = make("today's booking", scheduled_for=today_iso())
        view = presenter.due_view([old, now])
        self.assertEqual(view.total, len(view.tasks) + len(view.scheduled))
        self.assertEqual(view.tasks[0].text, "today's booking")

    def test_scheduled_matrix_tasks_join_the_count(self):
        class Booked:
            scheduled_for = today_iso()

        view = presenter.due_view([make("task", scheduled_for=today_iso())],
                                  [Booked()])
        self.assertEqual(view.total, 2)
        self.assertEqual(view.text, "2 booked for today →")


class TodayViewTests(unittest.TestCase):
    def test_an_empty_day_has_no_body_to_show(self):
        view = presenter.today_view([make("still open")])
        self.assertEqual(view.body, "")

    def test_finished_titles_are_listed(self):
        task = make("book the dentist")
        task.set_done(True)
        view = presenter.today_view([task])
        self.assertIn("·  book the dentist", view.body)

    def test_sessions_are_added_as_a_footer_when_there_were_any(self):
        task = make("thing")
        task.set_done(True)
        log = log_with(FocusSession(minutes=25, started_at=stamp(today_iso())))
        view = presenter.today_view([task], session_log=log)
        self.assertIn("Plus 1 focus session — 25 minutes.", view.body)

    def test_no_sessions_means_no_zero_session_footer(self):
        task = make("thing")
        task.set_done(True)
        view = presenter.today_view([task], session_log=log_with())
        self.assertNotIn("Plus", view.body)
        self.assertNotIn("0 focus", view.body)


class WeekViewTests(unittest.TestCase):
    def setUp(self):
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)

    def test_days_with_nothing_are_omitted_never_listed_as_zeros(self):
        log = log_with(
            FocusSession(minutes=15, started_at=stamp(self.yesterday.isoformat())))
        view = presenter.week_view([], session_log=log, today=self.today)
        self.assertEqual([d.label for d in view.days], ["Yesterday"])

    def test_the_two_nearest_days_are_named_not_dated(self):
        log = log_with(
            FocusSession(minutes=15, started_at=stamp(self.yesterday.isoformat())),
            FocusSession(minutes=30, started_at=stamp(self.today.isoformat())),
        )
        view = presenter.week_view([], session_log=log, today=self.today)
        self.assertEqual([d.label for d in view.days], ["Yesterday", "Today"])

    def test_older_days_use_their_weekday_name(self):
        older = self.today - timedelta(days=3)
        log = log_with(
            FocusSession(minutes=15, started_at=stamp(older.isoformat())))
        view = presenter.week_view([], session_log=log, today=self.today)
        self.assertEqual([d.label for d in view.days], [older.strftime("%A")])

    def test_anything_older_than_a_week_is_outside_the_window(self):
        stale = self.today - timedelta(days=10)
        log = log_with(
            FocusSession(minutes=99, started_at=stamp(stale.isoformat())))
        view = presenter.week_view([], session_log=log, today=self.today)
        self.assertEqual(view.days, [])
        self.assertEqual(view.total_minutes, 0)

    def test_totals_add_up_across_the_week(self):
        log = log_with(
            FocusSession(minutes=15, started_at=stamp(self.yesterday.isoformat())),
            FocusSession(minutes=30, started_at=stamp(self.yesterday.isoformat(),
                                                      "11:00:00")),
        )
        view = presenter.week_view([], session_log=log, today=self.today)
        self.assertEqual(view.total_sessions, 2)
        self.assertEqual(view.total_minutes, 45)

    def test_a_day_can_earn_its_line_with_finished_tasks_alone(self):
        task = make("finished thing")
        task.set_done(True)
        view = presenter.week_view([task], session_log=log_with(),
                                   today=self.today)
        self.assertEqual([d.label for d in view.days], ["Today"])
        self.assertEqual(view.days[0].sessions, 0)
        self.assertEqual(view.days[0].titles, ["finished thing"])

    def test_a_quiet_week_is_empty_not_seven_zeros(self):
        view = presenter.week_view([], session_log=log_with(), today=self.today)
        self.assertEqual(view.days, [])
        self.assertEqual(view.total_sessions, 0)


if __name__ == "__main__":
    unittest.main()
