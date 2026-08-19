"""What carries into the next round of a repeat, and what belongs to the round.

`Task.next_instance` copies the task through `to_dict`/`from_dict` and then
clears the handful of fields that belonged to *this* round. That list was
written by hand and immediately went stale: the three handoff marks were added
to `Task` without being added to it, so finishing a repeating task that had
been handed to an agent booked the next round **already claiming to be out
with that agent** — and every round after inherited the claim, because each
copies the last.

So this is keyed on ``dataclasses.fields(Task)``: every field must be
classified as *setup, carried forward* or *per-round, reset*, and a field
added in future fails the suite until someone decides which it is. Exactly the
shape of `tests/test_conversions.py`, for the same reason — the previous
version of this promise was a comment, and a comment cannot fail.
"""

import dataclasses
import unittest

from cognitive_offload.models import PER_ROUND_FIELDS, Task
from cognitive_offload.queries import rank_for_starting
from cognitive_offload.rows import task_row

# Setup you did once: it describes the task, so every round gets it.
CARRIED = {
    "text": "the task is the same task",
    "description": "notes about the task, not about one round of it",
    "first_step": "the way in does not change between rounds",
    "kind": "how it feels to start does not change",
    "tags": "how you file it does not change",
    "priority": "flagged is a property of the task",
    "pinned": "pinned is a property of the task",
    "estimate_minutes": "the guess is about the work, not the round",
    "repeat": "it would stop repeating after one round",
}
# Decided per round, never inherited.
PER_ROUND = {
    "snoozed_until": '"Not today" was about today',
    "handed_to": "the next round was never handed to anyone",
    "handed_off_on": "as above",
    "follow_up_on": "as above",
}
# Neither: the next round is a new, unfinished record on its own day.
FRESH = {
    "id": "a new round is a new record",
    "created_at": "it is created now, not when the first round was",
    "scheduled_for": "the whole point — it moves to the next date",
    "done": "the next round has not been done",
    "completed_at": "meaningless until it is",
}


def a_repeating_task(**kw) -> Task:
    fields = dict(
        text="Take the bins out",
        description="green bin, alternate weeks",
        first_step="wheel it to the kerb",
        kind="admin",
        tags=["home"],
        priority=1,
        pinned=True,
        estimate_minutes=5,
        repeat="weekly",
        scheduled_for="2026-08-21",
        snoozed_until="2026-08-20",
        handed_to="Claude Desktop",
        handed_off_on="2026-08-19",
        follow_up_on="2026-08-22",
    )
    fields.update(kw)
    return Task(**fields)


class ClassificationTests(unittest.TestCase):
    def test_every_field_is_classified(self):
        """The guard that catches the next one. A field added to Task must be
        put in exactly one of the three lists above — which is a decision
        someone has to make, not a default they can drift past."""
        classified = set(CARRIED) | set(PER_ROUND) | set(FRESH)
        actual = {f.name for f in dataclasses.fields(Task)}
        self.assertEqual(
            actual - classified, set(),
            "on Task but not classified — decide whether the next round "
            "inherits it, and add it to CARRIED, PER_ROUND or FRESH",
        )
        self.assertEqual(classified - actual, set(),
                         "classified but no longer a field on Task")

    def test_no_field_is_in_two_lists(self):
        self.assertEqual(len(CARRIED) + len(PER_ROUND) + len(FRESH),
                         len({*CARRIED, *PER_ROUND, *FRESH}))

    def test_the_code_and_this_file_agree_on_what_is_per_round(self):
        """The app clears `PER_ROUND_FIELDS`; this file says which they are.
        Two lists of the same thing is how the original bug happened, so they
        are asserted equal rather than both maintained by hand."""
        self.assertEqual(set(PER_ROUND_FIELDS), set(PER_ROUND))

    def test_every_classification_carries_a_reason(self):
        for reason in [*CARRIED.values(), *PER_ROUND.values(), *FRESH.values()]:
            self.assertTrue(reason.strip())


class NextRoundTests(unittest.TestCase):
    def setUp(self):
        self.task = a_repeating_task()
        self.next = self.task.next_instance("2026-08-19")

    def test_the_fixture_sets_every_field_away_from_its_default(self):
        """Otherwise a field that is dropped compares equal to one that is
        carried, and this whole file passes for the wrong reason."""
        for f in dataclasses.fields(Task):
            if f.name in FRESH:
                continue
            default = (f.default_factory() if f.default_factory
                       is not dataclasses.MISSING else f.default)
            if default is dataclasses.MISSING:
                continue
            with self.subTest(field=f.name):
                self.assertNotEqual(getattr(self.task, f.name), default)

    def test_setup_carries_into_the_next_round(self):
        for name in sorted(CARRIED):
            with self.subTest(field=name):
                self.assertEqual(getattr(self.next, name),
                                 getattr(self.task, name),
                                 f"{name} was lost between rounds")

    def test_per_round_state_does_not(self):
        for name in sorted(PER_ROUND):
            with self.subTest(field=name):
                self.assertEqual(getattr(self.next, name), "",
                                 f"{name} was inherited by a round it was "
                                 f"never set in")

    def test_the_next_round_is_a_new_unfinished_record(self):
        self.assertNotEqual(self.next.id, self.task.id)
        self.assertFalse(self.next.done)
        self.assertIsNone(self.next.completed_at)
        self.assertGreater(self.next.scheduled_for, self.task.scheduled_for)


class HandoffLeakTests(unittest.TestCase):
    """The bug this file was written for, asserted as behaviour rather than
    as field values."""

    def test_the_next_round_does_not_claim_to_be_out_with_an_agent(self):
        nxt = a_repeating_task().next_instance("2026-08-19")
        self.assertFalse(nxt.is_waiting())
        row = task_row(nxt)
        self.assertNotIn("Waiting on", row.subtitle)
        self.assertNotIn("waiting", [b.text for b in row.badges])
        self.assertNotIn("check back", [b.text for b in row.badges])

    def test_the_next_round_is_offered_as_something_to_start(self):
        """A stale check-back date still ahead of the new round's own date
        used to exclude it from the suggestion slot — measured at thirty
        consecutive rounds for a daily repeat handed over with a thirty-day
        check-back."""
        task = a_repeating_task(repeat="daily", scheduled_for="2026-08-20",
                                follow_up_on="2026-09-18")
        for _ in range(5):
            task = task.next_instance(task.scheduled_for)
            with self.subTest(due=task.scheduled_for):
                self.assertIn(task, rank_for_starting([task],
                                                      on=task.scheduled_for))

    def test_the_claim_does_not_compound_over_rounds(self):
        """Each round copies the last, so an inherited mark would live for
        ever rather than for one round."""
        task = a_repeating_task()
        for round_number in range(1, 7):
            task = task.next_instance(task.scheduled_for)
            with self.subTest(round=round_number):
                self.assertFalse(task.is_waiting())

    def test_a_handoff_on_a_one_off_task_is_untouched(self):
        """Only the *next round* is not out with anyone. This one still is."""
        task = a_repeating_task(repeat="")
        self.assertTrue(task.is_waiting())
        self.assertIsNone(task.next_instance("2026-08-19"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
