"""The dialogs' collect() methods, which every app test mocks away.

Each dialog is built against a bare withdrawn root and collect() is called
directly - no show(), so no event loop and no modal grab.
"""

import unittest
from unittest import mock

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
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
class DialogCollectTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    # -- task editor ---------------------------------------------------
    def test_every_feel_round_trips(self):
        from cognitive_offload.dialogs import TaskEditorDialog
        from cognitive_offload.models import TASK_KINDS

        for kind in list(TASK_KINDS) + [""]:
            dialog = TaskEditorDialog(self.root, title="t", kind=kind)
            self.assertEqual(dialog.collect()["kind"], kind, kind)
            dialog.destroy()

    def test_an_empty_title_is_refused(self):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="   ")
        with mock.patch("cognitive_offload.dialogs.messagebox.showwarning") as warn:
            self.assertIsNone(dialog.collect())
            warn.assert_called_once()
        dialog.destroy()

    def test_an_unparseable_date_is_refused(self):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="t", scheduled_for="the 32nd")
        with mock.patch("cognitive_offload.dialogs.messagebox.showwarning") as warn:
            self.assertIsNone(dialog.collect())
            warn.assert_called_once()
        dialog.destroy()

    def test_tags_are_split_trimmed_and_lowered(self):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="t", with_tags=True)
        dialog.tags_entry.delete(0, "end")
        dialog.tags_entry.insert(0, " Work , , HOME ")
        self.assertEqual(dialog.collect()["tags"], ["work", "home"])
        dialog.destroy()

    # -- focus dialog --------------------------------------------------
    def test_session_length_is_clamped(self):
        from cognitive_offload.dialogs import StartFocusDialog

        for typed, expected in ((999, 120), (0, 1), (25, 25)):
            dialog = StartFocusDialog(self.root, task_text="t", minutes=15)
            dialog.minutes_var.set(typed)
            self.assertEqual(dialog.collect()["minutes"], expected)
            dialog.destroy()

    def test_warmup_ticks_are_counted(self):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, task_text="t",
                                  warmup_steps=["a", "b", "c"], show_warmup=True)
        dialog.warmup_vars[0].set(True)
        dialog.warmup_vars[2].set(True)
        self.assertEqual(dialog.collect()["warmup_done"], 2)
        dialog.destroy()

    # -- quadrant picker -----------------------------------------------
    def test_a_bogus_initial_quadrant_falls_back(self):
        from cognitive_offload.dialogs import QuadrantDialog

        dialog = QuadrantDialog(self.root, initial="nonsense")
        self.assertEqual(dialog.collect(), "do_first")
        dialog.destroy()

    # -- prompt --------------------------------------------------------
    def test_the_prompt_trims_and_allows_an_empty_answer(self):
        from cognitive_offload.dialogs import PromptDialog

        dialog = PromptDialog(self.root, "t", "p", initial="  spaced  ")
        self.assertEqual(dialog.collect(), "spaced")
        dialog.entry.delete(0, "end")
        self.assertEqual(dialog.collect(), "")  # blank clears a booking
        dialog.destroy()

    # -- the estimate --------------------------------------------------
    def test_the_estimate_collects_as_minutes_and_junk_is_no_guess(self):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="t", estimate_minutes=25)
        self.assertEqual(dialog.collect()["estimate_minutes"], 25)
        dialog.estimate_entry.delete(0, "end")
        self.assertEqual(dialog.collect()["estimate_minutes"], 0)
        dialog.estimate_entry.insert(0, "an hour?")
        self.assertEqual(dialog.collect()["estimate_minutes"], 0)  # never an error
        dialog.estimate_entry.delete(0, "end")
        dialog.estimate_entry.insert(0, "9999")
        self.assertEqual(dialog.collect()["estimate_minutes"], 480)
        dialog.destroy()

    # -- the snooze exit -----------------------------------------------
    def test_a_snoozed_task_offers_a_way_back_into_the_running(self):
        from datetime import date, timedelta

        from cognitive_offload.dialogs import TaskEditorDialog

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        dialog = TaskEditorDialog(self.root, title="t", snoozed_until=tomorrow)
        self.assertIsNotNone(dialog.unsnooze_var)
        self.assertFalse(dialog.collect()["clear_snooze"])
        dialog.unsnooze_var.set(True)
        self.assertTrue(dialog.collect()["clear_snooze"])
        dialog.destroy()

    def test_an_unsnoozed_task_shows_no_snooze_chrome(self):
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="t")
        self.assertIsNone(dialog.unsnooze_var)
        self.assertFalse(dialog.collect()["clear_snooze"])
        dialog.destroy()

    # -- the start picker ----------------------------------------------
    def test_the_picker_follows_its_content_height(self):
        from cognitive_offload.dialogs import StartHereDialog
        from cognitive_offload.models import Task

        tasks = [Task(text=f"t{n}", kind="admin") for n in range(5)]
        dialog = StartHereDialog(self.root, tasks)
        dialog.update_idletasks()
        with_rows = dialog.winfo_reqheight()
        dialog.kind_var.set("creative")  # no creative tasks: empty-state line
        dialog._refresh()
        dialog.update_idletasks()
        self.assertLess(dialog.winfo_reqheight(), with_rows)
        self.assertIn(f"x{dialog.winfo_reqheight()}", dialog.geometry())
        dialog.destroy()

    # -- the start dialog's rituals ------------------------------------
    def test_untouched_ladder_collects_as_none(self):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, warmup_steps=["a", "b", "c"])
        result = dialog.collect()
        self.assertIsNone(result["warmup_steps"])
        self.assertTrue(result["show_warmup"])
        self.assertFalse(result["popout"])
        dialog.destroy()

    def test_edited_ladder_collects_stripped_and_blankless(self):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, warmup_steps=["a", "b", "c"])
        dialog._edit_steps()
        dialog._step_entries[0].delete(0, "end")
        dialog._step_entries[0].insert(0, "  make tea  ")
        dialog._step_entries[1].delete(0, "end")  # blank: dropped
        self.assertEqual(dialog.collect()["warmup_steps"], ["make tea", "c"])
        dialog.destroy()

    def test_clearing_every_step_is_allowed(self):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, warmup_steps=["a"])
        dialog._edit_steps()
        for entry in dialog._step_entries:
            entry.delete(0, "end")
        self.assertEqual(dialog.collect()["warmup_steps"], [])
        dialog.destroy()

    def test_the_popout_and_ladder_prefs_prefill_from_config(self):
        from cognitive_offload.dialogs import StartFocusDialog

        dialog = StartFocusDialog(self.root, warmup_steps=["a"],
                                  show_warmup=False, popout=True)
        result = dialog.collect()
        self.assertFalse(result["show_warmup"])
        self.assertTrue(result["popout"])
        dialog.destroy()

    def test_the_session_end_mentions_parked_thoughts(self):
        from cognitive_offload.dialogs import SessionEndDialog

        from tkinter import ttk

        dialog = SessionEndDialog(self.root, "15 minutes", "a task", parked=2)
        texts = [w.cget("text") for w in dialog.body.winfo_children()
                 if isinstance(w, ttk.Label)]
        self.assertTrue(any("2 thoughts parked" in t for t in texts))
        dialog.destroy()

    # -- session end ---------------------------------------------------
    def test_closing_the_session_dialog_means_carry_on(self):
        from cognitive_offload.dialogs import SessionEndDialog

        dialog = SessionEndDialog(self.root, "15 minutes", "a task")
        dialog.cancel()
        self.assertEqual(dialog.result["choice"], "carry_on")

    def test_closing_it_still_keeps_a_typed_hand_off(self):
        from cognitive_offload.dialogs import SessionEndDialog

        dialog = SessionEndDialog(self.root, "15 minutes", "a task")
        dialog.next_entry.insert(0, "  pick up at the summary  ")
        dialog.cancel()
        self.assertEqual(dialog.result["next_step"], "pick up at the summary")

    def test_each_button_reports_its_choice_and_the_hand_off(self):
        from cognitive_offload.dialogs import SessionEndDialog

        for choice in ("done", "break", "carry_on"):
            dialog = SessionEndDialog(self.root, "15 minutes", "a task",
                                      first_step="the old step")
            dialog.next_entry.insert(0, "the new step")
            dialog._choose(choice)
            self.assertEqual(dialog.result, {"choice": choice, "next_step": "the new step"})

    def _focus(self, dialog, widget):
        """Push X focus onto ``widget`` and wait for it to actually arrive."""
        import time

        dialog.deiconify()
        for _ in range(100):
            dialog.update()
            if dialog.focus_get() is widget:
                return True
            widget.focus_force()
            time.sleep(0.01)
        return False

    def test_enter_in_the_hand_off_field_never_marks_the_task_done(self):
        # Typing a next step and hitting Enter is the most ingrained habit on
        # a text field; it must mean "keep the step, carry on" — not "finished".
        from cognitive_offload.dialogs import SessionEndDialog

        dialog = SessionEndDialog(self.root, "15 minutes", "a task")
        if not self._focus(dialog, dialog.next_entry):
            self.skipTest("could not obtain X focus")
        dialog.next_entry.insert(0, "reread the last paragraph")
        dialog.next_entry.event_generate("<Return>")
        self.root.update()
        self.assertEqual(dialog.result,
                         {"choice": "carry_on", "next_step": "reread the last paragraph"})

    def test_enter_is_bound_to_the_entry_not_the_whole_dialog(self):
        # The old dialog-wide <Return> → "done" binding is the bug: it fired
        # from anywhere, including the hand-off field. Only Escape may live
        # on the toplevel; Enter belongs to the entry, and it keeps the step.
        from cognitive_offload.dialogs import SessionEndDialog

        dialog = SessionEndDialog(self.root, "15 minutes", "a task")
        self.assertNotIn("<Key-Return>", dialog.bind())
        self.assertIn("<Key-Return>", dialog.next_entry.bind())
        dialog.next_entry.insert(0, "reread the last paragraph")
        dialog._keep_step()
        self.assertEqual(dialog.result,
                         {"choice": "carry_on", "next_step": "reread the last paragraph"})

    def test_enter_elsewhere_in_the_dialog_chooses_nothing(self):
        from cognitive_offload.dialogs import SessionEndDialog

        dialog = SessionEndDialog(self.root, "15 minutes", "a task")
        if not self._focus(dialog, dialog):
            self.skipTest("could not obtain X focus")
        dialog.event_generate("<Return>")
        self.root.update()
        self.assertIsNone(dialog.result)
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
