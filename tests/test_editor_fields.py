"""The task editor's fields must reach every caller, in both directions.

Three bugs, one disease. `TaskEditorDialog` is opened from three places and
each one names its arguments by hand, so each hand-written list quietly went
stale as the dialog grew:

* **The matrix editor did not pass `repeat`.** A quadrant task wearing a
  `weekly` badge opened saying *"Does not repeat"* — and since the result was
  not applied either, setting the combobox to "Does not repeat" changed
  nothing. The dialog was not merely incomplete, it was **lying**, and it
  refused the correction.
* **The matrix editor did not pass `handed_to`.** So the take-back checkbox
  never appeared there, and "Take it back" is a Delegate-only button — a
  waiting task moved to any other quadrant had no way out of the mark at all.
* **The matrix add path dropped `estimate_minutes` and `repeat`.** Filled in
  as "about 25 minutes, every week" and saved as neither, silently. The worst
  shape a data loss can take, because the person watched themselves type it.

So this is keyed on the dialog's own signature and on the dict `collect()`
actually returns, both read from the source rather than written out again
here. A field added to the dialog in future fails this suite until every
caller either uses it or is **named below with a reason**. The previous
version of this promise was three people remembering; nobody remembered.

Read with `ast` rather than by importing, so it runs on a box with no Tk.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "cognitive_offload" / "app.py"
DIALOGS = ROOT / "cognitive_offload" / "dialogs.py"

# Not task fields: how the window is labelled, and whether the tag row shows.
NOT_A_FIELD = {"self", "parent", "window_title", "with_tags"}

# A caller that may pass nothing, because it has nothing to pass.
INPUT_EXEMPT = {
    "add_matrix_task": "it creates a task, so every field starts at its "
                       "default — passing anything would be inventing content",
}
# (caller, field) pairs that deliberately do not cross, each with its reason.
INPUT_FIELD_EXEMPT = {
    ("edit_matrix_task", "tags"):
        "a quadrant row shows no tags at all, so the matrix is not where they "
        "are edited; they survive the trip through it untouched, which "
        "tests/test_conversions.py pins",
}
OUTPUT_EXEMPT = {
    ("edit_matrix_task", "tags"): "as above — the dialog is opened without the "
                                  "tag row, so it returns no tags to apply",
    ("add_matrix_task", "tags"): "as above",
    ("add_matrix_task", "clear_snooze"):
        "a task that does not exist yet cannot be excused from suggestions, "
        "so the dialog never draws the control and always returns False",
    ("add_matrix_task", "take_back"): "as above — nothing to take back yet",
}


def tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def functions(node) -> dict:
    return {n.name: n for n in ast.walk(node)
            if isinstance(n, ast.FunctionDef)}


def editor_parameters() -> set:
    """Every task field `TaskEditorDialog.__init__` accepts."""
    for node in ast.walk(tree(DIALOGS)):
        if isinstance(node, ast.ClassDef) and node.name == "TaskEditorDialog":
            init = functions(node)["__init__"]
            args = init.args
            names = [a.arg for a in args.args + args.kwonlyargs]
            return {n for n in names if n not in NOT_A_FIELD}
    raise AssertionError("TaskEditorDialog.__init__ not found")


def collected_keys() -> set:
    """Every key `collect()` puts in the dict it returns."""
    for node in ast.walk(tree(DIALOGS)):
        if isinstance(node, ast.ClassDef) and node.name == "TaskEditorDialog":
            collect = functions(node)["collect"]
            keys = set()
            for sub in ast.walk(collect):
                # result = {...}
                if isinstance(sub, ast.Dict):
                    keys |= {k.value for k in sub.keys
                             if isinstance(k, ast.Constant)
                             and isinstance(k.value, str)}
                # result["tags"] = ...
                if isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if (isinstance(target, ast.Subscript)
                                and isinstance(target.slice, ast.Constant)
                                and isinstance(target.slice.value, str)):
                            keys.add(target.slice.value)
            return keys
    raise AssertionError("TaskEditorDialog.collect not found")


def call_sites() -> dict:
    """{caller name: set of keyword arguments it passes to the editor}."""
    found = {}
    for func in functions(tree(APP)).values():
        for node in ast.walk(func):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "TaskEditorDialog"):
                found[func.name] = {kw.arg for kw in node.keywords if kw.arg}
    return found


def keys_read_by(caller: str) -> set:
    """Every string key the caller reads off a dict — `x["k"]` or `x.get("k")`.

    Deliberately not scoped to a variable called `result`: a rename must not
    quietly turn this net off.
    """
    func = functions(tree(APP))[caller]
    keys = set()
    for node in ast.walk(func):
        if (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            keys.add(node.slice.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    return keys


class NetGuardTests(unittest.TestCase):
    """Guard the guard: a net that found nothing would pass in silence."""

    def test_the_readers_actually_find_something(self):
        self.assertGreaterEqual(len(editor_parameters()), 10)
        self.assertGreaterEqual(len(collected_keys()), 10)
        self.assertEqual(set(call_sites()),
                         {"edit_selected_details", "edit_matrix_task",
                          "add_matrix_task"})

    def test_every_exemption_names_a_real_caller_and_a_real_field(self):
        callers = set(call_sites())
        fields = editor_parameters()
        keys = collected_keys()
        self.assertEqual(set(INPUT_EXEMPT) - callers, set())
        for caller, field in INPUT_FIELD_EXEMPT:
            self.assertIn(caller, callers)
            self.assertIn(field, fields)
        for caller, key in OUTPUT_EXEMPT:
            self.assertIn(caller, callers)
            self.assertIn(key, keys)

    def test_every_exemption_carries_a_reason(self):
        for reason in (list(INPUT_EXEMPT.values())
                       + list(INPUT_FIELD_EXEMPT.values())
                       + list(OUTPUT_EXEMPT.values())):
            self.assertTrue(reason.strip())


class InputTests(unittest.TestCase):
    def test_every_caller_shows_the_task_as_it_actually_is(self):
        fields = editor_parameters()
        for caller, passed in sorted(call_sites().items()):
            if caller in INPUT_EXEMPT:
                continue
            for field in sorted(fields):
                if (caller, field) in INPUT_FIELD_EXEMPT:
                    continue
                with self.subTest(caller=caller, field=field):
                    self.assertIn(
                        field, passed,
                        f"{caller} opens the editor without {field}, so the "
                        f"dialog shows a default where the task has a value "
                        f"— pass it, or add ({caller!r}, {field!r}) to "
                        f"INPUT_FIELD_EXEMPT with a reason",
                    )

    def test_a_creator_is_exempt_only_by_being_named(self):
        """The exemption is for callers with nothing to show, not a way to
        opt out of the net."""
        for caller in INPUT_EXEMPT:
            self.assertEqual(call_sites()[caller] - NOT_A_FIELD, set(),
                             f"{caller} is exempt from passing fields but "
                             f"passes some; it is no longer a creator")


class OutputTests(unittest.TestCase):
    def test_every_caller_applies_everything_the_person_typed(self):
        keys = collected_keys()
        for caller in sorted(call_sites()):
            read = keys_read_by(caller)
            for key in sorted(keys):
                if (caller, key) in OUTPUT_EXEMPT:
                    continue
                with self.subTest(caller=caller, key=key):
                    self.assertIn(
                        key, read,
                        f"{caller} never reads {key!r} from the dialog, so "
                        f"whatever the person put there is discarded without "
                        f"a word — apply it, or add ({caller!r}, {key!r}) to "
                        f"OUTPUT_EXEMPT with a reason",
                    )

    def test_no_caller_reads_a_key_the_dialog_does_not_return(self):
        """The other direction: a typo reads as an empty field for ever."""
        keys = collected_keys()
        for caller in sorted(call_sites()):
            # Only keys that look like dialog fields; a caller reads plenty of
            # other dicts. Anything the dialog returns is the closed set here.
            for key in sorted(keys_read_by(caller) & _NEAR_MISSES):
                with self.subTest(caller=caller, key=key):
                    self.assertIn(key, keys)


#: keys that would be a plausible mistyping of a real one. Kept small on
#: purpose: this test exists to catch `result["repeats"]`, not to police
#: every dict in app.py.
_NEAR_MISSES = {"repeats", "waiting", "waits_on", "checkback", "check_back_on",
                "estimate", "first_steps", "schedule_for", "taken_back"}


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
