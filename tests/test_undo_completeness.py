"""Ctrl+Z has to put back everything the action took.

`push_undo` snapshots two things: the task list and the step log. Anything
else an action touches — the matrix files, the completed-tasks log, the
scratchpad — has to be restored by a callable handed to `attach_undo`, or
undo puts half the change back and leaves the other half standing.

That is the same shape as the four stale field lists this codebase spent a
release curing: a hand-written correspondence with nothing checking it. So
this reads the source instead. Every function that pushes an undo entry and
also touches a store the snapshot does not hold must either attach a restore
or be named below with a reason.

It catches nothing today. That is the point of writing it now rather than
after the next one.
"""

import ast
import unittest
from pathlib import Path

APP = Path("cognitive_offload/app.py")

#: Attributes that are state the undo snapshot does NOT hold. `tasks` and
#: `steps_log` are absent on purpose: those two ARE the snapshot.
OUTSIDE_THE_SNAPSHOT = {
    "matrix": "the quadrant files on disk",
    "_matrix_cache": "the quadrant rows held in memory",
    "completed_log": "what was finished and then cleared away",
    "note_text": "the scratchpad",
    "session_log": "the record of focus blocks",
    "config_store": "saved preferences",
}

#: ...and the methods that reach the same state without naming the attribute.
#: `clear_notes` writes the scratchpad through `set_scratchpad`, so watching
#: `note_text` alone would have let a scratchpad-clobbering action through
#: with no restore — the blind spot a net has to be checked for rather than
#: assumed out of.
WRITERS_OUTSIDE = {
    "set_scratchpad": "the scratchpad",
    "append_scratchpad": "the scratchpad",
}

#: Functions that push an undo entry, touch one of the above, and still do
#: not attach a restore — each with the reason it is right not to.
ALLOWED = {
    "copy_matrix_to_tasks":
        "reads the quadrant cache to copy FROM it and leaves the files "
        "untouched, so there is nothing on that side to put back",
    "begin_focus":
        "reads config_store for the session length and the ladder; it does "
        "not write to it before the undo entry is pushed",
    "_finish_session":
        "banks a focus session, and un-banking fifteen minutes you actually "
        "spent is not what Ctrl+Z is for. It only scrolls the scratchpad into "
        "view (`note_text.see`) rather than writing to it, and reads "
        "config_store for the break length",
}


def _functions():
    tree = ast.parse(APP.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _calls(node):
    return {n.func.attr for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


def _touches(node):
    named = {n.attr for n in ast.walk(node)
             if isinstance(n, ast.Attribute) and n.attr in OUTSIDE_THE_SNAPSHOT}
    return named | (_calls(node) & set(WRITERS_OUTSIDE))


def pushers():
    """Every function that opens an undo entry, with what it reaches for."""
    found = {}
    for node in _functions():
        calls = _calls(node)
        if "push_undo" in calls:
            found[node.name] = (calls, _touches(node), node.lineno)
    return found


class UndoCompletenessTests(unittest.TestCase):
    def test_there_are_undo_pushers_to_check(self):
        """A net that finds nothing to look at is not passing, it is absent."""
        self.assertGreaterEqual(len(pushers()), 10)

    def test_every_pusher_that_reaches_outside_restores_it(self):
        for name, (calls, outside, line) in sorted(pushers().items()):
            if not outside or name in ALLOWED:
                continue
            with self.subTest(name):
                self.assertIn(
                    "attach_undo", calls,
                    f"{name} (app.py:{line}) pushes an undo entry and touches "
                    f"{sorted(outside)}, which the snapshot does not hold. "
                    "Attach a restore, or add it to ALLOWED with the reason "
                    "it does not need one.")

    def test_every_exemption_names_a_function_that_still_exists(self):
        names = set(pushers())
        for name in ALLOWED:
            with self.subTest(name):
                self.assertIn(name, names,
                              "an exemption for a function that no longer "
                              "pushes an undo entry — stale")

    def test_every_exemption_still_needs_to_be_one(self):
        """An exemption that has quietly started attaching a restore is a
        comment claiming something untrue about the code beside it."""
        for name, (calls, outside, _line) in pushers().items():
            if name not in ALLOWED:
                continue
            with self.subTest(name):
                self.assertTrue(
                    outside,
                    f"{name} no longer touches anything outside the snapshot "
                    "— take it off ALLOWED")
                self.assertNotIn(
                    "attach_undo", calls,
                    f"{name} attaches a restore now — take it off ALLOWED")

    def test_every_exemption_carries_a_reason(self):
        for name, reason in ALLOWED.items():
            with self.subTest(name):
                self.assertTrue(reason.strip(),
                                "an exemption without a reason is an oversight "
                                "wearing a badge")

    def test_the_state_list_matches_what_the_snapshot_holds(self):
        """`push_undo`'s own arguments are the definition of "inside".

        If a third thing is ever snapshotted, it must leave this list — and if
        one is dropped from the snapshot, it must join it.
        """
        [push] = [n for n in _functions() if n.name == "push_undo"]
        snapshotted = {n.attr for n in ast.walk(push)
                       if isinstance(n, ast.Attribute)}
        self.assertIn("tasks", snapshotted)
        self.assertIn("steps_log", snapshotted)
        for name in set(OUTSIDE_THE_SNAPSHOT) | set(WRITERS_OUTSIDE):
            self.assertNotIn(
                name, snapshotted,
                f"{name} is snapshotted now — it is not outside any more")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
