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

    def answer_session_end(self, choice):
        """Answer the end-of-session dialog without opening a real window."""
        patcher = mock.patch("cognitive_offload.app.SessionEndDialog")
        dialog = patcher.start()
        dialog.return_value.show.return_value = choice
        self.addCleanup(patcher.stop)
        return mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False)

    def run_session(self, minutes=15, first_step="", choice="carry_on"):
        """Start a focus session on the selection and run it to expiry."""
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": minutes, "first_step": first_step, "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 10_000
        with self.answer_session_end(choice):
            self.app._tick_timer()

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

    def test_editing_a_task_updates_every_field(self):
        self.capture("rough note")
        self.select(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as dialog:
            dialog.return_value.show.return_value = {
                "title": "polished",
                "content": "the details",
                "tags": ["work"],
                "first_step": "open the doc",
                "kind": "creative",
                "scheduled_for": "2026-08-01",
            }
            self.app.edit_selected_details()
        task = self.app.tasks[0]
        self.assertEqual(task.text, "polished")
        self.assertEqual(task.description, "the details")
        self.assertEqual(task.tags, ["work"])
        self.assertEqual(task.first_step, "open the doc")
        self.assertEqual(task.kind, "creative")
        self.assertEqual(task.scheduled_for, "2026-08-01")
        self.assertTrue(task.is_ready)

    # -- starting / focus sessions -------------------------------------
    def test_start_here_picks_a_task_and_opens_the_session(self):
        self.capture("the thing")
        chosen = self.app.tasks[0]
        with mock.patch("cognitive_offload.app.StartHereDialog") as picker, \
             mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            picker.return_value.show.return_value = chosen
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "open the file", "warmup_done": 2,
            }
            self.app.start_here()

        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._focus_task_id, chosen.id)
        # The first step named at the door is kept on the task.
        self.assertEqual(self.app.tasks[0].first_step, "open the file")
        self.assertIn("the thing", self.app.focus_task_var.get())
        self.app.pause_timer()

    def test_start_here_with_nothing_open_says_so_kindly(self):
        with mock.patch("cognitive_offload.app.StartHereDialog") as picker:
            self.app.start_here()
            picker.assert_not_called()
        self.assertIn("fine place", self.app.status_var.get())

    def test_cancelling_the_focus_dialog_starts_nothing(self):
        self.capture("nope")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = None
            self.app.focus_on_selected()
        self.assertFalse(self.app._timer_running)

    def test_finishing_a_session_logs_it_and_shows_momentum(self):
        self.capture("deep work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "open it", "warmup_done": 0,
            }
            self.app.focus_on_selected()

        # Jump the clock to the end instead of waiting fifteen minutes.
        self.app._timer_deadline = self.app._timer_deadline - 10_000
        with self.answer_session_end("carry_on"):
            self.app._tick_timer()

        self.assertFalse(self.app._timer_running)
        self.assertEqual(self.app.session_log.count_today(), 1)
        self.assertEqual(self.app.session_log.sessions[0].task, "deep work")
        self.assertEqual(self.app.session_log.minutes_today(), 15)
        self.assertIn("1 session today", self.app.momentum_var.get())

    def test_a_break_is_offered_and_does_not_log_a_second_session(self):
        self.capture("something")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 1, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 10_000
        with self.answer_session_end("break"):
            self.app._tick_timer()  # finishes focus, starts the break

        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._timer_mode, "break")
        self.app._timer_deadline -= 10_000
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False):
            self.app._tick_timer()  # break ends, no new session offered
        self.assertEqual(len(self.app.session_log.sessions), 1)

    def test_sessions_persist_across_restarts(self):
        self.app.session_log.record(minutes=15, task="earlier work")
        from cognitive_offload.sessions import SessionLog

        reloaded = SessionLog(self.app.config_store.sessions_file).load()
        self.assertEqual(len(reloaded.sessions), 1)
        self.assertEqual(reloaded.sessions[0].task, "earlier work")

    def test_focus_on_multiple_selection_is_refused(self):
        self.capture("one")
        self.capture("two")
        self.select(0, 1)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            self.app.focus_on_selected()
            starter.assert_not_called()
        self.assertIn("one at a time", self.app.status_var.get())

    def test_timer_progress_bar_tracks_elapsed_time(self):
        self.app.start_timer(minutes=10)
        self.assertEqual(self.app.timer_progress["value"], 0)
        self.app._timer_deadline -= 300  # five minutes in
        self.app._tick_timer()
        self.assertAlmostEqual(self.app.timer_progress["value"], 500, delta=20)
        self.app.pause_timer()

    # -- feel, first step, booked time ---------------------------------
    def test_kind_filter_narrows_the_list(self):
        self.capture("paperwork")
        self.capture("write something")
        self.app.tasks[0].kind = "creative"
        self.app.tasks[1].kind = "admin"
        self.app.kind_filter_var.set("Admin sprint")
        self.app.refresh_tasks()
        self.assertEqual(len(self.visible_texts()), 1)
        self.assertIn("paperwork", self.visible_texts()[0])
        self.app.clear_kind_filter()
        self.assertEqual(len(self.visible_texts()), 2)

    def test_list_marks_a_task_that_has_a_first_step(self):
        self.capture("vague thing")
        # No nagging marker on tasks without one - only a positive mark.
        self.assertNotIn("ready", self.visible_texts()[0])
        self.app.tasks[0].first_step = "open the folder"
        self.app.refresh_tasks()
        self.assertIn("ready", self.visible_texts()[0])

    def test_booked_tasks_surface_in_the_banner(self):
        from cognitive_offload.models import today_iso

        self.assertEqual(self.app.due_var.get(), "")
        self.capture("booked thing")
        self.app.tasks[0].scheduled_for = today_iso()
        self.app.refresh_tasks()
        self.assertIn("1 booked", self.app.due_var.get())

    def test_booking_a_matrix_task_persists_and_counts(self):
        from cognitive_offload.models import today_iso

        self.app.matrix.create("schedule", "annual review prep", "")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        with mock.patch("cognitive_offload.app.simpledialog.askstring", return_value="today"):
            self.app.book_matrix_time("schedule")

        booked = self.app.matrix.list("schedule")[0]
        self.assertEqual(booked.scheduled_for, today_iso())
        self.assertTrue(booked.is_due())
        self.assertIn("booked for today", self.app.due_var.get())

    def test_matrix_rows_show_the_booking_and_ready_mark(self):
        task = self.app.matrix.create("schedule", "quarterly review", "notes")
        task.first_step = "open the calendar"
        self.app.matrix.set_scheduled(task, "2999-01-01")
        self.app.refresh_matrix()
        row = self.app.matrix_lists["schedule"].get(0)
        self.assertIn("quarterly review", row)
        self.assertIn("ready", row)
        self.assertIn("booked 2999-01-01", row)
        self.assertNotIn("(today)", row)

    def test_booking_rejects_nonsense_dates(self):
        self.app.matrix.create("schedule", "something", "")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        with mock.patch("cognitive_offload.app.simpledialog.askstring", return_value="squelch"), \
             mock.patch("cognitive_offload.app.messagebox.showwarning") as warn:
            self.app.book_matrix_time("schedule")
            warn.assert_called_once()
        self.assertEqual(self.app.matrix.list("schedule")[0].scheduled_for, "")

    def test_matrix_round_trip_keeps_first_step_and_booking(self):
        self.capture("carry me")
        task = self.app.tasks[0]
        task.first_step = "open the drawer"
        task.kind = "admin"
        task.scheduled_for = "2026-08-02"
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()

        stored = self.app.matrix.list("schedule")[0]
        self.assertEqual(stored.first_step, "open the drawer")
        self.assertEqual(stored.scheduled_for, "2026-08-02")

        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.matrix_to_tasks("schedule")
        back = self.app.tasks[0]
        self.assertEqual(back.first_step, "open the drawer")
        self.assertEqual(back.kind, "admin")
        self.assertEqual(back.scheduled_for, "2026-08-02")

    def test_new_fields_survive_save_and_reload(self):
        self.capture("full task")
        self.app.tasks[0].first_step = "click the thing"
        self.app.tasks[0].kind = "deadline"
        self.app.tasks[0].scheduled_for = "2026-09-09"
        self.app.save_state(silent=True)
        self.app.tasks = []
        self.app.load_state()
        task = self.app.tasks[0]
        self.assertEqual(task.first_step, "click the thing")
        self.assertEqual(task.kind, "deadline")
        self.assertEqual(task.scheduled_for, "2026-09-09")

    # -- appearance ----------------------------------------------------
    def test_theme_toggles_and_is_remembered(self):
        from cognitive_offload import theme
        from cognitive_offload.storage import Config

        self.assertEqual(self.app.theme_name, "light")
        self.app.toggle_theme()
        self.assertEqual(self.app.theme_name, "dark")
        self.assertEqual(theme.tokens().name, "dark")
        self.assertEqual(self.app.theme_button.cget("text"), "Light")

        self.app._save_config()
        reloaded = Config(self.app.config_store.path).load()
        self.assertEqual(reloaded.theme, "dark")

        self.app.toggle_theme()
        self.assertEqual(theme.tokens().name, "light")

    def test_switching_theme_keeps_the_tasks_rendered(self):
        self.capture("still here")
        self.app.toggle_theme()
        self.assertEqual(self.app.task_list.size(), 1)
        self.assertIn("still here", self.app.task_list.get(0))

    def test_calm_mode_hides_the_extras_without_losing_them(self):
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        for widget in (self.app.filter_row, self.app.task_toolbar, self.app.search_row):
            self.assertEqual(widget.winfo_manager(), "")  # un-gridded

        self.app.calm_var.set(False)
        self.app.apply_calm_mode()
        for widget in (self.app.filter_row, self.app.task_toolbar, self.app.search_row):
            self.assertEqual(widget.winfo_manager(), "grid")

    def test_calm_mode_is_persisted(self):
        from cognitive_offload.storage import Config

        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.app._save_config()
        self.assertTrue(Config(self.app.config_store.path).load().calm_mode)

    # -- row list behaviour --------------------------------------------
    def test_ctrl_click_extends_and_unpicks_a_selection(self):
        for text in ("one", "two", "three"):
            self.capture(text)
        self.app.task_list._click(0)
        self.app.task_list._click(2, toggle=True)
        self.assertEqual(self.app.task_list.curselection(), (0, 2))
        self.app.task_list._click(2, toggle=True)
        self.assertEqual(self.app.task_list.curselection(), (0,))

    def test_shift_click_selects_the_range(self):
        for text in ("one", "two", "three"):
            self.capture(text)
        self.app.task_list._click(0)
        self.app.task_list._click(2, extend=True)
        self.assertEqual(self.app.task_list.curselection(), (0, 1, 2))

    def test_arrow_keys_move_the_selection(self):
        for text in ("one", "two"):
            self.capture(text)
        self.app.task_list._click(0)
        self.app.task_list._move(1)
        self.assertEqual(self.app.task_list.curselection(), (1,))
        self.app.task_list._move(-1)
        self.assertEqual(self.app.task_list.curselection(), (0,))
        self.app.task_list._move(-1)  # already at the top: stays put
        self.assertEqual(self.app.task_list.curselection(), (0,))

    def test_row_list_reports_an_empty_state_rather_than_a_blank_box(self):
        self.assertEqual(self.app.task_list.size(), 0)
        self.assertIn("Capture a thought", self.app.task_list._empty_text)

    # -- focus window --------------------------------------------------
    def test_focus_window_opens_updates_and_closes(self):
        self.capture("deep work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "open it", "warmup_done": 1,
            }
            self.app.focus_on_selected()
        self.app.open_focus_window()
        window = self.app._focus_window
        self.assertIsNotNone(window)
        self.assertEqual(window.task_var.get(), "deep work")
        self.assertIn("open it", window.step_var.get())

        self.app._timer_deadline -= 60
        self.app._tick_timer()
        self.assertNotEqual(window.time_var.get(), "00:00")

        window.close()
        self.assertIsNone(self.app._focus_window)
        self.app.pause_timer()

    def test_finishing_early_banks_the_minutes_actually_done(self):
        self.capture("something")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 20, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 300  # five minutes in
        self.app._tick_timer()
        with self.answer_session_end("carry_on"):
            self.app.finish_session_early()
        self.assertEqual(self.app.session_log.count_today(), 1)
        self.assertEqual(self.app.session_log.sessions[0].minutes, 5)
        self.assertFalse(self.app._timer_running)

    # -- regressions found by the audit --------------------------------
    def test_done_early_after_a_finished_session_banks_nothing_extra(self):
        """The one place that could invent minutes the user had not earned."""
        self.capture("deep work")
        self.select(0)
        self.run_session(minutes=15)
        self.assertEqual(self.app.session_log.count_today(), 1)
        self.assertEqual(self.app.session_log.minutes_today(), 15)

        self.app.open_focus_window()
        with self.answer_session_end("carry_on"):
            self.app._focus_window._done()
        self.assertEqual(self.app.session_log.count_today(), 1)
        self.assertEqual(self.app.session_log.minutes_today(), 15)

    def test_done_early_after_a_break_logs_nothing(self):
        self.capture("something")
        self.select(0)
        self.run_session(minutes=15, choice="break")
        self.assertEqual(self.app._timer_mode, "break")
        self.app._timer_deadline -= 10_000
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False):
            self.app._tick_timer()  # break expires
        before = self.app.session_log.count_today()
        self.app.finish_session_early()
        self.assertEqual(self.app.session_log.count_today(), before)

    def test_pausing_updates_the_pop_out_button(self):
        self.app.start_timer(minutes=10)
        self.app.open_focus_window()
        self.assertEqual(self.app._focus_window.pause_button.cget("text"), "Pause")
        self.app.pause_timer()
        self.assertEqual(self.app._focus_window.pause_button.cget("text"), "Resume")

    def test_switching_theme_keeps_the_pop_out_alive(self):
        self.app.start_timer(minutes=10)
        self.app.open_focus_window()
        window = self.app._focus_window
        self.app.toggle_theme()
        self.assertIs(self.app._focus_window, window)
        self.assertTrue(window.winfo_exists())
        self.assertTrue(self.app._timer_running)
        self.app.pause_timer()

    def test_reset_clears_the_focus_task(self):
        self.capture("a task")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        self.assertIsNotNone(self.app._focus_task_id)
        self.app.reset_timer()
        self.assertIsNone(self.app._focus_task_id)
        self.assertEqual(self.app.focus_task_var.get(), "Nothing picked yet")

    def test_starting_a_second_session_asks_before_dropping_the_first(self):
        self.capture("first")
        self.capture("second")
        self.select(1)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        running_id = self.app._focus_task_id

        self.select(0)
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False) as ask, \
             mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            self.app.focus_on_selected()
            ask.assert_called_once()
            starter.assert_not_called()
        self.assertEqual(self.app._focus_task_id, running_id)
        self.assertTrue(self.app._timer_running)
        self.app.pause_timer()

    def test_momentum_hover_restores_the_previous_status(self):
        self.app.set_status("Deleted 3 task(s).")
        self.app.on_momentum_hover("2026-07-27: 2 sessions")
        self.assertIn("2 sessions", self.app.status_var.get())
        self.app.on_momentum_hover("")
        self.assertEqual(self.app.status_var.get(), "Deleted 3 task(s).")

    def test_selection_set_clamps_and_accepts_end(self):
        for text in ("one", "two"):
            self.capture(text)
        self.app.task_list.selection_set(99)
        self.assertEqual(self.app.task_list.curselection(), (1,))
        self.app.task_list.selection_clear()
        self.app.task_list.selection_set(tk.END)
        self.assertEqual(self.app.task_list.curselection(), (1,))
        self.app.task_list.selection_clear()
        self.app.task_list.selection_set(-5)
        self.assertEqual(self.app.task_list.curselection(), (0,))

    def test_selection_set_on_an_empty_list_is_a_no_op(self):
        self.app.task_list.selection_set(0)
        self.assertEqual(self.app.task_list.curselection(), ())

    def test_space_in_a_matrix_quadrant_does_nothing(self):
        self.app.matrix.create("do_first", "a matrix task", "")
        self.app.refresh_matrix()
        listing = self.app.matrix_lists["do_first"]
        listing.selection_set(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as dialog:
            listing._activate_toggle()
            dialog.assert_not_called()

    def test_calm_mode_clears_the_filters_it_hides(self):
        self.capture("findable")
        self.capture("other")
        self.app.search_var.set("findable")
        self.app.refresh_tasks()
        self.assertEqual(self.app.task_list.size(), 1)

        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.assertEqual(self.app.search_var.get(), "")
        self.assertEqual(self.app.task_list.size(), 2)

    def test_ctrl_f_leaves_calm_mode_so_the_search_box_is_there(self):
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.app.focus_search()
        self.assertFalse(self.app.calm_var.get())
        self.assertEqual(self.app.search_row.winfo_manager(), "grid")

    def test_done_is_reachable_in_calm_mode(self):
        self.capture("finish me")
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.select(0)
        self.app.toggle_selected_done()  # the button lives outside the hidden toolbar
        self.assertTrue(self.app.tasks[0].done)

    # -- what got done today -------------------------------------------
    def test_done_today_appears_only_once_there_is_something_to_show(self):
        self.capture("a thing")
        self.assertEqual(self.app.today_var.get(), "")
        self.select(0)
        self.app.toggle_selected_done()
        self.assertIn("1 done today", self.app.today_var.get())

    def test_finishing_a_session_can_close_the_task(self):
        self.capture("the whole job")
        self.select(0)
        self.run_session(minutes=15, choice="done")
        self.assertTrue(self.app.tasks[0].done)
        self.assertIn("1 done today", self.app.today_var.get())
        self.app.undo()  # and it is undoable like every other mutation
        self.assertFalse(self.app.tasks[0].done)

    def test_finishing_a_session_can_leave_the_task_open(self):
        self.capture("more to do")
        self.select(0)
        self.run_session(minutes=15, choice="carry_on")
        self.assertFalse(self.app.tasks[0].done)

    def test_finish_time_is_shown_while_running_and_cleared_when_not(self):
        self.app.start_timer(minutes=10)
        self.assertRegex(self.app.finish_var.get(), r"^ends \d{2}:\d{2}$")
        self.app.pause_timer()
        self.assertEqual(self.app.finish_var.get(), "")

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
