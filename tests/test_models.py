import unittest
from datetime import date, timedelta

from cognitive_offload.models import MatrixTask, Note, Task, parse_date_input


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
