"""Breaking a task into steps, and the one invariant that makes it safe.

A task held exactly one step. The moment it was done the task was a blank
wall again, so every transition charged a fresh decision — the one thing this
app's own rules say not to charge for. "Write the report" is a wall; "open
last year's, copy the headings, fill in the numbers" is three things you can
start.

The design constraint was not the feature, it was `first_step`: **forty-seven
references across seven modules**, and it is what `is_ready` reads, which is
what the whole "where do I start?" ranking scores highest. A second answer to
"what next" would have been a second source of truth, and this project has
spent several releases fixing exactly that shape of bug.

So there is no second answer. A task with a plan *defines* `first_step` as
`steps[steps_done]`, `_fix_steps` is the only place that says so, and not one
of those forty-seven readers changed. Most of this file is about that
invariant holding under editing, loading, repeating and junk input, because
the day it stops holding is the day the row and the ranking disagree about
what you are supposed to be doing.
"""

import dataclasses
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cognitive_offload.models import MatrixTask, Task
from cognitive_offload.rows import matrix_row, task_row

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None

PLAN = ["open last year's report", "copy the headings across",
        "fill in this year's numbers", "send it to Dana"]


def planned(**kw) -> Task:
    task = Task(text="Write the quarterly report", **kw)
    task.set_rest(PLAN[1:])
    return task


class BuildingAPlanTests(unittest.TestCase):
    def setUp(self):
        self.task = Task(text="Write the quarterly report",
                         first_step=PLAN[0])
        self.task.set_rest(PLAN[1:])

    def test_the_step_you_are_on_heads_the_plan(self):
        self.assertEqual(self.task.steps, PLAN)
        self.assertEqual(self.task.steps_done, 0)
        self.assertEqual(self.task.first_step, PLAN[0])

    def test_the_editor_is_shown_the_rest_and_not_the_step_itself(self):
        """The step box owns one line and the plan box owns the rest. Showing
        the same line in both is how two controls end up disagreeing about
        which of them won."""
        self.assertEqual(self.task.rest_of_plan, PLAN[1:])

    def test_a_plan_of_one_step_is_just_a_first_step(self):
        """Two ways to say the same thing is how they drift. The app already
        has a field, a badge and a whole vocabulary for one step."""
        task = Task(text="Bins", first_step="wheel it to the kerb")
        task.set_rest([])
        self.assertEqual(task.steps, [])
        self.assertEqual(task.first_step, "wheel it to the kerb")

    def test_a_plan_typed_against_no_first_step_supplies_one(self):
        task = Task(text="Write the report")
        task.set_rest(PLAN)
        self.assertEqual(task.first_step, PLAN[0])
        self.assertEqual(task.steps, PLAN)

    def test_rewriting_what_is_left_keeps_where_you_got_to(self):
        """Changing your mind about the rest must not throw away the fact
        that you have already done two of them."""
        self.task.advance_step()
        self.task.advance_step()
        self.assertEqual(self.task.steps_done, 2)
        self.task.set_rest(["email it to Dana instead"])
        self.assertEqual(self.task.steps_done, 2)
        self.assertEqual(self.task.steps[:3], PLAN[:3])
        self.assertEqual(self.task.steps[3], "email it to Dana instead")

    def test_blank_lines_and_padding_are_not_steps(self):
        task = Task(text="x", first_step="a")
        task.set_rest(["  b  ", "", "   ", "c"])
        self.assertEqual(task.steps, ["a", "b", "c"])


class MovingThroughAPlanTests(unittest.TestCase):
    def setUp(self):
        self.task = planned(first_step=PLAN[0])

    def test_ticking_a_step_off_moves_the_first_step_with_it(self):
        self.assertTrue(self.task.advance_step())
        self.assertEqual(self.task.steps_done, 1)
        self.assertEqual(self.task.first_step, PLAN[1])

    def test_the_last_step_has_nowhere_to_advance_to(self):
        for _ in range(len(PLAN) - 1):
            self.assertTrue(self.task.advance_step())
        self.assertFalse(self.task.advance_step())
        self.assertEqual(self.task.first_step, PLAN[-1])
        self.assertEqual(self.task.steps_left, 0)

    def test_a_task_with_no_plan_cannot_advance(self):
        self.assertFalse(Task(text="x", first_step="a").advance_step())

    def test_steps_left_counts_what_comes_after_this_one(self):
        self.assertEqual(self.task.steps_left, 3)
        self.task.advance_step()
        self.assertEqual(self.task.steps_left, 2)

    def test_rewording_the_step_rewrites_it_where_it_lives(self):
        """Editing the step box on a task with a plan has to reach the plan,
        or the two disagree until the next load silently reverts the edit."""
        self.task.advance_step()
        self.task.set_current_step("copy the headings, not the numbers")
        self.assertEqual(self.task.first_step, "copy the headings, not the numbers")
        self.assertEqual(self.task.steps[1], "copy the headings, not the numbers")
        self.assertEqual(Task.from_dict(self.task.to_dict()).first_step,
                         "copy the headings, not the numbers")

    def test_emptying_a_step_removes_it_rather_than_leaving_a_hole(self):
        self.task.advance_step()
        self.task.set_current_step("")
        self.assertNotIn("", self.task.steps)
        self.assertEqual(self.task.steps, [PLAN[0], PLAN[2], PLAN[3]])
        self.assertEqual(self.task.first_step, PLAN[2])


class TheInvariantTests(unittest.TestCase):
    """`first_step == steps[steps_done]`, held in one place, or the row and
    the ranking disagree about what you are supposed to be doing."""

    def test_a_drifted_file_is_repaired_rather_than_believed(self):
        task = Task.from_dict({"text": "x", "steps": PLAN, "steps_done": 2,
                               "first_step": "something else entirely"})
        self.assertEqual(task.first_step, PLAN[2])

    def test_a_cursor_past_the_end_is_pulled_back_to_the_last_step(self):
        task = Task.from_dict({"text": "x", "steps": PLAN, "steps_done": 99})
        self.assertEqual(task.steps_done, len(PLAN) - 1)
        self.assertEqual(task.first_step, PLAN[-1])

    def test_a_negative_or_unreadable_cursor_starts_at_the_beginning(self):
        for value in (-4, "two", None, 1.5e9):
            with self.subTest(steps_done=value):
                task = Task.from_dict({"text": "x", "steps": PLAN,
                                       "steps_done": value})
                self.assertTrue(0 <= task.steps_done < len(PLAN))
                self.assertEqual(task.first_step, PLAN[task.steps_done])

    def test_junk_where_the_plan_should_be_is_no_plan(self):
        for value in ("just a string", 7, {"a": 1}, [None, 3, ""], None):
            with self.subTest(steps=value):
                task = Task.from_dict({"text": "x", "steps": value})
                self.assertIsInstance(task.steps, list)
                self.assertTrue(all(isinstance(s, str) and s for s in task.steps))

    def test_the_invariant_survives_the_disk(self):
        task = planned(first_step=PLAN[0])
        task.advance_step()
        back = Task.from_dict(task.to_dict())
        self.assertEqual(back.steps, task.steps)
        self.assertEqual(back.steps_done, task.steps_done)
        self.assertEqual(back.first_step, back.steps[back.steps_done])

    def test_both_models_hold_it(self):
        item = MatrixTask(title="x", steps=PLAN, steps_done=2,
                          first_step="stale")
        self.assertEqual(item.first_step, PLAN[2])
        self.assertTrue(item.advance_step())
        self.assertEqual(item.first_step, PLAN[3])

    def test_the_two_models_offer_the_same_plan_surface(self):
        """Two copies of a predicate is how the two tabs' answers drift
        apart; the waiting mark was written as free functions for exactly
        this reason and so is this."""
        for name in ("steps", "steps_done", "rest_of_plan", "set_rest",
                     "set_current_step", "advance_step", "steps_left"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(Task(text="x"), name))
                self.assertTrue(hasattr(MatrixTask(title="x"), name))

    def test_a_task_with_a_plan_is_ready_to_start(self):
        """`is_ready` reads `first_step`, and the ranking scores it highest.
        A plan must therefore make a task MORE startable, never less."""
        self.assertTrue(planned().is_ready)


class FindingItAgainTests(unittest.TestCase):
    """Search read the title, the details, the CURRENT step and the tags —
    so a plan's later steps were invisible to it. The app says out loud that
    a task stays "in every search"; a step you typed and cannot find teaches
    you to distrust the whole box."""

    def setUp(self):
        self.task = Task(text="Write the quarterly report",
                         description="for the board")
        self.task.set_rest(PLAN[:2] + ["ring the insurance company about the excess"])

    def test_a_step_you_have_not_reached_yet_is_findable(self):
        self.assertTrue(self.task.matches("insurance"))

    def test_a_step_you_have_already_passed_is_still_findable(self):
        self.task.advance_step()
        self.task.advance_step()
        self.assertTrue(self.task.matches(PLAN[0]))

    def test_the_things_that_always_matched_still_do(self):
        for term in ("quarterly", "board", PLAN[0], "QUARTERLY"):
            with self.subTest(term=term):
                self.assertTrue(self.task.matches(term))

    def test_it_has_not_started_matching_everything(self):
        for term in ("mortgage", "zzz"):
            with self.subTest(term=term):
                self.assertFalse(self.task.matches(term))

    def test_a_task_with_no_plan_is_unaffected(self):
        plain = Task(text="Bins", first_step="wheel it to the kerb")
        self.assertTrue(plain.matches("kerb"))
        self.assertFalse(plain.matches("insurance"))

    def test_the_visible_list_finds_it_too(self):
        """The wiring, not just the predicate: `filter_tasks` is what the
        search box actually calls."""
        from cognitive_offload.queries import visible_tasks

        other = Task(text="Book the dentist")
        found = visible_tasks([self.task, other], search="insurance")
        self.assertEqual([t.text for t in found], ["Write the quarterly report"])


class WhatTheRowSaysTests(unittest.TestCase):
    def test_a_task_with_a_plan_says_where_in_it_you_are(self):
        task = planned(first_step=PLAN[0])
        task.advance_step()
        self.assertEqual(task_row(task).subtitle,
                         f"→ {PLAN[1]} · step 2 of 4")

    def test_a_plan_that_has_shrunk_to_one_step_stops_calling_itself_a_plan(self):
        """Reachable, not theoretical: delete the only other step and the
        plan has one entry. A row reading "step 1 of 1" is a control that
        tells you nothing, in the slot where the first step should be."""
        task = Task(text="x", first_step="a")
        task.set_rest(["b"])
        self.assertEqual(task.steps, ["a", "b"])
        task.advance_step()
        task.set_current_step("")           # drop "b"
        self.assertEqual(task.steps, [])
        self.assertEqual(task.first_step, "a")
        self.assertEqual(task_row(task).subtitle, "→ a")

    def test_a_single_step_plan_loaded_from_a_file_is_not_one_either(self):
        task = Task.from_dict({"text": "x", "steps": ["only this"]})
        self.assertEqual(task.steps, [])
        self.assertEqual(task.first_step, "only this")
        self.assertNotIn("step 1 of", task_row(task).subtitle)

    def test_a_task_with_no_plan_reads_exactly_as_it_always_did(self):
        task = Task(text="x", first_step="open the doc")
        self.assertEqual(task_row(task).subtitle, "→ open the doc")

    def test_the_matrix_row_says_the_same_thing(self):
        item = MatrixTask(title="x", steps=PLAN, steps_done=3)
        self.assertEqual(matrix_row(item).subtitle,
                         f"→ {PLAN[3]} · step 4 of 4")

    def test_a_task_out_with_someone_still_says_that_first(self):
        """The waiting line wins: the step belongs to whoever has it now."""
        task = planned(first_step=PLAN[0], handed_to="Dana")
        self.assertIn("Waiting on Dana", task_row(task).subtitle)
        self.assertNotIn("step 1 of", task_row(task).subtitle)

    def test_it_counts_what_exists_and_never_what_is_missing(self):
        """The line is evidence of progress, not a debt. This app has no
        streaks, no zeros and no scolding, and a plan must not smuggle one
        in through the subtitle."""
        task = planned(first_step=PLAN[0])
        for _ in range(3):
            subtitle = task_row(task).subtitle.lower()
            for word in ("left", "remaining", "still", "outstanding", "only",
                         "incomplete", "unfinished", "behind", "overdue"):
                self.assertNotIn(word, subtitle, f"the plan line says {word!r}")
            task.advance_step()


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
class EditorTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _editor(self, **kw):
        from cognitive_offload.dialogs import TaskEditorDialog

        kw.setdefault("title", "Write the quarterly report")
        dialog = TaskEditorDialog(self.root, **kw)
        self.addCleanup(dialog.destroy)
        return dialog

    def test_the_plan_box_holds_the_rest_and_not_the_current_step(self):
        dialog = self._editor(first_step=PLAN[0], rest_of_plan=PLAN[1:])
        self.assertEqual(dialog.plan_text.get("1.0", "end").strip(),
                         "\n".join(PLAN[1:]))

    def test_the_tick_box_appears_only_when_there_is_somewhere_to_go(self):
        self.assertIsNone(self._editor(first_step="a").step_done_var)
        self.assertIsNotNone(
            self._editor(first_step="a", rest_of_plan=["b"]).step_done_var)

    def test_the_tick_box_names_the_step_it_would_move_you_to(self):
        from tkinter import ttk

        dialog = self._editor(first_step=PLAN[0], rest_of_plan=PLAN[1:])
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Checkbutton):
                    texts.append(child.cget("text"))
                walk(child)

        walk(dialog)
        self.assertTrue(any(PLAN[1] in text for text in texts), texts)

    def test_what_someone_pastes_in_is_taken_as_steps(self):
        """split_lines already strips bullets, checkboxes and the "[time]"
        prefix quick capture writes — which is exactly the shape of a note
        someone made earlier and is now pasting in."""
        dialog = self._editor(first_step="a")
        dialog.plan_text.insert("1.0", "- b\n* [ ] c\n\n  • d  \n")
        self.assertEqual(dialog.collect()["rest_of_plan"], ["b", "c", "d"])

    def test_an_empty_plan_box_returns_an_empty_plan(self):
        self.assertEqual(self._editor(first_step="a").collect()["rest_of_plan"], [])


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

    def _result(self, **overrides):
        result = {"title": "Write the quarterly report", "content": "", "tags": [],
                  "first_step": PLAN[0], "kind": "", "scheduled_for": "",
                  "estimate_minutes": 0, "repeat": "", "clear_snooze": False,
                  "take_back": False, "waiting_on": "", "check_back": "",
                  "rest_of_plan": [], "step_done": False}
        result.update(overrides)
        return result

    def _capture(self, text="Write the quarterly report"):
        self.app.capture_entry.insert(0, text)
        self.app.add_task_from_capture()
        self.app.task_list.selection_set(0)

    def _edit(self, **overrides):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._result(**overrides)
            self.app.edit_selected_details()
            return editor.call_args

    def test_a_plan_typed_into_the_editor_is_kept(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        task = self.app.tasks[0]
        self.assertEqual(task.steps, PLAN)
        self.assertEqual(task.first_step, PLAN[0])

    def test_the_editor_is_reopened_showing_the_rest_of_the_plan(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        call = self._edit(rest_of_plan=PLAN[1:])
        self.assertEqual(call.kwargs["rest_of_plan"], PLAN[1:])

    def test_rewording_the_step_in_the_editor_reaches_the_plan(self):
        """The step box on a task with a plan IS the current line of it. A
        plain assignment to first_step would leave the two disagreeing until
        the next load silently reverted the edit — and every app-level test
        that happens to type the same words the plan already holds would
        pass anyway."""
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self._edit(first_step="open the one from last quarter",
                   rest_of_plan=PLAN[1:])
        task = self.app.tasks[0]
        self.assertEqual(task.first_step, "open the one from last quarter")
        self.assertEqual(task.steps[0], "open the one from last quarter",
                         "the plan still holds the old wording")
        from cognitive_offload.models import Task as T
        self.assertEqual(T.from_dict(task.to_dict()).first_step,
                         "open the one from last quarter")

    def test_ticking_the_box_moves_to_the_next_step(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self._edit(rest_of_plan=PLAN[1:], step_done=True)
        self.assertEqual(self.app.tasks[0].first_step, PLAN[1])
        self.assertEqual(self.app.tasks[0].steps_done, 1)

    def test_the_status_line_says_what_is_next_not_what_is_left(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self._edit(rest_of_plan=PLAN[1:], step_done=True)
        self.assertEqual(self.app.status_var.get(), f"Next: {PLAN[1]}")

    def test_undo_puts_you_back_where_you_were_in_the_plan(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self._edit(rest_of_plan=PLAN[1:], step_done=True)
        self.app.undo()
        self.assertEqual(self.app.tasks[0].steps_done, 0)
        self.assertEqual(self.app.tasks[0].first_step, PLAN[0])

    def test_a_plan_survives_the_trip_to_the_matrix_and_back(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self._edit(rest_of_plan=PLAN[1:], step_done=True)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as q:
            q.return_value.show.return_value = "do_first"
            self.app.send_selected_to_matrix()
        moved = self.app.matrix.list("do_first")[0]
        self.assertEqual(moved.steps, PLAN)
        self.assertEqual(moved.steps_done, 1)
        self.app.matrix_lists["do_first"].selection_set(0)
        self.app.matrix_to_tasks("do_first")
        self.assertEqual(self.app.tasks[0].steps, PLAN)
        self.assertEqual(self.app.tasks[0].steps_done, 1)

    def test_a_quadrant_task_can_be_broken_down_too(self):
        self.app.matrix.create("do_first", "Write the quarterly report")
        self.app.refresh_matrix()
        self.app.matrix_lists["do_first"].selection_set(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._result(rest_of_plan=PLAN[1:])
            del editor.return_value.show.return_value["tags"]
            self.app.edit_matrix_task("do_first")
        [task] = self.app.matrix.list("do_first")
        self.assertEqual(task.steps, PLAN)

    def test_a_new_quadrant_task_keeps_the_plan_it_was_created_with(self):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            result = self._result(rest_of_plan=PLAN[1:])
            del result["tags"]
            editor.return_value.show.return_value = result
            self.app.add_matrix_task("do_first")
        [task] = self.app.matrix.list("do_first")
        self.assertEqual(task.steps, PLAN)
        self.assertEqual(task.first_step, PLAN[0])

    def test_it_reaches_the_disk(self):
        from cognitive_offload.storage import MatrixStore

        self.app.matrix.create("do_first", "Write the quarterly report")
        self.app.refresh_matrix()
        self.app.matrix_lists["do_first"].selection_set(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            result = self._result(rest_of_plan=PLAN[1:], step_done=False)
            del result["tags"]
            editor.return_value.show.return_value = result
            self.app.edit_matrix_task("do_first")
        fresh = MatrixStore(self.app.config_store.matrix_db_path)
        [reloaded] = fresh.list("do_first")
        self.assertEqual(reloaded.steps, PLAN)
        self.assertEqual(reloaded.first_step, PLAN[0])

    def test_the_row_on_screen_shows_the_place_in_the_plan(self):
        self._capture()
        self._edit(rest_of_plan=PLAN[1:])
        self.assertIn("step 1 of 4", self.app.task_list.get(0))


class FieldCoverageTests(unittest.TestCase):
    """The plan added two fields to two models. Both completeness nets have
    their own copies of that decision; this only checks nothing was added to
    one model and forgotten on the other."""

    def test_both_models_carry_both_fields(self):
        for model in (Task, MatrixTask):
            names = {f.name for f in dataclasses.fields(model)}
            with self.subTest(model=model.__name__):
                self.assertIn("steps", names)
                self.assertIn("steps_done", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


@unittest.skipUnless(_display_available(), "tkinter display not available")
class SessionEndTests(unittest.TestCase):
    """The end of a block asks a task with a plan a different question.

    Two things can have happened in the last fifteen minutes — you finished
    this step, or you did not — and one blank field labelled "where does it
    pick up next time?" conflated them. On a task with a plan it invited a
    description of the NEXT step while the cursor was still on this one, so
    typing the honest answer overwrote the wrong line.
    """

    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _dialog(self, **kw):
        from cognitive_offload.dialogs import SessionEndDialog

        kw.setdefault("first_step", PLAN[0])
        dialog = SessionEndDialog(self.root, "15 minutes banked.",
                                  "Write the quarterly report", 5, **kw)
        self.addCleanup(dialog.destroy)
        return dialog

    def _labels(self, dialog):
        from tkinter import ttk

        found = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Label, ttk.Checkbutton)):
                    found.append(child.cget("text"))
                walk(child)

        walk(dialog)
        return found

    def test_a_task_with_no_plan_is_asked_exactly_what_it_always_was(self):
        dialog = self._dialog()
        self.assertEqual(dialog.next_entry.get(), "")
        self.assertIsNone(dialog.step_done_var)
        text = " ".join(self._labels(dialog))
        self.assertIn("Where does it pick up next time?", text)
        self.assertIn(f"was: {PLAN[0]}", text)

    def test_a_task_with_a_plan_is_shown_the_step_it_is_on(self):
        """Prefilled, so accepting it unchanged means what it looks like:
        nothing. A blank box at the tired end of a block is a question; a
        filled one is a confirmation."""
        dialog = self._dialog(rest_of_plan=PLAN[1:], place="step 1 of 4")
        self.assertEqual(dialog.next_entry.get(), PLAN[0])
        text = " ".join(self._labels(dialog))
        self.assertIn("What does this step say now?", text)
        self.assertIn("step 1 of 4", text)
        self.assertNotIn("was:", text)
        # "Leave it blank" is an invitation on an empty box and a lie on a
        # filled one: blanking a prefilled step changes nothing.
        self.assertNotIn("Leave it blank", text)
        self.assertIn("leaving it as it is is an answer", text)

    def test_the_tick_box_appears_and_names_the_step_it_moves_to(self):
        dialog = self._dialog(rest_of_plan=PLAN[1:], place="step 1 of 4")
        self.assertIsNotNone(dialog.step_done_var)
        self.assertTrue(any(PLAN[1] in text for text in self._labels(dialog)))

    def test_the_last_step_offers_no_tick_box(self):
        """There is nowhere to move on to, and a checkbox that does nothing
        is worse than no checkbox."""
        dialog = self._dialog(rest_of_plan=[], place="step 4 of 4")
        self.assertIsNone(dialog.step_done_var)

    def test_every_way_out_reports_whether_the_step_was_finished(self):
        for method in ("_keep_step", "cancel"):
            dialog = self._dialog(rest_of_plan=PLAN[1:], place="step 1 of 4")
            dialog.step_done_var.set(True)
            getattr(dialog, method)()
            with self.subTest(exit=method):
                self.assertTrue(dialog.result["step_done"])


@unittest.skipUnless(_display_available(), "tkinter display not available")
class SessionEndThroughTheAppTests(unittest.TestCase):
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
        self.app.capture_entry.insert(0, "Write the quarterly report")
        self.app.add_task_from_capture()
        self.task = self.app.tasks[0]
        self.task.first_step = PLAN[0]
        self.task.set_rest(PLAN[1:])
        self.app._focus_task_id = self.task.id

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _finish(self, **answer):
        answer.setdefault("choice", "carry_on")
        answer.setdefault("next_step", "")
        answer.setdefault("step_done", False)
        with mock.patch("cognitive_offload.app.SessionEndDialog") as dialog:
            dialog.return_value.show.return_value = answer
            self.app._finish_session(15)
            return dialog.call_args

    def test_the_dialog_is_told_where_in_the_plan_the_task_is(self):
        call = self._finish()
        self.assertEqual(call.kwargs["rest_of_plan"], PLAN[1:])
        self.assertEqual(call.kwargs["place"], "step 1 of 4")
        self.assertEqual(call.kwargs["first_step"], PLAN[0])

    def test_ticking_the_box_moves_the_task_on(self):
        self._finish(step_done=True)
        self.assertEqual(self.task.steps_done, 1)
        self.assertEqual(self.task.first_step, PLAN[1])

    def test_typing_rewords_the_step_you_were_on_not_a_later_one(self):
        """The bug the redesign exists for: the old field described the NEXT
        step while the cursor was still on this one."""
        self._finish(next_step="open the one from last quarter")
        self.assertEqual(self.task.steps[0], "open the one from last quarter")
        self.assertEqual(self.task.steps[1], PLAN[1], "a later step was rewritten")
        self.assertEqual(self.task.steps_done, 0)

    def test_rewording_and_finishing_do_both_in_the_right_order(self):
        self._finish(next_step="open last quarter's instead", step_done=True)
        self.assertEqual(self.task.steps[0], "open last quarter's instead")
        self.assertEqual(self.task.steps_done, 1)
        self.assertEqual(self.task.first_step, PLAN[1])

    def test_answering_nothing_changes_nothing(self):
        before = (list(self.task.steps), self.task.steps_done)
        self._finish()
        self.assertEqual((list(self.task.steps), self.task.steps_done), before)

    def test_marking_the_task_done_does_not_also_walk_the_plan(self):
        self._finish(choice="done", step_done=True)
        self.assertTrue(self.task.done)
        self.assertEqual(self.task.steps_done, 0)

    def test_undo_reaches_it(self):
        self._finish(step_done=True)
        self.app.undo()
        self.assertEqual(self.app.tasks[0].steps_done, 0)


class WhereYouAreDuringASessionTests(unittest.TestCase):
    """During a session the one thing about the plan worth showing is where
    you are in it — not what is coming, which is a decision, on the screen
    someone is looking at because deciding is the hard part."""

    def test_the_focus_caption_says_the_place(self):
        from cognitive_offload.rows import focus_caption, plan_place

        task = planned(first_step=PLAN[0])
        task.advance_step()
        self.assertEqual(focus_caption(task, task.first_step, plan_place(task)),
                         f"Write the quarterly report\n→ {PLAN[1]} · step 2 of 4")

    def test_a_task_with_no_plan_reads_exactly_as_before(self):
        from cognitive_offload.rows import focus_caption, plan_place

        task = Task(text="Bins", first_step="wheel it to the kerb")
        self.assertEqual(plan_place(task), "")
        self.assertEqual(focus_caption(task, task.first_step, plan_place(task)),
                         "Bins\n→ wheel it to the kerb")

    def test_free_focus_and_a_stepless_task_are_untouched(self):
        from cognitive_offload.rows import focus_caption

        self.assertEqual(focus_caption(None, "just start"), "Free focus — just start")
        self.assertEqual(focus_caption(Task(text="Bins"), ""), "Bins")


@unittest.skipUnless(_display_available(), "tkinter display not available")
class StartDialogPlaceTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _labels(self, dialog):
        from tkinter import ttk

        found = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label):
                    found.append(child.cget("text"))
                walk(child)

        walk(dialog)
        return found

    def _dialog(self, **kw):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, task_text="Write the report",
                                  first_step=PLAN[0], **kw)
        self.addCleanup(dialog.destroy)
        return dialog

    def test_the_place_is_shown_when_there_is_one(self):
        self.assertIn("step 2 of 4", self._labels(self._dialog(place="step 2 of 4")))

    def test_nothing_is_added_for_a_task_with_no_plan(self):
        """Counted, not pattern-matched: an empty label packed anyway is
        still a row of dead space, and "does not start with 'step '" is true
        of an empty string."""
        with_place = self._labels(self._dialog(place="step 2 of 4"))
        without = self._labels(self._dialog())
        self.assertEqual(len(without), len(with_place) - 1)
        self.assertNotIn("", without)

    def test_the_plan_itself_is_not_shown_here(self):
        """Deliberately: what comes next is a decision, and this is the
        screen someone is on because deciding is what they are stuck on."""
        labels = " ".join(self._labels(self._dialog(place="step 2 of 4")))
        for step in PLAN[1:]:
            self.assertNotIn(step, labels)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class StartingASessionKeepsThePlanInStepTests(unittest.TestCase):
    """A fourth place that wrote `first_step` directly.

    The editor and the session-end dialog were both fixed to go through
    `set_current_step`; the start dialog was not. On a task with a plan,
    renaming the first move as you start left `first_step` disagreeing with
    the plan — and `_fix_steps` puts that right on the next load, so the
    rename survived exactly until the app was closed.
    """

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
        self.app.capture_entry.insert(0, "Write the quarterly report")
        self.app.add_task_from_capture()
        self.task = self.app.tasks[0]
        self.task.first_step = PLAN[0]
        self.task.set_rest(PLAN[1:])
        self.app.task_list.selection_set(0)

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _start(self, first_step):
        with mock.patch("cognitive_offload.app.StartFocusDialog") as dialog:
            dialog.return_value.show.return_value = {
                "first_step": first_step, "minutes": 15, "warmup_done": 0,
                "warmup_steps": None, "show_warmup": True, "popout": False}
            self.app.begin_focus(self.app.tasks[0])
            return dialog.call_args

    def test_renaming_the_first_move_reaches_the_plan(self):
        self._start("open the one from last quarter")
        task = self.app.tasks[0]
        self.assertEqual(task.first_step, "open the one from last quarter")
        self.assertEqual(task.steps[0], "open the one from last quarter",
                         "the plan still holds the old wording")

    def test_the_rename_survives_being_written_out(self):
        """The half that made it a data loss rather than a cosmetic slip."""
        self._start("open the one from last quarter")
        from cognitive_offload.models import Task as T

        back = T.from_dict(self.app.tasks[0].to_dict())
        self.assertEqual(back.first_step, "open the one from last quarter")

    def test_the_dialog_is_told_where_in_the_plan_the_task_is(self):
        call = self._start(PLAN[0])
        self.assertEqual(call.kwargs["place"], "step 1 of 4")

    def test_the_focus_card_says_the_place(self):
        self._start(PLAN[0])
        self.assertIn("step 1 of 4", self.app.focus_task_var.get())

    def test_a_task_with_no_plan_is_told_no_place(self):
        self.app.tasks[0].set_rest([])
        self.app.tasks[0].first_step = "wheel it to the kerb"
        call = self._start("wheel it to the kerb")
        self.assertEqual(call.kwargs["place"], "")
        self.assertNotIn("step ", self.app.focus_task_var.get())
