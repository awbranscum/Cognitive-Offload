"""`first_step` has one writer, and it is not an assignment statement.

A task with a plan **defines** `first_step` as `steps[steps_done]`, and
`models._fix_steps` is the only place that says so. Writing to the attribute
directly is therefore not a small liberty: it leaves the two disagreeing, and
the invariant repairs that on the next load — so the edit survives exactly
until the app is closed and then silently reverts.

That has happened **four times**: the task editor, the matrix editor, the
session-end dialog and the start dialog, each fixed by hand after the fact,
the last of them found only because a mutant survived. `models.py` holds the
invariant; outside it, `x.first_step = y` is ordinary Python and the only
thing standing between a fifth site and the same silent loss was that
somebody grepped once.

So this is a net rather than a memory: every assignment to `.first_step`
outside the model must be **named below with a reason**. Read with `ast`, so
it runs on a box with no Tk.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCHED = ("app.py", "dialogs.py", "rows.py", "presenter.py", "queries.py",
           "storage.py", "handoff.py")

# {(file, function): reason}. A direct write is only ever right when the plan
# is rebuilt around it immediately afterwards.
ALLOWED = {
    ("app.py", "add_matrix_task"):
        "a task that did not exist a moment ago has no plan to disagree with, "
        "and the very next line calls set_rest, which builds the plan around "
        "this value — tests/test_plan.py pins that",
}


def assignments_to_first_step(path: Path):
    """{function name: count} for every `x.first_step = ...` in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {}
    for func in [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        count = 0
        for node in ast.walk(func):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == "first_step":
                    count += 1
        if count:
            found[func.name] = count
    return found


def all_assignments():
    found = {}
    for name in WATCHED:
        path = ROOT / "cognitive_offload" / name
        if not path.exists():
            continue
        for func, count in assignments_to_first_step(path).items():
            found[(name, func)] = count
    return found


class TheNetTests(unittest.TestCase):
    def test_every_direct_write_is_a_decision_someone_made(self):
        for where, count in sorted(all_assignments().items()):
            with self.subTest(file=where[0], function=where[1]):
                self.assertIn(
                    where, ALLOWED,
                    f"{where[1]} in {where[0]} writes .first_step directly "
                    f"({count}x). On a task with a plan that leaves the two "
                    f"disagreeing until the next load silently reverts it — "
                    f"call set_current_step, or add it to ALLOWED with a "
                    f"reason",
                )

    def test_the_exemptions_are_all_still_real(self):
        """A site that has since been fixed must not leave its licence lying
        around for the next person to reuse."""
        self.assertEqual(set(ALLOWED) - set(all_assignments()), set(),
                         "listed as allowed but no longer writes first_step")

    def test_every_exemption_carries_a_reason(self):
        for reason in ALLOWED.values():
            self.assertTrue(reason.strip())

    def test_the_reader_actually_finds_writes(self):
        """Guard the guard: a finder that matched nothing would let every
        site through in silence."""
        source = ROOT / "cognitive_offload" / "models.py"
        self.assertTrue(assignments_to_first_step(source),
                        "the model itself assigns first_step; if this finds "
                        "none, the net is blind")

    def test_the_model_is_where_the_writing_belongs(self):
        """The point of the exercise: the invariant has one home."""
        inside = assignments_to_first_step(ROOT / "cognitive_offload" / "models.py")
        self.assertIn("_fix_steps", inside)
        self.assertIn("_set_current_step", inside)


class TheWayItShouldBeDoneTests(unittest.TestCase):
    """The net says what not to do; this says the alternative works."""

    def test_set_current_step_keeps_the_two_in_step(self):
        from cognitive_offload.models import Task

        task = Task(text="Write the report", first_step="open last year's")
        task.set_rest(["copy the headings"])
        task.set_current_step("open the one from last quarter")
        self.assertEqual(task.steps[0], "open the one from last quarter")
        self.assertEqual(Task.from_dict(task.to_dict()).first_step,
                         "open the one from last quarter")

    def test_a_direct_write_is_reverted_by_the_next_load(self):
        """The failure this net exists to prevent, demonstrated once so the
        cost is on the record rather than in a commit message."""
        from cognitive_offload.models import Task

        task = Task(text="Write the report", first_step="open last year's")
        task.set_rest(["copy the headings"])
        task.first_step = "open the one from last quarter"   # the mistake
        self.assertEqual(Task.from_dict(task.to_dict()).first_step,
                         "open last year's", "the edit did not silently revert")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
