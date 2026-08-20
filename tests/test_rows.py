"""Row building: what a task looks like in the list.

Imports tkinter but never opens a window, so these run headless.
"""

import unittest

from cognitive_offload.rows import (
    TITLE_LIMIT,
    matrix_row as _matrix_row,
    short as _short,
    task_row as _task_row,
)
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


class PastedParagraphTests(unittest.TestCase):
    """A row draws a ceiling; the task keeps everything.

    Row height grew about 0.43px per character with nothing stopping it. A
    1000-character paste made a row 437px tall — taller than the whole
    visible list at the window's floor — a 4000-character one 1729px, and
    8000 characters took the X server's pixmap allocation down with the app.

    Three hundred characters is a guard rail, not a wrap-vs-ellipsis policy:
    the longest title in this project's own fixtures is 138 characters, so it
    never touches anything a person typed.
    """

    # Stripped: a Task strips its own text, so a fixture ending in a space
    # would fail the "keeps every character" check on the space rather
    # than on anything this is about.
    PARAGRAPH = ("Ring the insurance company about the rejected claim. " * 40).strip()

    def test_an_ordinary_title_is_untouched(self):
        text = ("Write the quarterly report for the regional board including "
                "the appendices and the revised headcount figures")
        self.assertLess(len(text), TITLE_LIMIT)
        self.assertEqual(_task_row(Task(text=text)).title, text)

    def test_a_title_at_the_limit_is_untouched(self):
        text = "x" * TITLE_LIMIT
        self.assertEqual(_task_row(Task(text=text)).title, text)

    def test_a_pasted_paragraph_is_cut_and_marked(self):
        row = _task_row(Task(text=self.PARAGRAPH))
        self.assertLessEqual(len(row.title), TITLE_LIMIT + 1)
        self.assertTrue(row.title.endswith("…"))
        self.assertTrue(self.PARAGRAPH.startswith(row.title[:-1]))

    def test_the_task_itself_keeps_every_character(self):
        """The ceiling is on what is drawn. Losing the text would be a far
        worse bug than the one being fixed."""
        task = Task(text=self.PARAGRAPH)
        _task_row(task)
        self.assertEqual(task.text, self.PARAGRAPH)

    def test_the_length_stops_mattering_past_the_limit(self):
        short_row = _task_row(Task(text=self.PARAGRAPH))
        longer = _task_row(Task(text=self.PARAGRAPH * 10))
        self.assertEqual(short_row.title, longer.title)

    def test_a_quadrant_row_gets_the_same_ceiling(self):
        row = _matrix_row(MatrixTask(title=self.PARAGRAPH))
        self.assertLessEqual(len(row.title), TITLE_LIMIT + 1)
        self.assertTrue(row.title.endswith("…"))

    def test_search_still_finds_what_the_row_no_longer_shows(self):
        """The words past the cut are still the task's, and still findable."""
        from cognitive_offload.queries import visible_tasks

        task = Task(text=self.PARAGRAPH + " ask for a supervisor")
        self.assertNotIn("supervisor", _task_row(task).title)
        self.assertEqual(visible_tasks([task], search="supervisor"), [task])

    def test_the_next_up_strip_gets_the_same_ceiling(self):
        from cognitive_offload import presenter

        task = Task(text=self.PARAGRAPH)
        task.first_step = "find the policy number"
        view = presenter.next_up_view([task])
        self.assertLessEqual(len(view.title), TITLE_LIMIT + 1)
        self.assertTrue(view.title.endswith("…"))

    def test_the_limit_is_generous_enough_to_be_invisible(self):
        """A guard rail that trips on ordinary use is not a guard rail."""
        self.assertGreaterEqual(TITLE_LIMIT, 200)


class ShortTests(unittest.TestCase):
    def test_it_cuts_on_a_word_boundary_when_one_is_near(self):
        self.assertEqual(_short("Ring the insurance company", 20),
                         "Ring the insurance…")

    def test_it_cuts_mid_word_rather_than_lose_half_the_line(self):
        self.assertEqual(_short("Reconciliationofthequarterly", 20),
                         "Reconciliationofthequ"[:20] + "…")

    def test_nothing_stays_nothing(self):
        self.assertEqual(_short("", 20), "")
        self.assertEqual(_short(None, 20), "")

    def test_the_resume_line_and_the_rows_share_one_cutter(self):
        """Two callers, two very different lengths, one rule — because two
        copies of a rule is how the two answers drift."""
        from cognitive_offload import presenter

        self.assertEqual(presenter.short("Ring the insurance company", 20),
                         _short("Ring the insurance company", 20))
