"""End-to-end smoke tests that drive the real Tk widgets.

Skipped automatically when tkinter or a display is unavailable, so the suite
still runs on a headless box without X.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
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


@unittest.skipUnless(_display_available(), "tkinter display not available")
class AppSmokeTests(unittest.TestCase):
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
        self.addCleanup(self.app.destroy)

    # -- helpers -------------------------------------------------------
    def capture(self, text):
        self.app.capture_entry.insert(0, text)
        self.app.add_task_from_capture()

    def select(self, *indices):
        self.app.task_list.selection_clear(0, tk.END)
        for index in indices:
            self.app.task_list.selection_set(index)

    def visible_texts(self):
        return [self.app.task_list.get(i) for i in range(self.app.task_list.size())]

    # -- tests ---------------------------------------------------------
    def test_starts_empty(self):
        self.assertEqual(self.app.tasks, [])
        self.assertEqual(self.app.task_list.size(), 0)

    def test_capture_adds_a_task_and_clears_the_entry(self):
        self.capture("write the report")
        self.assertEqual([t.text for t in self.app.tasks], ["write the report"])
        self.assertEqual(self.app.capture_entry.get(), "")
        self.assertIn("write the report", self.visible_texts()[0])

    def test_capture_to_scratchpad_keeps_the_text(self):
        self.app.capture_entry.insert(0, "half an idea")
        self.app.add_note_from_capture()
        self.assertIn("half an idea", self.app.scratchpad_text())
        self.assertEqual(self.app.tasks, [])

    def test_typed_scratchpad_text_survives_a_save_and_reload(self):
        # The old version dropped anything typed directly into the scratchpad.
        self.app.note_text.insert("1.0", "a thought I typed")
        self.app.save_state(silent=True)
        self.app.set_scratchpad("")
        self.app.load_state()
        self.assertIn("a thought I typed", self.app.scratchpad_text())

    def test_toggle_done_and_priority_on_a_multi_selection(self):
        self.capture("one")
        self.capture("two")
        self.select(0, 1)
        self.app.toggle_selected_done()
        self.assertTrue(all(t.done for t in self.app.tasks))
        self.select(0, 1)
        self.app.toggle_selected_done()
        self.assertFalse(any(t.done for t in self.app.tasks))
        self.select(0)
        self.app.toggle_selected_priority()
        self.assertEqual(sum(t.priority for t in self.app.tasks), 1)

    def test_actions_target_the_right_task_when_titles_are_identical(self):
        self.capture("duplicate")
        self.capture("duplicate")
        self.app.tasks[0].description = "second one"
        self.app.tasks[1].description = "first one"
        self.app.refresh_tasks()
        self.select(1)
        self.app.delete_selected()
        self.assertEqual(len(self.app.tasks), 1)
        self.assertEqual(self.app.tasks[0].description, "second one")

    def test_actions_follow_the_task_through_sorting(self):
        self.capture("plain")
        self.capture("flagged")
        self.select(0)
        self.app.toggle_selected_priority()  # "flagged" jumps to the top
        self.app.sort_var.set("Alphabetical")
        self.app.refresh_tasks()
        rows = self.visible_texts()
        self.assertIn("flagged", rows[0])
        self.select(1)  # "plain" under alphabetical ordering
        self.app.delete_selected()
        self.assertEqual([t.text for t in self.app.tasks], ["flagged"])

    def test_delete_is_undoable(self):
        self.capture("precious")
        self.select(0)
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.delete_selected()
        self.assertEqual(self.app.tasks, [])
        self.app.undo()
        self.assertEqual([t.text for t in self.app.tasks], ["precious"])

    def test_search_and_tag_filters_drive_the_listbox(self):
        self.capture("email bob")
        self.capture("buy milk")
        self.app.search_var.set("milk")
        self.app.refresh_tasks()
        self.assertEqual(len(self.visible_texts()), 1)
        self.app.clear_search()
        self.assertEqual(len(self.visible_texts()), 2)

        self.select(0)
        with mock.patch("cognitive_offload.app.simpledialog.askstring", return_value="errand"):
            self.app.tag_selected()
        self.app.tag_filter_var.set("errand")
        self.app.refresh_tasks()
        self.assertEqual(len(self.visible_texts()), 1)
        self.app.clear_tag_filter()
        self.assertEqual(len(self.visible_texts()), 2)

    def test_hide_done_toggle(self):
        self.capture("finished")
        self.select(0)
        self.app.toggle_selected_done()
        self.app.show_done_var.set(False)
        self.app.refresh_tasks()
        self.assertEqual(self.visible_texts(), [])

    def test_brain_dump_creates_one_task_per_line(self):
        self.app.note_text.insert("1.0", "- first\n- second\n\n- third\n")
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.brain_dump_into_tasks()
        self.assertEqual([t.text for t in self.app.tasks], ["third", "second", "first"])

    def test_clear_completed_removes_only_finished_tasks(self):
        self.capture("keep")
        self.capture("drop")
        self.select(0)
        self.app.toggle_selected_done()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_completed()
        self.assertEqual([t.text for t in self.app.tasks], ["keep"])

    def test_send_to_matrix_then_back_again(self):
        self.capture("triage me")
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()

        self.assertEqual(self.app.tasks, [])
        self.assertEqual(len(self.app.matrix.list("schedule")), 1)
        self.assertEqual(self.app.matrix_lists["schedule"].size(), 1)

        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.matrix_to_tasks("schedule")
        self.assertEqual([t.text for t in self.app.tasks], ["triage me"])
        self.assertEqual(self.app.matrix.list("schedule"), [])

    def test_matrix_move_between_quadrants(self):
        self.app.matrix.create("eliminate", "second thoughts", "")
        self.app.refresh_matrix()
        self.app.matrix_lists["eliminate"].selection_set(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "do_first"
            self.app.move_matrix_tasks("eliminate")
        self.assertEqual(self.app.matrix_lists["eliminate"].size(), 0)
        self.assertEqual(self.app.matrix_lists["do_first"].size(), 1)

    def test_matrix_copy_leaves_the_files_in_place(self):
        self.app.matrix.create("delegate", "hand off", "with notes")
        self.app.refresh_matrix()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.copy_matrix_to_tasks("delegate")
        self.assertEqual([t.text for t in self.app.tasks], ["hand off"])
        self.assertEqual(len(self.app.matrix.list("delegate")), 1)

    def test_state_survives_a_full_save_load_cycle(self):
        self.capture("persisted")
        self.select(0)
        self.app.toggle_selected_priority()
        self.app.note_text.insert("1.0", "scratch text")
        self.app.save_state(silent=True)

        self.app.tasks = []
        self.app.set_scratchpad("")
        self.app.refresh_tasks()
        self.app.load_state()

        self.assertEqual([t.text for t in self.app.tasks], ["persisted"])
        self.assertEqual(self.app.tasks[0].priority, 1)
        self.assertIn("scratch text", self.app.scratchpad_text())

    def test_timer_countdown_and_reset(self):
        self.app.work_minutes.set(2)
        self.app.on_timer_minutes_changed()
        self.assertEqual(self.app.timer_label.cget("text"), "02:00")
        self.app.start_timer()
        self.assertTrue(self.app._timer_running)
        self.app.pause_timer()
        self.assertFalse(self.app._timer_running)
        self.assertEqual(self.app.timer_button.cget("text"), "Resume")
        self.app.reset_timer()
        self.assertEqual(self.app.timer_label.cget("text"), "02:00")

    def test_editing_a_task_updates_text_tags_and_description(self):
        self.capture("rough note")
        self.select(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as dialog:
            dialog.return_value.show.return_value = ("polished", "the details", ["work"])
            self.app.edit_selected_details()
        task = self.app.tasks[0]
        self.assertEqual((task.text, task.description, task.tags), ("polished", "the details", ["work"]))

    def test_dirty_flag_tracks_edits_and_saves(self):
        self.assertFalse(self.app._dirty)
        self.capture("something")
        self.assertTrue(self.app._dirty)
        self.app.save_state(silent=True)
        self.assertFalse(self.app._dirty)
        self.app.note_text.insert("1.0", "typing")
        self.app.update()  # let the <<Modified>> event reach the handler
        self.assertTrue(self.app._dirty)


if __name__ == "__main__":
    unittest.main()
