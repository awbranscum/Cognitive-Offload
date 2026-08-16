import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cognitive_offload.models import Task
from cognitive_offload.ports import Locations, app_private_locations, desktop_locations
from cognitive_offload.storage import (
    CATEGORY_KEYS,
    Config,
    InstanceLock,
    MatrixStore,
    NotASessionError,
    StateStore,
    StorageError,
    atomic_write_text,
    display_path,
    slugify,
)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class AtomicWriteTests(TempDirTest):
    def test_creates_parent_directories(self):
        target = self.root / "a" / "b" / "file.txt"
        atomic_write_text(target, "hello")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_leaves_no_temp_files_behind(self):
        target = self.root / "file.txt"
        atomic_write_text(target, "one")
        atomic_write_text(target, "two")
        self.assertEqual(target.read_text(encoding="utf-8"), "two")
        self.assertEqual([p.name for p in self.root.iterdir()], ["file.txt"])


class StateStoreTests(TempDirTest):
    def test_missing_file_gives_an_empty_session(self):
        data = StateStore(self.root / "nope.json").load()
        self.assertEqual(data["tasks"], [])
        self.assertEqual(data["scratchpad"], "")

    def test_save_then_load_roundtrip(self):
        store = StateStore(self.root / "data.json")
        tasks = [Task(text="one", priority=1), Task(text="two", tags=["work"])]
        store.save(tasks, "some notes", 40)
        loaded = store.load()
        self.assertEqual([t.text for t in loaded["tasks"]], ["one", "two"])
        self.assertEqual(loaded["tasks"][0].priority, 1)
        self.assertEqual(loaded["scratchpad"], "some notes")
        self.assertEqual(loaded["timer_minutes"], 40)

    def test_corrupt_file_raises_storage_error(self):
        path = self.root / "data.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(StorageError):
            StateStore(path).load()

    def test_legacy_notes_become_the_scratchpad(self):
        path = self.root / "data.json"
        path.write_text(
            json.dumps(
                {
                    "tasks": [{"text": "legacy", "done": False, "created_at": "2024-01-01 00:00:00"}],
                    "notes": [{"text": "remember this", "created_at": "2024-01-01 00:00:00"}],
                    "timer_minutes": 25,
                }
            ),
            encoding="utf-8",
        )
        loaded = StateStore(path).load()
        self.assertEqual(loaded["tasks"][0].text, "legacy")
        self.assertIn("remember this", loaded["scratchpad"])

    def test_save_keeps_one_backup(self):
        store = StateStore(self.root / "data.json")
        store.save([Task(text="first")], "", 25)
        store.save([Task(text="second")], "", 25)
        backup = self.root / "data.json.bak"
        self.assertTrue(backup.exists())
        self.assertIn("first", backup.read_text(encoding="utf-8"))

    def test_unwritable_location_raises_storage_error(self):
        store = StateStore(self.root / "data.json" / "nested.json")
        (self.root / "data.json").write_text("blocking file", encoding="utf-8")
        with self.assertRaises(StorageError):
            store.save([], "", 25)

    def test_bad_records_are_skipped_not_fatal(self):
        path = self.root / "data.json"
        path.write_text(
            json.dumps({"tasks": [{"text": "good"}, "junk", {"text": ""}], "scratchpad": ""}),
            encoding="utf-8",
        )
        loaded = StateStore(path).load()
        self.assertEqual([t.text for t in loaded["tasks"]], ["good"])


class ConfigTests(TempDirTest):
    def test_missing_config_uses_defaults(self):
        config = Config(self.root / "cfg.json").load()
        self.assertEqual(config.focus_minutes, 15)
        self.assertTrue(config.show_done)

    def test_corrupt_config_does_not_raise(self):
        path = self.root / "cfg.json"
        path.write_text("<<<garbage>>>", encoding="utf-8")
        config = Config(path).load()
        self.assertEqual(config.focus_minutes, 15)

    def test_roundtrip(self):
        path = self.root / "cfg.json"
        config = Config(path)
        config.db_path = self.root / "db"
        config.matrix_db_path = self.root / "matrix"
        config.focus_minutes = 50
        config.sort_order = "created"
        config.show_done = False
        config.save()

        reloaded = Config(path).load()
        self.assertEqual(reloaded.db_path, self.root / "db")
        self.assertEqual(reloaded.matrix_db_path, self.root / "matrix")
        self.assertEqual(reloaded.focus_minutes, 50)
        self.assertEqual(reloaded.sort_order, "created")
        self.assertFalse(reloaded.show_done)

    def test_out_of_range_values_are_clamped(self):
        path = self.root / "cfg.json"
        path.write_text(json.dumps({"focus_minutes": 9999, "sort_order": "bogus"}), encoding="utf-8")
        config = Config(path).load()
        self.assertEqual(config.focus_minutes, 120)
        self.assertEqual(config.sort_order, "priority")

    def test_popout_on_start_round_trips_and_defaults_off(self):
        path = self.root / "cfg.json"
        self.assertFalse(Config(path).load().popout_on_start)
        config = Config(path)
        config.popout_on_start = True
        config.save()
        self.assertTrue(Config(path).load().popout_on_start)

    def test_appearance_settings_round_trip(self):
        path = self.root / "cfg.json"
        config = Config(path)
        config.theme = "dark"
        config.calm_mode = True
        config.focus_minutes = 20
        config.save()
        reloaded = Config(path).load()
        self.assertEqual(reloaded.theme, "dark")
        self.assertTrue(reloaded.calm_mode)
        self.assertEqual(reloaded.focus_minutes, 20)

    def test_unknown_theme_falls_back_to_light(self):
        path = self.root / "cfg.json"
        path.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")
        self.assertEqual(Config(path).load().theme, "light")

    def test_sessions_file_follows_db_path(self):
        config = Config(self.root / "cfg.json")
        config.db_path = self.root / "elsewhere"
        self.assertEqual(config.sessions_file, self.root / "elsewhere" / "sessions.json")

    def test_state_file_follows_db_path(self):
        config = Config(self.root / "cfg.json")
        config.db_path = self.root / "elsewhere"
        self.assertEqual(config.state_file, self.root / "elsewhere" / "data.json")


class CompletedLogTests(TempDirTest):
    """The record of what got done, kept so a tidy-up cannot erase the day."""

    def test_round_trips_with_the_session(self):
        store = StateStore(self.root / "data.json")
        log = [{"text": "finished thing", "completed_at": "2026-07-27 10:00:00"}]
        store.save([Task(text="still open")], "", 15, log)
        loaded = store.load()
        self.assertEqual(loaded["completed_log"], log)

    def test_absent_in_older_files(self):
        path = self.root / "data.json"
        path.write_text(json.dumps({"tasks": [], "scratchpad": ""}), encoding="utf-8")
        self.assertEqual(StateStore(path).load()["completed_log"], [])

    def test_junk_entries_are_dropped(self):
        path = self.root / "data.json"
        path.write_text(json.dumps({
            "tasks": [],
            "completed_log": ["nope", {"no_text": 1}, {"text": "kept"}],
        }), encoding="utf-8")
        self.assertEqual(StateStore(path).load()["completed_log"],
                         [{"text": "kept", "completed_at": ""}])

    def test_it_is_capped(self):
        from cognitive_offload.storage import COMPLETED_LOG_LIMIT

        store = StateStore(self.root / "data.json")
        log = [{"text": f"t{i}", "completed_at": "2026-07-27 10:00:00"}
               for i in range(COMPLETED_LOG_LIMIT + 40)]
        store.save([], "", 15, log)
        self.assertEqual(len(store.load()["completed_log"]), COMPLETED_LOG_LIMIT)


class NotASessionFileTests(TempDirTest):
    def test_valid_json_that_is_not_a_session_is_refused(self):
        """Loading it as empty and autosaving over it is how data vanishes."""
        path = self.root / "data.json"
        path.write_text(json.dumps({"unrelated": "document"}), encoding="utf-8")
        with self.assertRaises(StorageError):
            StateStore(path).load()

    def test_a_future_version_file_is_refused_and_untouched(self):
        from cognitive_offload.storage import NewerSessionError

        path = self.root / "data.json"
        original = json.dumps({"version": 99, "tasks": [{"text": "from the future"}],
                               "scratchpad": ""})
        path.write_text(original, encoding="utf-8")
        with self.assertRaises(NewerSessionError):
            StateStore(path).load()
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_unreadable_records_are_counted_not_silent(self):
        path = self.root / "data.json"
        path.write_text(json.dumps({
            "tasks": [{"text": "good"}, "junk", 42, {"text": "also good"}],
            "scratchpad": "",
        }), encoding="utf-8")
        loaded = StateStore(path).load()
        self.assertEqual([t.text for t in loaded["tasks"]], ["good", "also good"])
        self.assertEqual(loaded["dropped"], 2)

    def test_a_clean_file_reports_nothing_dropped(self):
        store = StateStore(self.root / "data.json")
        store.save([Task(text="fine")], "", 15)
        self.assertEqual(store.load()["dropped"], 0)

    def test_a_foreign_file_is_refused_as_not_ours_never_corrupt(self):
        # NotASessionError is the "leave it alone" signal: the file is fine,
        # so the recovery flow must not quarantine or rename it.
        path = self.root / "data.json"
        path.write_text(json.dumps({"unrelated": "document"}), encoding="utf-8")
        with self.assertRaises(NotASessionError):
            StateStore(path).load()
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with self.assertRaises(NotASessionError):
            StateStore(path).load()

    def test_a_session_with_only_a_scratchpad_still_loads(self):
        path = self.root / "data.json"
        path.write_text(json.dumps({"scratchpad": "just notes"}), encoding="utf-8")
        self.assertEqual(StateStore(path).load()["scratchpad"], "just notes")


class BackupPolicyTests(TempDirTest):
    def test_the_backup_holds_the_session_as_it_was_opened(self):
        store = StateStore(self.root / "data.json")
        store.save([Task(text="as opened")], "", 15)
        store._backed_up = False  # simulate the next run opening this file
        store.save([Task(text="first edit")], "", 15)
        store.save([Task(text="second edit")], "", 15)
        store.save([Task(text="third edit")], "", 15)
        backup = (self.root / "data.json.bak").read_text(encoding="utf-8")
        self.assertIn("as opened", backup)
        self.assertNotIn("second edit", backup)


class RecoveryTests(TempDirTest):
    """The corrupt-file paths: quarantine, restore, and .bak protection."""

    def _spoil(self, store):
        store.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(StorageError):
            store.load()

    def test_quarantine_moves_the_bad_file_aside(self):
        store = StateStore(self.root / "data.json")
        self._spoil(store)
        spoiled = store.quarantine()
        self.assertIsNotNone(spoiled)
        self.assertFalse(store.path.exists())
        self.assertTrue(spoiled.name.startswith("data.json.corrupt-"))
        self.assertEqual(spoiled.read_text(encoding="utf-8"), "{not json")

    def test_two_quarantines_do_not_overwrite_each_other(self):
        store = StateStore(self.root / "data.json")
        self._spoil(store)
        first = store.quarantine()
        self._spoil(store)
        second = store.quarantine()
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_a_failed_load_keeps_the_backup_out_of_reach_of_save(self):
        # The old catastrophe: load fails, user is told to Save, and the
        # once-per-run backup copies the corrupt file over the good .bak.
        store = StateStore(self.root / "data.json")
        store.save([Task(text="the good copy")], "", 15)
        store._backed_up = False  # a fresh run opens the file
        store.save([Task(text="still good")], "", 15)  # writes the .bak
        store._backed_up = False  # next run...
        self._spoil(store)  # ...finds the file corrupt
        store.save([], "", 15)  # explicit Save after the failed load
        backup = store.backup_path.read_text(encoding="utf-8")
        self.assertIn("the good copy", backup)
        self.assertNotIn("{not json", backup)

    def test_restore_backup_brings_the_previous_session_back(self):
        store = StateStore(self.root / "data.json")
        store.save([Task(text="yesterday's work")], "", 15)
        store._backed_up = False
        store.save([Task(text="also kept")], "", 15)
        self._spoil(store)
        self.assertIsNotNone(store.quarantine())
        self.assertTrue(store.restore_backup())
        loaded = store.load()
        self.assertEqual([t.text for t in loaded["tasks"]], ["yesterday's work"])

    def test_preserve_backup_stops_a_fresh_start_replacing_the_bak(self):
        store = StateStore(self.root / "data.json")
        store.save([Task(text="the last good session")], "", 15)
        store._backed_up = False
        store.save([Task(text="edit")], "", 15)  # .bak now holds the good session
        self._spoil(store)
        store.quarantine()
        store.preserve_backup()  # user declined the restore; starting fresh
        store.save([], "", 15)
        store.save([Task(text="new life")], "", 15)
        backup = store.backup_path.read_text(encoding="utf-8")
        self.assertIn("the last good session", backup)

    def test_a_successful_load_clears_the_suspect_flag(self):
        store = StateStore(self.root / "data.json")
        self._spoil(store)
        store.path.write_text(
            json.dumps({"tasks": [], "scratchpad": "ok"}), encoding="utf-8")
        store.load()
        store.save([Task(text="fine again")], "", 15)
        self.assertTrue(store.backup_path.exists())


class VanishedMatrixFolderTests(TempDirTest):
    def test_writing_into_a_missing_root_refuses_instead_of_forking(self):
        import shutil as _shutil

        store = MatrixStore(self.root / "matrix")
        store.ensure()
        store.create("do_first", "before the vanish", "")
        _shutil.rmtree(self.root / "matrix")
        with self.assertRaises(StorageError):
            store.create("do_first", "after the vanish", "")
        # No fresh tree was silently forked.
        self.assertFalse((self.root / "matrix").exists())

    def test_listing_a_missing_root_is_calmly_empty(self):
        store = MatrixStore(self.root / "never-created")
        self.assertEqual(store.list("do_first"), [])


class MatrixUpdateRollbackTests(TempDirTest):
    def test_a_failed_rename_never_leaves_two_files(self):
        from unittest import mock

        store = MatrixStore(self.root)
        store.ensure()
        task = store.create("do_first", "old name", "content")
        with mock.patch.object(MatrixStore, "_unlink",
                               side_effect=StorageError("locked")):
            with self.assertRaises(StorageError):
                store.update(task, "new name", "content")
        files = list((self.root / "DoFirst").glob("*.task"))
        self.assertEqual(len(files), 1)
        self.assertIn("old name", files[0].name)
        # The in-memory task matches the file that survived.
        self.assertEqual(task.title, "old name")
        self.assertEqual(Path(task.path), files[0])

    def test_an_unrenamed_update_is_untouched_by_the_rollback(self):
        store = MatrixStore(self.root)
        store.ensure()
        task = store.create("do_first", "same name", "old content")
        store.update(task, "same name", "new content")
        files = list((self.root / "DoFirst").glob("*.task"))
        self.assertEqual(len(files), 1)
        self.assertIn("new content", files[0].read_text(encoding="utf-8"))


class InstanceLockTests(TempDirTest):
    def test_acquire_creates_and_owns(self):
        lock = InstanceLock(self.root)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.owned)
        self.assertTrue((self.root / ".lock").exists())

    def test_a_second_acquire_fails_and_names_the_holder(self):
        first = InstanceLock(self.root)
        self.assertTrue(first.acquire())
        second = InstanceLock(self.root)
        self.assertFalse(second.acquire())
        self.assertFalse(second.owned)
        self.assertIn("started", second.holder())

    def test_takeover_claims_and_release_unlinks(self):
        first = InstanceLock(self.root)
        first.acquire()
        second = InstanceLock(self.root)
        self.assertFalse(second.acquire())
        second.takeover()
        self.assertTrue(second.owned)
        second.release()
        self.assertFalse((self.root / ".lock").exists())

    def test_release_without_ownership_leaves_the_lock_alone(self):
        first = InstanceLock(self.root)
        first.acquire()
        second = InstanceLock(self.root)
        second.acquire()
        second.release()  # not owned: must not delete first's lock
        self.assertTrue((self.root / ".lock").exists())

    def test_an_unwritable_folder_does_not_block_the_app(self):
        blocked = self.root / "file-not-folder"
        blocked.write_text("x", encoding="utf-8")
        lock = InstanceLock(blocked / "nested")
        self.assertTrue(lock.acquire())  # save will complain instead
        self.assertFalse(lock.owned)

    def test_an_unreadable_lock_still_reports_something(self):
        """A live holder is still refused, and still described.

        This used to assert that an unreadable lock file blocked acquisition
        on its own. That assertion encoded the old rule — the file existing
        meant somebody held it — and a crashed copy is exactly the case the
        lock can now answer without asking. So the refusal is now pinned
        where it belongs: with a copy that really is running.
        """
        holder = InstanceLock(self.root)
        self.assertTrue(holder.acquire())
        (self.root / ".lock").write_bytes(b"\xff\xfe garbage")
        second = InstanceLock(self.root)
        self.assertFalse(second.acquire())
        self.assertEqual(second.holder(), "details unreadable")

    def test_a_lock_left_by_a_crash_is_claimed_without_asking(self):
        """The point of the whole mechanism.

        Nothing is running; only a file is left over. Opening the app must
        not stop to ask a question nobody can answer.
        """
        (self.root / ".lock").write_text(
            '{"pid": 999999, "host": "gone", "started": "2026-08-15 22:14:03"}',
            encoding="utf-8",
        )
        lock = InstanceLock(self.root)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.owned)

    def test_a_crashed_copy_leaving_garbage_is_also_claimed(self):
        (self.root / ".lock").write_bytes(b"\xff\xfe garbage")
        lock = InstanceLock(self.root)
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.owned)

    def test_claiming_a_stale_lock_rewrites_it_with_this_copy(self):
        (self.root / ".lock").write_text('{"pid": 999999, "host": "gone"}',
                                         encoding="utf-8")
        lock = InstanceLock(self.root)
        lock.acquire()
        self.assertEqual(json.loads((self.root / ".lock").read_text())["pid"],
                         os.getpid())

    def test_a_released_lock_is_free_for_the_next_copy(self):
        first = InstanceLock(self.root)
        first.acquire()
        first.release()
        second = InstanceLock(self.root)
        self.assertTrue(second.acquire())
        self.assertTrue(second.owned)

    # -- the guard must survive a real death, not a simulated one --------
    def _hold_lock_in_a_child(self):
        """Start a separate process that takes the lock and waits."""
        child = subprocess.Popen(
            [sys.executable, "-c",
             "import sys, time\n"
             f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
             "from cognitive_offload.storage import InstanceLock\n"
             f"lock = InstanceLock({str(self.root)!r})\n"
             "print(lock.acquire(), flush=True)\n"
             "time.sleep(60)\n"],
            stdout=subprocess.PIPE, text=True)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        held = child.stdout.readline().strip()
        if held != "True":
            self.skipTest("child could not take the lock")
        return child

    def test_a_copy_that_is_really_running_still_blocks(self):
        """The reason the lock exists: two copies would overwrite each other."""
        self._hold_lock_in_a_child()
        mine = InstanceLock(self.root)
        self.assertFalse(mine.acquire())
        self.assertFalse(mine.owned)

    def test_a_killed_copy_stops_blocking_the_next_launch(self):
        """SIGKILL: no cleanup can possibly run, so the file stays behind.

        This is the case a user actually hits — a crash, a force-quit, a
        battery running out — and the one that used to cost them a modal
        before the window appeared.
        """
        child = self._hold_lock_in_a_child()
        blocked = InstanceLock(self.root)
        self.assertFalse(blocked.acquire())  # while it lives

        child.send_signal(signal.SIGKILL)
        child.wait()
        self.assertTrue((self.root / ".lock").exists(),
                        "the file must survive, or this proves nothing")

        after = InstanceLock(self.root)
        self.assertTrue(after.acquire())
        self.assertTrue(after.owned)


class LockCertaintyTests(TempDirTest):
    """A refusal has to say whether it *knows*.

    "A copy is running" and "we cannot tell whether a copy is running" want
    different things said to the person: the first must not offer the
    crashed-copy reassurance, because following it causes the very overwrite
    the warning is about.
    """

    def test_a_fresh_lock_starts_certain(self):
        lock = InstanceLock(self.root)
        self.assertFalse(lock.uncertain)

    def test_a_live_holder_is_a_certain_refusal(self):
        first = InstanceLock(self.root)
        first.acquire()
        second = InstanceLock(self.root)
        self.assertFalse(second.acquire())
        self.assertFalse(second.uncertain,
                         "a live copy holds it — that is a fact, not a guess")

    def test_an_unlockable_filesystem_refuses_but_admits_it_cannot_tell(self):
        """Where locking is unsupported, a crash leftover is still possible."""
        first = InstanceLock(self.root)
        first.acquire()
        second = InstanceLock(self.root)
        with mock.patch("cognitive_offload.storage._take_lock", return_value=None):
            self.assertFalse(second.acquire())
        self.assertTrue(second.uncertain)

    def test_a_lock_file_that_will_not_open_is_also_uncertain(self):
        """The file is there but unreadable — no grounds to claim anything.

        Only the *second* open is blocked: the first is the O_EXCL create,
        and failing that one means an unwritable folder, which deliberately
        lets the app start and complain at the first save instead.
        """
        (self.root / ".lock").write_text("{}", encoding="utf-8")
        lock = InstanceLock(self.root)
        with mock.patch("cognitive_offload.storage.os.open",
                        side_effect=[FileExistsError(), PermissionError("nope")]):
            self.assertFalse(lock.acquire())
        self.assertTrue(lock.uncertain)


class LocationsTests(unittest.TestCase):
    def test_the_desktop_layout_is_unchanged(self):
        """An existing install must find its files exactly where it left them."""
        where = desktop_locations("/home/someone")
        self.assertEqual(where.data_dir, Path("/home/someone/.cognitive_offload"))
        self.assertEqual(where.matrix_dir, Path("/home/someone/MatrixTasks"))
        self.assertEqual(where.config_file,
                         Path("/home/someone/.cognitive_offload_config.json"))

    def test_a_private_directory_needs_no_home_and_no_dotfiles(self):
        """The shape Android hands an app, and what a USB-stick install wants."""
        where = app_private_locations("/data/user/0/app/files")
        self.assertEqual(where.data_dir, Path("/data/user/0/app/files/data"))
        self.assertEqual(where.config_file, Path("/data/user/0/app/files/config.json"))
        for path in (where.data_dir, where.matrix_dir, where.config_file):
            self.assertTrue(str(path).startswith("/data/user/0/app/files"))
            self.assertFalse(path.name.startswith("."))

    def test_config_writes_where_the_platform_says(self):
        with tempfile.TemporaryDirectory() as tmp:
            where = app_private_locations(tmp)
            config = Config(locations=where)
            self.assertEqual(config.path, where.config_file)
            self.assertEqual(config.db_path, where.data_dir)
            self.assertEqual(config.state_file, where.data_dir / "data.json")
            config.save()
            self.assertTrue(where.config_file.exists())

    def test_config_still_defaults_to_the_desktop_layout(self):
        self.assertEqual(Config().locations.data_dir,
                         desktop_locations().data_dir)

    def test_a_saved_folder_choice_still_wins_over_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            chosen = Path(tmp) / "somewhere else"
            config_file = Path(tmp) / "config.json"
            config_file.write_text(json.dumps({"db_path": str(chosen)}),
                                   encoding="utf-8")
            config = Config(path=config_file).load()
            self.assertEqual(config.db_path, chosen)

    def test_display_path_shortens_against_the_home_it_is_given(self):
        where = Locations(data_dir=Path("/srv/app/data"),
                          matrix_dir=Path("/srv/app/MatrixTasks"),
                          config_file=Path("/srv/app/config.json"),
                          home=Path("/srv/app"))
        self.assertEqual(display_path(where.data_dir / "data.json", home=where.home),
                         "~/data/data.json")

    def test_display_path_default_is_the_running_users_home(self):
        self.assertEqual(display_path(Path.home() / "x.json"), "~/x.json")


class SlugTests(unittest.TestCase):
    def test_removes_path_separators(self):
        self.assertNotIn("/", slugify("a/b"))
        self.assertNotIn("\\", slugify("a\\b"))

    def test_falls_back_when_nothing_survives(self):
        self.assertEqual(slugify("***"), "task")

    def test_truncates_long_titles(self):
        self.assertLessEqual(len(slugify("x" * 200)), 60)


class MatrixStoreTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.store = MatrixStore(self.root / "matrix")
        self.store.ensure()

    def test_ensure_creates_every_quadrant(self):
        for key in CATEGORY_KEYS:
            self.assertTrue(self.store.path_for(key).is_dir())

    def test_create_and_list(self):
        self.store.create("do_first", "Ship the thing", "details")
        tasks = self.store.list("do_first")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Ship the thing")
        self.assertEqual(tasks[0].content, "details")

    def test_two_tasks_may_share_a_title(self):
        self.store.create("do_first", "Same name", "first")
        self.store.create("do_first", "Same name", "second")
        tasks = self.store.list("do_first")
        self.assertEqual(len(tasks), 2)
        self.assertEqual({t.content for t in tasks}, {"first", "second"})

    def test_titles_with_slashes_are_safe(self):
        task = self.store.create("schedule", "review 2024/2025 plan", "x")
        self.assertTrue(Path(task.path).exists())
        self.assertEqual(self.store.list("schedule")[0].title, "review 2024/2025 plan")

    def test_update_renames_the_file_and_leaves_no_orphan(self):
        task = self.store.create("do_first", "Old title", "body")
        old_path = Path(task.path)
        self.store.update(task, "New title", "new body")
        self.assertFalse(old_path.exists())
        tasks = self.store.list("do_first")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "New title")
        self.assertEqual(tasks[0].content, "new body")

    def test_update_without_rename_keeps_the_same_file(self):
        task = self.store.create("do_first", "Title", "body")
        path = Path(task.path)
        self.store.update(task, "Title", "edited")
        self.assertTrue(path.exists())
        self.assertEqual(self.store.list("do_first")[0].content, "edited")

    def test_a_failed_move_does_not_leave_the_task_in_two_quadrants(self):
        from unittest import mock

        task = self.store.create("schedule", "half moved", "body")
        old_path = Path(task.path)
        with mock.patch.object(MatrixStore, "_unlink", side_effect=StorageError("locked")):
            with self.assertRaises(StorageError):
                self.store.move(task, "do_first")
        self.assertEqual([t.title for t in self.store.list("schedule")], ["half moved"])
        self.assertEqual(self.store.list("do_first"), [])
        self.assertEqual(Path(task.path), old_path)
        self.assertEqual(task.category, "schedule")

    def test_restore_writes_a_deleted_task_back(self):
        task = self.store.create("delegate", "comes back", "body")
        self.store.delete(task)
        self.assertEqual(self.store.list("delegate"), [])
        self.store.restore(task)
        restored = self.store.list("delegate")
        self.assertEqual([t.title for t in restored], ["comes back"])
        self.assertEqual(restored[0].content, "body")

    def test_move_between_quadrants(self):
        task = self.store.create("eliminate", "Reconsider", "body")
        old_path = Path(task.path)
        self.store.move(task, "do_first")
        self.assertFalse(old_path.exists())
        self.assertEqual(self.store.list("eliminate"), [])
        self.assertEqual(self.store.list("do_first")[0].title, "Reconsider")

    def test_move_to_a_quadrant_that_already_has_that_title(self):
        self.store.create("do_first", "Duplicate", "existing")
        task = self.store.create("schedule", "Duplicate", "incoming")
        self.store.move(task, "do_first")
        self.assertEqual(len(self.store.list("do_first")), 2)
        self.assertEqual(self.store.list("schedule"), [])

    def test_delete(self):
        task = self.store.create("delegate", "Hand off", "")
        self.store.delete(task)
        self.assertEqual(self.store.list("delegate"), [])
        self.store.delete(task)  # deleting twice must not raise

    def test_legacy_plain_text_files_are_readable(self):
        legacy = self.store.path_for("schedule") / "Legacy Task.task"
        legacy.write_text("just some text", encoding="utf-8")
        tasks = self.store.list("schedule")
        self.assertEqual(tasks[0].title, "Legacy Task")
        self.assertEqual(tasks[0].content, "just some text")

    def test_legacy_json_files_are_readable_and_upgradeable(self):
        legacy = self.store.path_for("schedule") / "Old.task"
        legacy.write_text(json.dumps({"title": "Old", "content": "body"}), encoding="utf-8")
        task = self.store.list("schedule")[0]
        self.assertEqual(task.title, "Old")
        self.store.update(task, "Renamed", "body")
        self.assertFalse(legacy.exists())
        self.assertEqual(self.store.list("schedule")[0].title, "Renamed")

    def test_unreadable_entries_do_not_break_listing(self):
        (self.store.path_for("do_first") / "broken.task").write_bytes(b"\xff\xfe\x00binary")
        self.store.create("do_first", "Fine", "")
        titles = [t.title for t in self.store.list("do_first")]
        self.assertIn("Fine", titles)

    def test_add_from_task_copies_description(self):
        task = Task(text="From list", description="the details")
        created = self.store.add_from_task("delegate", task)
        self.assertEqual(created.title, "From list")
        self.assertEqual(self.store.list("delegate")[0].content, "the details")

    def test_listing_a_missing_folder_returns_empty(self):
        store = MatrixStore(self.root / "does-not-exist")
        self.assertEqual(store.list("do_first"), [])

    def test_unknown_quadrant_raises(self):
        with self.assertRaises(KeyError):
            self.store.path_for("nonsense")


if __name__ == "__main__":
    unittest.main()
