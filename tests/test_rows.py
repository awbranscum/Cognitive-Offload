"""Row building: what a task looks like in the list.

Imports tkinter but never opens a window, so these run headless.
"""

import unittest

from cognitive_offload.rows import matrix_row as _matrix_row, task_row as _task_row
from cognitive_offload.models import MatrixTask, Task, today_iso


def badge_texts(row):
    return [badge.text for badge in row.badges]


def badge_variants(row):
    return [badge.variant for badge in row.badges]


class TaskRowTests(unittest.TestCase):
    def test_title_and_id_carry_through(self):
        task = Task(text="write the thing")
        row = _task_row(task)
        self.assertEqual(row.title, "write the thing")
        self.assertEqual(row.id, task.id)

    def test_first_step_becomes_the_subtitle(self):
        row = _task_row(Task(text="x", first_step="open the folder"))
        self.assertEqual(row.subtitle, "→ open the folder")

    def test_description_is_the_fallback_subtitle(self):
        row = _task_row(Task(text="x", description="some context\nmore"))
        self.assertEqual(row.subtitle, "some context")

    def test_no_subtitle_when_there_is_nothing_to_say(self):
        self.assertEqual(_task_row(Task(text="x")).subtitle, "")

    def test_ready_badge_only_when_a_first_step_exists(self):
        self.assertNotIn("ready", badge_texts(_task_row(Task(text="x"))))
        self.assertIn("ready", badge_texts(_task_row(Task(text="x", first_step="go"))))

    def test_feel_becomes_a_badge_with_its_own_colour(self):
        row = _task_row(Task(text="x", kind="creative"))
        self.assertIn("creative", badge_texts(row))
        self.assertIn("creative", badge_variants(row))

    def test_a_booking_due_today_says_today(self):
        row = _task_row(Task(text="x", scheduled_for=today_iso()))
        self.assertIn("today", badge_texts(row))
        self.assertIn("today", badge_variants(row))

    def test_a_future_booking_shows_its_date(self):
        row = _task_row(Task(text="x", scheduled_for="2999-01-01"))
        self.assertIn("booked 2999-01-01", badge_texts(row))
        self.assertNotIn("today", badge_texts(row))

    def test_tags_become_hash_badges(self):
        row = _task_row(Task(text="x", tags=["work", "home"]))
        self.assertIn("#work", badge_texts(row))
        self.assertIn("#home", badge_texts(row))

    def test_a_finished_task_drops_the_nagging_badges(self):
        task = Task(text="x", first_step="go", kind="admin", scheduled_for=today_iso())
        task.set_done(True)
        row = _task_row(task)
        self.assertEqual(badge_texts(row), ["done"])
        self.assertTrue(row.done)
        self.assertTrue(row.subtitle.startswith("done "))

    def test_flagged_is_marked_on_the_row_not_as_a_badge(self):
        row = _task_row(Task(text="x", priority=1))
        self.assertTrue(row.flagged)
        self.assertNotIn("priority", badge_texts(row))

    def test_row_text_includes_title_badges_and_subtitle(self):
        text = _task_row(Task(text="a task", first_step="step one", tags=["work"])).as_text()
        for fragment in ("a task", "ready", "#work", "step one"):
            self.assertIn(fragment, text)


class MatrixRowTests(unittest.TestCase):
    def test_title_first_step_and_badges(self):
        row = _matrix_row(MatrixTask(title="quarterly review", first_step="open the calendar",
                                     kind="deadline", scheduled_for="2999-01-01"))
        self.assertEqual(row.title, "quarterly review")
        self.assertEqual(row.subtitle, "→ open the calendar")
        self.assertIn("ready", badge_texts(row))
        self.assertIn("deadline", badge_texts(row))
        self.assertIn("booked 2999-01-01", badge_texts(row))

    def test_content_is_the_fallback_subtitle(self):
        row = _matrix_row(MatrixTask(title="t", content="a note about it"))
        self.assertEqual(row.subtitle, "a note about it")

    def test_due_booking_reads_today(self):
        row = _matrix_row(MatrixTask(title="t", scheduled_for=today_iso()))
        self.assertIn("today", badge_texts(row))


if __name__ == "__main__":
    unittest.main()
