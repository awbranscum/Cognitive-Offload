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


def _descendants(widget):
    """Every widget anywhere inside, at any depth."""
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_descendants(child))
    return found


def _labels(widget):
    """Every ttk.Label anywhere inside a dialog, however it is nested."""
    from tkinter import ttk

    found = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Label):
            found.append(child)
        found.extend(_labels(child))
    return found


def _buttons(widget):
    """Every ttk.Button anywhere inside, at any depth."""
    from tkinter import ttk

    found = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button):
            found.append(child)
        found.extend(_buttons(child))
    return found


@unittest.skipUnless(_display_available(), "tkinter display not available")
class ReachableSaveTests(unittest.TestCase):
    """The way to keep an edit has to be on the screen.

    The task editor opened at a fixed 520px against content that wanted 578
    with a tag row — so Tk laid out everything above and **did not draw Save
    or Cancel at all**. Not scrolled off; not clipped; absent, on a window
    whose only other exit is Escape, which throws the edit away. Measured at
    every height from 520 up, the row first appeared at 668.

    Every optional row added since made it worse, which is why this is pinned
    rather than fixed and forgotten: the next one is somebody typing a field
    into a dialog that already does not fit.
    """

    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _opened(self, **kw):
        """A dialog sized the way show() sizes it, without the modal grab."""
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="Send the passport form", **kw)
        self.addCleanup(dialog.destroy)
        dialog.update_idletasks()
        dialog._fit_to_content()
        dialog.deiconify()
        dialog.update()
        return dialog

    def _fullest(self):
        """Every optional row at once — the case that overflowed first."""
        return self._opened(
            with_tags=True, snoozed_until="2099-01-01",
            content="They said four to six weeks.",
            first_step="find the reference number in the confirmation email")

    def test_save_is_drawn_at_all(self):
        dialog = self._fullest()
        labels = [b.cget("text") for b in _buttons(dialog)]
        self.assertIn("Save", labels)
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        self.assertTrue(save.winfo_ismapped(),
                        "Save exists but Tk never placed it — the row ran off "
                        "the bottom of a window that could not fit it")

    def test_save_is_inside_the_window_it_belongs_to(self):
        dialog = self._fullest()
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        bottom = (save.winfo_rooty() - dialog.winfo_rooty()) + save.winfo_height()
        self.assertLessEqual(bottom, dialog.winfo_height(),
                             "Save is placed past the bottom edge")

    def test_the_editor_is_as_tall_as_what_it_holds(self):
        """The fix, rather than its symptom: a fixed height was always going
        to be wrong for a dialog whose rows come and go."""
        dialog = self._fullest()
        self.assertGreaterEqual(dialog.winfo_height(),
                                min(dialog.winfo_reqheight(),
                                    dialog._max_height))

    def test_a_ceiling_takes_the_room_from_the_notes_not_from_the_buttons(self):
        """On a screen too short for the content something has to give. It
        must be the box you can scroll, not the button you cannot reach."""
        dialog = self._fullest()
        dialog.geometry("520x520")
        dialog.update()
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        self.assertTrue(save.winfo_ismapped())
        self.assertLess(dialog.content_text.winfo_height(), 154,
                        "the notes box did not give up the room")

    def test_every_dialog_with_a_button_row_still_draws_it(self):
        """The row moved out of the body for every dialog, not just this one."""
        from cognitive_offload.dialogs import (HandoffDialog, PromptDialog,
                                               QuadrantDialog, TaskEditorDialog)

        builders = (
            lambda: TaskEditorDialog(self.root, title="t", with_tags=True),
            lambda: PromptDialog(self.root, "Add tag", "Tag name"),
            lambda: QuadrantDialog(self.root, "Send to the matrix"),
            lambda: HandoffDialog(self.root, "Chase the claim"),
        )
        for build in builders:
            dialog = build()
            self.addCleanup(dialog.destroy)
            dialog.update_idletasks()
            dialog._fit_to_content()
            dialog.deiconify()
            dialog.update()
            with self.subTest(dialog=type(dialog).__name__):
                mapped = [b for b in _buttons(dialog) if b.winfo_ismapped()]
                self.assertTrue(mapped, "no button was placed")


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
    def test_the_editor_keeps_an_estimate_typed_with_its_unit(self):
        """"20 mins" used to be saved as no guess at all.

        estimate_minutes = 0 means "no guess", so a discarded estimate is
        indistinguishable from a blank field — and the calibration line
        ("You guessed ~20 min; it took about 35") then never appears, with
        nothing to connect that silence to what was typed.
        """
        from cognitive_offload.dialogs import TaskEditorDialog
        for typed, expected in (("20 mins", 20), ("1h", 60), ("~15", 15)):
            with self.subTest(typed=typed):
                dialog = TaskEditorDialog(self.root, title="a task")
                dialog.estimate_entry.delete(0, "end")
                dialog.estimate_entry.insert(0, typed)
                dialog.ok()
                self.assertEqual(dialog.result["estimate_minutes"], expected)
                dialog.destroy()

    def test_an_unreadable_estimate_stays_a_silent_no_guess(self):
        """The dialog's own decision, kept: "junk is just 'no guess', never
        an error dialog". An optional guess is not worth a modal."""
        from unittest import mock
        from cognitive_offload.dialogs import TaskEditorDialog
        dialog = TaskEditorDialog(self.root, title="a task")
        dialog.estimate_entry.delete(0, "end")
        dialog.estimate_entry.insert(0, "half an hour")
        with mock.patch("cognitive_offload.dialogs.messagebox") as box:
            dialog.ok()
        self.assertEqual(dialog.result["estimate_minutes"], 0)
        self.assertFalse(box.showwarning.called, "no modal over an optional guess")
        dialog.destroy()

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

    def test_the_editor_offers_a_way_out_of_a_handoff_only_while_one_is_on(self):
        """Built like the snooze exit above it: carrying the waiting mark onto
        the main list without this would leave a task marked as out with
        nothing able to clear it."""
        from cognitive_offload.dialogs import TaskEditorDialog

        plain = TaskEditorDialog(self.root, title="t")
        self.assertIsNone(plain.unwait_var)
        self.assertFalse(plain.collect()["take_back"])
        plain.destroy()

        out = TaskEditorDialog(self.root, title="t", handed_to="Codex",
                               follow_up_on="2099-01-01")
        self.assertIsNotNone(out.unwait_var)
        self.assertFalse(out.collect()["take_back"])   # untouched = leave it
        out.unwait_var.set(True)
        self.assertTrue(out.collect()["take_back"])
        # Checkbuttons, not Labels: _labels() would look straight past the
        # only widget this test is about.
        texts = " ".join(
            str(w.cget("text")) for w in _descendants(out)
            if "text" in (w.keys() if hasattr(w, "keys") else ())
        )
        self.assertIn("Codex", texts)
        for scold in ("fail", "gave up", "should have", "never"):
            self.assertNotIn(scold, texts.lower())
        out.destroy()

    # -- the week in evidence ------------------------------------------
    def test_the_week_review_lists_days_titles_and_totals(self):
        from cognitive_offload.dialogs import WeekReviewDialog
        from cognitive_offload.presenter import WeekDay

        days = [
            WeekDay(label="Tuesday", sessions=3, minutes=45,
                    titles=["Book the dentist"]),
            WeekDay(label="Today", sessions=0, minutes=0,
                    titles=["Water the plants"]),
        ]
        dialog = WeekReviewDialog(self.root, days, 3, 45)
        # Walk the whole dialog, not body's direct children: the day list
        # lives inside a scrolled frame now, and what this test cares about
        # is what the dialog SAYS, not which frame holds it.
        texts = [w.cget("text") for w in _labels(dialog)]
        self.assertTrue(any("Tuesday · 3 sessions · 45 min" in t for t in texts))
        self.assertTrue(any("✓ Book the dentist" in t for t in texts))
        # A day with finished tasks but no sessions shows no "0 sessions".
        self.assertTrue(any(t == "Today" for t in texts))
        self.assertFalse(any("0 session" in t for t in texts))
        self.assertTrue(any("3 sessions · 45 minutes across the week" in t
                            for t in texts))
        dialog.destroy()

    def test_a_quiet_week_is_just_a_quiet_week(self):
        from cognitive_offload.dialogs import WeekReviewDialog

        dialog = WeekReviewDialog(self.root, [], 0, 0)
        texts = " ".join(w.cget("text") for w in _labels(dialog))
        self.assertIn("quiet week", texts)
        self.assertNotIn("0 session", texts)
        for scold in ("nothing done", "missed", "only"):
            self.assertNotIn(scold, texts.lower())
        dialog.destroy()

    def test_a_busy_week_keeps_its_total_and_its_way_out_on_screen(self):
        """A week of long titles used to render taller than the screen.

        The window is not resizable and did not scroll, so the totals line
        and the Close button were simply gone — on exactly the week that
        earned them. Escape still worked, but only if you knew.
        """
        from cognitive_offload.dialogs import WeekReviewDialog
        from cognitive_offload.presenter import WeekDay

        long_title = ("call the insurance company back about the rejected "
                      "claim and get the appeal deadline in writing")
        # Deliberately more than a real week: the count has to overflow
        # whatever screen this runs on, or the assertions below pass for
        # the wrong reason on a tall one.
        days = [WeekDay(label=f"Day {n}", sessions=2, minutes=50,
                        titles=[long_title] * 15) for n in range(7)]
        dialog = WeekReviewDialog(self.root, days, 14, 350)
        dialog.update_idletasks()
        dialog._fit_to_content()  # what show() does, without blocking
        dialog.deiconify()
        dialog.update()

        self.assertLessEqual(dialog.winfo_height(),
                             dialog.winfo_screenheight(),
                             "the review is taller than the screen")
        # The dialog IS the clipping parent: both must end above its edge.
        bottom = dialog.winfo_rooty() + dialog.winfo_height()
        for control in (dialog.totals_label, dialog.close_button):
            control_bottom = control.winfo_rooty() + control.winfo_height()
            self.assertLessEqual(control_bottom, bottom, str(control))
        dialog.destroy()

    def test_a_quiet_week_does_not_grow_furniture_it_does_not_need(self):
        """The fix must not cost the ordinary week anything: no scrollbar,
        and no reserved empty space below the last day."""
        from tkinter import ttk

        from cognitive_offload.dialogs import WeekReviewDialog
        from cognitive_offload.presenter import WeekDay

        days = [WeekDay(label="Tuesday", sessions=1, minutes=25,
                        titles=["Book the dentist"])]
        dialog = WeekReviewDialog(self.root, days, 1, 25)
        dialog.update_idletasks()
        dialog._fit_to_content()
        dialog.deiconify()
        dialog.update()
        bars = [w for w in _descendants(dialog) if isinstance(w, ttk.Scrollbar)]
        self.assertTrue(bars, "the scrollbar should exist, just be unpacked")
        self.assertFalse(any(b.winfo_ismapped() for b in bars),
                         "a one-day week showed a scrollbar")
        self.assertLess(dialog.winfo_height(), 400,
                        "a one-day week reserved room it never used")
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
