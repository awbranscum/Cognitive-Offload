"""The focus/break state machine, tested without a display.

These invariants used to live only in tests that drive real Tk widgets and
skip on a headless box. They are the app's honesty guarantees, so they get
to run everywhere.
"""

import unittest

from cognitive_offload.timer import FocusTimer


class FocusTimerTests(unittest.TestCase):
    def test_a_fresh_block_clears_the_previous_blocks_banked_flag(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        self.assertEqual(timer.tick(10_000.0), "focus")  # expires, banks
        self.assertTrue(timer.banked)
        timer.start(10_001.0, minutes=20)
        self.assertFalse(timer.banked)
        self.assertEqual(timer.total, 20 * 60)

    def test_plain_start_after_expiry_is_a_fresh_block(self):
        """The old dead-'Done early' bug, provable headless now."""
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        timer.tick(10_000.0)
        # The plain Start button: no minutes argument.
        timer.start(10_001.0, fallback_minutes=20)
        self.assertFalse(timer.banked)
        self.assertEqual(timer.remaining, 20 * 60)
        # 'Done early' works on this block again — the old bug left banked
        # set and made it a dead button. (A running block banks minimum one
        # minute; that floor is the app's long-standing contract.)
        self.assertEqual(timer.bank_early(fallback_minutes=20), ("focus", 1))

    def test_resume_leaves_a_paused_block_alone(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        timer.tick(300.0)
        timer.pause(300.0)
        self.assertEqual(timer.remaining, 600)
        timer.start(500.0)  # resume: the 200s away do not count against the block
        self.assertEqual(timer.remaining, 600)
        timer.tick(600.0)
        self.assertEqual(timer.remaining, 500)

    def test_start_while_running_is_refused(self):
        timer = FocusTimer()
        self.assertTrue(timer.start(0.0, minutes=15))
        self.assertFalse(timer.start(1.0, minutes=5))
        self.assertEqual(timer.total, 15 * 60)

    def test_pause_never_invents_time(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        timer.pause(400.0)
        self.assertEqual(timer.remaining, 500)
        self.assertFalse(timer.pause(500.0))  # double-pause changes nothing
        self.assertEqual(timer.remaining, 500)

    def test_bank_early_guards_both_ends(self):
        timer = FocusTimer()
        # Never started: nothing to bank.
        self.assertIsNone(timer.bank_early(fallback_minutes=15))
        timer.start(0.0, minutes=15)
        timer.tick(10_000.0)  # natural expiry banked it
        self.assertIsNone(timer.bank_early(fallback_minutes=15))

    def test_bank_early_returns_the_elapsed_minutes(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=20)
        timer.tick(300.0)
        mode, elapsed = timer.bank_early(fallback_minutes=20)
        self.assertEqual((mode, elapsed), ("focus", 5))
        self.assertFalse(timer.running)
        self.assertEqual(timer.remaining, timer.total)

    def test_a_banked_break_reports_break_and_resets_to_focus_length(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=5, mode="break")
        timer.tick(120.0)
        mode, elapsed = timer.bank_early(fallback_minutes=25)
        self.assertEqual(mode, "break")
        self.assertEqual(timer.mode, "focus")
        self.assertEqual(timer.total, 25 * 60)

    def test_the_spinbox_guard_protects_a_paused_block(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        timer.tick(600.0)
        timer.pause(600.0)
        self.assertFalse(timer.set_length_if_idle(16))
        self.assertEqual(timer.remaining, 300)
        timer.reset(16)
        self.assertTrue(timer.set_length_if_idle(16))

    def test_expiry_reports_the_old_mode_exactly_once(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=5, mode="break")
        self.assertEqual(timer.tick(100.0), "")
        self.assertEqual(timer.tick(10_000.0), "break")
        self.assertEqual(timer.mode, "focus")  # never credits a break as focus
        self.assertEqual(timer.tick(10_001.0), "")  # not running: reports nothing

    def test_deferred_finish_holds_at_zero_then_completes(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        self.assertEqual(timer.tick(10_000.0, allow_finish=False), "")
        self.assertTrue(timer.running)
        self.assertEqual(timer.remaining, 0)
        self.assertFalse(timer.banked)
        self.assertEqual(timer.tick(10_001.0), "focus")
        self.assertTrue(timer.banked)

    def test_closing_in_window_edges(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=15)
        timer.tick(900 - 121)
        self.assertFalse(timer.closing_in)  # 121s left: not yet
        timer.tick(900 - 120)
        self.assertTrue(timer.closing_in)   # 120s: the soft landing begins
        timer.tick(900 - 1)
        self.assertTrue(timer.closing_in)   # 1s: still landing
        timer.tick(10_000.0)
        self.assertFalse(timer.closing_in)  # expired: over
        timer.start(20_000.0, minutes=5, mode="break")
        timer.tick(20_000.0 + 5 * 60 - 60)
        self.assertFalse(timer.closing_in)  # breaks never nag

    def test_fraction_and_elapsed_track_the_clock(self):
        timer = FocusTimer()
        timer.start(0.0, minutes=10)
        timer.tick(300.0)
        self.assertEqual(timer.elapsed, 300)
        self.assertAlmostEqual(timer.fraction, 0.5)

    def test_open_block_tracks_the_whole_block_lifecycle(self):
        timer = FocusTimer()
        self.assertFalse(timer.open_block)   # idle: nothing underway
        timer.start(0.0, minutes=10)
        self.assertTrue(timer.open_block)    # running
        timer.pause(300.0)
        self.assertTrue(timer.open_block)    # paused partway: still open
        timer.start(400.0)                   # resume
        timer.tick(10_000.0)
        self.assertFalse(timer.open_block)   # expired naturally: over
        timer.start(20_000.0, minutes=10)
        timer.tick(20_300.0)
        timer.pause(20_300.0)
        timer.bank_early(15)
        self.assertFalse(timer.open_block)   # banked early: over
        timer.start(30_000.0, minutes=10)
        timer.reset(15)
        self.assertFalse(timer.open_block)   # reset: over


if __name__ == "__main__":
    unittest.main()
