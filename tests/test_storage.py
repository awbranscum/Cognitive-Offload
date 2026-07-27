import json
import tempfile
import unittest
from pathlib import Path

from cognitive_offload.models import Task
from cognitive_offload.storage import (
    CATEGORY_KEYS,
    Config,
    MatrixStore,
    StateStore,
    StorageError,
    atomic_write_text,
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
        self.assertEqual(config.timer_minutes, 15)
        self.assertTrue(config.show_done)

    def test_corrupt_config_does_not_raise(self):
        path = self.root / "cfg.json"
        path.write_text("<<<garbage>>>", encoding="utf-8")
        config = Config(path).load()
        self.assertEqual(config.timer_minutes, 15)

    def test_roundtrip(self):
        path = self.root / "cfg.json"
        config = Config(path)
        config.db_path = self.root / "db"
        config.matrix_db_path = self.root / "matrix"
        config.timer_minutes = 50
        config.sort_order = "created"
        config.show_done = False
        config.save()

        reloaded = Config(path).load()
        self.assertEqual(reloaded.db_path, self.root / "db")
        self.assertEqual(reloaded.matrix_db_path, self.root / "matrix")
        self.assertEqual(reloaded.timer_minutes, 50)
        self.assertEqual(reloaded.sort_order, "created")
        self.assertFalse(reloaded.show_done)

    def test_out_of_range_values_are_clamped(self):
        path = self.root / "cfg.json"
        path.write_text(json.dumps({"timer_minutes": 9999, "sort_order": "bogus"}), encoding="utf-8")
        config = Config(path).load()
        self.assertEqual(config.timer_minutes, 240)
        self.assertEqual(config.sort_order, "priority")

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
