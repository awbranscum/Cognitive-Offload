"""End-to-end smoke tests that drive the real Tk widgets.

Skipped automatically when tkinter or a display is unavailable, so the suite
still runs on a headless box without X.
"""

import contextlib
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

    def answer_prompt(self, value):
        """Answer the themed one-line prompt without opening a real window."""
        patcher = mock.patch("cognitive_offload.app.PromptDialog")
        dialog = patcher.start()
        dialog.return_value.show.return_value = value
        self.addCleanup(patcher.stop)
        return contextlib.nullcontext()

    def answer_session_end(self, choice, next_step=""):
        """Answer the end-of-session dialog without opening a real window."""
        patcher = mock.patch("cognitive_offload.app.SessionEndDialog")
        dialog = patcher.start()
        dialog.return_value.show.return_value = {"choice": choice, "next_step": next_step}
        self.addCleanup(patcher.stop)
        return mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False)

    def run_session(self, minutes=15, first_step="", choice="carry_on", next_step=""):
        """Start a focus session on the selection and run it to expiry."""
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": minutes, "first_step": first_step, "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 10_000
        with self.answer_session_end(choice, next_step):
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
        with self.answer_prompt("errand"):
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
        with self.answer_prompt("today"):
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
        with self.answer_prompt("squelch"), \
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

    def test_done_early_still_works_on_a_block_started_with_plain_start(self):
        """A finished block's banked flag must not outlive it.

        Finish a session, answer "keep going", then press the plain Start
        button: that is a new block, and "Done early" has to bank it.
        """
        self.capture("deep work")
        self.select(0)
        self.run_session(minutes=15)
        self.assertEqual(self.app.session_log.count_today(), 1)

        self.app.work_minutes.set(20)
        self.app.start_timer()  # the plain Start/Resume path, no minutes
        self.assertFalse(self.app._session_banked)
        self.app._timer_deadline -= 300  # five minutes in
        self.app._tick_timer()
        with self.answer_session_end("carry_on"):
            self.app.finish_session_early()
        self.assertEqual(self.app.session_log.count_today(), 2)
        self.assertEqual(self.app.session_log.sessions[-1].minutes, 5)

    def test_midnight_rollover_refreshes_the_momentum_summary_too(self):
        """Yesterday's sessions must not be reported as today's."""
        self.app._day = "2000-01-01"
        self.app.momentum_var.set("stale: 3 sessions today")
        self.app._roll_over_the_day()
        self.assertEqual(self.app.momentum_var.get(), self.app.session_log.summary())

    def test_reset_clears_the_banked_flag_with_the_rest_of_the_timer(self):
        self.capture("deep work")
        self.select(0)
        self.run_session(minutes=15)
        self.app.reset_timer()
        self.assertFalse(self.app._session_banked)

    def test_nudging_the_minutes_spinbox_keeps_a_paused_block(self):
        """An accidental arrow-click during a pause must not wipe the block."""
        self.app.start_timer(minutes=15)
        self.app._timer_deadline -= 600  # ten minutes in
        self.app._tick_timer()
        self.app.pause_timer()
        remaining = self.app._timer_remaining
        self.app.work_minutes.set(16)
        self.app.on_timer_minutes_changed()  # the spinbox arrows call this
        self.assertEqual(self.app._timer_total, 15 * 60)
        self.assertEqual(self.app._timer_remaining, remaining)
        # ...while an idle timer still follows the spinbox as before.
        self.app.reset_timer()
        self.app.on_timer_minutes_changed()
        self.assertEqual(self.app._timer_total, 16 * 60)

    def test_a_failing_autosave_says_so_once_not_every_thirty_seconds(self):
        self.capture("unsaved work")
        with mock.patch.object(self.app, "save_state", return_value=False):
            self.app._autosave()
            self.assertIn("auto-save", self.app.status_var.get().lower())
            self.app.hold_status("quiet again")
            self.app._autosave()  # still failing: no fresh nag
            self.assertEqual(self.app.status_var.get(), "quiet again")
        self.app.save_state(silent=True)  # a working save clears the streak
        with mock.patch.object(self.app, "save_state", return_value=False):
            self.app.capture_entry.insert(0, "more")
            self.app.add_task_from_capture()
            self.app._autosave()
            self.assertIn("auto-save", self.app.status_var.get().lower())

    def test_quit_stays_open_when_the_rescue_export_fails(self):
        self.capture("precious")
        with mock.patch.object(self.app, "save_state", return_value=False), \
                mock.patch("cognitive_offload.app.messagebox.askyesnocancel",
                           return_value=True), \
                mock.patch.object(self.app, "export_state", return_value=False):
            self.app.on_close()
        self.assertTrue(self.app.winfo_exists())

    def test_quit_cancel_stays_here(self):
        self.capture("precious")
        with mock.patch.object(self.app, "save_state", return_value=False), \
                mock.patch("cognitive_offload.app.messagebox.askyesnocancel",
                           return_value=None):
            self.app.on_close()
        self.assertTrue(self.app.winfo_exists())

    def test_a_failed_session_log_write_is_mentioned_not_fatal(self):
        with mock.patch.object(self.app.session_log, "save",
                               side_effect=OSError("disk full")):
            self.app._bank_session(5)
        self.assertIn("couldn't write the session log", self.app.status_var.get())
        self.assertEqual(self.app.session_log.count_today(), 1)  # still in memory

    def test_the_timer_waits_for_an_open_modal_before_finishing(self):
        """Completion must not steal the grab from an open dialog."""
        self.capture("focused work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        holder = tk.Toplevel(self.app)
        holder.update()
        try:
            holder.grab_set()
        except tk.TclError:
            holder.destroy()
            self.skipTest("cannot hold a grab on this display")
        if self.app.grab_current() is None:
            holder.destroy()
            self.skipTest("grab not effective on this display")
        self.app._timer_deadline -= 10_000
        with self.answer_session_end("carry_on"):
            self.app._tick_timer()
            # Deferred: still "running", nothing logged, dialog undisturbed.
            self.assertTrue(self.app._timer_running)
            self.assertEqual(self.app.session_log.count_today(), 0)
            holder.grab_release()
            holder.destroy()
            self.app._tick_timer()
        self.assertEqual(self.app.session_log.count_today(), 1)
        self.assertFalse(self.app._timer_running)

    def test_a_lone_surrogate_cannot_kill_the_save(self):
        """Some Tk builds hand back unpaired surrogates for astral emoji."""
        self.capture("emoji task")
        self.app.tasks[0].text = "broken \ud83d emoji"
        self.assertTrue(self.app.save_state(silent=True))
        self.app.load_state()
        self.assertIn("broken", self.app.tasks[0].text)

    # -- the estimate --------------------------------------------------
    def test_an_estimate_shows_as_a_quiet_badge(self):
        self.capture("guessed work")
        self.app.tasks[0].estimate_minutes = 25
        self.app.refresh_tasks()
        self.assertIn("~25 min", self.visible_texts()[0])

    def test_finishing_a_guessed_task_states_both_numbers_without_judgment(self):
        self.capture("guessed work")
        self.app.tasks[0].estimate_minutes = 10
        self.select(0)
        self.run_session(minutes=15, choice="done")
        status = self.app.status_var.get()
        self.assertIn("guessed ~10 min", status.lower())
        self.assertIn("about 15", status)
        for scold in ("late", "over", "wrong", "should", "only"):
            self.assertNotIn(scold, status.lower())

    def test_finishing_without_a_guess_keeps_the_plain_message(self):
        self.capture("no guess")
        self.select(0)
        self.run_session(minutes=15, choice="done")
        self.assertNotIn("guessed", self.app.status_var.get().lower())

    # -- not today / warm start ----------------------------------------
    def test_not_today_excuses_the_suggestion_but_keeps_the_task(self):
        self.capture("dreaded thing")
        self.assertEqual(self.app.next_title_var.get(), "dreaded thing")
        self.app.snooze_next()
        # The strip moved on (nothing else open, so it hides)...
        self.assertEqual(self.app.next_title_var.get(), "")
        # ...but the task is still on the list, unbadged and undeleted.
        self.assertEqual([t.text for t in self.app.tasks], ["dreaded thing"])
        self.assertIn("come back tomorrow", self.app.status_var.get())
        self.assertNotIn("snooze", self.visible_texts()[0].lower())

    def test_not_today_moves_to_the_next_open_task(self):
        self.capture("dreaded")
        self.capture("doable")
        first = self.app.next_title_var.get()
        self.app.snooze_next()
        second = self.app.next_title_var.get()
        self.assertNotEqual(first, second)
        self.assertTrue(second)

    def test_undo_reverses_a_snooze(self):
        self.capture("dreaded thing")
        self.app.snooze_next()
        self.app.undo()
        self.assertEqual(self.app.tasks[0].snoozed_until, "")
        self.assertEqual(self.app.next_title_var.get(), "dreaded thing")

    def test_a_banked_session_makes_the_task_warm_in_next_up(self):
        """Yesterday's work resurfaces instead of being buried by age."""
        self.capture("ancient backlog")
        self.capture("worked on recently")
        worked = next(t for t in self.app.tasks if t.text == "worked on recently")
        ancient = next(t for t in self.app.tasks if t.text == "ancient backlog")
        ancient.created_at = "2020-01-01 00:00:00"
        worked.created_at = "2020-06-01 00:00:00"
        # Without warmth, the older task wins the tiebreak.
        self.app.refresh_next_up()
        self.assertEqual(self.app.next_title_var.get(), "ancient backlog")
        self.select(next(i for i, t in enumerate(self.app._visible)
                         if t.id == worked.id))
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 300
        self.app._tick_timer()
        with self.answer_session_end("carry_on"):
            self.app.finish_session_early()
        self.app.refresh_next_up()
        self.assertEqual(self.app.next_title_var.get(), "worked on recently")

    # -- pinning -------------------------------------------------------
    def test_pinning_actually_reorders_the_visible_list(self):
        """The old 'move to top' reordered a list the sort immediately re-sorted."""
        self.capture("old and buried")
        self.capture("flagged and loud")
        self.capture("newest")
        flagged = next(i for i, t in enumerate(self.app._visible)
                       if t.text == "flagged and loud")
        self.select(flagged)
        self.app.toggle_selected_priority()
        buried = next(i for i, t in enumerate(self.app._visible)
                      if t.text == "old and buried")
        self.select(buried)
        self.app.promote_selected()
        self.assertEqual(self.app._visible[0].text, "old and buried")
        self.assertIn("Pinned 1 task(s) to the top.", self.app.status_var.get())
        self.assertIn("pinned", self.visible_texts()[0])

    def test_pinning_again_unpins(self):
        self.capture("a")
        self.capture("b")
        target = next(i for i, t in enumerate(self.app._visible) if t.text == "a")
        self.select(target)
        self.app.promote_selected()
        self.assertTrue(next(t for t in self.app.tasks if t.text == "a").pinned)
        self.select(0)  # the pinned task is now first
        self.app.promote_selected()
        self.assertFalse(next(t for t in self.app.tasks if t.text == "a").pinned)
        self.assertIn("Unpinned", self.app.status_var.get())

    def test_pinning_under_another_sort_does_not_claim_a_reorder(self):
        self.capture("a")
        self.app.sort_var.set("Created")
        self.select(0)
        self.app.promote_selected()
        self.assertIn("under Priority sort", self.app.status_var.get())

    def test_a_pin_survives_save_and_load(self):
        self.capture("keep me on top")
        self.select(0)
        self.app.promote_selected()
        self.assertTrue(self.app.save_state(silent=True))
        self.app.load_state()
        self.assertTrue(self.app.tasks[0].pinned)

    def test_undo_reverses_a_pin(self):
        self.capture("a")
        self.select(0)
        self.app.promote_selected()
        self.app.undo()
        self.assertFalse(self.app.tasks[0].pinned)

    def test_replacing_a_running_session_banks_silently_and_starts_the_new_one(self):
        """No end-of-session ceremony for the old block mid-start.

        The old flow opened the replaced task's SessionEndDialog in the middle
        of starting the new one, and its "take a break" answer started a break
        that silently swallowed the session being started.
        """
        self.capture("old thing")
        self.capture("new thing")
        old = next(t for t in self.app.tasks if t.text == "old thing")
        new = next(t for t in self.app.tasks if t.text == "new thing")
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.begin_focus(old)
        self.app._timer_deadline -= 300  # five minutes in
        self.app._tick_timer()

        with mock.patch("cognitive_offload.app.SessionEndDialog") as ender, \
                mock.patch("cognitive_offload.app.messagebox.askyesno",
                           return_value=True), \
                mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.begin_focus(new)
            ender.assert_not_called()

        self.assertEqual(self.app.session_log.sessions[-1].minutes, 5)
        self.assertEqual(self.app.session_log.sessions[-1].task, "old thing")
        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._timer_mode, "focus")
        self.assertFalse(self.app._session_banked)
        self.assertEqual(self.app._focus_task_id, new.id)
        # The bank notice must survive start_timer's own status message.
        self.assertIn('5 min banked on "old thing"', self.app.status_var.get())
        self.app.pause_timer()

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

    # -- round-two regressions -----------------------------------------
    def test_a_loaded_session_does_not_start_part_finished(self):
        """A stale total made a fresh clock look two-thirds run, then logged it."""
        self.capture("something")
        self.app.work_minutes.set(5)
        self.app.save_state(silent=True)
        self.app.load_state()
        self.assertEqual(self.app._timer_total, 5 * 60)
        self.assertEqual(self.app._timer_remaining, 5 * 60)
        self.assertEqual(self.app.timer_progress["value"], 0)
        self.app.finish_session_early()
        self.assertEqual(self.app.session_log.count_today(), 0)

    def test_opening_another_file_keeps_working_in_it(self):
        other = Path(self._tmp.name) / "other.json"
        from cognitive_offload.storage import StateStore
        from cognitive_offload.models import Task
        StateStore(other).save([Task(text="from the other file")], "", 15)
        with mock.patch("cognitive_offload.app.filedialog.askopenfilename",
                        return_value=str(other)):
            self.app.load_state_dialog()
        self.assertEqual([t.text for t in self.app.tasks], ["from the other file"])
        self.assertEqual(self.app.state_store.path, other)
        self.capture("added after opening")
        self.app.save_state(silent=True)
        self.assertIn("added after opening", other.read_text(encoding="utf-8"))

    def test_changing_folders_asks_before_dropping_unsaved_work(self):
        self.capture("precious")
        from cognitive_offload.storage import StorageError
        target = Path(self._tmp.name) / "elsewhere"
        target.mkdir()
        with mock.patch.object(self.app.state_store, "save", side_effect=StorageError("disk full")), \
             mock.patch("cognitive_offload.app.filedialog.askdirectory", return_value=str(target)), \
             mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False) as ask:
            self.app.change_db_folder()
            ask.assert_called_once()
        self.assertEqual([t.text for t in self.app.tasks], ["precious"])
        self.assertNotEqual(self.app.config_store.db_path, target)

    def test_undo_after_sending_to_the_matrix_removes_the_file_too(self):
        self.capture("goes to the matrix")
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()
        self.assertEqual(len(self.app.matrix.list("schedule")), 1)
        self.app.undo()
        self.assertEqual([t.text for t in self.app.tasks], ["goes to the matrix"])
        self.assertEqual(self.app.matrix.list("schedule"), [])  # not in two places

    def test_undo_still_finds_a_matrix_file_renamed_after_the_send(self):
        """The undo entry must survive the file being renamed or moved."""
        self.capture("original name")
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()
        created = self.app.matrix.list("schedule")[0]
        self.app.matrix.update(created, "renamed since", "")   # new slug, new file
        moved = self.app.matrix.move(created, "do_first")      # and a new folder
        self.assertTrue(Path(moved.path).exists())
        self.app.undo()
        self.assertEqual([t.text for t in self.app.tasks], ["original name"])
        self.assertEqual(self.app.matrix.list("do_first"), [])   # file really gone
        self.assertEqual(self.app.matrix.list("schedule"), [])
        self.assertFalse(Path(moved.path).exists())

    def test_focus_on_this_starts_a_session_straight_from_the_matrix(self):
        """Booked work gets the start machinery in one click, not four steps."""
        self.app.matrix.create("schedule", "booked deep work", "notes")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "open it", "warmup_done": 0,
            }
            self.app.focus_matrix_task("schedule")
        self.assertEqual([t.text for t in self.app.tasks], ["booked deep work"])
        self.assertEqual(self.app.matrix.list("schedule"), [])
        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._focus_task_id, self.app.tasks[0].id)
        self.assertEqual(self.app.notebook.index(self.app.notebook.select()), 0)
        self.app.pause_timer()

    def test_focus_on_this_cancelled_still_imports_but_starts_nothing(self):
        self.app.matrix.create("do_first", "urgent thing", "")
        self.app.refresh_matrix()
        self.app.matrix_lists["do_first"].selection_set(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = None  # user backed out
            self.app.focus_matrix_task("do_first")
        self.assertEqual([t.text for t in self.app.tasks], ["urgent thing"])
        self.assertFalse(self.app._timer_running)
        # ...and Ctrl+Z reverses even the import.
        self.app.undo()
        self.assertEqual(self.app.tasks, [])
        self.assertEqual([t.title for t in self.app.matrix.list("do_first")],
                         ["urgent thing"])

    def test_sending_to_the_matrix_lands_on_the_destination_quadrant(self):
        self.capture("triaged away")
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "delegate"
            self.app.send_selected_to_matrix()
        chosen_page = self.app.matrix_notebook.index(self.app.matrix_notebook.select())
        from cognitive_offload.storage import CATEGORY_KEYS
        self.assertEqual(chosen_page, CATEGORY_KEYS.index("delegate"))
        self.assertEqual(self.app.matrix_lists["delegate"].curselection(), (0,))

    def test_the_booked_banner_selects_the_due_rows(self):
        from cognitive_offload.models import today_iso

        self.app.matrix.create("schedule", "later", "")
        created = self.app.matrix.create("schedule", "due now", "")
        self.app.matrix.set_scheduled(created, today_iso())
        self.app.refresh_matrix()
        self.app.show_booked()
        listing = self.app.matrix_lists["schedule"]
        selected = [self.app._matrix_cache["schedule"][i].title
                    for i in listing.curselection()]
        self.assertEqual(selected, ["due now"])

    def test_undo_after_pulling_from_the_matrix_puts_the_file_back(self):
        self.app.matrix.create("schedule", "comes back", "notes")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.matrix_to_tasks("schedule")
        self.assertEqual(self.app.matrix.list("schedule"), [])
        self.app.undo()
        self.assertEqual(self.app.tasks, [])
        restored = self.app.matrix.list("schedule")
        self.assertEqual([t.title for t in restored], ["comes back"])

    def test_a_pin_survives_the_matrix_round_trip(self):
        self.capture("anchored")
        self.select(0)
        self.app.promote_selected()
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.matrix_to_tasks("schedule")
        self.assertTrue(self.app.tasks[0].pinned)

    def test_sending_to_the_matrix_keeps_tags_and_priority(self):
        self.capture("carry everything")
        task = self.app.tasks[0]
        task.tags = ["work"]
        task.priority = 1
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "delegate"
            self.app.send_selected_to_matrix()
        stored = self.app.matrix.list("delegate")[0]
        self.assertEqual(stored.tags, ["work"])
        self.assertEqual(stored.priority, 1)
        self.assertEqual(stored.to_task().tags, ["work"])
        self.assertEqual(stored.to_task().priority, 1)

    def test_clearing_the_scratchpad_is_undoable(self):
        self.app.note_text.insert("1.0", "notes I would hate to lose")
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_notes()
        self.assertEqual(self.app.scratchpad_text(), "")
        self.app.undo()
        self.assertIn("hate to lose", self.app.scratchpad_text())

    def test_matrix_selection_survives_a_refresh(self):
        self.app.matrix.create("schedule", "stays selected", "")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.refresh_matrix()
        self.assertEqual(self.app.matrix_lists["schedule"].curselection(), (0,))

    def test_starting_a_session_during_a_break_is_offered(self):
        self.capture("a task")
        self.select(0)
        self.app.start_timer(minutes=5, mode="break")
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False) as ask, \
             mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            self.app.focus_on_selected()
            ask.assert_called_once()
            self.assertIn("break", ask.call_args[0][1].lower())
            starter.assert_not_called()
        self.app.pause_timer()

    def test_cancelling_the_new_session_leaves_the_running_one_alone(self):
        self.capture("in progress")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        running_id = self.app._focus_task_id

        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True), \
             mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = None  # cancelled at the ladder
            self.app.focus_on_selected()
        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._focus_task_id, running_id)
        self.assertEqual(self.app.session_log.count_today(), 0)
        self.app.pause_timer()

    def test_the_already_running_prompt_reports_time_spent(self):
        self.capture("a task")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 20, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        self.app._timer_deadline -= 300  # five minutes in
        self.app._tick_timer()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=False) as ask:
            self.app.focus_on_selected()
            self.assertIn("5 minutes into", ask.call_args[0][1])
        self.app.pause_timer()

    def test_pausing_in_the_last_second_still_banks_the_session(self):
        self.capture("nearly done")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        self.app._timer_deadline -= (15 * 60 - 1)  # one second left
        self.app.pause_timer()
        with self.answer_session_end("carry_on"):
            self.app.finish_session_early()
        self.assertEqual(self.app.session_log.count_today(), 1)

    def test_parking_a_thought_does_not_touch_the_session(self):
        self.capture("the work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0}
            self.app.focus_on_selected()
        self.app.open_focus_window()
        window = self.app._focus_window
        window.park_entry.insert(0, "email Dana about the invoice")
        window._park()

        self.assertIn("email Dana", self.app.scratchpad_text())
        self.assertEqual(window.park_entry.get(), "")
        self.assertEqual([t.text for t in self.app.tasks], ["the work"])  # not a task
        self.assertTrue(self.app._timer_running)                          # not paused
        self.assertEqual(self.app.session_log.count_today(), 0)
        window._park()  # empty park is a no-op
        self.app.pause_timer()

    def test_search_scroll_resets_when_the_list_shrinks(self):
        for index in range(60):
            self.capture(f"task {index:02d}")
        self.app.task_list.canvas.yview_moveto(1.0)
        self.app.search_var.set("task 03")
        self.app.refresh_tasks()
        self.assertEqual(self.app.task_list.canvas.yview()[0], 0.0)

    # -- coverage the audit found missing -------------------------------
    def test_switching_theme_actually_recolours_widgets(self):
        self.capture("a task")
        before = self.app.task_list.canvas.cget("background")
        self.app.toggle_theme()
        after = self.app.task_list.canvas.cget("background")
        self.assertNotEqual(before, after)
        from cognitive_offload import theme
        self.assertEqual(after, theme.DARK.card)

    def test_rows_are_really_drawn_not_just_recorded(self):
        self.capture("visible task")
        self.app.tasks[0].first_step = "open it"
        self.app.refresh_tasks()
        cell = self.app.task_list._pool[0]
        self.assertEqual(cell["title"].cget("text"), "visible task")
        self.assertIn("open it", cell["subtitle"].cget("text"))
        self.assertTrue(cell["visible"])

    def test_the_empty_state_is_rendered_not_just_configured(self):
        self.assertEqual(self.app.task_list.size(), 0)
        self.assertTrue(self.app.task_list._empty_label.winfo_manager())
        self.capture("now there is one")
        self.assertFalse(self.app.task_list._empty_label.winfo_manager())

    def test_momentum_strip_draws_a_cell_per_day_and_never_red(self):
        self.app.session_log.record(minutes=15)
        self.app.refresh_momentum()
        strip = self.app.momentum_strip
        items = strip.find_all()
        self.assertEqual(len(items), 14)
        colours = {strip.itemcget(i, "fill").lower() for i in items}
        for colour in colours:
            red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
            self.assertFalse(red > green + 40 and red > blue + 40, f"{colour} reads as red")

    def test_calm_mode_is_restored_from_config_at_startup(self):
        from cognitive_offload.app import CognitiveOffloadApp
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.app._save_config()

        from cognitive_offload.storage import Config
        # A second app in the same process is how "next launch" is observable
        # without tearing down the interpreter under the test runner. The
        # previous "run" has exited as far as the folder lock is concerned.
        self.app._instance_lock.release()
        restored = CognitiveOffloadApp(config=Config(self.app.config_store.path).load())
        restored.withdraw()
        self.addCleanup(restored.destroy)
        self.assertTrue(restored.calm_var.get())
        self.assertEqual(restored.filter_row.winfo_manager(), "")
        self.assertEqual(restored.header_extras.winfo_manager(), "")

    # -- the day's record ----------------------------------------------
    def test_clearing_completed_keeps_the_days_record(self):
        self.capture("finished thing")
        self.select(0)
        self.app.toggle_selected_done()
        self.assertIn("1 done today", self.app.today_var.get())

        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_completed()
        self.assertEqual(self.app.tasks, [])
        # The task is gone from the list, but the day is not reset to zero.
        self.assertIn("1 done today", self.app.today_var.get())

    def test_the_days_record_survives_a_save_and_reload(self):
        self.capture("finished thing")
        self.select(0)
        self.app.toggle_selected_done()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_completed()
        self.app.save_state(silent=True)
        self.app.completed_log = []
        self.app.load_state()
        self.assertIn("1 done today", self.app.today_var.get())

    def test_undoing_clear_completed_restores_the_record_too(self):
        self.capture("finished thing")
        self.select(0)
        self.app.toggle_selected_done()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_completed()
        self.app.undo()
        self.assertEqual([t.text for t in self.app.tasks], ["finished thing"])
        self.assertEqual(self.app.completed_log, [])
        self.assertIn("1 done today", self.app.today_var.get())  # counted once, not twice

    def test_a_failed_matrix_import_never_leaves_a_task_in_both_stores(self):
        """Insert-after-delete: an I/O error must not create a duplicate."""
        from cognitive_offload.storage import StorageError

        for title in ("first", "second"):
            self.app.matrix.create("schedule", title, "")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0, 1)
        calls = {"n": 0}
        real_delete = type(self.app.matrix).delete

        def flaky(task):
            calls["n"] += 1
            if calls["n"] > 1:
                raise StorageError("locked")
            real_delete(self.app.matrix, task)

        with mock.patch.object(self.app.matrix, "delete", side_effect=flaky), \
                mock.patch("cognitive_offload.app.messagebox.showerror"):
            self.app.matrix_to_tasks("schedule")
        moved = [t.text for t in self.app.tasks]
        self.app.refresh_matrix()
        left_behind = [t.title for t in self.app._matrix_cache["schedule"]]
        # Exactly one moved, exactly one stayed — and neither is in both.
        self.assertEqual(len(moved), 1)
        self.assertEqual(len(left_behind), 1)
        self.assertNotIn(left_behind[0], moved)

    def test_a_batch_that_fails_halfway_says_so(self):
        from cognitive_offload.storage import StorageError

        for title in ("one", "two"):
            self.app.matrix.create("schedule", title, "")
        self.app.refresh_matrix()
        self.app.matrix_lists["schedule"].selection_set(0, 1)
        calls = {"n": 0}

        def flaky(_task):
            calls["n"] += 1
            if calls["n"] > 1:
                raise StorageError("locked")

        with mock.patch.object(self.app.matrix, "delete", side_effect=flaky), \
             mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True), \
             mock.patch("cognitive_offload.app.messagebox.showerror"):
            self.app.delete_matrix_tasks("schedule")
        self.assertIn("1 of 2", self.app.status_var.get())

    # -- the hand-off --------------------------------------------------
    def test_the_hand_off_replaces_the_spent_first_step(self):
        """The first step you just used up is useless to tomorrow's you."""
        self.capture("the long job")
        self.app.tasks[0].first_step = "open last quarter's doc"
        self.app.refresh_tasks()
        self.select(0)
        self.run_session(choice="carry_on", next_step="draft the risks section")
        self.assertEqual(self.app.tasks[0].first_step, "draft the risks section")
        self.assertTrue(self.app.tasks[0].is_ready)

    def test_a_blank_hand_off_leaves_the_task_alone(self):
        self.capture("the long job")
        self.app.tasks[0].first_step = "open the doc"
        self.app.refresh_tasks()
        self.select(0)
        self.run_session(choice="carry_on", next_step="")
        self.assertEqual(self.app.tasks[0].first_step, "open the doc")

    def test_the_hand_off_is_ignored_when_the_task_is_finished(self):
        self.capture("the long job")
        self.app.tasks[0].first_step = "open the doc"
        self.app.refresh_tasks()
        self.select(0)
        self.run_session(choice="done", next_step="typed then changed my mind")
        self.assertTrue(self.app.tasks[0].done)
        self.assertEqual(self.app.tasks[0].first_step, "open the doc")

    def test_the_hand_off_is_undoable(self):
        self.capture("the long job")
        self.app.tasks[0].first_step = "open the doc"
        self.app.refresh_tasks()
        self.select(0)
        self.run_session(choice="carry_on", next_step="the next move")
        self.app.undo()
        self.assertEqual(self.app.tasks[0].first_step, "open the doc")

    # -- next up --------------------------------------------------------
    def test_the_app_names_the_next_thing_without_being_asked(self):
        self.capture("vague thing")
        self.capture("ready thing")
        self.app.tasks[0].first_step = "open the folder"
        self.app.refresh_tasks()
        # The one that says how to start outranks the one that does not.
        self.assertEqual(self.app.next_title_var.get(), "ready thing")
        self.assertIn("open the folder", self.app.next_step_var.get())

    def test_a_task_with_no_first_step_says_so_rather_than_nothing(self):
        self.capture("vague thing")
        self.assertEqual(self.app.next_title_var.get(), "vague thing")
        self.assertIn("no first step", self.app.next_step_var.get())

    def test_next_up_is_hidden_when_there_is_nothing_open(self):
        self.assertEqual(self.app.next_title_var.get(), "")
        self.assertEqual(self.app.next_frame.winfo_manager(), "")
        self.capture("something")
        self.assertEqual(self.app.next_frame.winfo_manager(), "grid")

    def test_start_this_goes_straight_to_the_session(self):
        self.capture("the thing")
        with mock.patch("cognitive_offload.app.StartHereDialog") as picker, \
             mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "open it", "warmup_done": 0}
            self.app.start_next()
            picker.assert_not_called()  # no picker: that is the whole point
        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app._focus_task_id, self.app.tasks[0].id)
        self.app.pause_timer()

    def test_not_that_one_walks_to_another_suggestion(self):
        for text in ("first", "second", "third"):
            self.capture(text)
        seen = {self.app.next_title_var.get()}
        self.app.skip_next()
        seen.add(self.app.next_title_var.get())
        self.app.skip_next()
        seen.add(self.app.next_title_var.get())
        self.assertEqual(len(seen), 3)
        self.app.skip_next()  # wraps rather than dead-ending
        self.assertIn(self.app.next_title_var.get(), seen)

    def test_not_that_one_with_a_single_task_says_so(self):
        self.capture("the only one")
        self.app.skip_next()
        self.assertEqual(self.app.next_title_var.get(), "the only one")
        self.assertIn("only thing open", self.app.status_var.get())

    def test_finishing_the_suggestion_moves_next_up_along(self):
        self.capture("first")
        self.capture("second")
        first_suggestion = self.app.next_title_var.get()
        for index, task in enumerate(self.app._visible):
            if task.text == first_suggestion:
                self.select(index)
                break
        self.app.toggle_selected_done()
        self.assertNotEqual(self.app.next_title_var.get(), first_suggestion)

    def test_next_up_survives_calm_mode(self):
        self.capture("still visible")
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.assertEqual(self.app.next_frame.winfo_manager(), "grid")
        self.assertEqual(self.app.next_title_var.get(), "still visible")

    def test_dirty_flag_tracks_edits_and_saves(self):
        self.assertFalse(self.app._dirty)
        self.capture("something")
        self.assertTrue(self.app._dirty)
        self.app.save_state(silent=True)
        self.assertFalse(self.app._dirty)
        self.app.note_text.insert("1.0", "typing")
        self.app.update()  # let the <<Modified>> event reach the handler
        self.assertTrue(self.app._dirty)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class InstanceGuardTests(unittest.TestCase):
    """Two copies on one session folder is silent last-writer-wins loss."""

    def _make_config(self):
        from cognitive_offload.storage import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        return config

    def test_the_app_locks_its_session_folder(self):
        from cognitive_offload.app import CognitiveOffloadApp

        config = self._make_config()
        app = CognitiveOffloadApp(config=config)
        app.withdraw()
        self.addCleanup(app.destroy)
        self.assertFalse(app.aborted)
        self.assertTrue((config.db_path / ".lock").exists())

    def test_declining_the_takeover_aborts_the_second_copy(self):
        from cognitive_offload.app import CognitiveOffloadApp

        config = self._make_config()
        first = CognitiveOffloadApp(config=config)
        first.withdraw()
        self.addCleanup(first.destroy)
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=False):
            second = CognitiveOffloadApp(config=config)
        self.assertTrue(second.aborted)
        # First copy's lock is untouched.
        self.assertTrue((config.db_path / ".lock").exists())
        self.assertTrue(first._instance_lock.owned)

    def test_accepting_the_takeover_claims_the_lock(self):
        from cognitive_offload.app import CognitiveOffloadApp

        config = self._make_config()
        first = CognitiveOffloadApp(config=config)
        first.withdraw()
        self.addCleanup(first.destroy)
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=True):
            second = CognitiveOffloadApp(config=config)
        second.withdraw()
        self.addCleanup(second.destroy)
        self.assertFalse(second.aborted)
        self.assertTrue(second._instance_lock.owned)

    def test_closing_releases_the_lock(self):
        from cognitive_offload.app import CognitiveOffloadApp

        config = self._make_config()
        app = CognitiveOffloadApp(config=config)
        app.withdraw()
        app.on_close()
        self.assertFalse((config.db_path / ".lock").exists())


@unittest.skipUnless(_display_available(), "tkinter display not available")
class CorruptRecoveryTests(unittest.TestCase):
    """Opening the app on an unreadable data.json must never cost data."""

    GOOD_SESSION = ('{"tasks": [{"text": "saved yesterday"}], '
                    '"scratchpad": "", "timer_minutes": 15}')

    def _make_app(self, corrupt=True, backup=None, restore=True):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        db = root / "db"
        db.mkdir(parents=True)
        if corrupt:
            (db / "data.json").write_text("{not json", encoding="utf-8")
        if backup is not None:
            (db / "data.json.bak").write_text(backup, encoding="utf-8")
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=restore), \
                mock.patch("cognitive_offload.app.messagebox.showerror"), \
                mock.patch("cognitive_offload.app.messagebox.showinfo"):
            app = CognitiveOffloadApp(config=config)
        app.withdraw()
        self.addCleanup(app.destroy)
        return app, db

    def _quarantined(self, db):
        return sorted(db.glob("data.json.corrupt-*"))

    def test_restoring_the_backup_brings_the_session_back(self):
        app, db = self._make_app(backup=self.GOOD_SESSION, restore=True)
        self.assertEqual([t.text for t in app.tasks], ["saved yesterday"])
        self.assertFalse(app._autosave_blocked)
        spoiled = self._quarantined(db)
        self.assertEqual(len(spoiled), 1)
        self.assertEqual(spoiled[0].read_text(encoding="utf-8"), "{not json")

    def test_declining_the_restore_starts_fresh_and_keeps_the_bak(self):
        app, db = self._make_app(backup=self.GOOD_SESSION, restore=False)
        self.assertEqual(app.tasks, [])
        self.assertFalse(app._autosave_blocked)
        # Two saves: the once-per-run backup must NOT replace the good .bak
        # with the fresh empty session.
        self.assertTrue(app.save_state(silent=True))
        app.capture_entry.insert(0, "new life")
        app.add_task_from_capture()
        self.assertTrue(app.save_state(silent=True))
        self.assertEqual((db / "data.json.bak").read_text(encoding="utf-8"),
                         self.GOOD_SESSION)
        self.assertEqual(len(self._quarantined(db)), 1)

    def test_no_backup_starts_fresh_with_the_bad_file_kept(self):
        app, db = self._make_app(backup=None)
        self.assertEqual(app.tasks, [])
        self.assertFalse(app._autosave_blocked)
        spoiled = self._quarantined(db)
        self.assertEqual(len(spoiled), 1)
        self.assertEqual(spoiled[0].read_text(encoding="utf-8"), "{not json")

    def test_a_foreign_file_is_left_exactly_where_it_is(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        db = root / "db"
        db.mkdir(parents=True)
        foreign = '{"someone": "elses file"}'
        (db / "data.json").write_text(foreign, encoding="utf-8")
        with mock.patch("cognitive_offload.app.messagebox.askyesno"), \
                mock.patch("cognitive_offload.app.messagebox.showerror"), \
                mock.patch("cognitive_offload.app.messagebox.showinfo"):
            app = CognitiveOffloadApp(config=config)
        app.withdraw()
        self.addCleanup(app.destroy)
        self.assertTrue(app._autosave_blocked)
        self.assertEqual((db / "data.json").read_text(encoding="utf-8"), foreign)
        self.assertEqual(sorted(db.glob("data.json.corrupt-*")), [])


if __name__ == "__main__":
    unittest.main()
