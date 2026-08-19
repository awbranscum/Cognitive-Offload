"""End-to-end smoke tests that drive the real Tk widgets.

Skipped automatically when tkinter or a display is unavailable, so the suite
still runs on a headless box without X.
"""

import contextlib
import json
import re
import tempfile
import unittest
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
        self.addCleanup(self._destroy_app)

    def _destroy_app(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass  # on_close tests already tore the window down

    # -- helpers -------------------------------------------------------
    def _really_focus(self, widget):
        """Map the window and wait for X focus to actually land on ``widget``.

        setUp withdraws the window, and a withdrawn window receives no key
        events at all — so ``event_generate`` on one is a no-op that any
        "nothing happened" assertion passes vacuously. Modelled on
        test_dialogs._focus, which is where the suite's two legitimate
        skips come from: if the display will not give us focus, say so
        rather than pretend the key was delivered.
        """
        import time

        self.app.deiconify()
        for _ in range(100):
            self.app.update()
            if self.app.focus_get() is widget:
                return True
            widget.focus_force()
            time.sleep(0.01)
        return False

    def _assert_key_delivery(self, widget):
        """Prove a key actually arrives before trusting a negative result.

        Without this, a broken guard and an undelivered event look
        identical — which is exactly how the test below passed for its
        whole life with the guard removed.
        """
        landed = []
        token = "<Key-F9>"
        widget.bind(token, lambda _e: landed.append(True), add=True)
        try:
            widget.event_generate(token)
            self.app.update()
        finally:
            widget.unbind(token)
        return bool(landed)

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

    def test_brain_dump_moves_the_lines_out_of_the_pad(self):
        """"Moved 3 lines" now means moved — a second dump used to
        create every task again."""
        self.app.note_text.insert("1.0", "- first\n- second\n- third\n")
        self.app.brain_dump_into_tasks()
        self.assertEqual(self.app.scratchpad_text().strip(), "")
        self.app.brain_dump_into_tasks()  # nothing left to dump
        self.assertEqual(len(self.app.tasks), 3)  # no duplicates

    def test_line_to_task_takes_only_its_line_with_it(self):
        self.app.note_text.insert("1.0", "keep me\ntake me\nkeep me too\n")
        self.app.note_text.mark_set("insert", "2.0")
        self.app.send_scratch_line_to_tasks()
        self.assertEqual([t.text for t in self.app.tasks], ["take me"])
        pad = self.app.scratchpad_text()
        self.assertNotIn("take me", pad)
        self.assertIn("keep me", pad)
        self.assertIn("keep me too", pad)

    def test_moving_one_line_says_line_not_line_s(self):
        """"Sent 1 line(s)" shipped on the button whose whole job is one line.

        v3.26.0 removed "1 task(s)" from fifteen status messages and these
        two survived, because they are passed positionally to _add_tasks —
        the extractor could not see them until v3.35.0 taught it to read
        that position. For Line → task the singular is not an edge case,
        it is the case.
        """
        self.app.note_text.insert("1.0", "ring the bank\nsomething else\n")
        self.app.note_text.mark_set("insert", "1.0")
        self.app.send_scratch_line_to_tasks()
        self.assertEqual(self.app.status_var.get(),
                         "Sent 1 line to the task list.")

    def test_dumping_one_line_says_line_not_line_s(self):
        self.app.note_text.insert("1.0", "call the dentist\n")
        self.app.brain_dump_into_tasks()
        self.assertEqual(self.app.status_var.get(), "Moved 1 line into tasks.")

    def test_several_lines_are_still_plural(self):
        self.app.note_text.insert("1.0", "one\ntwo\nthree\n")
        self.app.brain_dump_into_tasks()
        self.assertEqual(self.app.status_var.get(), "Moved 3 lines into tasks.")

    def test_a_status_template_with_no_count_is_left_alone(self):
        """`.format` is given both keys, so a template using neither must
        pass through untouched rather than raising or growing a stray word."""
        self.capture("a thought")
        self.assertEqual(self.app.status_var.get(), "Captured as task.")

    def test_undo_reverses_the_whole_move_pad_and_list_together(self):
        self.app.note_text.insert("1.0", "- one\n- two\n")
        before = self.app.scratchpad_text()
        self.app.brain_dump_into_tasks()
        self.assertEqual(len(self.app.tasks), 2)
        self.app.undo()
        self.assertEqual(self.app.tasks, [])
        self.assertEqual(self.app.scratchpad_text(), before)
        # and the same for a single line
        self.app.note_text.mark_set("insert", "1.0")
        self.app.send_scratch_line_to_tasks()
        self.assertEqual(len(self.app.tasks), 1)
        self.app.undo()
        self.assertEqual(self.app.tasks, [])
        self.assertEqual(self.app.scratchpad_text(), before)

    def test_clear_completed_removes_only_finished_tasks(self):
        self.capture("keep")
        self.capture("drop")
        self.select(0)
        self.app.toggle_selected_done()
        with mock.patch("cognitive_offload.app.messagebox.askyesno", return_value=True):
            self.app.clear_completed()
        self.assertEqual([t.text for t in self.app.tasks], ["keep"])

    def test_the_f1_help_dialog_constructs(self):
        """The only dialog no flow test builds — a style or font
        regression in its constructor would break F1 unnoticed."""
        from cognitive_offload.dialogs import ShortcutsDialog
        dialog = ShortcutsDialog(self.app)
        try:
            self.assertGreater(len(dialog.body.winfo_children()), 4)
        finally:
            dialog.destroy()

    # -- the cheat-sheet has to stay true ------------------------------
    #
    # A shortcuts dialog is a promise, and the README taught this branch
    # that promises drift. These pin the property in both directions:
    # everything listed is bound, and everything bound is listed.

    #: how a row's accelerator label maps onto a tk sequence
    KEY_SEQUENCES = {
        "Ctrl+G": "<Control-Key-g>", "Ctrl+R": "<Control-Key-r>",
        "Ctrl+N": "<Control-Key-n>", "Ctrl+B": "<Control-Key-b>",
        "Ctrl+P": "<Control-Key-p>", "Ctrl+T": "<Control-Key-t>",
        "Ctrl+M": "<Control-Key-m>", "Ctrl+Z": "<Control-Key-z>",
        "Ctrl+F": "<Control-Key-f>", "Ctrl+S": "<Control-Key-s>",
        "Ctrl+O": "<Control-Key-o>", "Ctrl+D": "<Control-Key-d>",
        "Ctrl+Up": "<Control-Key-Up>", "Ctrl+1": "<Control-Key-1>",
        "Ctrl+2": "<Control-Key-2>", "Escape": "<Key-Escape>",
        "F1": "<Key-F1>",
        # Named keys whose tk spelling is not the label: the sheet says what
        # is printed on the keyboard, tk says what X calls it.
        "Enter": "<Key-Return>", "Ctrl+Enter": "<Control-Key-Return>",
        "Space": "<Key-space>", "Delete": "<Key-Delete>",
        "Up": "<Key-Up>", "Down": "<Key-Down>",
    }

    def test_every_shortcut_the_help_lists_is_actually_bound(self):
        """A cheat-sheet that lies is worse than no cheat-sheet.

        It is read by someone who could not remember the key — exactly the
        person who will not work out that the sheet is wrong.
        """
        from cognitive_offload.dialogs import ShortcutsDialog
        bound = set(self.app.bind_all())
        bound |= set(self.app.capture_entry.bind())
        bound |= set(self.app.task_list.canvas.bind())
        missing = []
        for _section, rows in ShortcutsDialog.SHORTCUTS:
            for accelerator, _what in rows:
                for part in accelerator.split(" / "):
                    key = part.split(" (")[0].strip()
                    if key == "Double click":
                        continue  # a mouse gesture, checked by on_activate
                    sequence = self.KEY_SEQUENCES.get(key, f"<Key-{key}>")
                    if sequence not in bound:
                        missing.append(f"{accelerator!r} -> {sequence}")
        self.assertEqual(missing, [], "the help lists a shortcut nothing binds")

    def test_every_global_shortcut_is_in_the_help(self):
        """The other direction: a key that works but is written down
        nowhere may as well not exist, for the person this app is for."""
        from cognitive_offload.dialogs import ShortcutsDialog
        listed = {self.KEY_SEQUENCES.get(part.split(" (")[0].strip())
                  for _s, rows in ShortcutsDialog.SHORTCUTS
                  for accelerator, _w in rows
                  for part in accelerator.split(" / ")}
        # tk binds these itself on every Tk app; they are not ours to document.
        tk_own = {"<<NextWindow>>", "<<PrevWindow>>", "<Alt-Key>", "<Key-F10>"}
        undocumented = sorted(set(self.app.bind_all()) - listed - tk_own)
        self.assertEqual(undocumented, [],
                         "a global shortcut is bound but not in the help")

    def test_enter_on_a_selected_task_opens_the_editor(self):
        """The row added because the key worked and the sheet was silent."""
        self.capture("write the letter")
        self.select(0)
        self.assertIn("<Key-Return>", self.app.task_list.canvas.bind())

    def test_change_folder_migrates_the_lock_and_the_logs(self):
        new = Path(self._tmp.name) / "elsewhere"
        new.mkdir()
        old_db = self.app.config_store.db_path
        old_lock = self.app._instance_lock
        with mock.patch("cognitive_offload.app.filedialog.askdirectory",
                        return_value=str(new)):
            self.app.change_db_folder()
        self.assertEqual(self.app.config_store.db_path, new)
        self.assertTrue((new / ".lock").exists())        # new folder held
        self.assertFalse((old_db / ".lock").exists())    # old one released
        self.assertIsNot(self.app._instance_lock, old_lock)
        self.assertTrue(str(self.app.session_log.path).startswith(str(new)))

    def test_change_folder_backs_off_when_the_new_folder_is_contested(self):
        new = Path(self._tmp.name) / "occupied"
        new.mkdir()
        old_db = self.app.config_store.db_path
        with mock.patch("cognitive_offload.app.filedialog.askdirectory",
                        return_value=str(new)), \
             mock.patch.object(self.app, "_claim_instance_lock",
                               return_value=False):
            self.app.change_db_folder()
        self.assertEqual(self.app.config_store.db_path, old_db)
        self.assertTrue((old_db / ".lock").exists())  # still ours
        self.assertIn("Kept the current session folder",
                      self.app.status_var.get())

    def _matrix_dialog_result(self, **overrides):
        """Everything TaskEditorDialog.collect() returns, not a subset.

        A stub that omits a key tests the app against a dialog that does not
        exist. It omitted `repeat` and `estimate_minutes` on the add path,
        which is how both went straight to the floor untested; the guard
        against the next one is tests/test_editor_fields.py.
        """
        result = {"title": "From the dialog", "content": "body text",
                  "first_step": "open it", "kind": "admin",
                  "scheduled_for": "", "estimate_minutes": 0, "repeat": "",
                  "clear_snooze": False, "take_back": False,
                  "waiting_on": "", "check_back": ""}
        result.update(overrides)
        return result

    def test_matrix_add_carries_every_dialog_field(self):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._matrix_dialog_result(
                scheduled_for="2026-09-01", estimate_minutes=25,
                repeat="weekly")
            self.app.add_matrix_task("do_first")
        [task] = self.app.matrix.list("do_first")
        self.assertEqual(task.title, "From the dialog")
        self.assertEqual(task.first_step, "open it")
        self.assertEqual(task.kind, "admin")
        self.assertEqual(task.scheduled_for, "2026-09-01")
        # Typed into the dialog and dropped on the floor until v3.51.0. The
        # person watched themselves fill both of these in.
        self.assertEqual(task.estimate_minutes, 25)
        self.assertEqual(task.repeat, "weekly")
        self.assertEqual(self.app.matrix_lists["do_first"].size(), 1)

    def test_matrix_edit_round_trips_the_fields(self):
        self.app.matrix.create("do_first", "Old title")
        self.app.refresh_matrix()
        self.app.matrix_lists["do_first"].selection_set(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = self._matrix_dialog_result(
                title="New title", estimate_minutes=45)
            self.app.edit_matrix_task("do_first")
        [task] = self.app.matrix.list("do_first")
        self.assertEqual(task.title, "New title")
        self.assertEqual(task.estimate_minutes, 45)
        self.assertEqual(task.kind, "admin")

    # -- repeating tasks -----------------------------------------------
    def _make_repeating(self, text="Take the bins out", repeat="weekly",
                        booked="2026-08-21"):
        self.capture(text)
        task = self.app.tasks[0]
        task.repeat = repeat
        task.scheduled_for = booked
        self.app.refresh_tasks()
        return task

    def test_finishing_a_repeating_task_books_the_next_one(self):
        task = self._make_repeating()
        self.select(0)
        self.app.toggle_selected_done()
        self.assertTrue(task.done)
        following = [t for t in self.app.tasks if not t.done and t.repeat == "weekly"]
        self.assertEqual(len(following), 1)
        self.assertGreater(following[0].scheduled_for, task.scheduled_for)

    def test_the_finished_round_stays_finished_so_the_week_still_counts_it(self):
        """A task that quietly reset its own date would erase the evidence
        that you did it — which is the one thing the week review is for."""
        task = self._make_repeating()
        self.select(0)
        self.app.toggle_selected_done()
        self.assertTrue(task.done)
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(len([t for t in self.app.tasks if t.done]), 1)

    def test_doing_the_bins_six_weeks_running_looks_like_six_things_done(self):
        for _ in range(6):
            open_repeats = [t for t in self.app.tasks
                            if not t.done and t.repeat == "weekly"]
            if not open_repeats:
                self._make_repeating()
                continue
            index = self.app._visible.index(open_repeats[0])
            self.select(index)
            self.app.toggle_selected_done()
        self.assertEqual(len([t for t in self.app.tasks if t.done]), 5)
        self.assertEqual(len([t for t in self.app.tasks if not t.done]), 1)

    def test_finishing_a_one_off_books_nothing(self):
        self.capture("a single thing")
        self.select(0)
        self.app.toggle_selected_done()
        self.assertEqual(len(self.app.tasks), 1)

    def test_a_task_already_done_is_not_completed_a_second_time(self):
        """Marking a mixed selection done must not re-book the ones that were
        already finished.

        Single selection cannot see this: ``target`` is only True when
        something selected is still open, so a lone done task takes the
        no-op branch either way. The guard only bites on a MIXED selection,
        which is exactly the shape the first version of this test missed.
        """
        first = self._make_repeating("Take the bins out")
        self.select(0)
        self.app.toggle_selected_done()          # first round done, next booked
        self.assertTrue(first.done)
        self._make_repeating("Water the plants", repeat="daily")
        self.app.refresh_tasks()
        before = len(self.app.tasks)

        # Select the finished one AND an open one together.
        open_task = [t for t in self.app.tasks if not t.done][0]
        self.select(self.app._visible.index(first),
                    self.app._visible.index(open_task))
        self.app.toggle_selected_done()
        # Exactly one new booking — from the open task, not from the finished
        # one, which must not be completed twice.
        self.assertEqual(len(self.app.tasks), before + 1)

    def test_un_ticking_a_repeating_task_books_nothing(self):
        """Un-ticking is a correction, not a completion."""
        self._make_repeating()
        self.select(0)
        self.app.toggle_selected_done()
        before = len(self.app.tasks)
        done = [t for t in self.app.tasks if t.done][0]
        self.select(self.app._visible.index(done))
        self.app.toggle_selected_done()          # back to open
        self.assertEqual(len(self.app.tasks), before)
        self.assertFalse(done.done)

    def test_ctrl_z_undoes_the_whole_thing_including_the_new_booking(self):
        self._make_repeating()
        before = len(self.app.tasks)
        self.select(0)
        self.app.toggle_selected_done()
        self.assertEqual(len(self.app.tasks), before + 1)
        self.app.undo()
        self.assertEqual(len(self.app.tasks), before)
        self.assertFalse(any(t.done for t in self.app.tasks))

    def test_the_status_reads_correctly_whichever_form_the_date_takes(self):
        """humanize_date returns "today", "tomorrow", "Sat", "in 9 days" and
        "2026-09-30". Any preposition that fits a weekday is wrong for a
        duration — "Next one booked for in 9 days." passed every test there
        was, and was only visible by running the app."""
        from cognitive_offload.models import humanize_date

        for booked, repeat in (("2026-08-21", "weekly"), ("", "daily"),
                               ("", "monthly"), ("", "fortnightly")):
            with self.subTest(repeat=repeat):
                self.app.tasks = []
                task = self._make_repeating(f"thing {repeat}", repeat, booked)
                self.select(self.app._visible.index(task))
                self.app.toggle_selected_done()
                status = self.app.status_var.get()
                self.assertIn("Next one", status)
                following = [t for t in self.app.tasks if not t.done][0]
                phrase = humanize_date(following.scheduled_for)
                self.assertIn(phrase, status)
                # The tell: a preposition immediately before "in 9 days".
                self.assertNotIn(f"for {phrase}", status)
                self.assertNotIn(f"on {phrase}", status)
                for scold in ("overdue", "missed", "forgot", "still", "again"):
                    self.assertNotIn(scold, status.lower())

    def test_the_editor_round_trips_a_repeat(self):
        self.capture("bins")
        self.select(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = {
                "title": "bins", "content": "", "tags": [], "first_step": "",
                "kind": "", "scheduled_for": "", "estimate_minutes": 0,
                "repeat": "monthly", "clear_snooze": False,
            }
            self.app.edit_selected_details()
        self.assertEqual(self.app.tasks[0].repeat, "monthly")

    def test_a_repeat_survives_a_save_and_reload(self):
        self._make_repeating(repeat="fortnightly")
        self.app.save_state()
        self.app.tasks = []
        self.app.load_state()
        self.assertEqual(self.app.tasks[0].repeat, "fortnightly")

    # -- how much is on screen at once ---------------------------------
    def _clickable(self):
        """(live, greyed) among everything you could click right now."""
        def walk(w):
            for child in w.winfo_children():
                yield child
                yield from walk(child)

        self.app.update_idletasks()
        live = greyed = 0
        for widget in walk(self.app):
            if not widget.winfo_ismapped():
                continue
            if widget.winfo_class() not in ("TButton", "TCheckbutton",
                                            "TCombobox", "TSpinbox"):
                continue
            if "disabled" in widget.state():
                greyed += 1
            else:
                live += 1
        return live, greyed

    def test_task_actions_are_not_offered_while_they_cannot_act(self):
        """First run offered 32 clickable things and about half could do
        nothing: every task action needs a selection, and there were no
        tasks. A control that looks live and does nothing is a decision that
        pays nothing back."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the dentist")
        self.app.task_list.selection_clear(0, tk.END)
        self.app.on_task_selection_changed()
        for button in self.app.needs_selection:
            self.assertIn("disabled", button.state(), button.cget("text"))

        self.select(0)
        self.app.on_task_selection_changed()   # what a real click fires
        for button in self.app.needs_selection:
            self.assertNotIn("disabled", button.state(), button.cget("text"))

    def test_selecting_a_task_lights_up_every_action_at_once(self):
        """The correlation is the lesson: it teaches what they apply to
        without a sentence and without a failed click."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the dentist")
        self.app.task_list.selection_clear(0, tk.END)
        self.app.on_task_selection_changed()
        before_live, before_grey = self._clickable()
        self.select(0)
        self.app.on_task_selection_changed()
        after_live, after_grey = self._clickable()
        self.assertGreater(after_live, before_live)
        self.assertLess(after_grey, before_grey)

    def test_greying_never_moves_anything(self):
        """Greyed rather than hidden, deliberately: a row that changes shape
        under you is its own kind of overwhelming."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the dentist")
        self.app.update()
        places = {b: (b.winfo_rootx(), b.winfo_rooty(), b.winfo_width())
                  for b in self.app.needs_selection}
        self.select(0)
        self.app.on_task_selection_changed()
        self.app.update()
        for button, before in places.items():
            self.assertEqual(
                (button.winfo_rootx(), button.winfo_rooty(), button.winfo_width()),
                before, button.cget("text"))

    def test_selecting_from_code_lights_the_actions_too(self):
        """The "booked for today" banner selects a row without any click, so
        the widget's own callback never fires. The actions stayed greyed over
        a visibly selected task."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        from cognitive_offload.models import today_iso

        self.capture("call the dentist")
        self.app.tasks[0].scheduled_for = today_iso()
        self.app.refresh_tasks()
        self.app.task_list.selection_clear(0, tk.END)
        self.app.on_task_selection_changed()
        self.app.show_booked()
        self.assertTrue(self.app.task_list.curselection())
        for button in self.app.needs_selection:
            self.assertNotIn("disabled", button.state(), button.cget("text"))

    def test_clear_done_waits_for_something_to_clear(self):
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the dentist")
        self.assertIn("disabled", self.app.needs_done_task.state())
        self.select(0)
        self.app.on_task_selection_changed()
        self.app.toggle_selected_done()
        self.assertNotIn("disabled", self.app.needs_done_task.state())

    def test_the_actions_come_back_when_the_selection_goes(self):
        """Greyed state must follow the list, not just the click that set
        it — deleting the selected task leaves nothing selected."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the dentist")
        self.select(0)
        self.app.delete_selected()
        for button in self.app.needs_selection:
            self.assertIn("disabled", button.state(), button.cget("text"))

    # -- handing a task to an agent ------------------------------------
    def _hand_off(self, target="claude_desktop", note="Draft it.", days=3):
        """Drive the real command with the two dialogs stubbed out."""
        with mock.patch("cognitive_offload.app.HandoffDialog") as ask, \
             mock.patch("cognitive_offload.app.HandoffDoneDialog") as done:
            ask.return_value.show.return_value = {
                "target": target, "follow_up_days": days, "note": note}
            self.app.hand_off_matrix_task("delegate")
        return done

    def test_handing_over_writes_a_brief_and_marks_the_task_waiting(self):
        """Delegate is the quadrant people cannot use because "give it to
        someone else" needs a someone else. This is that someone — and the
        task must not vanish into it."""
        root = Path(self._tmp.name) / "handoff"
        self.app.config_store.handoff_root = root
        self.app.matrix.create("delegate", "Chase the insurance claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        self._hand_off(note="Draft the appeal letter.")

        written = list(root.rglob("*.md")) + list(root.rglob("*.json"))
        self.assertEqual(len(written), 1, written)
        text = written[0].read_text(encoding="utf-8")
        self.assertIn("Chase the insurance claim", text)
        self.assertIn("Draft the appeal letter.", text)

        [task] = self.app.matrix.list("delegate")
        self.assertTrue(task.is_waiting())
        self.assertEqual(task.handed_to, "Claude Desktop")
        # The half that stops a handoff becoming a disappearance.
        self.assertTrue(task.follow_up_on > task.handed_off_on)

    def test_a_task_out_with_an_agent_stays_visibly_out_after_send_to_tasks(self):
        """The bug this pass exists for. Hand a task to an agent, press
        Send to tasks, and it used to arrive in the main list with no waiting
        state, no badge and no subtitle — while the brief sat on disk and the
        agent may have been working on it. That is the disappearance the
        handoff exists to prevent, walked in through a different door."""
        self.app.config_store.handoff_root = Path(self._tmp.name) / "handoff"
        self.app.matrix.create("delegate", "Chase the insurance claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        self._hand_off()

        self.app.matrix_lists["delegate"].selection_set(0)
        self.app.matrix_to_tasks("delegate")

        [task] = self.app.tasks
        self.assertTrue(task.is_waiting(), "the handoff was forgotten")
        self.assertEqual(task.handed_to, "Claude Desktop")
        self.assertTrue(task.follow_up_on)
        # ...and it must be visible, not merely stored.
        from cognitive_offload.rows import task_row

        row = task_row(task)
        self.assertIn("Waiting on Claude Desktop", row.subtitle)
        self.assertIn("waiting", [b.text for b in row.badges])

    def test_taking_a_handoff_back_from_the_task_editor(self):
        self.app.config_store.handoff_root = Path(self._tmp.name) / "handoff"
        self.app.matrix.create("delegate", "Chase the claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        self._hand_off()
        self.app.matrix_lists["delegate"].selection_set(0)
        self.app.matrix_to_tasks("delegate")
        self.assertTrue(self.app.tasks[0].is_waiting())

        self.select(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = {
                "title": "Chase the claim", "content": "", "tags": [],
                "first_step": "", "kind": "", "scheduled_for": "",
                "estimate_minutes": 0, "repeat": "", "clear_snooze": False,
                "take_back": True,
            }
            self.app.edit_selected_details()
        self.assertFalse(self.app.tasks[0].is_waiting())
        # ...and it is a suggestion again, since it is yours now.
        from cognitive_offload.queries import rank_for_starting

        self.assertIn(self.app.tasks[0], rank_for_starting(self.app.tasks))

    def test_a_repeat_survives_a_trip_through_the_matrix(self):
        """The row said "every week"; a round trip through the matrix used to
        take that away with nothing to connect the loss to the action."""
        self.capture("Take the bins out")
        self.app.tasks[0].repeat = "weekly"
        self.app.refresh_tasks()
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as q:
            q.return_value.show.return_value = "do_first"
            self.app.send_selected_to_matrix()
        self.assertEqual(self.app.matrix.list("do_first")[0].repeat, "weekly")
        self.app.matrix_lists["do_first"].selection_set(0)
        self.app.matrix_to_tasks("do_first")
        self.assertEqual(self.app.tasks[0].repeat, "weekly")
        # ...and it still books the next round when finished.
        before = len(self.app.tasks)
        self.select(0)
        self.app.toggle_selected_done()
        self.assertEqual(len(self.app.tasks), before + 1)

    def test_a_snooze_survives_a_trip_through_the_matrix(self):
        """"Not today" is about the task, not about where you filed it."""
        self.capture("Ring the dentist")
        self.app.tasks[0].snoozed_until = "2099-01-01"
        self.app.refresh_tasks()
        self.select(0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as q:
            q.return_value.show.return_value = "schedule"
            self.app.send_selected_to_matrix()
        self.app.matrix_lists["schedule"].selection_set(0)
        self.app.matrix_to_tasks("schedule")
        self.assertEqual(self.app.tasks[0].snoozed_until, "2099-01-01")

    def test_the_command_reaches_the_clipboard(self):
        root = Path(self._tmp.name) / "handoff"
        self.app.config_store.handoff_root = root
        self.app.matrix.create("delegate", "Ring the vet")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        done = self._hand_off(target="codex")
        command = self.app.clipboard_get()
        self.assertIn("codex", command)
        # The dialog is told the same command the clipboard got: two copies
        # of one string is exactly the drift this branch exists to stop.
        self.assertEqual(done.call_args.args[-1], command)
        self.assertIn(str(list(root.rglob("*.md"))[0]), command)

    def test_ctrl_z_takes_back_a_handoff(self):
        """Every other matrix command is undoable; this one moves a task out
        of your own hands, so it had better be."""
        self.app.config_store.handoff_root = Path(self._tmp.name) / "handoff"
        self.app.matrix.create("delegate", "Chase the claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        self._hand_off()
        self.assertTrue(self.app.matrix.list("delegate")[0].is_waiting())
        self.app.undo()
        self.assertFalse(self.app.matrix.list("delegate")[0].is_waiting())

    def test_taking_it_back_is_never_described_as_a_failure(self):
        self.app.config_store.handoff_root = Path(self._tmp.name) / "handoff"
        self.app.matrix.create("delegate", "Chase the claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        self._hand_off()
        self.app.matrix_lists["delegate"].selection_set(0)
        self.app.take_back_matrix_task("delegate")
        self.assertFalse(self.app.matrix.list("delegate")[0].is_waiting())
        status = self.app.status_var.get().lower()
        for scold in ("fail", "gave up", "abandon", "never"):
            self.assertNotIn(scold, status)

    def test_an_unwritable_handoff_folder_changes_nothing(self):
        """The task must not be marked as waiting for an agent that was
        never given anything."""
        self.app.config_store.handoff_root = Path(self._tmp.name) / "handoff"
        self.app.matrix.create("delegate", "Chase the claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        with mock.patch("cognitive_offload.handoff.write_brief",
                        side_effect=OSError("read-only file system")), \
             mock.patch("cognitive_offload.app.messagebox.showerror") as err:
            self._hand_off()
        self.assertTrue(err.called)
        self.assertFalse(self.app.matrix.list("delegate")[0].is_waiting())

    def test_cancelling_the_handoff_dialog_writes_nothing(self):
        root = Path(self._tmp.name) / "handoff"
        self.app.config_store.handoff_root = root
        self.app.matrix.create("delegate", "Chase the claim")
        self.app.refresh_matrix()
        self.app.matrix_lists["delegate"].selection_set(0)
        # HandoffDoneDialog is patched too even though a cancel must never
        # reach it: unpatched, a regression here opens a real modal and the
        # test HANGS instead of failing. A regression should fail.
        with mock.patch("cognitive_offload.app.HandoffDialog") as ask, \
             mock.patch("cognitive_offload.app.HandoffDoneDialog") as done:
            ask.return_value.show.return_value = None
            self.app.hand_off_matrix_task("delegate")
        self.assertFalse(done.called, "a cancelled handoff still reported one")
        self.assertFalse(root.exists())
        self.assertFalse(self.app.matrix.list("delegate")[0].is_waiting())

    def test_matrix_add_save_failure_reports_and_stays_clean(self):
        from cognitive_offload.storage import StorageError
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor, \
             mock.patch.object(self.app.matrix, "create",
                               side_effect=StorageError("folder gone")), \
             mock.patch("cognitive_offload.app.messagebox.showerror") as err:
            editor.return_value.show.return_value = self._matrix_dialog_result()
            self.app.add_matrix_task("do_first")
        err.assert_called_once()
        self.assertEqual(self.app.matrix.list("do_first"), [])

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

    def test_the_quadrant_tabs_and_counts_reach_the_widgets(self):
        """The wiring, not the wording: presenter decides, the tab shows it.

        Nothing asserted this before — the tab text and the count label
        were computed inside refresh_matrix and read by no test, so the
        pairing of quadrant to notebook index was free to drift silently.
        """
        from cognitive_offload.storage import CATEGORY_KEYS
        self.app.matrix.create("do_first", "one", "")
        self.app.matrix.create("do_first", "two", "")
        self.app.matrix.create("delegate", "hand off", "")
        self.app.refresh_matrix()

        # By index, not by membership: the tab must be paired with its own
        # quadrant. An earlier version of this test used assertIn over the
        # whole list and passed happily with the order reversed, which is
        # the one thing it was written to catch.
        tabs = [self.app.matrix_notebook.tab(i, "text")
                for i in range(len(CATEGORY_KEYS))]
        self.assertEqual(tabs, ["Do First (2)", "Schedule",
                                "Delegate (1)", "Eliminate"])
        # The empty ones carry no number at all, not "(0)".
        self.assertNotIn("(0)", "".join(tabs))
        self.assertEqual(
            self.app.matrix_count_labels["do_first"].cget("text"), "2 tasks")
        self.assertEqual(
            self.app.matrix_count_labels["schedule"].cget("text"), "0 tasks")

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
        # With a task on the list, so the filter row has something to filter:
        # on an empty list it stays down when calm mode lifts, which is its
        # own rule and not this test's subject.
        self.capture("something to filter")
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

        # Not "the clock is not 00:00" — that passes for a clock frozen at
        # its starting time, which is exactly what a broken sync produces.
        # Assert the pop-out AGREES with the main window, across several
        # ticks, so a change on either side is caught.
        seen = []
        for _ in range(3):
            self.app._timer_deadline -= 60
            self.app._tick_timer()
            seen.append((self.app.timer_label.cget("text"), window.time_var.get()))
        for main, popped in seen:
            self.assertEqual(popped, main,
                             "the pop-out drifted from the main window's clock")
        self.assertEqual([m for m, _p in seen], ["14:00", "13:00", "12:00"],
                         "and the clock has to actually count down")

        window.close()
        self.assertIsNone(self.app._focus_window)
        self.app.pause_timer()

    def test_a_long_task_wraps_in_the_list_instead_of_being_cut_off(self):
        """The list used to show about 78 characters of a 137-character task.

        Not scrolled off and not shortened with an ellipsis — simply
        absent, ending mid-word, behind a scrollbar that only goes down.
        Two tasks that begin the same way looked identical. The capture
        box invites exactly this ("Anything in your head — it does not
        have to be tidy"), so the list has to be able to show it.
        """
        import tkinter.font as tkfont

        long_text = ("ring the council about the bins and the recycling they "
                     "keep missing on odd weeks, ask for the reference and "
                     "whether it affects the charge")
        self.capture("short one")
        self.capture(long_text)
        self.app.deiconify()  # withdrawn windows don't lay out
        self.app.refresh_tasks()
        self.app.update()
        self.app.update_idletasks()

        rows = {self.app.task_list._pool[i]["title"].cget("text"):
                self.app.task_list._pool[i]["title"] for i in range(2)}
        long_label, short_label = rows[long_text], rows["short one"]

        def lines(label):
            metrics = tkfont.Font(font=label.cget("font")).metrics("linespace")
            return max(1, round(label.winfo_reqheight() / metrics))

        viewport = self.app.task_list.canvas.winfo_width()
        self.assertGreater(lines(long_label), 1,
                           "the long task still sits on one clipped line")
        self.assertLessEqual(long_label.winfo_reqwidth(), viewport,
                             "the title is wider than the list can show")
        # Short rows must not pay for it.
        self.assertEqual(lines(short_label), 1)

    def test_a_long_task_keeps_every_word_however_many_badges_it_carries(self):
        """The v3.41.0 fix came back through the badge strip.

        The badges sit on the title's own line and are 0-430px wide depending
        on the row, but one wraplength was applied to the whole pool. So the
        title wrapped at the full row width, was given only what the badges
        left, and Tk clipped the difference — a Label wraps at ``wraplength``
        and does not re-wrap to fit its allocation. Measured before: the same
        129-character title showed 100% of itself on a bare row and **41%**
        on a fully-badged one, ending mid-word.
        """
        from cognitive_offload.models import today_iso

        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        long_text = ("call the insurance company back about the rejected claim "
                     "and ask for a supervisor and get the appeal deadline in "
                     "writing this time")
        self.capture(long_text)
        task = self.app.tasks[0]
        task.first_step = "ring them"
        task.kind = "admin"
        task.scheduled_for = today_iso()
        task.estimate_minutes = 10
        task.repeat = "weekly"
        task.pinned = True
        self.app.refresh_tasks()
        self.app.update()

        title = self.app.task_list._pool[0]["title"]
        self.assertGreater(len(title.cget("text")), 100, "fixture got shorter")
        # Every word fits in the room it was given: a Label that needs more
        # width than it has is showing less text than it holds.
        self.assertLessEqual(
            title.winfo_reqwidth(), title.winfo_width(),
            "the title is clipped — it wrapped wider than the badges left it",
        )

    def test_badges_take_their_room_from_the_title_not_from_the_words(self):
        """The same task, with and without badges: the badged one must take
        MORE lines, never fewer words."""
        import tkinter.font as tkfont

        from cognitive_offload.models import today_iso

        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        long_text = ("call the insurance company back about the rejected claim "
                     "and ask for a supervisor")
        self.capture(long_text)   # bare
        self.capture(long_text)   # will carry badges
        badged = self.app.tasks[0]
        badged.kind = "admin"
        badged.scheduled_for = today_iso()
        badged.estimate_minutes = 10
        badged.pinned = True
        self.app.refresh_tasks()
        self.app.update()

        def lines(label):
            metrics = tkfont.Font(font=label.cget("font")).metrics("linespace")
            return max(1, round(label.winfo_reqheight() / metrics))

        titles = [self.app.task_list._pool[i]["title"] for i in range(2)]
        wide, narrow = max(titles, key=lambda w: w.cget("wraplength")), \
                       min(titles, key=lambda w: w.cget("wraplength"))
        self.assertLess(narrow.cget("wraplength"), wide.cget("wraplength"),
                        "the badged row got the same wrap width as the bare one")
        self.assertGreaterEqual(lines(narrow), lines(wide),
                                "the badged row lost lines instead of gaining them")
        for label in titles:
            self.assertLessEqual(label.winfo_reqwidth(), label.winfo_width(),
                                 label.cget("text")[:40])

    def test_the_wrap_width_is_right_before_any_further_layout_pass(self):
        """Measured the moment the row is applied, with no update() after.

        The badge strip's *requested* width is correct as soon as its badges
        are set; its allocated width is still 1 until the geometry manager
        runs. Reading the allocated one leaves the title ~187px too wide, and
        a later <Configure> quietly re-fits it — so a test that calls
        update() first sees the corrected value and passes over the bug.
        Nothing guarantees that <Configure> arrives: it only fires when the
        geometry actually changes.
        """
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the insurance company back about the rejected claim")
        self.app.update()          # settle the list once, deliberately
        task = self.app.tasks[0]
        task.kind = "admin"
        task.pinned = True
        task.estimate_minutes = 10
        self.app.refresh_tasks()   # ...and now NO update(): read the decision

        cell = self.app.task_list._pool[0]
        expected = (self.app.task_list._wrap_at
                    - cell["badges"].winfo_reqwidth()
                    - self.app.task_list.BADGE_GAP)
        self.assertEqual(cell["title"].cget("wraplength"), expected,
                         "the title was wrapped against the badge strip's "
                         "allocated width instead of its requested width")

    def _badged_long_task(self):
        from cognitive_offload.models import today_iso

        long_text = ("call the insurance company back about the rejected claim "
                     "and ask for a supervisor and get the appeal deadline in "
                     "writing this time")
        self.capture(long_text)
        task = self.app.tasks[0]
        task.first_step = "ring them"
        task.kind = "admin"
        task.scheduled_for = today_iso()
        task.estimate_minutes = 10
        task.repeat = "weekly"
        task.pinned = True
        task.tags = ["health", "phone"]
        return task

    def test_one_task_is_never_taller_than_the_list_it_sits_in(self):
        """Making badges narrow the title instead of clipping it left nothing
        bounding how narrow. At the app's own minimum width a fully-badged
        long task rendered ELEVEN lines — 224px, taller than the whole visible
        list, filling it and pushing every other task out of view."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self._badged_long_task()
        for width in (1600, 1400, 1240, 1120):
            with self.subTest(window=width):
                self.app.geometry(f"{width}x880")
                self.app.update_idletasks()
                self.app.refresh_tasks()
                self.app.update()
                frame = self.app.task_list._pool[0]["frame"]
                self.assertLessEqual(
                    frame.winfo_height(), 140,
                    f"one row is {frame.winfo_height()}px at {width}px wide",
                )

    def test_the_badges_give_way_before_the_title_does(self):
        """The strip is the compressible thing — it already had a "+k" pill,
        keyed on a count when width is what binds."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        task = self._badged_long_task()
        self.app.geometry("1120x880")
        self.app.update_idletasks()
        self.app.refresh_tasks()
        self.app.update()
        cell = self.app.task_list._pool[0]
        from cognitive_offload.rows import task_row

        wanted = len(task_row(task).badges)
        drawn = cell["badges"]._fit()
        self.assertLess(len(drawn), wanted, "nothing was collapsed")
        self.assertTrue(drawn[-1].text.startswith("+"),
                        f"no overflow pill: {[b.text for b in drawn]}")

    def test_a_short_title_keeps_the_badges_it_has_room_for(self):
        """Capping by share alone collapsed "Bins" — a four-letter task —
        down to four badges on a wide screen, for no reason at all."""
        from cognitive_offload.models import today_iso
        from cognitive_offload.rows import task_row

        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("Bins")
        task = self.app.tasks[0]
        task.first_step = "x"
        task.kind = "admin"
        task.scheduled_for = today_iso()
        task.estimate_minutes = 10
        task.repeat = "weekly"
        task.pinned = True
        self.app.geometry("1240x880")
        self.app.update_idletasks()
        self.app.refresh_tasks()
        self.app.update()
        cell = self.app.task_list._pool[0]
        self.assertEqual(len(cell["badges"]._fit()), len(task_row(task).badges),
                         "a short title lost badges it had room for")

    def test_the_strip_never_draws_wider_than_its_budget(self):
        """Including the overflow pill: room is reserved for "+k" before the
        last badge is accepted, so the marker can never bust the budget."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self._badged_long_task()
        for width in (1600, 1240, 1120):
            with self.subTest(window=width):
                self.app.geometry(f"{width}x880")
                self.app.update_idletasks()
                self.app.refresh_tasks()
                self.app.update()
                strip = self.app.task_list._pool[0]["badges"]
                self.assertLessEqual(strip.winfo_reqwidth(), strip.max_width,
                                     [b.text for b in strip._fit()])

    def test_resizing_alone_re_budgets_the_badges(self):
        """Dragging the window narrower fires a Configure event and nothing
        else — no refresh, so `_apply_row` never runs. The titles were
        re-wrapped on that path but the badge budgets were not, so the strip
        kept the room it was given at the old width and squeezed the title.
        """
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self._badged_long_task()
        self.app.geometry("1600x880")
        self.app.update_idletasks()
        self.app.refresh_tasks()
        self.app.update()
        wide = self.app.task_list._pool[0]["badges"].max_width

        # Resize only. No refresh_tasks() — this is what a drag does.
        self.app.geometry("1120x880")
        self.app.update()
        cell = self.app.task_list._pool[0]
        self.assertLess(cell["badges"].max_width, wide,
                        "the badge budget did not follow the window in")
        self.assertLessEqual(cell["badges"].winfo_reqwidth(),
                             cell["badges"].max_width)
        self.assertLessEqual(cell["title"].winfo_reqwidth(),
                             cell["title"].winfo_width(),
                             "the title was clipped after a bare resize")

    def test_the_title_font_is_built_against_this_app_not_a_global_default(self):
        """A Font belongs to the Tk instance that made it.

        With no ``root=`` it binds to ``tkinter._default_root``, which is a
        *different* app in a process that built two and ``None`` once the
        first is destroyed. The badge measurement thirty lines above has
        carried this guard from the start; the title measurement was added
        without it.
        """
        from tkinter import font as tkfont

        listing = self.app.task_list
        listing._title_fonts.clear()
        listing._title_widths.clear()
        with mock.patch.object(tkfont, "Font", wraps=tkfont.Font) as made:
            listing._title_width("Chase the insurance claim", bold=True)
        self.assertTrue(made.called)
        self.assertIn("root", made.call_args.kwargs,
                      "the font was built against the global default root")

    def test_a_font_it_cannot_build_lays_out_roughly_rather_than_crashing(self):
        """This measurement only decides how wide a badge strip may be. Dying
        on a refresh is far too large a consequence for that; the badge
        measurement estimates instead, and so does this one now."""
        from tkinter import font as tkfont

        listing = self.app.task_list
        listing._title_fonts.clear()
        listing._title_widths.clear()
        title = "Chase the insurance claim appeal before Friday"
        with mock.patch.object(tkfont, "Font",
                               side_effect=RuntimeError("no default root")):
            estimated = listing._title_width(title, bold=True)
        self.assertGreater(estimated, 0)
        # Erring wide is the safe direction: the budget then falls back to
        # the share rather than squeezing the title on a guess.
        self.assertGreaterEqual(estimated, len(title) * 7)

    def test_a_measurement_that_fails_midway_is_also_survivable(self):
        listing = self.app.task_list
        listing._title_fonts.clear()
        listing._title_widths.clear()
        listing._title_width("warm the cache", bold=False)
        broken = mock.Mock()
        broken.measure.side_effect = tk.TclError("font is gone")
        listing._title_fonts["normal"] = broken
        self.assertGreater(listing._title_width("a fresh title", bold=False), 0)

    def test_the_title_is_still_never_clipped_at_any_width(self):
        """The v3.49.0 promise must survive the fix to its own side effect."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self._badged_long_task()
        for width in (1600, 1400, 1240, 1120):
            with self.subTest(window=width):
                self.app.geometry(f"{width}x880")
                self.app.update_idletasks()
                self.app.refresh_tasks()
                self.app.update()
                title = self.app.task_list._pool[0]["title"]
                self.assertLessEqual(title.winfo_reqwidth(), title.winfo_width())

    def test_a_row_that_loses_its_badges_gets_its_width_back(self):
        """Rows come from a pool, so a cell that carried badges is reused for
        one that does not."""
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        self.capture("call the insurance company back about the rejected claim")
        task = self.app.tasks[0]
        task.kind = "admin"
        task.pinned = True
        task.estimate_minutes = 10
        self.app.refresh_tasks()
        self.app.update()
        narrow = self.app.task_list._pool[0]["title"].cget("wraplength")

        task.kind = ""
        task.pinned = False
        task.estimate_minutes = 0
        task.first_step = ""
        self.app.refresh_tasks()
        self.app.update()
        # The FULL room, not merely "wider than before": a sticky
        # has-badges flag still subtracts the empty strip's 1px and passed a
        # greater-than check while being wrong.
        self.assertEqual(self.app.task_list._pool[0]["title"].cget("wraplength"),
                         self.app.task_list._wrap_at,
                         "a row with no badges did not get the full width back")
        self.assertGreater(self.app.task_list._wrap_at, narrow)

    def test_focus_window_grows_to_keep_its_controls_when_the_title_wraps(self):
        """A four-line title used to push Pause and the Park row clean off
        the fixed-height window — the re-fit only ran while the title was
        still empty."""
        self.capture("call the insurance company back about the rejected "
                     "claim, ask for a supervisor, and get the appeal "
                     "deadline in writing this time")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "warmup_done": 0,
                "first_step": "find the claim number in the shared folder",
            }
            self.app.focus_on_selected()
        self.app.open_focus_window()
        window = self.app._focus_window
        window.deiconify()  # withdrawn windows don't lay out
        self.app._tick_timer()
        window.update()
        # The window IS the clipping parent here: everything must end
        # above its bottom edge.
        bottom = window.winfo_rooty() + window.winfo_height()
        for control in (window.pause_button, window.park_entry):
            control_bottom = control.winfo_rooty() + control.winfo_height()
            self.assertLessEqual(control_bottom, bottom, str(control))
        window.close()
        self.app.pause_timer()

    def test_focus_window_height_is_stable_across_ticks(self):
        """The every-tick re-fit must be a no-op when nothing changed."""
        self.capture("short")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app.open_focus_window()
        window = self.app._focus_window
        window.deiconify()
        self.app._tick_timer()
        window.update()
        first = window.winfo_height()
        for _ in range(5):
            self.app._tick_timer()
            window.update()
        self.assertEqual(window.winfo_height(), first)
        window.close()
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

    def test_the_done_today_pill_is_gone_entirely_when_zero(self):
        """An empty tinted pill is a 0-done scoreboard in disguise."""
        self.capture("open thing")
        self.assertEqual(self.app.today_label.winfo_manager(), "")
        self.select(0)
        self.app.toggle_selected_done()
        self.assertEqual(self.app.today_label.winfo_manager(), "pack")
        self.assertIn("1 done today", self.app.today_var.get())
        self.app.undo()
        self.assertEqual(self.app.today_label.winfo_manager(), "")

    def test_the_ends_line_says_tomorrow_across_midnight(self):
        """The wiring: a rolled-over block reaches the label.

        This used to also assert that an un-patched 15-minute block says
        nothing about tomorrow — which is false in the last quarter hour of
        any day, so the suite failed for anyone running it near midnight.
        The same-day case is now covered properly in test_presenter, against
        a fixed clock, which is what timer_view taking `now` was for.
        """
        self.app.start_timer(minutes=15)
        # Pretend the block ends 26 hours out so the date rolls over.
        with mock.patch.object(self.app.timer, "remaining", 26 * 3600):
            self.app._update_timer_label()
        self.assertIn("tomorrow", self.app.finish_var.get())
        self.app.pause_timer()

    def test_a_refused_start_keeps_the_running_blocks_parked_thoughts(self):
        self.app.start_timer(minutes=15)
        self.app.park_thought("mid-block thought")
        self.app.start_timer(minutes=20)  # refused: already running
        self.assertEqual(self.app._parked_this_session, ["mid-block thought"])
        self.app.pause_timer()

    def test_the_window_floor_is_a_size_the_app_works_at(self):
        from cognitive_offload.theme import px
        # Measured against the layout rather than chosen: nothing overflows
        # its card down to 1100x670 in the worst legitimate state, so this
        # keeps 20-30px of clearance. The old floor was 1160x790, and 790 is
        # taller than a 768px laptop screen — which is the bug.
        #
        # Compared through window_bounds rather than against the two numbers
        # directly, because the floor is deliberately clamped by the screen:
        # on a 1024x768 display the app is RIGHT to ask for 1008x696, and a
        # hard-coded pair turns that correct behaviour into a red suite. The
        # designed floor is still asserted — it is the first argument.
        designed = (px(self.app, 1120), px(self.app, 700))
        _opening, expected = self._sized_for(self.app.winfo_screenwidth(),
                                             self.app.winfo_screenheight())
        self.assertEqual(self.app.wm_minsize(), expected)
        self.assertEqual(
            tuple(min(d, e) for d, e in zip(designed, expected)), expected,
            "the floor is no longer the designed one, capped by the screen")

    def _sized_for(self, width, height):
        """(opening size, floor) for a screen of this size.

        Against the pure helper rather than a real window: a withdrawn
        window reports 1x1 for its geometry, and standing up one X display
        per resolution is what made this bug invisible for so long.
        """
        from cognitive_offload.app import window_bounds
        from cognitive_offload.theme import px

        return window_bounds(
            screen=(width, height),
            design=(px(self.app, 1240), px(self.app, 880)),
            floor=(px(self.app, 1120), px(self.app, 700)),
            margin=(px(self.app, 16), px(self.app, 72)),
        )

    def test_the_window_never_opens_bigger_than_the_screen(self):
        """It opened 880 tall on a 768px laptop — 113px past the bottom edge,
        taking the whole toolbar, the whole footer, the status bar and the
        only route into the week review with it."""
        for width, height in ((1024, 768), (1280, 720), (1366, 768),
                              (1440, 900), (1920, 1080)):
            with self.subTest(screen=f"{width}x{height}"):
                (opened_w, opened_h), _floor = self._sized_for(width, height)
                self.assertLessEqual(opened_h, height,
                                     "opens taller than the screen")
                self.assertLessEqual(opened_w, width,
                                     "opens wider than the screen")

    def test_the_floor_is_never_taller_than_the_screen_can_show(self):
        """The half that made the old bug unrecoverable: the floor was 790,
        which is itself taller than a 768px screen, so dragging the corner
        stopped while the window was still overflowing."""
        for width, height in ((1024, 768), (1280, 720), (1366, 768)):
            with self.subTest(screen=f"{width}x{height}"):
                _opened, (floor_w, floor_h) = self._sized_for(width, height)
                self.assertLess(floor_h, height,
                                "cannot be resized to fit the screen")
                self.assertLess(floor_w, width)

    def test_a_big_screen_still_gets_the_designed_size(self):
        """Fitting small screens must not shrink the app for everyone else."""
        from cognitive_offload.theme import px

        (opened_w, opened_h), floor = self._sized_for(1920, 1080)
        self.assertEqual((opened_w, opened_h),
                         (px(self.app, 1240), px(self.app, 880)))
        self.assertEqual(floor, (px(self.app, 1120), px(self.app, 700)))

    def test_the_room_left_for_a_taskbar_is_real(self):
        """A window that fills the screen exactly still hides its footer under
        the taskbar, and the footer is where Undo lives.

        Asserted unconditionally. The first version of this test only checked
        when `opened_h < height`, which is false in precisely the case that
        matters — a margin of zero makes the window exactly screen-height and
        skipped the assertion instead of failing it.
        """
        for width, height in ((1024, 768), (1280, 720), (1366, 768)):
            with self.subTest(screen=f"{width}x{height}"):
                (_opened_w, opened_h), _floor = self._sized_for(width, height)
                self.assertLessEqual(
                    opened_h, height - 40,
                    "no room left for a taskbar: the footer, and Undo with "
                    "it, would sit underneath it",
                )

    def test_the_window_really_takes_the_size_it_worked_out(self):
        """Drives the real window, not just the arithmetic.

        `window_bounds` being correct says nothing about whether
        `_fit_to_screen` uses its answer — replacing the geometry call with
        the old unclamped constant left every other test in this group
        passing, which is the wrong-layer trap one level up.
        """
        self.app.deiconify()
        self.addCleanup(self.app.withdraw)
        for width, height in ((1366, 768), (1280, 720)):
            with self.subTest(screen=f"{width}x{height}"):
                with mock.patch.object(type(self.app), "winfo_screenwidth",
                                       return_value=width), \
                     mock.patch.object(type(self.app), "winfo_screenheight",
                                       return_value=height):
                    self.app._fit_to_screen()
                self.app.update()
                self.assertLessEqual(self.app.winfo_height(), height - 40)
                self.assertLessEqual(self.app.winfo_width(), width)
                floor_w, floor_h = self.app.wm_minsize()
                self.assertLess(floor_h, height)
                self.assertLess(floor_w, width)
        self.app._fit_to_screen()  # put it back for the rest of the suite

    def test_px_carries_design_pixels_to_the_screens_dpi(self):
        from cognitive_offload.theme import px
        screen = mock.Mock()
        screen.winfo_fpixels.return_value = 96.0
        self.assertEqual(px(screen, 320), 320)   # identity at design DPI
        screen.winfo_fpixels.return_value = 192.0
        self.assertEqual(px(screen, 320), 640)   # doubles on a 2x panel
        self.assertEqual(px(screen, 1160), 2320)
        screen.winfo_fpixels.return_value = 72.0
        self.assertEqual(px(screen, 320), 320)   # never shrinks below design

    def test_the_floor_state_still_shows_tasks_and_search(self):
        """At the app's own minimum, with a session running, the list and
        the search entry must both still exist — they didn't."""
        self.app.deiconify()  # withdrawn windows don't lay out
        self.app.geometry("1120x700")  # the floor
        # The worst legitimate state, not the demo state: a title long
        # enough to wrap in NEXT UP, plus a wrapping first step. Short
        # titles made this test pass while real ones clipped the toolbar.
        self.app.capture_entry.insert(0, "call the insurance company back "
                                         "about the claim they rejected")
        self.app.add_task_from_capture()
        for n in range(3):
            self.app.capture_entry.insert(0, f"task {n}")
            self.app.add_task_from_capture()
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "warmup_done": 0,
                "first_step": "a long first step written out in enough "
                              "detail that the step line wraps as well",
            }
            self.app.focus_on_selected()
        self.app.update()
        self.assertGreater(self.app.task_list.winfo_height(), 50)  # ≥1 row visible
        self.assertGreaterEqual(self.app.search_entry.winfo_width(), 100)
        toolbar = self.app.task_toolbar
        self.assertGreater(toolbar.winfo_height(), 10)
        # Inside its PARENT, not just the window: Tk clips a child to the
        # card, and winfo still reports the assigned position of the
        # invisible part — measuring against the window passes while the
        # toolbar is clipped to nothing (that was this test's first bug).
        card = toolbar.master
        toolbar_bottom = toolbar.winfo_rooty() + toolbar.winfo_height()
        card_bottom = card.winfo_rooty() + card.winfo_height()
        self.assertLessEqual(toolbar_bottom, card_bottom)
        # Width too: ttk's default nine-character button minimum made the
        # seven toolbar buttons request more than the card's width, so
        # "To matrix" and "Clear done" clipped mid-word at the floor.
        self.assertLessEqual(toolbar.winfo_reqwidth(), toolbar.winfo_width())
        card_right = card.winfo_rootx() + card.winfo_width()
        for button in toolbar.grid_slaves():
            button_right = button.winfo_rootx() + button.winfo_width()
            self.assertLessEqual(button_right, card_right, button.cget("text"))
        # The filter row's last control ("Show done") clipped to "Sh" at
        # the old floor — every filter control must end inside the card.
        for control in self.app.filter_row.grid_slaves():
            control_right = control.winfo_rootx() + control.winfo_width()
            self.assertLessEqual(control_right, card_right, str(control))
        self.app.pause_timer()

    def test_exactly_one_extra_badge_is_shown_not_summarised(self):
        self.capture("seven tags")
        self.app.tasks[0].tags = [f"t{n}" for n in range(7)]
        self.app.refresh_tasks()
        self.app.update()
        strip = self.app.task_list._pool[0]["badges"]
        texts = [strip.itemcget(i, "text") for i in strip.find_all()
                 if strip.type(i) == "text"]
        self.assertEqual(len(texts), 7)
        self.assertNotIn("+1", texts)
        self.assertIn("#t6", texts)

    def test_a_tag_flood_cannot_hide_the_title(self):
        """15 tags used to squeeze the title label to zero width."""
        self.capture("the title that matters")
        self.app.tasks[0].tags = [f"tag{n}" for n in range(15)]
        self.app.refresh_tasks()
        self.app.update()
        cell = self.app.task_list._pool[0]
        # The badge strip drew a capped set plus one overflow pill...
        texts = [cell["badges"].itemcget(item, "text")
                 for item in cell["badges"].find_all()
                 if cell["badges"].type(item) == "text"]
        self.assertEqual(len(texts), self.app.task_list._pool[0]["badges"].MAX_BADGES + 1)
        self.assertEqual(texts[-1], "+9")
        # ...and the title still has real width on screen.
        self.assertGreater(cell["title"].winfo_width(), 60)
        self.assertIn("the title that matters", self.visible_texts()[0])

    def test_hover_survives_a_re_render(self):
        self.capture("aaa")
        self.capture("bbb")
        listing = self.app.task_list
        listing._hover(0, True)
        hover_colour = listing._hover_colour()
        self.app.refresh_tasks()
        cell = listing._pool[0]
        self.assertEqual(str(cell["frame"].cget("background")), hover_colour)
        listing._hover(0, False)
        self.app.refresh_tasks()
        self.assertNotEqual(str(cell["frame"].cget("background")), hover_colour)

    def test_typing_in_the_capture_box_never_triggers_task_shortcuts(self):
        """The while-typing guard: capture must never fight your fingers.

        This test used to pass with the guard deleted. It generated its
        keys into a window setUp had withdrawn, so nothing was delivered
        and "nothing happened" was true for the wrong reason — for its
        whole life it could not fail. The window is now mapped, focus is
        waited for, and a probe key is proved to arrive before any
        negative result is believed.

        What it protects is worth the ceremony: typing "Delete the old
        files" into the capture box must not delete the selected task, and
        Ctrl+P/T/Up must not fire mid-word.
        """
        self.capture("precious task")
        self.select(0)
        if not self._really_focus(self.app.capture_entry):
            self.skipTest("could not obtain X focus")
        if not self._assert_key_delivery(self.app.capture_entry):
            self.skipTest("key events are not being delivered")
        # Keys that are destructive shortcuts when the list has focus.
        # The dialogs are patched not to weaken the test — with the guard
        # working none of them is ever reached — but so that a regression
        # FAILS instead of hanging: Ctrl+T opens a modal prompt, and a
        # blocked CI runner is a far worse signal than a red one.
        with mock.patch("cognitive_offload.app.PromptDialog") as prompt, \
                mock.patch("cognitive_offload.app.messagebox"):
            prompt.return_value.show.return_value = None
            for sequence in ("<Delete>", "<Control-p>", "<Control-t>",
                             "<Control-Up>"):
                self.app.capture_entry.event_generate(sequence)
            self.app.update()
        self.assertEqual([t.text for t in self.app.tasks], ["precious task"])
        self.assertEqual(self.app.tasks[0].priority, 0)
        self.assertFalse(self.app.tasks[0].pinned)
        self.assertFalse(prompt.called, "Ctrl+T opened a dialog mid-word")

    def test_opening_a_file_with_unreadable_records_warns_and_blocks(self):
        import json as _json

        outside = Path(self._tmp.name) / "damaged.json"
        outside.write_text(
            _json.dumps({"tasks": [{"text": "ok"}, "junk"], "scratchpad": ""}),
            encoding="utf-8")
        with mock.patch("cognitive_offload.app.filedialog.askopenfilename",
                        return_value=str(outside)), \
                mock.patch("cognitive_offload.app.messagebox.showwarning") as warn:
            self.app.load_state_dialog()
        warn.assert_called_once()
        self.assertTrue(self.app._autosave_blocked)
        self.assertEqual([t.text for t in self.app.tasks], ["ok"])

    def test_show_week_groups_by_day_and_omits_empty_days(self):
        from datetime import date, timedelta

        from cognitive_offload.sessions import FocusSession

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        stale = (date.today() - timedelta(days=10)).isoformat()  # outside the week
        self.app.session_log.sessions = [
            FocusSession(minutes=15, started_at=f"{yesterday} 09:00:00"),
            FocusSession(minutes=30, started_at=f"{yesterday} 11:00:00"),
            FocusSession(minutes=99, started_at=f"{stale} 09:00:00"),
        ]
        self.capture("finished thing")
        self.select(0)
        self.app.toggle_selected_done()  # completed today
        with mock.patch("cognitive_offload.app.WeekReviewDialog") as review:
            self.app.show_week()
        days, total_sessions, total_minutes = review.call_args.args[1:4]
        self.assertEqual(total_sessions, 2)
        self.assertEqual(total_minutes, 45)
        self.assertEqual([d.label for d in days], ["Yesterday", "Today"])
        self.assertEqual(days[0].sessions, 2)
        self.assertEqual(days[1].titles, ["finished thing"])
        self.assertEqual(days[1].sessions, 0)

    def test_a_vanished_matrix_folder_is_named_not_silent(self):
        import shutil as _shutil

        _shutil.rmtree(self.app.matrix.root)
        self.app.refresh_matrix()
        self.assertIn("missing", self.app.status_var.get())
        with mock.patch("cognitive_offload.app.messagebox.showerror"):
            before = sorted(Path(self.app.config_store.db_path).parent.rglob("*.task"))
            self.app.matrix.root.parent  # no-op; keep flow obvious
            try:
                self.app.matrix.create("do_first", "into the void", "")
            except Exception:
                pass
            after = sorted(Path(self.app.config_store.db_path).parent.rglob("*.task"))
        self.assertEqual(before, after)  # nothing forked into a fresh tree

    # -- session rituals -----------------------------------------------
    def test_ladder_edits_and_popout_preference_persist(self):
        self.capture("ritual work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
                "warmup_steps": ["my own step"], "show_warmup": False,
                "popout": True,
            }
            self.app.focus_on_selected()
        self.assertEqual(self.app.config_store.warmup_steps, ["my own step"])
        self.assertFalse(self.app.config_store.show_warmup)
        self.assertTrue(self.app.config_store.popout_on_start)
        # The pop-out opened without a second click.
        self.assertIsNotNone(self.app._focus_window)
        from cognitive_offload.storage import Config
        reloaded = Config(self.app.config_store.path).load()
        self.assertEqual(reloaded.warmup_steps, ["my own step"])
        self.assertTrue(reloaded.popout_on_start)
        self.app._focus_window.close()
        self.app.pause_timer()

    def test_parked_thoughts_reach_the_session_end_dialog(self):
        self.capture("focus work")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app.park_thought("email Dana")
        self.app.park_thought("buy milk")
        self.app._timer_deadline -= 10_000
        with mock.patch("cognitive_offload.app.SessionEndDialog") as ender, \
                mock.patch("cognitive_offload.app.messagebox.askyesno",
                           return_value=False):
            ender.return_value.show.return_value = {"choice": "carry_on",
                                                    "next_step": ""}
            self.app._tick_timer()
            self.assertEqual(ender.call_args.kwargs.get("parked"), 2)
        # A fresh block starts with a clean slate.
        self.app.start_timer(minutes=15)
        with mock.patch("cognitive_offload.app.SessionEndDialog") as ender, \
                mock.patch("cognitive_offload.app.messagebox.askyesno",
                           return_value=False):
            ender.return_value.show.return_value = {"choice": "carry_on",
                                                    "next_step": ""}
            self.app._timer_deadline -= 10_000
            self.app._tick_timer()
            self.assertEqual(ender.call_args.kwargs.get("parked"), 0)

    # -- soft landing / relative dates / snooze exit -------------------
    def test_the_last_two_minutes_announce_a_soft_landing(self):
        self.app.start_timer(minutes=15)
        self.app._timer_deadline = __import__("time").monotonic() + 100
        self.app._tick_timer()
        self.assertIn("stopping point", self.app.finish_var.get())
        self.app.pause_timer()

    def test_mid_block_has_no_landing_chatter(self):
        self.app.start_timer(minutes=15)
        self.app._tick_timer()
        self.assertNotIn("stopping point", self.app.finish_var.get())
        self.assertIn("ends ", self.app.finish_var.get())
        self.app.pause_timer()

    def test_the_pop_out_goes_amber_for_the_landing_and_back(self):
        from cognitive_offload.theme import tokens

        self.app.start_timer(minutes=15)
        self.app.open_focus_window()
        window = self.app._focus_window
        self.app._timer_deadline = __import__("time").monotonic() + 90
        self.app._tick_timer()
        self.assertIn("stopping point", window.step_var.get())
        self.assertEqual(str(window.time_label.cget("foreground")),
                         tokens().warning)
        self.app._timer_deadline = __import__("time").monotonic() + 600
        self.app._tick_timer()
        self.assertNotIn("stopping point", window.step_var.get())
        self.assertEqual(str(window.time_label.cget("foreground")), "")
        window.close()
        self.app.pause_timer()

    def test_booked_badges_speak_in_relative_dates(self):
        from datetime import date, timedelta

        self.capture("future thing")
        self.app.tasks[0].scheduled_for = (date.today() + timedelta(days=1)).isoformat()
        self.app.refresh_tasks()
        self.assertIn("booked tomorrow", self.visible_texts()[0])

    def test_only_a_booking_dated_today_says_today(self):
        """Twelve rows all claiming "today" when two of them are today makes
        the badge carry no information, and the honest response to a badge
        that lies is to disbelieve every one of them."""
        from datetime import date, timedelta
        from cognitive_offload.models import today_iso

        self.capture("booked weeks ago")
        self.capture("booked for today")
        stale = next(t for t in self.app.tasks if t.text == "booked weeks ago")
        stale.scheduled_for = (date.today() - timedelta(days=54)).isoformat()
        now = next(t for t in self.app.tasks if t.text == "booked for today")
        now.scheduled_for = today_iso()
        self.app.refresh_tasks()
        rows = {t.text: self.visible_texts()[i]
                for i, t in enumerate(self.app._visible)}
        self.assertIn("today", rows["booked for today"])
        self.assertNotIn("today", rows["booked weeks ago"])
        # It still says WHEN it was for — a missed booking is a nudge, not
        # a telling-off, and never a bare ISO date.
        self.assertIn("booked", rows["booked weeks ago"])
        self.assertNotIn(stale.scheduled_for, rows["booked weeks ago"])

    def test_the_banner_counts_and_opens_todays_bookings_only(self):
        from datetime import date, timedelta
        from cognitive_offload.models import today_iso

        for text, offset in (("ancient", 60), ("old", 12), ("actually today", 0)):
            self.capture(text)
            task = next(t for t in self.app.tasks if t.text == text)
            task.scheduled_for = (date.today() - timedelta(days=offset)).isoformat()
        self.app.refresh_tasks()
        self.assertIn("1 booked for today", self.app.due_var.get())
        # ...and the click lands on that one, not the oldest.
        self.app.show_booked()
        self.assertIn("actually today", self.app.status_var.get())
        self.assertEqual(today_iso(),
                         self.app.selected_tasks()[0].scheduled_for)

    def test_clearing_a_snooze_from_the_editor(self):
        from datetime import date, timedelta

        self.capture("dreaded thing")
        task = self.app.tasks[0]
        task.snoozed_until = (date.today() + timedelta(days=1)).isoformat()
        self.select(0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as editor:
            editor.return_value.show.return_value = {
                "title": task.text, "content": "", "tags": [], "first_step": "",
                "kind": "", "scheduled_for": "", "estimate_minutes": 0,
                "clear_snooze": True,
            }
            self.app.edit_selected_details()
        self.assertEqual(task.snoozed_until, "")
        self.assertEqual(self.app.next_title_var.get(), "dreaded thing")

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

    def test_reset_keeps_the_minutes_you_actually_did(self):
        """Quitting mid-block already banks them and so does "Done early".
        Reset binning them charged the person who tidied up before
        stopping — on a depleted afternoon, the only person pressing it."""
        self.capture("book the dentist")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        task_id = self.app.tasks[0].id
        self.app._timer_deadline -= 4 * 60
        self.app._tick_timer()
        self.app.reset_timer()
        self.assertEqual(self.app.session_log.minutes_today(), 4)
        [record] = self.app.session_log.sessions
        self.assertEqual(record.task, "book the dentist")
        self.assertEqual(record.task_id, task_id)  # so it warms tomorrow
        self.assertIn("banked", self.app.status_var.get())  # not "Timer reset."

    def test_reset_banks_nothing_when_there_is_nothing_to_bank(self):
        # An untouched timer, a second press, and a break must all stay silent
        # — the rule is "count what happened", never "manufacture a number".
        self.app.reset_timer()
        self.assertEqual(self.app.session_log.sessions, [])
        self.assertIn("Timer reset", self.app.status_var.get())

        self.capture("something")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 3 * 60
        self.app._tick_timer()
        self.app.reset_timer()
        self.app.reset_timer()  # idempotent: bank_early guards on timer.banked
        self.assertEqual(len(self.app.session_log.sessions), 1)

        self.app.start_timer(minutes=5, mode="break")
        self.app._timer_deadline -= 2 * 60
        self.app._tick_timer()
        self.app.reset_timer()
        self.assertEqual(len(self.app.session_log.sessions), 1)  # break: no record

    def test_replacing_a_paused_block_still_banks_its_minutes(self):
        self.capture("the big one")
        self.capture("something smaller")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 25, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 6 * 60
        self.app._tick_timer()
        self.app.pause_timer()  # stopped, thought better of it
        self.select(1)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter, \
             mock.patch("cognitive_offload.app.messagebox.askyesno") as asked:
            starter.return_value.show.return_value = {
                "minutes": 10, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        asked.assert_not_called()  # a pause must not be interrogated
        self.assertEqual(self.app.session_log.minutes_today(), 6)
        self.app.pause_timer()

    def test_next_up_steps_out_of_sight_while_a_block_runs(self):
        """The largest button on the window said "Start this" on a different
        task, sixty seconds into the block you fought to begin."""
        self.capture("the other thing")
        self.capture("the one I chose")
        chosen = next(t for t in self.app.tasks if t.text == "the one I chose")
        self.select(next(i for i, t in enumerate(self.app._visible)
                         if t.id == chosen.id))
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.assertEqual(self.app.next_frame.grid_info(), {})
        # The keyboard path is deliberately untouched: only the soliciting
        # button goes away, not the deliberate keystroke.
        self.assertEqual(self.app.next_title_var.get(), "the other thing")
        # A pause is exactly when "what should I do instead?" is fair.
        self.app.pause_timer()
        self.app.refresh_next_up()
        self.assertNotEqual(self.app.next_frame.grid_info(), {})
        self.app.reset_timer()
        self.assertNotEqual(self.app.next_frame.grid_info(), {})

    def test_next_up_never_pitches_the_task_you_are_focusing_on(self):
        """Mid-session, "what should I start?" is not the thing in progress."""
        self.capture("second string")
        self.capture("the main event")
        main = next(t for t in self.app.tasks if t.text == "the main event")
        main.priority = 1
        self.app.refresh_tasks()
        self.assertEqual(self.app.next_title_var.get(), "the main event")
        self.select(next(i for i, t in enumerate(self.app._visible)
                         if t.id == main.id))
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.assertEqual(self.app.next_title_var.get(), "second string")
        # Paused partway is still an open block — resuming is the plan.
        # (Partway matters: a block paused inside its first second reads
        # remaining == total, which the whole app — bank_early included —
        # treats as "never really started".)
        self.app._timer_deadline -= 300
        self.app._tick_timer()
        self.app.pause_timer()
        self.app.refresh_next_up()
        self.assertEqual(self.app.next_title_var.get(), "second string")
        self.app.reset_timer()

    def test_with_nothing_else_to_suggest_the_box_goes_quiet_mid_session(self):
        self.capture("the only task")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        # Nothing else to offer: quiet, not a pitch to switch tasks.
        self.assertEqual(self.app.next_title_var.get(), "")
        self.assertEqual(self.app.next_frame.grid_info(), {})
        # Reset closes the block; the task is suggestible again.
        self.app.reset_timer()
        self.assertEqual(self.app.next_title_var.get(), "the only task")

    def test_not_that_one_says_so_when_the_session_leaves_one_option(self):
        """Two open tasks, one in-session: the walk has nowhere to go and
        must say so instead of silently doing nothing."""
        self.capture("the alternative")
        self.capture("in progress")
        chosen = next(t for t in self.app.tasks if t.text == "in progress")
        self.select(next(i for i, t in enumerate(self.app._visible)
                         if t.id == chosen.id))
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.assertEqual(self.app.next_title_var.get(), "the alternative")
        self.app.skip_next()
        self.assertEqual(self.app.next_title_var.get(), "the alternative")
        self.assertIn("only thing open", self.app.status_var.get())
        # A third task gives the walk somewhere to go again.
        self.capture("a real alternative")
        before = self.app.next_title_var.get()
        self.app.skip_next()
        after = self.app.next_title_var.get()
        self.assertNotEqual(after, before)
        self.assertIn(after, ("the alternative", "a real alternative"))
        # And never the task the session is on.
        self.assertNotEqual(after, "in progress")
        self.app.pause_timer()

    def test_closing_the_app_mid_block_keeps_the_minutes(self):
        """Closing the lid without ceremony must not erase the evidence."""
        self.capture("long report")
        self.select(0)
        task_id = self.app.tasks[0].id
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 25, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 18 * 60
        self.app._tick_timer()
        log_path = self.app.session_log.path
        self.app.on_close()
        data = json.loads(log_path.read_text())
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["minutes"], 18)
        self.assertEqual(data["sessions"][0]["task_id"], task_id)

    def test_a_cancelled_quit_keeps_the_block_running_and_unbanked(self):
        self.capture("long report")
        self.select(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 25, "first_step": "", "warmup_done": 0,
            }
            self.app.focus_on_selected()
        self.app._timer_deadline -= 5 * 60
        self.app._tick_timer()
        log_path = self.app.session_log.path
        self.app._dirty = True
        with mock.patch.object(self.app, "save_state", return_value=False), \
             mock.patch("cognitive_offload.app.messagebox.askyesnocancel",
                        return_value=None):
            self.app.on_close()
        self.assertTrue(self.app.winfo_exists())  # still here
        self.assertTrue(self.app.timer.open_block)  # block untouched
        self.assertFalse(log_path.exists())  # nothing banked
        self.app.pause_timer()

    def test_closing_during_a_break_records_no_focus_minutes(self):
        self.app.start_timer(minutes=5, mode="break")
        self.app._timer_deadline -= 3 * 60
        self.app._tick_timer()
        log_path = self.app.session_log.path
        self.app.on_close()
        if log_path.exists():
            self.assertEqual(json.loads(log_path.read_text())["sessions"], [])

    def test_the_primary_button_focus_ring_contrasts_with_its_fill(self):
        """t.ring is the primary fill's own hex in the light theme, so an
        inherited focus ring was invisible exactly on the buttons that
        start things."""
        style = ttk.Style(self.app)
        for _ in range(2):  # light, then dark
            for name in ("Default.TButton", "SmDefault.TButton"):
                ring = style.lookup(name, "focuscolor")
                fill = style.lookup(name, "background")
                self.assertTrue(ring, name)
                self.assertNotEqual(ring, fill, name)
            self.app.toggle_theme()

    def test_a_checked_checkbox_is_visibly_different_from_unchecked(self):
        """The clam engine fills the box with indicatorbackground; without
        a selected mapping the tick was white on a white box."""
        style = ttk.Style(self.app)
        for name in ("TCheckbutton", "Card.TCheckbutton"):
            mapping = dict()
            spec = style.map(name, "indicatorbackground")
            for entry in spec:
                *states, colour = entry
                mapping[tuple(states)] = colour
            self.assertIn(("selected",), mapping, name)
            resting = style.lookup(name, "indicatorbackground")
            self.assertNotEqual(mapping[("selected",)], resting, name)

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
        # "1 task", not "1 task(s)" — the status bar speaks one way now.
        self.assertIn("Pinned 1 task to the top.", self.app.status_var.get())
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

    def _replace_question(self, seconds_in):
        """What you are asked when starting a block over a running one."""
        self.capture("the one I am on")
        self.capture("the one I want")
        old = next(t for t in self.app.tasks if t.text == "the one I am on")
        new = next(t for t in self.app.tasks if t.text == "the one I want")
        with mock.patch("cognitive_offload.app.StartFocusDialog") as starter:
            starter.return_value.show.return_value = {
                "minutes": 15, "first_step": "", "warmup_done": 0,
            }
            self.app.begin_focus(old)
        self.app._timer_deadline -= seconds_in
        self.app._tick_timer()
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=False) as ask:
            self.app.begin_focus(new)
        self.addCleanup(self.app.pause_timer)
        return ask.call_args.args[1]

    def test_replacing_a_block_no_longer_says_the_minutes_are_dropped(self):
        """The question contradicted the code twelve lines below it.

        Replacing a block banks its minutes — "Drop it" told the person they
        were about to lose the work they managed, which is the fear that
        keeps someone pinned in a block they cannot work in.
        """
        question = self._replace_question(seconds_in=300)
        self.assertNotIn("Drop it", question)
        self.assertIn("kept, not lost", question)
        self.assertIn("5 minutes into", question)

    def test_the_number_asked_about_is_the_number_that_gets_banked(self):
        """A promise about "those minutes" must name the right figure.

        Floor division said "0 minutes" for a block the timer would still
        bank one minute of.
        """
        question = self._replace_question(seconds_in=20)
        self.assertIn("1 minute into", question)
        self.assertNotIn("0 minute", question)

    def test_the_question_and_the_log_agree_on_a_part_minute(self):
        """The promise, at a length where rounding rules actually differ.

        Both existing checks use 300s and 20s. Five minutes is 300 seconds
        exactly, where `round` and floor division give the same answer — so
        swapping one for the other changed nothing any test could see, and
        the number in the question was free to drift away from the number
        in the log. That drift is the defect this promise was written for,
        in the other direction.

        342s is 5.7 minutes: `round` says 6, floor says 5. The assertion is
        that the two sides AGREE, not that either equals 6 — the promise is
        the agreement, and pinning the arithmetic would just re-state the
        implementation.
        """
        question = self._replace_question(seconds_in=342)
        asked = int(re.search(r"You are (\d+) minute", question).group(1))

        # What the timer would actually bank for the same block.
        from cognitive_offload.timer import FocusTimer
        clock = FocusTimer()
        clock.total = self.app._timer_total
        clock.remaining = self.app._timer_total - 342
        clock.running = True
        _mode, banked = clock.bank_early(fallback_minutes=5)

        self.assertEqual(asked, banked,
                         "the question named a different number from the log")
        self.assertEqual(asked, 6, "5.7 minutes rounds to 6, it does not floor to 5")

    def test_declining_the_replacement_leaves_the_block_running(self):
        """So "kept either way" is true on both branches, not just one."""
        self._replace_question(seconds_in=300)
        self.assertTrue(self.app._timer_running)
        self.assertEqual(self.app.session_log.count_today(), 0)

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
        # The card no longer claims a task is in progress. What it says
        # instead depends on whether there is anything to remember: with a
        # session just banked it is the resume line, and with nothing it is
        # the idle caption. Both are "not focused on anything".
        caption = self.app.focus_task_var.get()
        self.assertTrue(caption == self.app.IDLE_CAPTION
                        or caption.startswith("Last time:"), caption)

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

    def test_a_filter_that_empties_the_list_says_the_work_is_still_there(self):
        """The end of the wire: presenter decides, the empty label shows it.

        Left alone, an empty list told you to take the win and stop while
        three tasks sat behind a search term you had forgotten. The app's
        promise is that you can put something down and it will be there.
        """
        for text in ("email the landlord", "book dentist", "file the tax thing"):
            self.capture(text)
        self.app.search_var.set("budget")
        self.app.refresh_tasks()

        self.assertEqual(self.app.task_list.size(), 0)
        shown = self.app.task_list._empty_label.cget("text")
        self.assertEqual(
            shown, "3 tasks still here — the filters above are hiding them.")
        self.assertTrue(self.app.task_list._empty_label.winfo_manager(),
                        "the message has to actually be on screen")
        self.assertEqual(len(self.app.tasks), 3, "and nothing was lost")

    def test_clearing_the_filter_restores_the_ordinary_empty_message(self):
        """It has to go back, or the reassurance becomes the new wrong text."""
        self.capture("something")
        self.app.search_var.set("no match")
        self.app.refresh_tasks()
        self.assertIn("still here", self.app.task_list._empty_label.cget("text"))
        self.app.clear_search()
        self.app.refresh_tasks()
        self.assertEqual(self.app.task_list.size(), 1)
        self.assertEqual(self.app.task_list._empty_label.cget("text"),
                         "Nothing here. Capture a thought above — "
                         "or take the win and stop.")

    def test_everything_done_and_hidden_is_still_told_to_take_the_win(self):
        """The case that must not change: nothing outstanding is a real win."""
        self.capture("a")
        self.capture("b")
        self.select(0, 1)  # both at once: marking done re-sorts the list
        self.app.toggle_selected_done()
        self.app.show_done_var.set(False)
        self.app.refresh_tasks()
        self.assertEqual(self.app.task_list.size(), 0)
        self.assertIn("take the win and stop",
                      self.app.task_list._empty_label.cget("text"))

    def test_the_folder_labels_and_the_counts_line_reach_the_screen(self):
        """Three labels the controller writes that no test used to read.

        The "which folder am I in" label is one this branch already spent a
        commit on; nothing guarded it. Checked here rather than assumed,
        because a label whose variable quietly stops being updated looks
        exactly like a label that is correct.
        """
        self.capture("one")
        self.capture("two")
        self.select(0)
        self.app.toggle_selected_done()
        self.app.refresh_all()
        self.assertEqual(self.app.counts_var.get(), "1 open · 1 done")
        self.assertIn(self.app.state_store.path.name, self.app.path_var.get())
        self.assertTrue(self.app.matrix_path_var.get(),
                        "the matrix tab's folder label must say something")

    def test_finish_time_is_shown_while_running_and_cleared_when_not(self):
        """Whether the line appears at all — not what it says.

        The " tomorrow" suffix is optional here on purpose. This assertion
        used to be anchored without it, so the suite failed for anyone
        running it between 23:50 and midnight, when a ten-minute block
        genuinely does end tomorrow. That is the same wall-clock assumption
        already fixed in test_the_ends_line_says_tomorrow_across_midnight,
        pointing the other way. Both halves of the suffix are pinned
        against a fixed clock in test_presenter; this one only cares that
        a running block shows a time and a paused one shows nothing.
        """
        self.app.start_timer(minutes=10)
        self.assertRegex(self.app.finish_var.get(),
                         r"^ends \d{2}:\d{2}( tomorrow)?$")
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

    # -- the matrix keeps its own promises about Ctrl+Z ------------------
    def _matrix_select(self, category, *indices):
        listing = self.app.matrix_lists[category]
        listing.selection_clear(0, tk.END)
        for index in indices:
            listing.selection_set(index)

    def _delete_selected_matrix(self, category):
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=True):
            self.app.delete_matrix_tasks(category)

    def test_every_matrix_command_registers_an_undo(self):
        """The README promises this; this is the fact behind the promise.

        Prose cannot be pinned the way strings can, so pin the property it
        describes instead. A sixth matrix command added without undo would
        make the README's safety claim wrong again, silently — that is
        exactly how it went wrong the first time — and this notices.
        """
        editor = {"title": "t", "content": "", "first_step": "",
                  "kind": "", "scheduled_for": ""}
        depth = lambda: len(self.app._undo_stack._entries)  # noqa: E731

        def run(label, command, **patches):
            self.app.matrix.create("do_first", f"seed for {label}", "")
            self.app.refresh_matrix()
            self._matrix_select("do_first", 0)
            before = depth()
            with contextlib.ExitStack() as stack:
                for target, value in patches.items():
                    patched = stack.enter_context(
                        mock.patch(f"cognitive_offload.app.{target}"))
                    if target == "messagebox":
                        patched.askyesno.return_value = value
                    else:
                        patched.return_value.show.return_value = value
                command()
            self.assertEqual(depth(), before + 1,
                             f"{label} left the undo stack untouched")
            self.assertIsNotNone(self.app._undo_stack._entries[-1].restore,
                                 f"{label} pushed an entry that undoes nothing")

        run("add", lambda: self.app.add_matrix_task("do_first"),
            TaskEditorDialog=editor)
        run("edit", lambda: self.app.edit_matrix_task("do_first"),
            TaskEditorDialog=editor)
        run("move", lambda: self.app.move_matrix_tasks("do_first"),
            QuadrantDialog="eliminate")
        run("book", lambda: self.app.book_matrix_time("do_first"),
            PromptDialog="tomorrow")
        run("delete", lambda: self.app.delete_matrix_tasks("do_first"),
            messagebox=True)

    def test_deleting_one_matrix_task_no_longer_asks(self):
        """The guard's only justification went away when undo arrived.

        The task list has always confirmed for a batch and not for one,
        because Ctrl+Z covers the single case. The matrix asked every time
        — correct while it had no undo, pure friction once it did.
        """
        self.app.matrix.create("do_first", "just this one", "")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0)
        with mock.patch("cognitive_offload.app.messagebox.askyesno") as ask:
            self.app.delete_matrix_tasks("do_first")
            ask.assert_not_called()
        self.assertEqual(self.app.matrix.list("do_first"), [])
        self.assertIn("Ctrl+Z", self.app.status_var.get())
        self.app.undo()
        self.assertEqual([t.title for t in self.app.matrix.list("do_first")],
                         ["just this one"])

    def test_deleting_several_matrix_tasks_still_asks(self):
        for title in ("one", "two", "three"):
            self.app.matrix.create("do_first", title, "")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0, 1, 2)
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=False) as ask:
            self.app.delete_matrix_tasks("do_first")
            ask.assert_called_once()
            self.assertIn("3 tasks", ask.call_args.args[1])
        self.assertEqual(len(self.app.matrix.list("do_first")), 3,
                         "declining must delete nothing")

    def test_undo_brings_a_deleted_matrix_task_back(self):
        self.app.matrix.create("do_first", "matters a lot", "the details")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0)
        self._delete_selected_matrix("do_first")
        self.assertEqual(self.app.matrix.list("do_first"), [])

        self.app.undo()
        restored = self.app.matrix.list("do_first")
        self.assertEqual([t.title for t in restored], ["matters a lot"])
        self.assertEqual(restored[0].content, "the details")

    def test_undoing_a_matrix_delete_leaves_unrelated_work_alone(self):
        """The other half, and the reason this was worse than "no undo".

        With the matrix silent about undo, Ctrl+Z popped whatever older entry
        was on the stack: the deleted task stayed deleted *and* a change the
        user was not thinking about was reverted instead.
        """
        self.capture("flag this one")
        self.select(0)
        self.app.toggle_selected_priority()
        self.assertTrue(self.app.tasks[0].priority)

        self.app.matrix.create("do_first", "matters a lot", "")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0)
        self._delete_selected_matrix("do_first")

        self.app.undo()
        self.assertEqual([t.title for t in self.app.matrix.list("do_first")],
                         ["matters a lot"])
        self.assertTrue(self.app.tasks[0].priority, "the flag was not the target")
        self.assertIn("matrix", self.app.status_var.get())

    def test_the_deleted_status_only_promises_undo_when_it_happened(self):
        self.app.matrix.create("do_first", "gone", "")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0)
        self._delete_selected_matrix("do_first")
        self.assertIn("Ctrl+Z", self.app.status_var.get())

        self._matrix_select("do_first")  # nothing selected
        self.app.delete_matrix_tasks("do_first")
        self.assertNotIn("Ctrl+Z", self.app.status_var.get())

    def test_undo_removes_a_task_added_to_the_matrix(self):
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as dialog:
            dialog.return_value.show.return_value = {
                "title": "added by hand", "content": "", "first_step": "",
                "kind": "", "scheduled_for": "",
            }
            self.app.add_matrix_task("delegate")
        self.assertEqual(len(self.app.matrix.list("delegate")), 1)
        self.app.undo()
        self.assertEqual(self.app.matrix.list("delegate"), [])

    def test_undo_restores_the_wording_of_an_edited_matrix_task(self):
        """An edit renames the file, so the old copy must know its own path."""
        self.app.matrix.create("schedule", "original title", "original content")
        self.app.refresh_matrix()
        self._matrix_select("schedule", 0)
        with mock.patch("cognitive_offload.app.TaskEditorDialog") as dialog:
            dialog.return_value.show.return_value = {
                "title": "renamed title", "content": "new content",
                "first_step": "", "kind": "", "scheduled_for": "",
            }
            self.app.edit_matrix_task("schedule")
        self.assertEqual([t.title for t in self.app.matrix.list("schedule")],
                         ["renamed title"])

        self.app.undo()
        back = self.app.matrix.list("schedule")
        self.assertEqual([t.title for t in back], ["original title"])
        self.assertEqual(back[0].content, "original content")

    def test_undo_moves_a_task_back_to_the_quadrant_it_came_from(self):
        self.app.matrix.create("do_first", "wandering task", "")
        self.app.refresh_matrix()
        self._matrix_select("do_first", 0)
        with mock.patch("cognitive_offload.app.QuadrantDialog") as dialog:
            dialog.return_value.show.return_value = "eliminate"
            self.app.move_matrix_tasks("do_first")
        self.assertEqual(len(self.app.matrix.list("eliminate")), 1)

        self.app.undo()
        self.assertEqual([t.title for t in self.app.matrix.list("do_first")],
                         ["wandering task"])
        self.assertEqual(self.app.matrix.list("eliminate"), [],
                         "a moved task must not end up in both quadrants")

    def test_undo_clears_a_booking_made_on_a_matrix_task(self):
        self.app.matrix.create("schedule", "needs a date", "")
        self.app.refresh_matrix()
        self._matrix_select("schedule", 0)
        with mock.patch("cognitive_offload.app.PromptDialog") as dialog:
            dialog.return_value.show.return_value = "tomorrow"
            self.app.book_matrix_time("schedule")
        self.assertTrue(self.app.matrix.list("schedule")[0].scheduled_for)

        self.app.undo()
        self.assertEqual(self.app.matrix.list("schedule")[0].scheduled_for, "")

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

    def test_which_finish_message_appears_and_in_what_order(self):
        """Pinned because the wording net cannot see this.

        The snapshot watches which strings EXIST, not which one is shown.
        The rotation index is read after the session count has already been
        incremented, so the first block after opening the app gets the
        SECOND message, not the first. That is easy to "tidy" into an
        off-by-one while every string still exists and the snapshot diff
        comes back empty — silently changing the sentence every person sees
        first, at the most loaded moment the app has.
        """
        seen = []
        for _ in range(4):
            with mock.patch("cognitive_offload.app.messagebox.askyesno",
                            return_value=False):
                self.app._finish_session(10)
            seen.append(self.app.status_var.get())

        self.assertEqual(seen, [
            "10 minutes done — that counts, however it went.",
            "Session finished. The hard part was starting, and you did that.",
            "That's 10 minutes on it. Banked.",
            "10 minutes done — that counts, however it went.",
        ])

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
class FilterRowTests(unittest.TestCase):
    """The filter row appears when there is something to filter.

    On a first run it was six live controls — a search box, Clear, three
    dropdowns and "Show done" — narrowing an empty list, on the screen a new
    person meets first. It obeys the rule calm mode already wrote down:
    never hide a control that is still filtering the list.
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

    def _capture(self, text):
        self.app.capture_entry.insert(0, text)
        self.app.add_task_from_capture()

    def _shown(self):
        return self.app.filter_row.winfo_manager() == "grid"

    def test_an_empty_list_has_nothing_to_filter(self):
        self.assertFalse(self._shown())

    def test_one_task_is_enough_to_bring_it_back(self):
        self._capture("book the dentist")
        self.assertTrue(self._shown())

    def test_it_goes_again_when_the_last_task_goes(self):
        self._capture("book the dentist")
        self.app.task_list.selection_set(0)
        self.app.delete_selected()
        self.assertFalse(self._shown())

    def test_a_search_that_matches_nothing_keeps_the_row(self):
        """The trap. Hide the row here and the list is empty with no visible
        reason why, and no way to undo the reason."""
        self._capture("book the dentist")
        self.app.search_var.set("nothing matches this")
        self.app.refresh_tasks()
        self.assertEqual(self.app.task_list.size(), 0)
        self.assertTrue(self._shown())

    def test_a_filter_on_an_emptied_list_keeps_the_row(self):
        self._capture("book the dentist")
        self.app.search_var.set("dentist")
        self.app.refresh_tasks()
        self.app.task_list.selection_set(0)
        self.app.delete_selected()
        self.assertFalse(self.app.tasks)
        self.assertTrue(self._shown(),
                        "the search term is still set and must stay visible")

    def test_show_done_being_off_counts_as_filtering(self):
        # Not thought of as a filter, but it hides finished tasks, which is
        # narrowing — and it is the one filter you can leave on by accident.
        self.app.show_done_var.set(False)
        self.app.refresh_tasks()
        self.assertTrue(self.app.any_filter_active())
        self.assertTrue(self._shown())

    def test_ctrl_f_pins_it_even_with_nothing_to_search(self):
        """A shortcut whose whole job is to put the cursor in that box must
        not leave the box hidden."""
        self.assertFalse(self._shown())
        self.app.focus_search()
        self.assertTrue(self._shown())

    def test_and_it_stays_pinned(self):
        self.app.focus_search()
        self.app.refresh_tasks()
        self.assertTrue(self._shown())

    def test_calm_mode_still_wins(self):
        self._capture("book the dentist")
        self.assertTrue(self._shown())
        self.app.calm_var.set(True)
        self.app.apply_calm_mode()
        self.assertFalse(self._shown())


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

    def _ask_for(self, uncertain):
        """What the second copy is asked when the lock refuses."""
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import InstanceLock

        app = CognitiveOffloadApp.__new__(CognitiveOffloadApp)
        lock = InstanceLock.__new__(InstanceLock)
        lock.uncertain = uncertain
        lock.acquire = lambda: False
        lock.holder = lambda: "started yesterday"
        lock.takeover = lambda: None
        with mock.patch("cognitive_offload.app.messagebox.askyesno",
                        return_value=False) as ask:
            CognitiveOffloadApp._claim_instance_lock(app, lock)
        return ask.call_args.args

    def test_a_running_copy_is_not_called_safe_to_override(self):
        """The reassurance that made this dangerous.

        While a crashed copy was indistinguishable from a live one, "that is
        safe if the other copy crashed" was kind and usually right. Now a
        crashed copy is claimed silently and never reaches this dialog, so
        offering that line here would be talking someone into the exact
        overwrite the warning is about.
        """
        title, body = self._ask_for(uncertain=False)
        self.assertEqual(title, "Already open")
        self.assertNotIn("crashed", body)
        self.assertNotIn("safe", body)
        self.assertIn("already open — switch to it", body)

    def test_when_the_folder_cannot_tell_the_reassurance_stays(self):
        """It is still true there, so it is still said."""
        title, body = self._ask_for(uncertain=True)
        self.assertEqual(title, "Already running?")
        self.assertIn("cannot say for certain", body)
        self.assertIn("crashed", body)

    def test_both_wordings_still_name_the_holder_and_the_stake(self):
        for uncertain in (True, False):
            _, body = self._ask_for(uncertain=uncertain)
            self.assertIn("started yesterday", body)
            self.assertIn("session folder", body)

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

    def test_a_corrupt_backup_blocks_autosave_and_loses_nothing(self):
        """The deepest branch: data.json AND the .bak are unreadable."""
        app, db = self._make_app(backup="{the bak is broken too", restore=True)
        self.assertTrue(app._autosave_blocked)
        self.assertEqual(app.tasks, [])
        spoiled = self._quarantined(db)
        self.assertEqual(len(spoiled), 1)
        self.assertEqual(spoiled[0].read_text(encoding="utf-8"), "{not json")
        # restore_backup copies, never moves: the bak survives on disk
        # exactly as it was, for the user to inspect.
        self.assertEqual((db / "data.json.bak").read_text(encoding="utf-8"),
                         "{the bak is broken too")

    def test_no_backup_starts_fresh_with_the_bad_file_kept(self):
        app, db = self._make_app(backup=None)
        self.assertEqual(app.tasks, [])
        self.assertFalse(app._autosave_blocked)
        spoiled = self._quarantined(db)
        self.assertEqual(len(spoiled), 1)
        self.assertEqual(spoiled[0].read_text(encoding="utf-8"), "{not json")

    def test_unreadable_records_block_autosave_until_an_explicit_save(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        (root / "db").mkdir(parents=True)
        (root / "db" / "data.json").write_text(
            '{"tasks": [{"text": "good"}, "junk"], "scratchpad": ""}',
            encoding="utf-8")
        with mock.patch("cognitive_offload.app.messagebox.showwarning") as warn:
            app = CognitiveOffloadApp(config=config)
        app.withdraw()
        self.addCleanup(app.destroy)
        warn.assert_called_once()
        self.assertIn("1 task record", warn.call_args.args[1])
        self.assertEqual([t.text for t in app.tasks], ["good"])
        self.assertTrue(app._autosave_blocked)
        # Ctrl+S is the informed consent; autosave resumes after it.
        self.assertTrue(app.save_state(silent=True))
        self.assertFalse(app._autosave_blocked)

    def test_a_future_version_session_is_refused_in_place(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        (root / "db").mkdir(parents=True)
        original = '{"version": 99, "tasks": [{"text": "future"}], "scratchpad": ""}'
        (root / "db" / "data.json").write_text(original, encoding="utf-8")
        with mock.patch("cognitive_offload.app.messagebox.showerror"), \
                mock.patch("cognitive_offload.app.messagebox.askyesno"):
            app = CognitiveOffloadApp(config=config)
        app.withdraw()
        self.addCleanup(app.destroy)
        self.assertTrue(app._autosave_blocked)
        self.assertEqual(app.tasks, [])
        self.assertEqual((root / "db" / "data.json").read_text(encoding="utf-8"),
                         original)
        self.assertEqual(sorted((root / "db").glob("data.json.corrupt-*")), [])

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
