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
        self.log.sessions.append(FocusSession(minutes=15, started_at=f"{old_day} 09:00:00"))
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
        self.log.sessions.append(FocusSession(minutes=60, started_at=f"{old_day} 09:00:00"))
        self.log.record(minutes=15)
        self.assertEqual(self.log.total_minutes(days=7), 15)
        self.assertEqual(self.log.total_minutes(days=14), 75)

    def test_set_path_starts_a_fresh_log(self):
        self.log.record(minutes=15)
        self.log.set_path(Path(self._tmp.name) / "other.json")
        self.assertEqual(self.log.sessions, [])


if __name__ == "__main__":
    unittest.main()
