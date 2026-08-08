import unittest

from cognitive_offload.models import Task, today_iso
from cognitive_offload.queries import (
    all_tags,
    counts,
    due_tasks,
    filter_tasks,
    rank_for_starting,
    sort_tasks,
    split_lines,
    suggest_tasks,
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

    def test_ranking_treats_a_pin_like_a_flag(self):
        flagged = make("flagged", priority=1, created="2024-01-01 00:00:00")
        pinned = make("pinned", created="2024-01-01 00:00:00")
        pinned.pinned = True
        ready = make("ready", created="2024-01-01 00:00:00")
        ready.first_step = "open the file"
        order = [t.text for t in rank_for_starting([flagged, pinned, ready])]
        self.assertEqual(order[0], "ready")          # a first step still wins
        self.assertEqual(set(order[1:]), {"flagged", "pinned"})  # equal weight

    def test_priority_sort_puts_pinned_above_flagged(self):
        flagged = make("flagged", priority=1, created="2024-06-01 00:00:00")
        pinned = make("pinned", created="2024-01-01 00:00:00")
        pinned.pinned = True
        order = [t.text for t in sort_tasks([flagged, pinned], "priority")]
        self.assertEqual(order, ["pinned", "flagged"])

    def test_a_pinned_done_task_stays_below_open_work(self):
        done_pinned = make("done", done=True)
        done_pinned.pinned = True
        open_plain = make("open")
        order = [t.text for t in sort_tasks([done_pinned, open_plain], "priority")]
        self.assertEqual(order, ["open", "done"])

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


class StartingTests(unittest.TestCase):
    """The ranking that answers "what can I actually start right now?"."""

    def test_a_task_with_a_first_step_outranks_one_without(self):
        vague = make("vague")
        ready = make("ready")
        ready.first_step = "open the folder"
        self.assertEqual([t.text for t in rank_for_starting([vague, ready])], ["ready", "vague"])

    def test_a_booked_task_that_is_due_comes_first(self):
        plain = make("plain")
        plain.first_step = "start it"
        booked = make("booked")
        booked.scheduled_for = "2020-01-01"  # long overdue is still due
        order = [t.text for t in rank_for_starting([plain, booked])]
        self.assertEqual(order[0], "booked")

    def test_flagged_beats_unflagged_when_all_else_is_equal(self):
        plain = make("plain")
        flagged = make("flagged", priority=1)
        self.assertEqual(
            [t.text for t in rank_for_starting([plain, flagged])], ["flagged", "plain"]
        )

    def test_older_tasks_win_ties(self):
        older = make("older", created="2024-01-01 00:00:00")
        newer = make("newer", created="2026-01-01 00:00:00")
        self.assertEqual([t.text for t in rank_for_starting([newer, older])], ["older", "newer"])

    def test_completed_tasks_are_never_suggested(self):
        self.assertEqual(rank_for_starting([make("done", done=True)]), [])

    def test_kind_filter_keeps_unsorted_tasks_in_the_running(self):
        admin = make("admin task")
        admin.kind = "admin"
        creative = make("creative task")
        creative.kind = "creative"
        unsorted = make("unsorted task")
        result = [t.text for t in rank_for_starting([admin, creative, unsorted], kind="admin")]
        self.assertIn("admin task", result)
        self.assertIn("unsorted task", result)
        self.assertNotIn("creative task", result)

    def test_a_matching_kind_outranks_an_unsorted_task(self):
        admin = make("admin task")
        admin.kind = "admin"
        unsorted = make("unsorted task")
        order = [t.text for t in rank_for_starting([unsorted, admin], kind="admin")]
        self.assertEqual(order[0], "admin task")

    def test_suggestions_are_a_short_list(self):
        tasks = [make(f"task {i}") for i in range(10)]
        self.assertEqual(len(suggest_tasks(tasks, limit=3)), 3)

    def test_suggestions_cycle_and_wrap_instead_of_running_out(self):
        tasks = [make(f"task {i}") for i in range(4)]
        first = [t.text for t in suggest_tasks(tasks, limit=3, offset=0)]
        second = [t.text for t in suggest_tasks(tasks, limit=3, offset=3)]
        self.assertNotEqual(first, second)
        self.assertEqual(len(second), 3)
        far = suggest_tasks(tasks, limit=3, offset=99)
        self.assertEqual(len(far), 3)

    def test_suggestions_never_exceed_the_number_of_open_tasks(self):
        self.assertEqual(len(suggest_tasks([make("only one")], limit=3)), 1)
        self.assertEqual(suggest_tasks([], limit=3), [])

    def test_due_tasks_are_open_scheduled_and_soonest_first(self):
        late = make("late")
        late.scheduled_for = "2020-01-01"
        today = make("today")
        today.scheduled_for = today_iso()
        future = make("future")
        future.scheduled_for = "2999-01-01"
        finished = make("finished", done=True)
        finished.scheduled_for = "2020-01-01"
        result = [t.text for t in due_tasks([today, late, future, finished])]
        self.assertEqual(result, ["late", "today"])

    def test_filter_by_kind(self):
        admin = make("admin task")
        admin.kind = "admin"
        other = make("other")
        self.assertEqual([t.text for t in filter_tasks([admin, other], kind="admin")], ["admin task"])

    def test_search_also_looks_in_the_first_step(self):
        task = make("opaque title")
        task.first_step = "email Dana about the invoice"
        self.assertEqual(len(filter_tasks([task], search="invoice")), 1)


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
