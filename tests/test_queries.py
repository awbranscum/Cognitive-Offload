import unittest

from cognitive_offload.models import Task
from cognitive_offload.queries import (
    all_tags,
    counts,
    filter_tasks,
    sort_tasks,
    split_lines,
    visible_tasks,
)


def make(text, priority=0, done=False, created="2024-01-01 00:00:00", tags=None, desc=""):
    task = Task(text=text, priority=priority, created_at=created, tags=tags or [], description=desc)
    if done:
        task.set_done(True)
    return task


class SortTests(unittest.TestCase):
    def test_priority_sort_puts_flagged_tasks_first(self):
        low = make("low", priority=0, created="2024-01-02 00:00:00")
        high = make("high", priority=1, created="2024-01-01 00:00:00")
        self.assertEqual([t.text for t in sort_tasks([low, high], "priority")], ["high", "low"])

    def test_priority_sort_pushes_completed_to_the_bottom(self):
        done_high = make("done", priority=1, done=True)
        open_low = make("open", priority=0)
        order = [t.text for t in sort_tasks([done_high, open_low], "priority")]
        self.assertEqual(order, ["open", "done"])

    def test_priority_sort_breaks_ties_with_newest_first(self):
        older = make("older", created="2024-01-01 00:00:00")
        newer = make("newer", created="2024-06-01 00:00:00")
        self.assertEqual([t.text for t in sort_tasks([older, newer], "priority")], ["newer", "older"])

    def test_created_sort_is_newest_first(self):
        a = make("a", created="2024-01-01 00:00:00")
        b = make("b", created="2025-01-01 00:00:00")
        self.assertEqual([t.text for t in sort_tasks([a, b], "created")], ["b", "a"])

    def test_alpha_sort_is_case_insensitive_and_open_first(self):
        tasks = [make("banana"), make("Apple"), make("aardvark", done=True)]
        self.assertEqual(
            [t.text for t in sort_tasks(tasks, "alpha")], ["Apple", "banana", "aardvark"]
        )

    def test_completed_sort_lists_recent_completions_first(self):
        first = make("first", done=True)
        first.completed_at = "2024-01-01 00:00:00"
        second = make("second", done=True)
        second.completed_at = "2024-02-01 00:00:00"
        order = [t.text for t in sort_tasks([first, second, make("open")], "completed")]
        self.assertEqual(order[:2], ["second", "first"])

    def test_sorting_does_not_mutate_the_input(self):
        tasks = [make("a", priority=0), make("b", priority=1)]
        sort_tasks(tasks, "priority")
        self.assertEqual([t.text for t in tasks], ["a", "b"])


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [
            make("Email Bob", tags=["work"], desc="about the budget"),
            make("Buy milk", tags=["errand"]),
            make("Old thing", done=True, tags=["work"]),
        ]

    def test_search_covers_description(self):
        found = filter_tasks(self.tasks, search="budget")
        self.assertEqual([t.text for t in found], ["Email Bob"])

    def test_search_is_case_insensitive(self):
        self.assertEqual(len(filter_tasks(self.tasks, search="EMAIL")), 1)

    def test_tag_filter(self):
        self.assertEqual(len(filter_tasks(self.tasks, tag="work")), 2)
        self.assertEqual(len(filter_tasks(self.tasks, tag="WORK")), 2)

    def test_hide_done(self):
        self.assertEqual(len(filter_tasks(self.tasks, show_done=False)), 2)

    def test_filters_combine(self):
        found = filter_tasks(self.tasks, search="thing", tag="work", show_done=True)
        self.assertEqual([t.text for t in found], ["Old thing"])
        self.assertEqual(filter_tasks(self.tasks, search="thing", show_done=False), [])

    def test_visible_tasks_filters_then_sorts(self):
        tasks = [make("alpha work", tags=["work"]), make("beta work", tags=["work"], priority=1)]
        result = visible_tasks(tasks, tag="work", order="priority")
        self.assertEqual([t.text for t in result], ["beta work", "alpha work"])

    def test_all_tags_is_sorted_and_unique(self):
        self.assertEqual(all_tags(self.tasks), ["errand", "work"])

    def test_counts(self):
        tasks = [make("a"), make("b", priority=1), make("c", done=True)]
        self.assertEqual(counts(tasks), (2, 1, 1))


class SplitLineTests(unittest.TestCase):
    def test_strips_bullets_and_blank_lines(self):
        raw = "- one\n\n* two\n  • three  \n"
        self.assertEqual(split_lines(raw), ["one", "two", "three"])

    def test_strips_capture_timestamp_prefix(self):
        raw = "[2024-05-05 09:00:00] call the bank"
        self.assertEqual(split_lines(raw), ["call the bank"])

    def test_keeps_bracketed_content_that_is_not_a_timestamp(self):
        raw = "[urgent] call the bank"
        self.assertEqual(split_lines(raw), ["[urgent] call the bank"])

    def test_strips_checkbox_markers(self):
        self.assertEqual(split_lines("- [ ] todo\n- [x] done"), ["todo", "done"])

    def test_empty_input(self):
        self.assertEqual(split_lines("   \n\n"), [])


if __name__ == "__main__":
    unittest.main()
