"""Moving a task between the two tabs must not quietly lose part of it.

Both conversions used to *say* they were total — `add_from_task` promised to
move a task "without dropping any fields" and `to_task` promised to keep
"every field" — and both were false, because each is a hand-written list of
assignments and nothing checked the list against the models.

So these tests are keyed on ``dataclasses.fields()`` rather than on a list of
field names written out again here. A field added to either model in future
must be either carried across or **named below as deliberately per-side**.
That is the whole point: the previous version of this promise was a docstring,
and a docstring cannot fail.
"""

import dataclasses
import tempfile
import unittest
from pathlib import Path

from cognitive_offload.models import MatrixTask, Task
from cognitive_offload.storage import MatrixStore

# The two models name the same thing differently in two places.
RENAMED = {"text": "title", "description": "content"}

# Fields that deliberately do NOT cross, each with the reason it does not.
# Adding a name here is a decision, not a shortcut — which is why the test
# below refuses to accept a name that is not actually a field.
TASK_ONLY = {
    "id": "a move creates a new record; the old id belongs to the old file",
    "created_at": "reset on purpose — see test_the_age_reset_is_deliberate",
    "done": "the matrix has no done state at all",
    "completed_at": "meaningless without 'done'",
}
MATRIX_ONLY = {
    "id": "as above, in the other direction",
    "created_at": "as above",
    "category": "which quadrant it sits in — nothing to hold it on the main list",
    "path": "the file backing it; assigned by the store, never part of the data",
    "updated_at": "a storage timestamp, not something the person wrote",
}


def fully_populated_task() -> Task:
    """A task with **every** field set away from its default.

    A field left at its default compares equal after being dropped entirely,
    so a fixture built from defaults would pass no matter how broken the
    conversion was. `test_the_fixture_leaves_nothing_at_its_default` is the
    guard that keeps that from rotting back in.
    """
    return Task(
        text="Chase the insurance claim appeal",
        description="They rejected it on 2 Aug; the deadline is in the email.",
        created_at="2026-01-02T03:04:05",
        completed_at="2026-01-03T04:05:06",
        done=True,
        priority=1,
        tags=["admin", "phone"],
        first_step="find the claim number",
        kind="admin",
        scheduled_for="2026-08-21",
        pinned=True,
        snoozed_until="2026-08-20",
        estimate_minutes=25,
        repeat="weekly",
        handed_to="Claude Desktop",
        handed_off_on="2026-08-19",
        follow_up_on="2026-08-22",
        steps=["find the claim number", "reread the rejection letter",
               "ring them and ask for a supervisor"],
        steps_done=1,
    )


def fully_populated_matrix_task() -> MatrixTask:
    return MatrixTask(
        title="Chase the insurance claim appeal",
        content="They rejected it on 2 Aug.",
        category="delegate",
        created_at="2026-01-02T03:04:05",
        updated_at="2026-01-02T03:04:06",
        first_step="find the claim number",
        kind="admin",
        scheduled_for="2026-08-21",
        tags=["admin", "phone"],
        priority=1,
        pinned=True,
        estimate_minutes=25,
        repeat="weekly",
        handed_to="Claude Desktop",
        handed_off_on="2026-08-19",
        follow_up_on="2026-08-22",
        snoozed_until="2026-08-20",
        steps=["find the claim number", "reread the rejection letter",
               "ring them and ask for a supervisor"],
        steps_done=1,
    )


def names(model) -> set:
    return {f.name for f in dataclasses.fields(model)}


class FixtureGuardTests(unittest.TestCase):
    """Guard the guard: these fixtures decide what the round-trip tests can
    even see."""

    def test_the_fixture_leaves_nothing_at_its_default(self):
        for build, model in ((fully_populated_task, Task),
                             (fully_populated_matrix_task, MatrixTask)):
            built = build()
            for f in dataclasses.fields(model):
                if f.name == "path":
                    continue  # assigned by the store, never by a caller
                default = (f.default_factory() if f.default_factory
                           is not dataclasses.MISSING else f.default)
                if default is dataclasses.MISSING:
                    continue  # a required field is always set
                with self.subTest(model=model.__name__, field=f.name):
                    self.assertNotEqual(
                        getattr(built, f.name), default,
                        f"{f.name} is still at its default, so dropping it "
                        f"entirely would pass this suite",
                    )

    def test_the_exemption_lists_name_only_real_fields(self):
        """A renamed field must not silently widen the exemption."""
        self.assertEqual(set(TASK_ONLY) - names(Task), set())
        self.assertEqual(set(MATRIX_ONLY) - names(MatrixTask), set())

    def test_every_exemption_carries_a_reason(self):
        for reason in list(TASK_ONLY.values()) + list(MATRIX_ONLY.values()):
            self.assertTrue(reason.strip())


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = MatrixStore(Path(self._tmp.name))
        self.store.ensure()

    def test_a_task_survives_a_round_trip_through_the_matrix(self):
        """Send to matrix, send back: everything the person wrote is still
        there. This is what both docstrings claim, asserted against the
        models rather than against a list someone remembered to update."""
        before = fully_populated_task()
        created = self.store.add_from_task("do_first", before)
        after = created.to_task()
        for name in sorted(names(Task) - set(TASK_ONLY)):
            with self.subTest(field=name):
                self.assertEqual(
                    getattr(after, name), getattr(before, name),
                    f"{name} was lost moving a task to the matrix and back",
                )

    def test_a_matrix_task_survives_a_round_trip_through_the_main_list(self):
        before = fully_populated_matrix_task()
        after = self.store.add_from_task(before.category, before.to_task())
        for name in sorted(names(MatrixTask) - set(MATRIX_ONLY)):
            with self.subTest(field=name):
                self.assertEqual(
                    getattr(after, name), getattr(before, name),
                    f"{name} was lost moving a matrix task to the list and back",
                )

    def test_the_round_trip_also_survives_the_disk(self):
        """The in-memory object is not the thing that comes back — the file
        is. A field carried by the conversion but missing from to_dict would
        pass the tests above and still be lost by morning."""
        before = fully_populated_task()
        self.store.add_from_task("do_first", before)
        reloaded = self.store.list("do_first")[0]
        after = reloaded.to_task()
        for name in sorted(names(Task) - set(TASK_ONLY)):
            with self.subTest(field=name):
                self.assertEqual(getattr(after, name), getattr(before, name),
                                 f"{name} did not survive being written out")

    def test_every_shared_field_really_is_shared(self):
        """Neither model may quietly grow a field the other has no home for
        without it being a recorded decision."""
        task_side = {RENAMED.get(n, n) for n in names(Task) - set(TASK_ONLY)}
        matrix_side = names(MatrixTask) - set(MATRIX_ONLY)
        self.assertEqual(
            task_side - matrix_side, set(),
            "on Task with nowhere to live on MatrixTask — carry it, or add it "
            "to TASK_ONLY with a reason",
        )
        back = {v: k for k, v in RENAMED.items()}
        self.assertEqual(
            {back.get(n, n) for n in matrix_side} - (names(Task) - set(TASK_ONLY)),
            set(),
            "on MatrixTask with nowhere to live on Task — carry it, or add it "
            "to MATRIX_ONLY with a reason",
        )


class DeliberateLossTests(unittest.TestCase):
    """The exemptions are decisions, so they get tests too — otherwise the
    list becomes a place to hide a bug."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = MatrixStore(Path(self._tmp.name))
        self.store.ensure()

    def test_a_finished_task_arrives_in_the_matrix_as_something_to_do(self):
        """The matrix has no done state, so a done task moved there is open
        again. Not a data loss — there is nowhere to put it."""
        task = fully_populated_task()
        self.assertTrue(task.done)
        back = self.store.add_from_task("do_first", task).to_task()
        self.assertFalse(back.done)
        self.assertIsNone(back.completed_at)

    def test_the_move_makes_a_new_record_rather_than_reusing_the_id(self):
        task = fully_populated_task()
        created = self.store.add_from_task("do_first", task)
        self.assertNotEqual(created.id, task.id)

    def test_the_age_reset_is_deliberate_and_visible(self):
        """`created_at` is reset on a move. That is a real trade — it feeds
        the "older first" tiebreak in rank_for_starting, so a task parked in
        the matrix comes back looking new. Recorded here so the behaviour
        cannot change by accident in either direction."""
        task = fully_populated_task()
        back = self.store.add_from_task("do_first", task).to_task()
        self.assertNotEqual(back.created_at, task.created_at)
        self.assertGreater(back.created_at, task.created_at)


class DocstringTests(unittest.TestCase):
    """The bug this file exists for was two docstrings making a promise the
    code stopped keeping. They are not allowed to make it loosely again."""

    def test_neither_conversion_claims_more_than_it_does(self):
        for func in (MatrixStore.add_from_task, MatrixTask.to_task):
            doc = (func.__doc__ or "").lower()
            with self.subTest(func=func.__qualname__):
                self.assertTrue(doc.strip(), "needs a docstring")
                # Unbounded claims only. "carries each field the two models
                # share" is bounded and true; "keeps every field" is the
                # sentence that was false for four releases.
                for overclaim in ("without dropping any fields",
                                  "keeping every field", "keeps every field",
                                  "all fields", "nothing is lost",
                                  "every field it"):
                    self.assertNotIn(
                        overclaim, doc,
                        f"{func.__qualname__} claims totality again; it has "
                        f"documented exceptions ({sorted(TASK_ONLY)})",
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
