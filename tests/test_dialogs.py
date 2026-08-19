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


def _controls(widget):
    """Every widget that a person could need to see or reach."""
    from tkinter import ttk

    kinds = (ttk.Label, ttk.Entry, ttk.Button, ttk.Checkbutton, ttk.Combobox,
             ttk.Radiobutton, tk.Text)
    found = []
    for child in widget.winfo_children():
        if isinstance(child, kinds):
            found.append(child)
        found.extend(_controls(child))
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
            rest_of_plan=["reread the rejection letter", "ring them"],
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

    def test_a_window_too_short_for_the_form_scrolls_instead_of_dropping_it(self):
        """The general form of the bug, not just its first symptom.

        Capping the height fixed Save and left everything else exposed: Tk's
        answer to a window shorter than its content is to stop placing
        widgets, so on the 1366x768 laptop this app supports on purpose the
        editor's ceiling is 614 against content wanting 828 — measured, the
        details box and the tag row were not drawn at 614, and nine controls
        were missing at 520. A ceiling without a scrollbar is a quieter
        version of the bug the ceiling was added to fix.
        """
        for height in (700, 614, 520):
            dialog = self._fullest()
            dialog.geometry(f"520x{height}")
            dialog.update()
            with self.subTest(window=height):
                missing = [type(w).__name__ for w in _controls(dialog)
                           if not w.winfo_ismapped()]
                self.assertEqual(missing, [], "widgets were never placed")
                self.assertTrue(dialog._vbar.winfo_ismapped(),
                                "no scrollbar, so the overflow is unreachable")

    def test_save_does_not_scroll_away_with_the_form(self):
        """The button row has to sit OUTSIDE the scrolling area. Inside it,
        Save is merely somewhere in a long page — which is the same failure
        as not drawing it, dressed up as a feature. Checked at the top of
        the scroll, where a row packed inside the form is furthest away.
        """
        dialog = self._fullest()
        dialog.geometry("520x520")
        dialog.update()
        dialog._canvas.yview_moveto(0)
        dialog.update()
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        self.assertTrue(save.winfo_ismapped())
        top = save.winfo_rooty() - dialog.winfo_rooty()
        self.assertLessEqual(top + save.winfo_height(), dialog.winfo_height())
        self.assertGreater(top, dialog._canvas.winfo_height() - 4,
                           "Save is inside the scrolling form")

    def _wheel_over(self, dialog, widget, up: bool = False):
        """One wheel notch delivered where the widget actually is.

        Root coordinates matter: `_on_wheel` asks `winfo_containing` what is
        under the pointer, and an event generated without them reports a
        position where the widget is not — which is a probe measuring itself
        rather than the app.
        """
        dialog.update()
        widget.event_generate("<Button-4>" if up else "<Button-5>", x=8, y=8,
                              rootx=widget.winfo_rootx() + 8,
                              rooty=widget.winfo_rooty() + 8)
        dialog.update()

    def test_the_wheel_over_the_notes_box_scrolls_the_notes_and_nothing_else(self):
        """A `Text`'s own class binding scrolls it and does NOT return
        "break", so the event carried on to the window binding as well —
        measured, one notch over the notes box moved the text AND slid the
        whole form by the same amount. Scrolling your own notes should not
        move the dialog out from under you."""
        dialog = self._fullest()
        dialog.geometry("520x520")
        dialog.update()
        dialog.content_text.delete("1.0", "end")
        dialog.content_text.insert("1.0", "\n".join(f"line {i}" for i in range(40)))
        # Both at the BOTTOM, then scroll UP: the form could move and the
        # notes box could move, so only the guard decides which does. Parked
        # at the end of the form and scrolling down, the form cannot move
        # anyway and this passed with the guard deleted.
        dialog._canvas.yview_moveto(1.0)
        dialog.content_text.yview_moveto(1.0)
        dialog.update()
        before_form = dialog._canvas.yview()[0]
        before_text = dialog.content_text.yview()[0]
        self.assertGreater(before_form, 0.0, "the form has nowhere to scroll up to")
        self.assertGreater(before_text, 0.0, "the notes box has nowhere to scroll up to")
        self._wheel_over(dialog, dialog.content_text, up=True)
        self.assertEqual(dialog._canvas.yview()[0], before_form,
                         "the form moved as well as the notes box")
        self.assertLess(dialog.content_text.yview()[0], before_text,
                        "the notes box did not scroll")

    def test_the_wheel_anywhere_else_scrolls_the_form(self):
        """The guard must not eat the wheel everywhere. Over anything that
        does not scroll itself, the form is what moves."""
        dialog = self._fullest()
        dialog.geometry("520x520")
        dialog._canvas.yview_moveto(0)
        dialog.update()
        self._wheel_over(dialog, dialog.title_entry)
        self.assertGreater(dialog._canvas.yview()[0], 0.0)

    def test_a_box_with_nothing_to_scroll_does_not_swallow_the_wheel(self):
        """Over a half-empty notes box the wheel should still move the form,
        or it dies in the middle of the dialog for no reason anyone can see."""
        dialog = self._fullest()
        dialog.content_text.delete("1.0", "end")
        dialog.content_text.insert("1.0", "one line")
        dialog.update()
        self.assertFalse(dialog._scrolls_itself(dialog.content_text))
        self.assertFalse(dialog._scrolls_itself(dialog.title_entry))
        self.assertFalse(dialog._scrolls_itself(None))
        dialog.content_text.insert("1.0", "\n".join(f"line {i}" for i in range(40)))
        dialog.update()
        self.assertTrue(dialog._scrolls_itself(dialog.content_text))

    def _with_focus(self, height):
        """A mapped dialog that really receives focus events, or a skip.

        setUp withdraws the root, and a withdrawn window is never given the
        X focus — so `focus_set()` records a preference and no `FocusIn` is
        ever delivered. Every assertion below would then pass by measuring
        nothing. Proven rather than assumed, the same way test_app_ui proves
        a key arrives before concluding anything from one.
        """
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        dialog = self._fullest()
        dialog.geometry(f"520x{height}")
        dialog.update()
        # With no window manager X focus follows the POINTER, so whether
        # these tests run at all came down to where the pointer happened to
        # be sitting: inside the dialog on a 1024x768 display, outside it on
        # a 1600x1200 one, where they silently skipped. Put it somewhere
        # deliberate instead.
        dialog.event_generate("<Motion>", warp=True, x=10, y=10)
        dialog.update()
        seen = []
        dialog.bind("<FocusIn>", lambda e: seen.append(e.widget), add="+")
        dialog.title_entry.focus_set()
        dialog.update()
        dialog.step_entry.focus_set()
        dialog.update()
        if not seen:
            self.skipTest("this display will not deliver focus events")
        return dialog

    def test_tabbing_never_puts_the_cursor_somewhere_you_cannot_see(self):
        """Tab moves focus by widget order, not by what is on screen. On a
        window short enough to scroll it walked straight into the details box
        at y=583 and the tag row at y=732, both below a 614px window — you
        type and nothing appears.

        Measured against the WINDOW rather than the canvas: the button row is
        deliberately outside the scrolling area, and a canvas-relative check
        calls that a failure.
        """
        for height in (614, 520):
            dialog = self._with_focus(height)
            current = dialog.title_entry
            current.focus_set()
            dialog.update()
            with self.subTest(window=height):
                for _ in range(16):
                    nxt = current.tk_focusNext()
                    if nxt is None or nxt is dialog.title_entry:
                        break
                    nxt.focus_set()
                    dialog.update()
                    current = nxt
                    top = nxt.winfo_rooty() - dialog.winfo_rooty()
                    self.assertGreaterEqual(top, 0, f"{nxt} is above the window")
                    self.assertLessEqual(
                        top + nxt.winfo_height(), dialog.winfo_height(),
                        f"{nxt} took focus below the bottom edge")

    def test_focus_scrolls_back_up_as_well_as_down(self):
        """Shift-Tab is a real key. A handler that only ever scrolls forward
        leaves the cursor above the top edge instead of below the bottom.

        Focus has to be moved away and back: re-focusing the widget that
        already holds it generates no event at all, so the obvious version of
        this test asserts against a handler that never ran.
        """
        dialog = self._with_focus(520)
        dialog.tags_entry.focus_set()          # somewhere near the bottom
        dialog.update()
        self.assertGreater(dialog._canvas.canvasy(0), 0,
                           "the form did not scroll down to the tag row")
        dialog.title_entry.focus_set()         # ...and back to the top
        dialog.update()
        top = dialog.title_entry.winfo_rooty() - dialog.winfo_rooty()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + dialog.title_entry.winfo_height(),
                             dialog.winfo_height())

    def test_the_buttons_are_left_where_they_are(self):
        """They sit outside the form on purpose, so nothing about focus or
        the wheel may drag them into the scrolling area."""
        dialog = self._fullest()
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        self.assertFalse(str(save).startswith(f"{dialog.body}."))

    def test_tabbing_to_save_does_not_jerk_the_form(self):
        """Save is not in the form, so nothing about it needs bringing into
        view — and scrolling anyway means the page lurches under you at the
        exact moment you are reaching for the button."""
        dialog = self._with_focus(520)
        dialog.step_entry.focus_set()
        dialog.update()
        parked = dialog._canvas.yview()[0]
        [save] = [b for b in _buttons(dialog) if b.cget("text") == "Save"]
        save.focus_set()
        dialog.update()
        self.assertEqual(dialog._canvas.yview()[0], parked,
                         "focusing Save scrolled the form for no reason")

    def test_the_scrollbar_appears_exactly_when_it_is_needed(self):
        """The other half: a permanent scrollbar on a dialog that fits is a
        control that does nothing, which is what this app spends its effort
        removing.

        Asserted as a *relationship* rather than against a fixed expectation
        per fixture, because whether any given form fits depends on the
        screen the test is running on — the ceiling is 80% of screen height.
        The first version of this test asserted "the fullest dialog shows no
        scrollbar", passed on a 1200px test display and failed on CI's 768px
        one, which was the test being wrong rather than the app.
        """
        for label, build in (("smallest", lambda: self._opened()),
                             ("fullest", self._fullest)):
            dialog = build()
            with self.subTest(dialog=label):
                needed = (dialog.body.winfo_reqheight()
                          > dialog._canvas.winfo_height())
                self.assertEqual(
                    bool(dialog._vbar.winfo_ismapped()), needed,
                    "the scrollbar is showing when there is nothing to scroll "
                    "to, or hiding when there is")

    def test_the_plain_editor_stays_inside_its_height_budget(self):
        """A ratchet, so the dialog cannot balloon unnoticed.

        Measured honestly rather than aspirationally: the plain editor wants
        ~639px, so on the 1366x768 laptop this app supports it is ~25px over
        an 80% ceiling and shows a scrollbar. That is a real limitation and
        it is recorded rather than asserted away — before the form scrolled
        it was much worse, because the same shortfall meant widgets were
        simply not drawn.

        The budget below is the ceiling on a 900px-tall screen, which the
        plain dialog clears comfortably. It exists to fail when someone adds
        another hundred pixels of rows, not to describe today to the pixel.
        """
        dialog = self._opened()
        self.assertLessEqual(
            dialog.body.winfo_reqheight(), int(900 * 0.8),
            "the plain task editor has grown past its height budget — every "
            "screen smaller than a desktop monitor now opens it scrolling")

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

    def test_a_snooze_that_has_run_out_shows_no_chrome_either(self):
        """The checkbox offers to end something that has already ended.

        It reads "Excused from suggestions until <date>", so on a spent date
        it is both an untrue sentence and a control that does nothing. The
        rule was written out inline here for a while and nothing tested it:
        replacing it with `if snoozed_until:` passed the whole suite.
        """
        from datetime import date, timedelta

        from cognitive_offload.dialogs import TaskEditorDialog

        for label, days in (("yesterday", -1), ("today", 0)):
            with self.subTest(label):
                spent = (date.today() + timedelta(days=days)).isoformat()
                dialog = TaskEditorDialog(self.root, title="t",
                                          snoozed_until=spent)
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
            self.assertEqual(dialog.result, {"choice": choice,
                                             "next_step": "the new step",
                                             "step_done": False})

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
                         {"choice": "carry_on",
                          "next_step": "reread the last paragraph",
                          "step_done": False})

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
                         {"choice": "carry_on",
                          "next_step": "reread the last paragraph",
                          "step_done": False})

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
