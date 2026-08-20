import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from cognitive_offload.models import today_iso
from cognitive_offload.sessions import MAX_SESSIONS, FocusSession, SessionLog


class SessionLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sessions.json"
        self.log = SessionLog(self.path)

    def test_starts_empty_when_there_is_no_file(self):
        self.assertEqual(self.log.load().sessions, [])
        self.assertEqual(self.log.count_today(), 0)

    def test_record_writes_through_to_disk(self):
        self.log.record(minutes=15, task="write the thing")
        reloaded = SessionLog(self.path).load()
        self.assertEqual(len(reloaded.sessions), 1)
        self.assertEqual(reloaded.sessions[0].minutes, 15)
        self.assertEqual(reloaded.sessions[0].task, "write the thing")

    def test_task_id_round_trips_and_old_records_tolerate_its_absence(self):
        self.log.record(minutes=15, task="thing", task_id="abc123")
        reloaded = SessionLog(self.path).load()
        self.assertEqual(reloaded.sessions[0].task_id, "abc123")
        old = FocusSession.from_dict({"minutes": 10, "task": "older"})
        self.assertEqual(old.task_id, "")
        self.assertNotIn("task_id", FocusSession(minutes=5).to_dict())

    def test_minutes_for_task_sums_only_that_tasks_completed_sessions(self):
        self.log.sessions = [
            FocusSession(minutes=15, task_id="a"),
            FocusSession(minutes=10, task_id="a"),
            FocusSession(minutes=99, task_id="b"),
            FocusSession(minutes=7, task_id="a", completed=False),
        ]
        self.assertEqual(self.log.minutes_for_task("a"), 25)
        self.assertEqual(self.log.minutes_for_task(""), 0)

    def test_recent_task_ids_is_a_two_day_window(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        stale = (date.today() - timedelta(days=5)).isoformat()
        self.log.sessions = [
            FocusSession(minutes=15, task_id="warm-today",
                         logged_at=f"{today} 09:00:00"),
            FocusSession(minutes=15, task_id="warm-yesterday",
                         logged_at=f"{yesterday} 21:00:00"),
            FocusSession(minutes=15, task_id="cold",
                         logged_at=f"{stale} 09:00:00"),
            FocusSession(minutes=15, logged_at=f"{today} 10:00:00"),  # no id
        ]
        self.assertEqual(self.log.recent_task_ids(),
                         {"warm-today", "warm-yesterday"})

    def test_counts_and_minutes_for_today(self):
        self.log.record(minutes=15)
        self.log.record(minutes=25)
        self.assertEqual(self.log.count_today(), 2)
        self.assertEqual(self.log.minutes_today(), 40)

    def test_counts_by_day_fills_quiet_days_with_zero(self):
        self.log.record(minutes=15)
        counts = self.log.counts_by_day(days=5)
        self.assertEqual(len(counts), 5)
        self.assertEqual([c for _day, c in counts[:4]], [0, 0, 0, 0])
        self.assertEqual(counts[-1], (today_iso(), 1))

    def test_counts_by_day_is_oldest_first(self):
        counts = self.log.counts_by_day(days=3)
        days = [day for day, _ in counts]
        self.assertEqual(days, sorted(days))

    def test_older_sessions_are_included_in_the_right_day(self):
        old_day = (date.today() - timedelta(days=3)).isoformat()
        self.log.sessions.append(FocusSession(minutes=15, logged_at=f"{old_day} 09:00:00"))
        counts = dict(self.log.counts_by_day(days=7))
        self.assertEqual(counts[old_day], 1)
        self.assertEqual(counts[today_iso()], 0)

    def test_incomplete_sessions_do_not_count(self):
        self.log.record(minutes=15, completed=False)
        self.assertEqual(self.log.count_today(), 0)

    def test_summary_is_never_scolding(self):
        self.assertEqual(self.log.summary(), "No sessions yet today")
        self.log.record(minutes=15)
        self.assertEqual(self.log.summary(), "1 session today · 15 min")
        self.log.record(minutes=15)
        self.assertEqual(self.log.summary(), "2 sessions today · 30 min")

    def test_corrupt_log_is_ignored_rather_than_fatal(self):
        self.path.write_text("{{{not json", encoding="utf-8")
        self.assertEqual(SessionLog(self.path).load().sessions, [])

    def test_junk_records_are_skipped(self):
        self.path.write_text(
            json.dumps({"sessions": [{"minutes": "abc"}, "nope", {"minutes": 15}]}),
            encoding="utf-8",
        )
        log = SessionLog(self.path).load()
        self.assertEqual([s.minutes for s in log.sessions], [0, 15])

    def test_history_is_capped(self):
        self.log.sessions = [FocusSession(minutes=1) for _ in range(MAX_SESSIONS + 50)]
        self.log.save()
        self.assertEqual(len(SessionLog(self.path).load().sessions), MAX_SESSIONS)

    def test_total_minutes_over_a_window(self):
        old_day = (date.today() - timedelta(days=10)).isoformat()
        self.log.sessions.append(FocusSession(minutes=60, logged_at=f"{old_day} 09:00:00"))
        self.log.record(minutes=15)
        self.assertEqual(self.log.total_minutes(days=7), 15)
        self.assertEqual(self.log.total_minutes(days=14), 75)

    def test_a_second_corruption_gets_its_own_quarantine_file(self):
        self.path.write_bytes(b"\xff garbage one")
        self.log.load()
        self.log.record(minutes=5)  # writes a fresh log
        self.path.write_bytes(b"\xff garbage two")
        SessionLog(self.path).load()
        spoiled = sorted(self.path.parent.glob("sessions.json.corrupt-*"))
        self.assertEqual(len(spoiled), 2)
        contents = {p.read_bytes() for p in spoiled}
        self.assertIn(b"\xff garbage one", contents)
        self.assertIn(b"\xff garbage two", contents)

    def test_a_damaged_log_is_parked_not_overwritten(self):
        self.path.write_text("{{{ not json", encoding="utf-8")
        log = SessionLog(self.path).load()
        self.assertEqual(log.sessions, [])
        spoiled = sorted(self.path.parent.glob("sessions.json.corrupt-*"))
        self.assertEqual(len(spoiled), 1)
        self.assertIn("not json", spoiled[0].read_text(encoding="utf-8"))
        log.record(minutes=15)  # tonight's first session must not destroy it
        self.assertIn("not json", spoiled[0].read_text(encoding="utf-8"))

    def test_set_path_starts_a_fresh_log(self):
        self.log.record(minutes=15)
        self.log.set_path(Path(self._tmp.name) / "other.json")
        self.assertEqual(self.log.sessions, [])


if __name__ == "__main__":
    unittest.main()


class WhatTheStampMeansTests(unittest.TestCase):
    """The timestamp is written when the block ENDS, and now says so.

    `SessionLog.record` is called from `_bank_session`, and nothing has ever
    passed a start time — so the field called ``started_at`` held the finish.
    A name that does not match its value is how the next person writes a real
    bug on top of it.
    """

    def test_a_freshly_recorded_block_is_stamped_now(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            log = SessionLog(Path(tmp) / "sessions.json")
            session = log.record(minutes=15, task="Write the report")
            self.assertEqual(session.day, today_iso())
            self.assertTrue(session.logged_at.startswith(today_iso()))

    def test_files_written_before_the_rename_are_still_read(self):
        """Throwing away a year of momentum over a key name would be its own
        bug: the old key means exactly the same instant."""
        session = FocusSession.from_dict({
            "started_at": "2026-08-19 21:30:00", "minutes": 25,
            "task": "Write the report", "completed": True})
        self.assertEqual(session.logged_at, "2026-08-19 21:30:00")
        self.assertEqual(session.day, "2026-08-19")
        self.assertEqual(session.minutes, 25)

    def test_the_new_key_wins_when_a_file_somehow_has_both(self):
        session = FocusSession.from_dict({
            "logged_at": "2026-08-20 00:05:00",
            "started_at": "2026-08-19 23:50:00", "minutes": 15})
        self.assertEqual(session.day, "2026-08-20")

    def test_what_is_written_now_uses_the_honest_name(self):
        session = FocusSession(minutes=15, logged_at="2026-08-19 21:30:00")
        record = session.to_dict()
        self.assertEqual(record["logged_at"], "2026-08-19 21:30:00")
        self.assertNotIn("started_at", record)

    def test_a_round_trip_keeps_the_day(self):
        session = FocusSession(minutes=15, logged_at="2026-08-19 21:30:00")
        self.assertEqual(FocusSession.from_dict(session.to_dict()).day,
                         session.day)

    def test_a_block_finished_after_midnight_counts_for_the_new_day(self):
        """Unchanged by the rename, and deliberate: someone who stops at 00:05
        seeing "1 session today" is kinder than seeing "none" the moment after
        they stopped."""
        session = FocusSession.from_dict({"logged_at": "2026-08-20 00:05:00",
                                          "minutes": 15})
        self.assertEqual(session.day, "2026-08-20")


class WrongShapedSessionsTests(unittest.TestCase):
    """`{"sessions": 42}` used to raise out of the app's constructor.

    The session log is loaded before the window exists, so a TypeError there
    is not a damaged log — it is an app that does not open.
    """

    SHAPES = {"a number": 42, "a boolean": True, "a string": "nope",
              "a dict": {"a": 1}, "a bare number at the top": 42}

    def _load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            path.write_text(json.dumps(payload))
            return SessionLog(path).load()

    def test_no_shape_raises(self):
        for label, value in self.SHAPES.items():
            with self.subTest(label):
                log = self._load(value if label.endswith("top")
                                 else {"sessions": value})
                self.assertEqual(log.sessions, [])

    def test_a_good_log_still_loads(self):
        log = self._load({"sessions": [
            {"logged_at": "2026-08-19 21:30:00", "minutes": 25, "task": "x"}]})
        self.assertEqual(len(log.sessions), 1)
        self.assertEqual(log.sessions[0].day, "2026-08-19")

    def test_one_bad_record_among_good_ones_is_skipped(self):
        log = self._load({"sessions": [
            {"logged_at": "2026-08-19 21:30:00", "minutes": 25},
            42,
            {"logged_at": "2026-08-19 22:00:00", "minutes": 15}]})
        self.assertEqual([s.minutes for s in log.sessions], [25, 15])


class SweepInterruptedWritesTests(unittest.TestCase):
    """The session log gets the same tidy-up as the state file."""

    def test_its_own_leftovers_go(self):
        import os
        import time

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            log = SessionLog(path)
            log.record(minutes=15, task="Write the report")
            stray = path.with_name(".sessions.json.abc.tmp")
            stray.write_text("half a save")
            when = time.time() - 200_000
            os.utime(stray, (when, when))

            SessionLog(path).load()
            self.assertFalse(stray.exists())
            self.assertEqual(len(SessionLog(path).load().sessions), 1)

    def test_a_missing_file_is_still_only_an_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = SessionLog(Path(tmp) / "never-written.json").load()
            self.assertEqual(log.sessions, [])
