"""Being able to *say* you are waiting on someone, not only on an agent.

Everything about the waiting state was already agnostic about who is holding
the task: `handed_to` is free text, `rows.waiting_line` says "Waiting on
{whoever}", and `rank_for_starting` steps the task out of the suggestion slot
until the check-back day. All of it was reachable one way only — hand a task
to an AI agent, from the Delegate quadrant of the other tab. So the state was
**read-only everywhere else**: a task could arrive on the main list already
marked, and could be taken back there, but could never be marked there.

Which left the most common case of all with no way in. Most of what anyone is
waiting on is a person: a reply, a form, a callback. Those are the tasks that
rot quietly, and this app already had exactly the right treatment built for
them — a fact ("check back Sat"), never a verdict ("overdue"); still in the
list, still in every search, just not offered as the next thing to start.

The tone is load-bearing here, so it is asserted rather than trusted: nothing
this feature says may blame anyone for waiting.
"""

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None


def _display_available() -> bool:
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


def _widgets(widget, kind):
    """Every widget of ``kind`` anywhere inside, at any depth."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(_widgets(child, kind))
    return found


def _in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# The helper above must stay above the decorator: a skipUnless that lands on a
# module-level function instead of the class turns the skip into an error on a
# headless box, which has happened here before.
@unittest.skipUnless(_display_available(), "tkinter display not available")
class EditorControlTests(unittest.TestCase):
    """One state, two directions, never both on screen."""

    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _editor(self, **kw):
        from cognitive_offload.dialogs import TaskEditorDialog

        kw.setdefault("title", "Send the passport form")
        dialog = TaskEditorDialog(self.root, **kw)
        self.addCleanup(dialog.destroy)
        return dialog

    def test_a_task_nobody_has_offers_the_way_in(self):
        dialog = self._editor()
        self.assertIsNotNone(dialog.waiting_entry)
        self.assertIsNotNone(dialog.check_back_entry)
        self.assertIsNone(dialog.unwait_var, "the way out is not for this task")

    def test_a_task_someone_has_offers_the_way_out(self):
        dialog = self._editor(handed_to="Mum", follow_up_on=_in_days(2))
        self.assertIsNotNone(dialog.unwait_var)
        self.assertIsNone(dialog.waiting_entry,
                          "two controls for one state is how they disagree")
        self.assertIsNone(dialog.check_back_entry)

    def test_the_field_says_who_it_is_for_without_naming_a_product(self):
        """It used to be an agent feature. The words have to stop saying so,
        or the person waiting on their landlord will not recognise it."""
        dialog = self._editor()
        text = " ".join(w.cget("text") for w in _widgets(dialog, ttk.Label))
        self.assertIn("Waiting on", text)
        self.assertIn("check back", text)
        self.assertIn("A person or an agent", text)

    def test_nothing_it_says_blames_anyone_for_waiting(self):
        dialog = self._editor()
        text = " ".join(w.cget("text") for w in _widgets(dialog, ttk.Label)).lower()
        for word in ("overdue", "late", "failed", "should have", "still not",
                     "chase", "nag", "behind"):
            self.assertNotIn(word, text, f"the waiting field says {word!r}")


@unittest.skipUnless(_display_available(), "tkinter display not available")
class EditorCollectTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _collect(self, who: str, when: str = ""):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="Send the passport form")
        self.addCleanup(dialog.destroy)
        dialog.waiting_entry.insert(0, who)
        dialog.check_back_entry.insert(0, when)
        return dialog.collect()

    def test_a_blank_date_books_the_check_back_three_days_out(self):
        """Handing something over and forgetting it is not delegating, it is
        losing it somewhere more respectable. Every wait gets a date, and the
        default is the one the agent handoff already used."""
        from cognitive_offload.handoff import DEFAULT_FOLLOW_UP_DAYS

        result = self._collect("Mum")
        self.assertEqual(result["waiting_on"], "Mum")
        self.assertEqual(result["check_back"], _in_days(DEFAULT_FOLLOW_UP_DAYS))

    def test_a_date_that_was_typed_is_the_one_that_is_used(self):
        result = self._collect("the letting agent", "tomorrow")
        self.assertEqual(result["check_back"], _in_days(1))

    def test_a_date_it_cannot_read_stops_the_save_rather_than_guessing(self):
        """A silently discarded date reads exactly like a blank field, and
        the whole point of this feature is the date."""
        with mock.patch("cognitive_offload.dialogs.messagebox.showwarning") as warn:
            self.assertIsNone(self._collect("Mum", "the 32nd"))
        self.assertTrue(warn.called)

    def test_a_junk_date_with_nobody_named_is_simply_not_in_play(self):
        with mock.patch("cognitive_offload.dialogs.messagebox.showwarning") as warn:
            result = self._collect("", "the 32nd")
        self.assertFalse(warn.called)
        self.assertEqual(result["waiting_on"], "")
        self.assertEqual(result["check_back"], "")

    def test_the_name_is_taken_as_typed_apart_from_stray_spaces(self):
        self.assertEqual(self._collect("  Dr Ahmed  ")["waiting_on"], "Dr Ahmed")


@unittest.skipUnless(_display_available(), "tkinter display not available")
class MarkedFromTheListTests(unittest.TestCase):
    """The main list, where the state could only ever be read before."""

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
        result = {"title": "Send the passport form", "content": "", "tags": [],
                  "first_step": "", "kind": "", "scheduled_for": "",
                  "estimate_minutes": 0, "repeat": "", "clear_snooze": False,
                  "take_back": False, "waiting_on": "", "check_back": ""}
        result.update(overrides)
        return result

    def _capture(self, text="Send the passport form"):
        self.app.capture_entry.insert(0, text)
        self.app.add_task_from_capture()
        self.app.task_list.selection_set(0)

    def _edit(self, **overrides):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._result(**overrides)
            self.app.edit_selected_details()

    def test_saying_who_has_it_marks_the_task_waiting(self):
        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        task = self.app.tasks[0]
        self.assertTrue(task.is_waiting())
        self.assertEqual(task.handed_to, "Mum")
        self.assertEqual(task.handed_off_on, date.today().isoformat())
        self.assertEqual(task.follow_up_on, _in_days(4))

    def test_the_row_then_says_so_on_the_list_itself(self):
        from cognitive_offload.rows import task_row

        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        row = task_row(self.app.tasks[0])
        self.assertIn("Waiting on Mum", row.subtitle)
        self.assertIn("waiting", [b.text for b in row.badges])

    def test_it_stops_being_offered_as_the_next_thing_to_start(self):
        """The behaviour the whole feature is for: still in the list, still in
        every search, just not the thing you are invited to pick up."""
        from cognitive_offload.queries import rank_for_starting

        self._capture()
        self._capture("Book the dentist")
        self.app.task_list.selection_clear()
        self.app.task_list.selection_set(0)
        waiting_id = self.app.tasks[0].id
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        ranked = [t.id for t in rank_for_starting(self.app.tasks)]
        self.assertNotIn(waiting_id, ranked)
        self.assertIn(waiting_id, [t.id for t in self.app.tasks],
                      "hiding it is the one thing this app will not do")

    def test_it_comes_back_into_the_running_on_the_check_back_day(self):
        """The mark is a pause, not a burial. From the day you said you would
        look again, picking it up yourself is a real option, so the app
        offers it — wearing `check back` rather than anything sharper."""
        from cognitive_offload.queries import rank_for_starting
        from cognitive_offload.rows import task_row

        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(-1))
        task = self.app.tasks[0]
        self.assertIn(task, rank_for_starting(self.app.tasks))
        self.assertIn("check back", [b.text for b in task_row(task).badges])

    def test_undo_puts_it_back_the_way_it_was(self):
        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        self.assertTrue(self.app.tasks[0].is_waiting())
        self.app.undo()
        self.assertFalse(self.app.tasks[0].is_waiting())

    def test_the_status_line_says_what_happened_without_ceremony(self):
        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        self.assertIn("Waiting on Mum", self.app.status_var.get())

    def test_taking_it_back_still_works_from_the_same_dialog(self):
        self._capture()
        self._edit(waiting_on="Mum", check_back=_in_days(4))
        self._edit(take_back=True)
        self.assertFalse(self.app.tasks[0].is_waiting())


@unittest.skipUnless(_display_available(), "tkinter display not available")
class MatrixEditorTests(unittest.TestCase):
    """The quadrant editor was showing a task that was not the task.

    It never passed `repeat`, `snoozed_until` or `handed_to`, so it said "Does
    not repeat" about a task wearing a `weekly` badge, and offered no way out
    of a wait anywhere but Delegate, where the button lives.
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

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _result(self, **overrides):
        result = {"title": "Chase the claim", "content": "", "first_step": "",
                  "kind": "", "scheduled_for": "", "estimate_minutes": 0,
                  "repeat": "", "clear_snooze": False, "take_back": False,
                  "waiting_on": "", "check_back": ""}
        result.update(overrides)
        return result

    def _select(self, category, index=0):
        self.app.refresh_matrix()
        self.app.matrix_lists[category].selection_set(index)

    def _edit(self, category, **overrides):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._result(**overrides)
            self.app.edit_matrix_task(category)
            return editor.call_args

    def test_the_editor_is_opened_with_the_task_as_it_actually_is(self):
        task = self.app.matrix.create("schedule", "Chase the claim")
        self.app.matrix.set_handoff(task, "Mum", date.today().isoformat(),
                                    _in_days(3))
        task.repeat = "weekly"
        self.app.matrix.update(task, task.title, task.content)
        self._select("schedule")
        call = self._edit("schedule", title="Chase the claim")
        self.assertEqual(call.kwargs["repeat"], "weekly",
                         "the dialog said 'Does not repeat' about a task "
                         "wearing a weekly badge")
        self.assertEqual(call.kwargs["handed_to"], "Mum")
        self.assertEqual(call.kwargs["follow_up_on"], _in_days(3))

    def test_a_wait_can_be_cleared_from_a_quadrant_that_has_no_button_for_it(self):
        """"Take it back" is a Delegate button. Move a waiting task anywhere
        else and, before this, the mark had no exit at all."""
        task = self.app.matrix.create("schedule", "Chase the claim")
        self.app.matrix.set_handoff(task, "Mum", date.today().isoformat(),
                                    _in_days(3))
        self._select("schedule")
        self._edit("schedule", title="Chase the claim", take_back=True)
        self.assertFalse(self.app.matrix.list("schedule")[0].is_waiting())

    def test_turning_a_repeat_off_in_a_quadrant_actually_turns_it_off(self):
        """The combobox was not merely showing the wrong value; the result was
        not applied either, so correcting it changed nothing."""
        task = self.app.matrix.create("do_first", "Take the bins out")
        task.repeat = "weekly"
        self.app.matrix.update(task, task.title, task.content)
        self._select("do_first")
        self._edit("do_first", title="Take the bins out", repeat="")
        self.assertEqual(self.app.matrix.list("do_first")[0].repeat, "")

    def test_a_wait_can_be_started_from_a_quadrant_too(self):
        self.app.matrix.create("schedule", "Chase the claim")
        self._select("schedule")
        self._edit("schedule", title="Chase the claim", waiting_on="Mum",
                   check_back=_in_days(4))
        [task] = self.app.matrix.list("schedule")
        self.assertTrue(task.is_waiting())
        self.assertEqual(task.handed_to, "Mum")
        self.assertEqual(task.follow_up_on, _in_days(4))

    def test_replacing_a_wait_with_an_agent_says_who_it_replaced(self):
        """Newest-holder-wins is right; doing it silently is not. Before the
        editor could mark a wait this needed one agent's task handed to
        another; now the person you were waiting on can be replaced by a
        click that never mentions them."""
        from unittest import mock as _mock

        task = self.app.matrix.create("delegate", "Chase the claim")
        self.app.matrix.set_handoff(task, "Mum", date.today().isoformat(),
                                    _in_days(3))
        self._select("delegate")
        with _mock.patch("cognitive_offload.app.HandoffDialog") as ask, \
             _mock.patch("cognitive_offload.app.HandoffDoneDialog"):
            ask.return_value.show.return_value = {
                "target": "codex", "note": "", "follow_up_days": 3}
            self.app.hand_off_matrix_task("delegate")
        self.assertIn("Was out with Mum", self.app.status_var.get())
        self.assertIn("Codex", self.app.status_var.get())

    def test_a_first_handoff_says_nothing_about_anyone_else(self):
        from unittest import mock as _mock

        self.app.matrix.create("delegate", "Chase the claim")
        self._select("delegate")
        with _mock.patch("cognitive_offload.app.HandoffDialog") as ask, \
             _mock.patch("cognitive_offload.app.HandoffDoneDialog"):
            ask.return_value.show.return_value = {
                "target": "codex", "note": "", "follow_up_days": 3}
            self.app.hand_off_matrix_task("delegate")
        self.assertNotIn("Was out with", self.app.status_var.get())
        self.assertIn("Handed to Codex", self.app.status_var.get())

    def test_it_survives_being_written_out_and_read_back(self):
        """The in-memory object is not the thing that comes back; the file is."""
        self.app.matrix.create("schedule", "Chase the claim")
        self._select("schedule")
        self._edit("schedule", title="Chase the claim", waiting_on="Mum",
                   check_back=_in_days(4), repeat="weekly")
        from cognitive_offload.storage import MatrixStore

        fresh = MatrixStore(self.app.config_store.matrix_db_path)
        [reloaded] = fresh.list("schedule")
        self.assertEqual(reloaded.handed_to, "Mum")
        self.assertEqual(reloaded.follow_up_on, _in_days(4))
        self.assertEqual(reloaded.repeat, "weekly")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
