import unittest
from datetime import date, timedelta

from cognitive_offload.models import (
    MatrixTask,
    Note,
    Task,
    parse_date_input,
    today_iso,
)


class TaskTests(unittest.TestCase):
    def test_ids_are_unique(self):
        a, b = Task(text="same"), Task(text="same")
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(a, b)

    def test_tasks_with_identical_text_are_distinct_in_a_list(self):
        tasks = [Task(text="write tests"), Task(text="write tests")]
        tasks.remove(tasks[1])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, tasks[0].id)

    def test_defaults_are_not_shared_between_instances(self):
        a, b = Task(text="a"), Task(text="b")
        a.add_tag("home")
        self.assertEqual(b.tags, [])

    def test_marking_done_stamps_and_clears(self):
        task = Task(text="thing")
        task.set_done(True)
        self.assertTrue(task.done)
        self.assertTrue(task.completed_at)
        task.set_done(False)
        self.assertFalse(task.done)
        self.assertIsNone(task.completed_at)

    def test_tags_are_normalised_and_deduped(self):
        task = Task(text="thing", tags=["Home", "home", " WORK "])
        self.assertEqual(task.tags, ["home", "work"])
        self.assertFalse(task.add_tag("HOME"))
        self.assertTrue(task.add_tag("errand"))
        self.assertTrue(task.remove_tag("Errand"))
        self.assertEqual(task.tags, ["home", "work"])

    def test_search_matches_text_description_and_tags(self):
        task = Task(text="Email Bob", description="About the Q3 budget", tags=["work"])
        for term in ("email", "BUDGET", "wor", ""):
            self.assertTrue(task.matches(term), term)
        self.assertFalse(task.matches("groceries"))

    def test_roundtrip_preserves_everything(self):
        task = Task(text="x", description="d", tags=["a"], priority=1)
        task.set_done(True)
        clone = Task.from_dict(task.to_dict())
        self.assertEqual(clone, task)

    def test_from_dict_accepts_legacy_records(self):
        legacy = {"text": "old task", "done": False, "created_at": "2024-01-01 10:00:00"}
        task = Task.from_dict(legacy)
        self.assertEqual(task.text, "old task")
        self.assertEqual(task.tags, [])
        self.assertEqual(task.priority, 0)
        self.assertIsNone(task.completed_at)
        self.assertTrue(task.id)

    def test_from_dict_ignores_junk_types(self):
        task = Task.from_dict({"text": "x", "tags": "not-a-list", "priority": "yes", "done": 1})
        self.assertEqual(task.tags, [])
        self.assertEqual(task.priority, 1)
        self.assertTrue(task.done)

    def test_humanize_date_speaks_in_temporal_distance(self):
        from cognitive_offload.models import humanize_date

        on = "2026-08-05"  # a Wednesday
        self.assertEqual(humanize_date("2026-08-05", on), "today")
        self.assertEqual(humanize_date("2026-08-06", on), "tomorrow")
        self.assertEqual(humanize_date("2026-08-07", on), "Fri")
        self.assertEqual(humanize_date("2026-08-11", on), "Tue")
        self.assertEqual(humanize_date("2026-08-12", on), "in 7 days")
        self.assertEqual(humanize_date("2026-08-19", on), "in 14 days")
        self.assertEqual(humanize_date("2026-08-20", on), "2026-08-20")  # far: plain
        self.assertEqual(humanize_date("not-a-date", on), "not-a-date")

    def test_humanize_date_places_the_past_without_arithmetic(self):
        """A missed booking has to say when it was for. An ISO string is
        precisely the flat data this function exists to remove."""
        from cognitive_offload.models import humanize_date

        on = "2026-08-05"  # a Wednesday
        self.assertEqual(humanize_date("2026-08-04", on), "yesterday")
        self.assertEqual(humanize_date("2026-08-01", on), "1 Aug")
        self.assertEqual(humanize_date("2026-06-16", on), "16 Jun")
        # Deliberately NOT the weekday form the near future uses: "Thu"
        # ahead is unambiguous, "Thu" behind could be four days ago or
        # eleven — a date you cannot place is the failure being fixed.
        self.assertNotEqual(humanize_date("2026-07-30", on), "Thu")

    def test_a_past_date_in_another_year_says_which_year(self):
        """"22 Dec" on a booking from last year reads as the coming December.

        Same failure the weekday form was rejected for, one scale up: a
        two-year-old booking rendered identically to a two-week-old one,
        on a screen that also says "in 7 days". This app is for people who
        keep tasks around, so a stale booking is the ordinary case.
        """
        from cognitive_offload.models import humanize_date

        on = "2026-08-18"
        self.assertEqual(humanize_date("2025-12-22", on), "22 Dec 2025")
        self.assertEqual(humanize_date("2024-08-18", on), "18 Aug 2024")

    def test_a_past_date_in_the_same_year_stays_short(self):
        """The year is carried only when it is doing work.

        "1 Aug" in August is already placeable, and every extra token on a
        row is one more thing to read past.
        """
        from cognitive_offload.models import humanize_date

        self.assertEqual(humanize_date("2026-08-01", "2026-08-18"), "1 Aug")
        self.assertNotIn("2026", humanize_date("2026-01-04", "2026-08-18"))

    def test_the_year_reads_as_a_fact_not_as_lateness(self):
        """Nothing here may imply a person is behind. It is a date, not a mark."""
        from cognitive_offload.models import humanize_date

        said = humanize_date("2025-12-22", "2026-08-18").lower()
        for scolding in ("overdue", "late", "missed", "still", "should"):
            self.assertNotIn(scolding, said)

    def test_estimate_round_trips_clamps_and_tolerates_junk(self):
        task = Task(text="x", estimate_minutes=25)
        self.assertEqual(Task.from_dict(task.to_dict()).estimate_minutes, 25)
        self.assertEqual(Task(text="x", estimate_minutes=9999).estimate_minutes, 480)
        self.assertEqual(Task(text="x", estimate_minutes=-5).estimate_minutes, 0)
        self.assertEqual(Task.from_dict({"text": "old file"}).estimate_minutes, 0)
        self.assertEqual(Task.from_dict({"text": "x", "estimate_minutes": "junk"})
                         .estimate_minutes, 0)

    def test_estimate_survives_the_matrix_round_trip(self):
        from cognitive_offload.models import MatrixTask

        task = Task(text="guessed", estimate_minutes=40)
        boxed = MatrixTask(title=task.text, estimate_minutes=task.estimate_minutes)
        self.assertEqual(MatrixTask.from_dict(boxed.to_dict()).estimate_minutes, 40)
        self.assertEqual(boxed.to_task().estimate_minutes, 40)

    def test_pinned_round_trips_and_tolerates_junk(self):
        task = Task(text="anchor", pinned=True)
        clone = Task.from_dict(task.to_dict())
        self.assertTrue(clone.pinned)
        self.assertTrue(clone.copy().pinned)
        self.assertFalse(Task.from_dict({"text": "old file"}).pinned)
        self.assertTrue(Task.from_dict({"text": "x", "pinned": "yes"}).pinned)
        self.assertFalse(Task.from_dict({"text": "x", "pinned": 0}).pinned)

    def test_done_without_timestamp_is_consistent(self):
        task = Task(text="x", done=False, completed_at="2024-01-01 00:00:00")
        self.assertIsNone(task.completed_at)


class FirstStepAndFeelTests(unittest.TestCase):
    def test_a_task_is_only_ready_once_it_names_a_first_step(self):
        task = Task(text="write the report")
        self.assertFalse(task.is_ready)
        task.first_step = "  open last quarter's file  "
        self.assertTrue(task.is_ready)

    def test_first_step_is_trimmed(self):
        self.assertEqual(Task(text="x", first_step="  do it  ").first_step, "do it")

    def test_unknown_feels_fall_back_to_unsorted(self):
        self.assertEqual(Task(text="x", kind="vibes").kind, "")
        self.assertEqual(Task(text="x", kind="admin").kind, "admin")

    def test_is_due_covers_today_and_anything_earlier(self):
        task = Task(text="x", scheduled_for="2026-05-05")
        self.assertTrue(task.is_due(on="2026-05-05"))
        self.assertTrue(task.is_due(on="2026-06-01"))
        self.assertFalse(task.is_due(on="2026-05-04"))
        self.assertFalse(Task(text="x").is_due(on="2026-05-05"))

    def test_new_fields_round_trip(self):
        task = Task(text="x", first_step="step", kind="admin", scheduled_for="2026-01-01")
        self.assertEqual(Task.from_dict(task.to_dict()), task)

    def test_records_saved_before_these_fields_existed_still_load(self):
        task = Task.from_dict({"text": "old", "done": False})
        self.assertEqual(task.first_step, "")
        self.assertEqual(task.kind, "")
        self.assertEqual(task.scheduled_for, "")
        self.assertFalse(task.is_ready)

    def test_search_covers_the_first_step(self):
        task = Task(text="opaque", first_step="call the bank")
        self.assertTrue(task.matches("bank"))


class DateInputTests(unittest.TestCase):
    def test_blank_means_no_date(self):
        self.assertEqual(parse_date_input(""), "")
        self.assertEqual(parse_date_input("   "), "")

    def test_today_and_tomorrow(self):
        self.assertEqual(parse_date_input("today"), date.today().isoformat())
        self.assertEqual(parse_date_input("TOMORROW"), (date.today() + timedelta(days=1)).isoformat())

    def test_iso_dates_pass_through(self):
        self.assertEqual(parse_date_input("2026-08-01"), "2026-08-01")

    def test_weekday_names_resolve_to_the_next_such_day(self):
        for name in ("monday", "fri", "Sunday"):
            result = parse_date_input(name)
            self.assertIsNotNone(result)
            self.assertGreater(result, date.today().isoformat())

    def test_nonsense_is_rejected_rather_than_guessed(self):
        for value in ("squelch", "32nd of never", "2026-13-45"):
            self.assertIsNone(parse_date_input(value))


class EstimateInputTests(unittest.TestCase):
    """What a person types into "About ⬚ minutes, at a guess"."""

    def setUp(self):
        from cognitive_offload.models import parse_estimate_input
        self.parse = parse_estimate_input

    def test_a_bare_number_is_minutes(self):
        self.assertEqual(self.parse("20"), 20)
        self.assertEqual(self.parse(" 90 "), 90)

    def test_the_units_people_actually_type_are_understood(self):
        """The label prints "minutes" to the RIGHT of the box, so typing the
        unit as well is the natural thing to do — and it was the input most
        reliably thrown away."""
        for typed, expected in (("20 mins", 20), ("20m", 20), ("20 minutes", 20),
                                ("1h", 60), ("2 hours", 120), ("1.5h", 90),
                                ("~15", 15), ("about 25", 25)):
            with self.subTest(typed=typed):
                self.assertEqual(self.parse(typed), expected)

    def test_an_empty_field_is_no_guess_not_a_failure(self):
        self.assertEqual(self.parse(""), 0)
        self.assertEqual(self.parse("   "), 0)

    def test_it_keeps_the_same_ceiling_as_the_store(self):
        self.assertEqual(self.parse("9999"), 480)
        self.assertEqual(self.parse("40 hours"), 480)

    def test_what_it_cannot_read_is_reported_rather_than_guessed(self):
        """None, not 0 — so a caller can tell junk from a real zero. The
        editor still maps both to "no guess" without a dialog, which is a
        decision the dialog states in its own comment."""
        for typed in ("soon", "half an hour", "mins", "-5", "later today"):
            with self.subTest(typed=typed):
                self.assertIsNone(self.parse(typed))
        self.assertEqual(self.parse("0"), 0, "a typed zero is a real answer")


class NoteTests(unittest.TestCase):
    def test_render_includes_timestamp(self):
        note = Note(text="idea", created_at="2024-05-05 09:00:00")
        self.assertEqual(note.render(), "[2024-05-05 09:00:00] idea")


class MatrixTaskTests(unittest.TestCase):
    def test_to_task_carries_content_into_description(self):
        matrix_task = MatrixTask(title="Ship it", content="notes here")
        task = matrix_task.to_task()
        self.assertEqual(task.text, "Ship it")
        self.assertEqual(task.description, "notes here")
        self.assertFalse(task.done)

    def test_to_task_carries_first_step_feel_and_booking(self):
        matrix_task = MatrixTask(
            title="Ship it", content="notes", first_step="open the repo",
            kind="deadline", scheduled_for="2026-08-08",
        )
        task = matrix_task.to_task()
        self.assertEqual(task.first_step, "open the repo")
        self.assertEqual(task.kind, "deadline")
        self.assertEqual(task.scheduled_for, "2026-08-08")

    def test_matrix_task_round_trips_through_json(self):
        original = MatrixTask(title="t", first_step="s", kind="admin", scheduled_for="2026-01-01")
        clone = MatrixTask.from_dict(original.to_dict())
        self.assertEqual(clone.first_step, "s")
        self.assertEqual(clone.kind, "admin")
        self.assertEqual(clone.scheduled_for, "2026-01-01")

    def test_matrix_is_due(self):
        self.assertTrue(MatrixTask(title="t", scheduled_for="2020-01-01").is_due())
        self.assertFalse(MatrixTask(title="t").is_due())


if __name__ == "__main__":
    unittest.main()


class RepeatTests(unittest.TestCase):
    """Bins, meds, bills and standing appointments — the things this audience
    loses, and the things the app could not hold at all until now."""

    def test_a_missed_repeat_never_becomes_a_backlog(self):
        """The single most reliable way to make someone stop opening an app
        is to greet them with fourteen copies of a task they feel bad about."""
        from cognitive_offload.models import next_occurrence

        # Booked six weeks ago and never done: still exactly one next date,
        # and it is in the future.
        nxt = next_occurrence("weekly", "2026-07-01", "2026-08-19")
        self.assertGreater(nxt, "2026-08-19")
        self.assertEqual(nxt, "2026-08-26")

    def test_being_on_time_keeps_the_rhythm(self):
        """Done early, a Friday task stays a Friday task instead of drifting
        a day earlier every week."""
        from cognitive_offload.models import next_occurrence

        # Booked Friday 21st, ticked off on Wednesday 19th.
        self.assertEqual(next_occurrence("weekly", "2026-08-21", "2026-08-19"),
                         "2026-08-28")

    def test_weekdays_skips_the_weekend(self):
        from cognitive_offload.models import next_occurrence

        # Friday 21 Aug 2026 -> Monday 24th, not Saturday 22nd.
        self.assertEqual(next_occurrence("weekdays", "2026-08-21", "2026-08-19"),
                         "2026-08-24")
        # ...and an ordinary weekday just moves on one.
        self.assertEqual(next_occurrence("weekdays", "2026-08-19", "2026-08-19"),
                         "2026-08-20")

    def test_monthly_does_not_skip_february(self):
        from cognitive_offload.models import next_occurrence

        self.assertEqual(next_occurrence("monthly", "2026-01-31", "2026-01-31"),
                         "2026-02-28")
        self.assertEqual(next_occurrence("monthly", "2026-12-15", "2026-12-15"),
                         "2027-01-15")

    def test_every_interval_moves_forward(self):
        from cognitive_offload.models import REPEAT_KEYS, next_occurrence

        for key in REPEAT_KEYS:
            if not key:
                continue
            self.assertGreater(next_occurrence(key, "2026-08-19", "2026-08-19"),
                               "2026-08-19", key)

    def test_a_task_that_does_not_repeat_produces_no_next_date(self):
        from cognitive_offload.models import next_occurrence

        self.assertEqual(next_occurrence("", "2026-08-19", "2026-08-19"), "")
        self.assertEqual(next_occurrence("every other tuesday", "", "2026-08-19"), "")

    def test_an_unreadable_stored_repeat_becomes_no_repeat(self):
        from cognitive_offload.models import Task

        self.assertEqual(Task(text="x", repeat="nonsense").repeat, "")
        self.assertEqual(Task.from_dict({"text": "x", "repeat": 7}).repeat, "")

    def test_a_nonsense_booking_still_yields_a_real_next_date(self):
        from cognitive_offload.models import next_occurrence

        self.assertRegex(next_occurrence("weekly", "not a date", "2026-08-19"),
                         r"^\d{4}-\d{2}-\d{2}$")

    def test_the_next_round_is_a_new_open_task_not_a_reset(self):
        """Resetting would delete the evidence that you did it, and the week
        review exists to hold exactly that evidence."""
        from cognitive_offload.models import Task

        task = Task(text="Take the bins out", repeat="weekly",
                    scheduled_for="2026-08-21", first_step="wheel it to the kerb",
                    tags=["home"], estimate_minutes=5)
        nxt = task.next_instance("2026-08-19")
        self.assertIsNotNone(nxt)
        self.assertNotEqual(nxt.id, task.id)
        self.assertFalse(nxt.done)
        self.assertIsNone(nxt.completed_at)
        self.assertEqual(nxt.scheduled_for, "2026-08-28")
        # Everything you set up once is carried, so it stays set up.
        self.assertEqual(nxt.first_step, "wheel it to the kerb")
        self.assertEqual(nxt.tags, ["home"])
        self.assertEqual(nxt.estimate_minutes, 5)
        self.assertEqual(nxt.repeat, "weekly")

    def test_a_snooze_does_not_carry_into_the_next_round(self):
        """"Not today" was about today, not about every future Tuesday."""
        from cognitive_offload.models import Task

        task = Task(text="bins", repeat="weekly", scheduled_for="2026-08-21",
                    snoozed_until="2026-08-20")
        self.assertEqual(task.next_instance("2026-08-19").snoozed_until, "")

    def test_a_non_repeating_task_has_no_next_instance(self):
        from cognitive_offload.models import Task

        self.assertIsNone(Task(text="one off").next_instance("2026-08-19"))

    def test_the_repeat_survives_a_round_trip(self):
        from cognitive_offload.models import Task

        task = Task(text="bins", repeat="fortnightly")
        self.assertEqual(Task.from_dict(task.to_dict()).repeat, "fortnightly")

    def test_a_file_written_before_repeats_existed_still_loads(self):
        from cognitive_offload.models import Task

        self.assertEqual(Task.from_dict({"text": "older"}).repeat, "")

    def test_the_labels_and_keys_agree_in_both_directions(self):
        from cognitive_offload.models import (
            REPEAT_KEY_BY_LABEL,
            REPEATS,
            repeat_label,
        )

        for key, label in REPEATS.items():
            self.assertEqual(REPEAT_KEY_BY_LABEL[label], key)
            self.assertEqual(repeat_label(key), label)
        self.assertEqual(repeat_label("nonsense"), REPEATS[""])

    def test_a_repeating_task_is_visibly_different_from_a_one_off(self):
        """Otherwise the reasonable thing to do with a finished one is delete
        it, which takes the recurrence with it."""
        from cognitive_offload.models import Task
        from cognitive_offload.rows import task_row

        badges = [b.text for b in task_row(Task(text="bins", repeat="weekly")).badges]
        self.assertIn("every week", badges)
        plain = [b.text for b in task_row(Task(text="once")).badges]
        self.assertNotIn("every week", plain)


class PutDownTests(unittest.TestCase):
    """Snoozed, or out with someone and not back yet: set aside on purpose.

    One predicate, on the model, because three readers now ask it — the
    ranking that fills the suggestion slot, the focus card above it, and the
    matrix. Two of those used to hold their own copy of the rule, which is
    how the card ended up naming a task the list had already agreed to stop
    naming.
    """

    #: the two models and the keyword each one calls its title, because the
    #: whole point of this class is that neither may answer differently.
    MODELS = ((Task, "text"), (MatrixTask, "title"))

    def _days(self, n):
        return (date.today() + timedelta(days=n)).isoformat()

    def _each(self):
        for cls, keyword in self.MODELS:
            with self.subTest(cls.__name__):
                yield cls(**{keyword: "Write the quarterly report"})

    def test_a_plain_task_is_not_put_down(self):
        for task in self._each():
            self.assertFalse(task.is_snoozed())
            self.assertFalse(task.is_put_down())

    def test_a_snooze_in_the_future_counts(self):
        for task in self._each():
            task.snoozed_until = self._days(1)
            self.assertTrue(task.is_snoozed())
            self.assertTrue(task.is_put_down())

    def test_a_snooze_today_has_already_run_out(self):
        # "Not today" writes tomorrow, so a date of today is spent. Anything
        # that treated it as live would keep a task set aside a day too long.
        for task in self._each():
            task.snoozed_until = today_iso()
            self.assertFalse(task.is_snoozed())

    def test_the_day_can_be_asked_about_rather_than_assumed(self):
        for task in self._each():
            task.snoozed_until = self._days(3)
            self.assertTrue(task.is_snoozed(on=self._days(2)))
            self.assertFalse(task.is_snoozed(on=self._days(3)))

    def test_waiting_on_someone_is_being_put_down_too(self):
        for task in self._each():
            task.handed_to = "Mum"
            task.follow_up_on = self._days(4)
            self.assertFalse(task.is_snoozed())
            self.assertTrue(task.is_put_down())

    def test_but_only_until_the_check_back_day(self):
        for task in self._each():
            task.handed_to = "Mum"
            task.follow_up_on = self._days(-1)
            self.assertTrue(task.is_waiting())
            self.assertFalse(task.is_put_down())

    def test_waiting_with_no_check_back_day_stays_put_down(self):
        # No date means no day on which it comes back by itself; the way out
        # is "Take it back", not the calendar.
        for task in self._each():
            task.handed_to = "Mum"
            self.assertTrue(task.is_put_down())
