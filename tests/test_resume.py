"""What was I doing?

An interruption costs the context, not the intention: you know you were
working, you have lost *what on*. Every piece of the answer was already being
written down — the session log knows what you were on and for how long, the
step log (v3.54.0) knows which step you actually finished, and the task knows
what comes next — and none of it was ever said out loud.

The slot it goes in matters as much as the sentence. The focus card read
"Nothing picked yet" when nothing was running: three words of dead text in
the most prominent place on the screen, at the exact moment someone is trying
to remember. Replacing dead text costs no pixels, which is the only kind of
addition this screen can afford after v3.48.0 spent a release taking things
off it.

The tone rules are load-bearing and tested rather than trusted: it never
counts the days, it never asks anything, and it says nothing rather than
something empty.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cognitive_offload import presenter
from cognitive_offload.models import Task
from cognitive_offload.sessions import FocusSession

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None


class FakeLog:
    def __init__(self, sessions):
        self.sessions = list(sessions)


def a_session(task_id, minutes=20, task="Write the quarterly report"):
    return FocusSession(minutes=minutes, task=task, task_id=task_id,
                        started_at="2026-08-19T10:00:00")


def a_step(task_id, step="copy the headings across", day="2026-08-19"):
    return {"step": step, "task": "Write the quarterly report",
            "task_id": task_id, "done_at": f"{day}T10:30:00"}


class WhatItSaysTests(unittest.TestCase):
    def setUp(self):
        self.task = Task(text="Write the quarterly report")
        self.log = FakeLog([a_session(self.task.id)])

    def _line(self, steps=(), tasks=None):
        return presenter.resume_line(
            self.log, list(steps),
            [self.task] if tasks is None else tasks)

    def test_the_bare_case_names_the_task_and_the_minutes(self):
        self.assertEqual(self._line(),
                         "Last time: 20 minutes on Write the quarterly report.")

    def test_one_minute_is_one_minute(self):
        self.log = FakeLog([a_session(self.task.id, minutes=1)])
        self.assertIn("1 minute on", self._line())
        self.assertNotIn("1 minutes", self._line())

    def test_a_step_you_finished_is_named(self):
        line = self._line(steps=[a_step(self.task.id)])
        self.assertIn("you finished", line)
        self.assertIn("copy the headings across", line)

    def test_what_comes_next_is_named(self):
        self.task.first_step = "fill in this year's numbers"
        self.assertIn("Next: fill in this year's numbers", self._line())

    def test_the_whole_sentence_together(self):
        self.task.first_step = "fill in this year's numbers"
        self.assertEqual(
            self._line(steps=[a_step(self.task.id)]),
            "Last time: 20 minutes on Write the quarterly report — you "
            "finished “copy the headings across”.\n"
            "Next: fill in this year's numbers")


class WhatItRefusesToSayTests(unittest.TestCase):
    def setUp(self):
        self.task = Task(text="Write the quarterly report")

    def _line(self, sessions=None, steps=(), tasks=None):
        log = FakeLog(sessions if sessions is not None else [a_session(self.task.id)])
        return presenter.resume_line(log, list(steps),
                                     [self.task] if tasks is None else tasks)

    def test_no_sessions_at_all_says_nothing(self):
        self.assertEqual(self._line(sessions=[]), "")

    def test_no_session_log_at_all_says_nothing(self):
        self.assertEqual(presenter.resume_line(None, None, [self.task]), "")

    def test_a_task_since_deleted_says_nothing(self):
        self.assertEqual(self._line(tasks=[]), "")

    def test_a_task_since_finished_says_nothing(self):
        """The card is for picking something up. A finished task is not that,
        and "last time you worked on the thing you have since completed" is a
        sentence with no use in it."""
        self.task.set_done(True)
        self.assertEqual(self._line(), "")

    def test_free_focus_sessions_are_skipped(self):
        """A session with no task cannot answer "what was I doing"; the one
        before it can."""
        line = self._line(sessions=[a_session(self.task.id),
                                    FocusSession(minutes=5, task="")])
        self.assertIn("Write the quarterly report", line)

    def test_the_most_recent_task_session_is_the_one_it_uses(self):
        other = Task(text="Ring the insurance company")
        log = FakeLog([a_session(other.id, task=other.text),
                       a_session(self.task.id)])
        # `other` first in the list on purpose: with both orders the same,
        # "matches by id" and "takes whatever is first" look identical.
        line = presenter.resume_line(log, [], [other, self.task])
        self.assertIn("Write the quarterly report", line)
        self.assertNotIn("insurance", line)

    def test_it_finds_the_task_by_id_and_not_by_position(self):
        """The list the app hands over is in whatever order the person is
        sorting by, which has nothing to do with what they last worked on."""
        others = [Task(text=f"Something else {i}") for i in range(3)]
        log = FakeLog([a_session(self.task.id)])
        line = presenter.resume_line(log, [], others + [self.task])
        self.assertIn("Write the quarterly report", line)
        self.assertNotIn("Something else", line)

    def test_a_step_from_another_task_is_not_borrowed(self):
        other = Task(text="Ring the insurance company")
        line = self._line(steps=[a_step(other.id, step="find the claim number")])
        self.assertNotIn("you finished", line)

    def test_a_step_written_before_ids_existed_is_not_guessed_at(self):
        """Entries from an older file carry no task_id. Matching them on the
        title would be a guess, and a wrong guess here puts words in
        someone's mouth about their own morning."""
        line = self._line(steps=[a_step("")])
        self.assertNotIn("you finished", line)


class ToneTests(unittest.TestCase):
    """These are the rules, not decoration."""

    def _lines(self):
        task = Task(text="Write the quarterly report",
                    first_step="fill in this year's numbers")
        log = FakeLog([a_session(task.id)])
        return [presenter.resume_line(log, [], [task]),
                presenter.resume_line(log, [a_step(task.id)], [task])]

    def test_it_never_counts_the_days(self):
        """"Six days ago" on a task you have been avoiding is a reproach, and
        this app keeps no score of that kind."""
        for line in self._lines():
            for word in ("ago", "days", "yesterday", "last week", "still",
                         "since", "haven't", "have not", "overdue", "left"):
                self.assertNotIn(word, line.lower(), f"the line says {word!r}")

    def test_it_never_asks_anything(self):
        """The point of reading it is to be spared a decision; a prompt at
        that moment puts one back."""
        for line in self._lines():
            self.assertNotIn("?", line)

    def test_it_says_what_happened_and_never_what_did_not(self):
        for line in self._lines():
            for word in ("only", "just", "no ", "nothing", "failed", "missed"):
                self.assertNotIn(word, line.lower(), f"the line says {word!r}")


def _display_available() -> bool:
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_display_available(), "tkinter display not available")
class OnTheFocusCardTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        self.app = CognitiveOffloadApp(config=config)
        self.app.withdraw()
        self.addCleanup(self._destroy)

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _worked_on(self, text="Write the quarterly report", first_step=""):
        self.app.capture_entry.insert(0, text)
        self.app.add_task_from_capture()
        task = self.app.tasks[0]
        task.first_step = first_step
        self.app.session_log.sessions.append(a_session(task.id, task=task.text))
        return task

    def test_an_empty_app_still_says_the_quiet_thing(self):
        self.app.set_idle_focus_caption()
        self.assertEqual(self.app.focus_task_var.get(), self.app.IDLE_CAPTION)

    def test_the_card_remembers_what_you_were_on(self):
        task = self._worked_on(first_step="fill in this year's numbers")
        self.app.set_idle_focus_caption()
        caption = self.app.focus_task_var.get()
        self.assertIn(task.text, caption)
        self.assertIn("Next: fill in this year's numbers", caption)

    def test_resetting_the_timer_leaves_the_memory_rather_than_dead_text(self):
        self._worked_on()
        self.app.reset_timer()
        self.assertTrue(self.app.focus_task_var.get().startswith("Last time:"))

    def test_a_running_focus_task_is_not_overwritten(self):
        """The card belongs to the session while there is one."""
        task = self._worked_on()
        self.app._focus_task_id = task.id
        self.app.focus_task_var.set("something the session put there")
        self.app._apply_state({"tasks": self.app.tasks, "scratchpad": "",
                               "timer_minutes": 15, "completed_log": [],
                               "steps_log": []})
        self.assertNotEqual(self.app.focus_task_var.get(), self.app.IDLE_CAPTION)

    def test_the_step_it_names_is_the_one_the_app_recorded(self):
        """End to end: tick a step off, and the card can say so."""
        task = self._worked_on()
        task.first_step = "open last year's report"
        task.set_rest(["copy the headings across"])
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = {
                "title": task.text, "content": "", "tags": [],
                "first_step": task.first_step, "kind": "", "scheduled_for": "",
                "estimate_minutes": 0, "repeat": "", "clear_snooze": False,
                "take_back": False, "waiting_on": "", "check_back": "",
                "rest_of_plan": ["copy the headings across"], "step_done": True}
            self.app.task_list.selection_set(0)
            self.app.edit_selected_details()
        self.app.set_idle_focus_caption()
        caption = self.app.focus_task_var.get()
        self.assertIn("you finished", caption)
        self.assertIn("open last year's report", caption)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class LengthTests(unittest.TestCase):
    """The three pieces the line quotes back are text the user typed.

    A person with a plan in their head types a paragraph into the capture box
    — that is the whole point of the capture box — and the line then quotes it
    back into a narrow card above the timer. Unbounded, it does not merely
    look untidy: at the window's minimum size a nine-line caption pushed the
    filter row, the task list and "Where do I start?" off the bottom of the
    panel, where nothing scrolls to reach them.
    """

    LONG = ("Write the quarterly report for the regional board including "
            "the appendices and the revised headcount figures")

    def test_a_short_piece_is_left_exactly_alone(self):
        self.assertEqual(presenter.short("Book the dentist"),
                         "Book the dentist")

    def test_a_piece_at_the_limit_is_left_alone(self):
        text = "x" * presenter.RESUME_PIECE_LIMIT
        self.assertEqual(presenter.short(text), text)

    def test_a_longer_piece_is_cut_and_marked_as_cut(self):
        cut = presenter.short(self.LONG)
        self.assertTrue(cut.endswith("…"), cut)
        self.assertLessEqual(len(cut), presenter.RESUME_PIECE_LIMIT + 1)
        self.assertTrue(self.LONG.startswith(cut[:-1]), cut)

    def test_it_cuts_between_words_when_one_is_near_enough(self):
        self.assertEqual(presenter.short(self.LONG), "Write the quarterly report for the…")

    def test_it_cuts_mid_word_rather_than_lose_half_the_line(self):
        # There *is* a word boundary here, four characters in — and using it
        # would leave "Ring…", which names nothing. A cut word carries more
        # of the task than a tidy break that throws the task away.
        self.assertEqual(
            presenter.short("Ring Reconciliationofthequarterlyheadcountfigures"),
            "Ring Reconciliationofthequarterlyheadcou…")

    def test_a_piece_with_no_word_boundary_at_all_is_still_cut(self):
        self.assertEqual(presenter.short("Reconciliationofthequarterlyheadcountfigures"),
                         "Reconciliationofthequarterlyheadcountfig…")

    def test_nothing_stays_nothing(self):
        self.assertEqual(presenter.short(""), "")
        self.assertEqual(presenter.short(None), "")

    def test_every_piece_of_the_line_is_bounded(self):
        task = Task(text=self.LONG)
        task.first_step = self.LONG
        line = presenter.resume_line(
            FakeLog([a_session(task.id, minutes=999, task=task.text)]),
            [a_step(task.id, step=self.LONG)], [task])
        self.assertNotIn(self.LONG, line)
        for piece in line.split("\n"):
            self.assertLessEqual(len(piece), 140, piece)
        self.assertEqual(line.count("…"), 3, line)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class AtTheSmallestWindowTests(unittest.TestCase):
    """The caption has to earn its pixels on the smallest screen too.

    Sized from ``minsize()`` rather than from two numbers: the floor is
    clamped to the screen, so a test that names 1120x700 passes on the
    development display and fails on a 1024x768 laptop — which is exactly how
    the last size test broke CI.
    """

    LONG = ("Write the quarterly report for the regional board including "
            "the appendices and the revised headcount figures")
    WANTED = ("Where do I start?", "Start")

    def setUp(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        self.app = CognitiveOffloadApp(config=config)
        self.addCleanup(self._destroy)
        self.app.deiconify()
        self.app.geometry("{}x{}".format(*self.app.minsize()))

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _fill_the_card(self):
        self.app.capture_entry.insert(0, self.LONG)
        self.app.add_task_from_capture()
        task = self.app.tasks[0]
        task.first_step = self.LONG
        self.app.steps_log.append(a_step(task.id, step=self.LONG))
        self.app.session_log.sessions.append(a_session(task.id, task=task.text))
        self.app.refresh_tasks()
        self.app.set_idle_focus_caption()
        self.app.update()
        self.app.update_idletasks()

    def _off_the_bottom(self):
        """Which of the primary buttons a person cannot see or reach."""
        floor = self.app.winfo_height()
        missing = []

        def walk(widget):
            for child in widget.winfo_children():
                text = child.cget("text") if "text" in child.keys() else ""
                if text in self.WANTED:
                    bottom = (child.winfo_rooty() - self.app.winfo_rooty()
                              + child.winfo_height())
                    if not child.winfo_ismapped() or bottom > floor:
                        missing.append(text)
                walk(child)

        walk(self.app)
        return missing

    def test_the_primary_buttons_survive_the_longest_caption(self):
        self._fill_the_card()
        self.assertEqual(self._off_the_bottom(), [])

    def test_they_are_the_buttons_this_test_thinks_they_are(self):
        # Without this the test above passes just as well when the two
        # buttons have been renamed and the walk finds nothing at all.
        self._fill_the_card()
        found = []

        def walk(widget):
            for child in widget.winfo_children():
                text = child.cget("text") if "text" in child.keys() else ""
                if text in self.WANTED:
                    found.append(text)
                walk(child)

        walk(self.app)
        self.assertEqual(sorted(set(found)), sorted(self.WANTED))

    def _caption_height(self):
        self.app.set_idle_focus_caption()
        self.app.update()
        self.app.update_idletasks()
        return self.app.focus_task_label.winfo_height()

    def test_an_unbounded_caption_is_what_would_push_them_out(self):
        # The pressure the bound exists to relieve, measured rather than
        # asserted about. Deliberately *not* "the buttons go missing": whether
        # they do depends on how wide the floor is on this screen, and a test
        # that believes in its own display is how the last size test broke CI.
        # The caption's own height is the thing that does not vary that way.
        # Measured in one window rather than two: a freshly built window has
        # not had its Configure event yet, so its label has no wrap width and
        # every caption measures one line tall.
        self._fill_the_card()
        bounded = self._caption_height()
        with mock.patch.object(presenter, "short", lambda text, limit=None: text):
            self.assertGreaterEqual(self._caption_height(), 2 * bounded)
