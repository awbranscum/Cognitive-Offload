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


if __name__ == "__main__":
    unittest.main()
