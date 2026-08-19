"""Steps finished are evidence, and nothing was writing them down.

`week_view` counts sessions, minutes and *finished tasks*. A step ticked off
is none of those, so a week spent moving through a four-step report showed
effort and no outcome — on the one screen whose stated job is that "I did
nothing this week" is a distortion the record corrects.

The obstacle was that `steps_done` is a **cursor, not a history**: nothing on
the task says when a step was ticked, so if it is not written down at the
moment it happens the evidence does not exist. Hence a log, the same shape as
the completed-tasks log that already exists so that tidying up cannot erase
the answer to "what did I get done today".

The cheaper idea — record the step on the focus session — was rejected on
purpose: it would credit steps ticked at session end and silently miss those
ticked in the editor, and a record that covers some of the thing is worse
than one that admits its scope.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cognitive_offload import presenter
from cognitive_offload.storage import STEPS_LOG_LIMIT, StateStore

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None

PLAN = ["open last year's report", "copy the headings across",
        "fill in this year's numbers", "send it to Dana"]


def entry(step, task="Write the quarterly report", day="2026-08-19"):
    return {"step": step, "task": task, "done_at": f"{day}T10:00:00"}


class ReadingTheLogTests(unittest.TestCase):
    def test_it_takes_the_steps_from_the_day_asked_for(self):
        log = [entry(PLAN[0], day="2026-08-18"), entry(PLAN[1]),
               entry(PLAN[2], day="2026-08-20")]
        self.assertEqual(presenter.steps_done_on(log, "2026-08-19"),
                         [(PLAN[1], "Write the quarterly report")])

    def test_it_keeps_the_order_they_were_done_in(self):
        log = [entry(PLAN[0]), entry(PLAN[1]), entry(PLAN[2])]
        self.assertEqual([s for s, _ in presenter.steps_done_on(log, "2026-08-19")],
                         PLAN[:3])

    def test_junk_in_the_file_is_simply_not_a_step(self):
        log = ["a string", None, {}, {"step": ""}, {"step": "   "},
               {"step": "real", "done_at": "2026-08-19T09:00:00"}]
        self.assertEqual(presenter.steps_done_on(log, "2026-08-19"),
                         [("real", "")])

    def test_no_log_at_all_is_no_steps(self):
        self.assertEqual(presenter.steps_done_on(None, "2026-08-19"), [])

    def test_a_step_is_named_with_the_task_it_belongs_to(self):
        """On its own a step is a fragment — "copy the headings across" is
        not evidence of anything — and a record that cannot be understood is
        not a record."""
        self.assertEqual(presenter.step_line("copy the headings", "The report"),
                         "copy the headings — The report")
        self.assertEqual(presenter.step_line("copy the headings", ""),
                         "copy the headings")


class WeekReviewTests(unittest.TestCase):
    def setUp(self):
        from datetime import date

        self.today = date(2026, 8, 19)

    def _view(self, log):
        return presenter.week_view([], [], None, today=self.today, steps_log=log)

    def test_a_day_with_only_steps_now_appears_at_all(self):
        """The case the whole finding is about: no session logged, nothing
        marked done, and three steps of a long task moved. That week used to
        read as empty."""
        view = self._view([entry(PLAN[0]), entry(PLAN[1])])
        self.assertEqual(len(view.days), 1)
        self.assertEqual(view.days[0].label, "Today")
        self.assertEqual([s for s, _ in view.days[0].steps], PLAN[:2])

    def test_a_day_with_nothing_is_still_left_out(self):
        """No zeros. A week review that reads as a row of noughts is one
        nobody opens twice."""
        # 2026-08-13 is INSIDE the window (offset 6), which is what makes
        # this test worth having: the date has to be genuinely out of range.
        self.assertEqual(self._view([entry(PLAN[0], day="2026-08-10")]).days, [])
        self.assertEqual(len(self._view([entry(PLAN[0], day="2026-08-13")]).days), 1)

    def test_steps_land_on_the_day_they_were_done(self):
        view = self._view([entry(PLAN[0], day="2026-08-17"), entry(PLAN[1])])
        self.assertEqual([d.label for d in view.days], ["Monday", "Today"])
        self.assertEqual([s for s, _ in view.days[0].steps], [PLAN[0]])

    def test_finished_tasks_and_finished_steps_stay_separate(self):
        """They are different evidence and must not be summed into one list
        that says neither thing clearly."""
        view = self._view([entry(PLAN[0])])
        self.assertEqual(view.days[0].titles, [])
        self.assertEqual(len(view.days[0].steps), 1)


class TodayViewTests(unittest.TestCase):
    def test_what_you_finished_today_includes_steps(self):
        view = presenter.today_view([], [], None, on="2026-08-19",
                                    steps_log=[entry(PLAN[0])])
        self.assertIn(PLAN[0], view.body)
        self.assertIn("Write the quarterly report", view.body)

    def test_a_day_with_neither_says_nothing_at_all(self):
        view = presenter.today_view([], [], None, on="2026-08-19", steps_log=[])
        self.assertEqual(view.body, "")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data.json"

    def test_the_log_survives_being_written_out(self):
        log = [entry(PLAN[0]), entry(PLAN[1])]
        StateStore(self.path).save([], "", 15, [], log)
        back = StateStore(self.path).load()
        self.assertEqual(back["steps_log"], log)

    def test_a_file_from_before_this_existed_still_loads(self):
        StateStore(self.path).save([], "", 15, [])
        self.assertEqual(StateStore(self.path).load()["steps_log"], [])

    def test_it_is_capped_rather_than_growing_for_ever(self):
        log = [entry(f"step {i}") for i in range(STEPS_LOG_LIMIT + 40)]
        StateStore(self.path).save([], "", 15, [], log)
        back = StateStore(self.path).load()["steps_log"]
        self.assertEqual(len(back), STEPS_LOG_LIMIT)
        self.assertEqual(back[-1]["step"], f"step {STEPS_LOG_LIMIT + 39}",
                         "the cap dropped the newest instead of the oldest")

    def test_a_damaged_entry_does_not_take_the_file_with_it(self):
        StateStore(self.path).save([], "", 15, [])
        import json

        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["steps_log"] = ["nonsense", {"step": 7}, entry(PLAN[0])]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        back = StateStore(self.path).load()["steps_log"]
        self.assertEqual([e["step"] for e in back], [PLAN[0]])

    def test_the_cap_is_roomier_than_the_completed_log(self):
        """A week of steps is many more entries than a week of finished
        tasks, and the log is the only copy."""
        from cognitive_offload.storage import COMPLETED_LOG_LIMIT

        self.assertGreater(STEPS_LOG_LIMIT, COMPLETED_LOG_LIMIT)


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
class ThroughTheAppTests(unittest.TestCase):
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

    def _planned_task(self):
        self.app.capture_entry.insert(0, "Write the quarterly report")
        self.app.add_task_from_capture()
        task = self.app.tasks[0]
        task.first_step = PLAN[0]
        task.set_rest(PLAN[1:])
        self.app.task_list.selection_set(0)
        return task

    def _result(self, **overrides):
        result = {"title": "Write the quarterly report", "content": "", "tags": [],
                  "first_step": PLAN[0], "kind": "", "scheduled_for": "",
                  "estimate_minutes": 0, "repeat": "", "clear_snooze": False,
                  "take_back": False, "waiting_on": "", "check_back": "",
                  "rest_of_plan": PLAN[1:], "step_done": False}
        result.update(overrides)
        return result

    def _edit(self, **overrides):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._result(**overrides)
            self.app.edit_selected_details()

    def test_ticking_a_step_writes_down_the_step_that_was_finished(self):
        """The one you just did, not the one you moved to."""
        self._planned_task()
        self._edit(step_done=True)
        self.assertEqual(len(self.app.steps_log), 1)
        written = self.app.steps_log[0]
        self.assertEqual(written["step"], PLAN[0])
        self.assertEqual(written["task"], "Write the quarterly report")
        self.assertTrue(written["done_at"])

    def test_saving_nothing_writes_nothing(self):
        self._planned_task()
        self._edit()
        self.assertEqual(self.app.steps_log, [])

    def test_undo_takes_the_record_back_with_the_cursor(self):
        """Restoring the cursor and leaving the entry behind would leave the
        week review claiming a step was finished that, as far as the task is
        concerned, never was."""
        self._planned_task()
        self._edit(step_done=True)
        self.app.undo()
        # Read back off the app: undo replaces the list with copies from the
        # snapshot, so a reference held from before is a different object.
        self.assertEqual(self.app.tasks[0].steps_done, 0)
        self.assertEqual(self.app.tasks[0].first_step, PLAN[0])
        self.assertEqual(self.app.steps_log, [])

    def test_undo_gives_back_the_earlier_steps_and_only_the_last(self):
        """One tick undone must leave the ones before it standing.

        The obvious version of this test — tick once, undo, expect an empty
        log — passes even when nothing is snapshotted at all, because empty
        is the right answer either way. It also passes when the snapshot
        merely *aliases* the live list. Two ticks and one undo separate all
        three cases.
        """
        self._planned_task()
        self._edit(step_done=True)
        self.assertEqual([e["step"] for e in self.app.steps_log], [PLAN[0]])
        self._edit(first_step=PLAN[1], rest_of_plan=PLAN[2:], step_done=True)
        self.assertEqual([e["step"] for e in self.app.steps_log], PLAN[:2])
        self.app.undo()
        self.assertEqual([e["step"] for e in self.app.steps_log], [PLAN[0]],
                         "undo took back a step that was finished earlier")
        self.assertEqual(self.app.tasks[0].steps_done, 1)

    def test_the_session_end_route_writes_it_too(self):
        task = self._planned_task()
        self.app._focus_task_id = task.id
        with mock.patch("cognitive_offload.app.SessionEndDialog") as dialog:
            dialog.return_value.show.return_value = {
                "choice": "carry_on", "next_step": "", "step_done": True}
            self.app._finish_session(15)
        self.assertEqual([e["step"] for e in self.app.steps_log], [PLAN[0]])

    def test_the_matrix_route_writes_it_too_and_undo_still_works(self):
        created = self.app.matrix.create("do_first", "Write the quarterly report")
        created.first_step = PLAN[0]
        created.set_rest(PLAN[1:])
        self.app.matrix.update(created, created.title, created.content)
        self.app.refresh_matrix()
        self.app.matrix_lists["do_first"].selection_set(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            result = self._result(step_done=True)
            del result["tags"]
            editor.return_value.show.return_value = result
            self.app.edit_matrix_task("do_first")
        self.assertEqual([e["step"] for e in self.app.steps_log], [PLAN[0]])
        # This flow registers its undo entry AFTER the writes, so its own
        # snapshot already holds the new entry — the restore has to win.
        self.app.undo()
        self.assertEqual(self.app.steps_log, [])

    def test_the_week_review_shows_it(self):
        self._planned_task()
        self._edit(step_done=True)
        view = presenter.week_view(self.app.tasks, self.app.completed_log,
                                   self.app.session_log,
                                   steps_log=self.app.steps_log)
        self.assertTrue(view.days)
        self.assertIn(PLAN[0], [s for s, _ in view.days[-1].steps])

    def test_it_reaches_the_disk_and_comes_back(self):
        self._planned_task()
        self._edit(step_done=True)
        self.app.save_state(silent=True)
        reloaded = StateStore(self.app.config_store.state_file).load()
        self.assertEqual([e["step"] for e in reloaded["steps_log"]], [PLAN[0]])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TheDoneTodayPillTests(unittest.TestCase):
    """The number on the pill is a promise about the panel it opens.

    The panel began listing finished steps as well as finished tasks; the
    pill went on counting tasks. Two consequences, and the second is the
    serious one: the number disagreed with what it opened, and on a day spent
    moving through one long task and finishing nothing the count was zero —
    which hides the pill, which is the panel's **only** route. One
    `Button-1` binding, no keyboard shortcut. The evidence existed and could
    not be reached.
    """

    def _view(self, tasks=(), steps=()):
        return presenter.task_list_view(list(tasks), completed_log=[],
                                        steps_log=list(steps))

    def _today(self):
        from cognitive_offload.models import today_iso

        return today_iso()

    def test_a_day_of_only_steps_still_shows_the_pill(self):
        view = self._view(steps=[entry(PLAN[0], day=self._today()),
                                 entry(PLAN[1], day=self._today())])
        self.assertEqual(view.done_today, 2)
        self.assertEqual(view.done_today_text, "2 done today →")

    def test_a_day_with_neither_still_says_nothing(self):
        """No zeros. "0 done today" is the kind of scoreboard this app exists
        not to keep."""
        self.assertEqual(self._view().done_today_text, "")

    def test_steps_from_another_day_do_not_count(self):
        self.assertEqual(self._view(steps=[entry(PLAN[0], day="2020-01-01")])
                         .done_today, 0)

    def test_the_number_matches_what_the_panel_lists(self):
        """The promise itself, asserted rather than assumed: whatever the
        pill says, the panel behind it has that many lines."""
        from cognitive_offload.models import Task

        done = Task(text="Ring the dentist")
        done.set_done(True)
        steps = [entry(PLAN[0], day=self._today()),
                 entry(PLAN[1], day=self._today())]
        view = self._view(tasks=[done], steps=steps)
        panel = presenter.today_view([done], [], None, steps_log=steps)
        listed = [line for line in panel.body.splitlines()
                  if line.startswith("·  ")]
        self.assertEqual(view.done_today, len(listed))
        self.assertEqual(view.done_today, 3)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class ThePillOnScreenTests(unittest.TestCase):
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

    def test_the_pill_is_hidden_on_a_day_with_nothing(self):
        self.app.refresh_tasks()
        self.app.update()
        self.assertFalse(self.app.today_label.winfo_manager())

    def test_a_day_of_only_steps_makes_the_pill_appear(self):
        """Which is what makes the panel reachable at all: the pill is its
        only route."""
        from cognitive_offload.models import today_iso

        self.app.steps_log = [entry(PLAN[0], day=today_iso())]
        self.app.refresh_tasks()
        self.app.update()
        self.assertTrue(self.app.today_label.winfo_manager(),
                        "the only way into the panel is hidden")
        self.assertIn("1 done today", self.app.today_var.get())
