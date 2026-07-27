import unittest

from cognitive_offload.models import MatrixTask, Note, Task


class TaskTests(unittest.TestCase):
    def test_ids_are_unique(self):
        a, b = Task(text="same"), Task(text="same")
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(a, b)

    def test_tasks_with_identical_text_are_distinct_in_a_list(self):
        tasks = [Task(text="write tests"), Task(text="write tests")]
        tasks.remove(tasks[1])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, tasks[0].id)

    def test_defaults_are_not_shared_between_instances(self):
        a, b = Task(text="a"), Task(text="b")
        a.add_tag("home")
        self.assertEqual(b.tags, [])

    def test_marking_done_stamps_and_clears(self):
        task = Task(text="thing")
        task.toggle_done()
        self.assertTrue(task.done)
        self.assertTrue(task.completed_at)
        task.toggle_done()
        self.assertFalse(task.done)
        self.assertIsNone(task.completed_at)

    def test_tags_are_normalised_and_deduped(self):
        task = Task(text="thing", tags=["Home", "home", " WORK "])
        self.assertEqual(task.tags, ["home", "work"])
        self.assertFalse(task.add_tag("HOME"))
        self.assertTrue(task.add_tag("errand"))
        self.assertTrue(task.remove_tag("Errand"))
        self.assertEqual(task.tags, ["home", "work"])

    def test_search_matches_text_description_and_tags(self):
        task = Task(text="Email Bob", description="About the Q3 budget", tags=["work"])
        for term in ("email", "BUDGET", "wor", ""):
            self.assertTrue(task.matches(term), term)
        self.assertFalse(task.matches("groceries"))

    def test_roundtrip_preserves_everything(self):
        task = Task(text="x", description="d", tags=["a"], priority=1)
        task.set_done(True)
        clone = Task.from_dict(task.to_dict())
        self.assertEqual(clone, task)

    def test_from_dict_accepts_legacy_records(self):
        legacy = {"text": "old task", "done": False, "created_at": "2024-01-01 10:00:00"}
        task = Task.from_dict(legacy)
        self.assertEqual(task.text, "old task")
        self.assertEqual(task.tags, [])
        self.assertEqual(task.priority, 0)
        self.assertIsNone(task.completed_at)
        self.assertTrue(task.id)

    def test_from_dict_ignores_junk_types(self):
        task = Task.from_dict({"text": "x", "tags": "not-a-list", "priority": "yes", "done": 1})
        self.assertEqual(task.tags, [])
        self.assertEqual(task.priority, 1)
        self.assertTrue(task.done)

    def test_done_without_timestamp_is_consistent(self):
        task = Task(text="x", done=False, completed_at="2024-01-01 00:00:00")
        self.assertIsNone(task.completed_at)


class NoteTests(unittest.TestCase):
    def test_render_includes_timestamp(self):
        note = Note(text="idea", created_at="2024-05-05 09:00:00")
        self.assertEqual(note.render(), "[2024-05-05 09:00:00] idea")


class MatrixTaskTests(unittest.TestCase):
    def test_to_task_carries_content_into_description(self):
        matrix_task = MatrixTask(title="Ship it", content="notes here")
        task = matrix_task.to_task()
        self.assertEqual(task.text, "Ship it")
        self.assertEqual(task.description, "notes here")
        self.assertFalse(task.done)


if __name__ == "__main__":
    unittest.main()
