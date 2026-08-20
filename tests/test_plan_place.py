""""step 2 of 3", and the surfaces that forget to say it.

A task with a plan says where in it you are. That is the whole visible
difference between a task and a wall: being part-way through something is
cheaper to resume than starting, and the number is the evidence.

The sentence is composed in one place (`rows.step_with_place`) because it was
composed in two, and the third surface to want it — the pop-out, the one that
is up *while you work* — quietly said only half of it, while
`focus_caption`'s docstring claimed the pop-out was covered.

So this is a net rather than a list of assertions: every surface that names a
step is checked for the place, and a surface that deliberately leaves it out
has to be named here with a reason.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cognitive_offload.models import Task
from cognitive_offload.rows import plan_place, step_with_place

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None


class ComposerTests(unittest.TestCase):
    def test_a_step_in_a_plan_says_where(self):
        self.assertEqual(step_with_place("copy the headings", "step 2 of 3"),
                         "copy the headings · step 2 of 3")

    def test_a_step_with_no_plan_is_left_alone(self):
        self.assertEqual(step_with_place("copy the headings", ""),
                         "copy the headings")

    def test_no_step_means_no_sentence(self):
        self.assertEqual(step_with_place("", "step 2 of 3"), "")

    def test_it_counts_what_exists_never_what_is_missing(self):
        # "step 2 of 3", never "1 left". A count of what remains is a debt.
        task = Task(text="Write the quarterly report")
        task.set_current_step("open last year's report")
        task.set_rest(["copy the headings across", "fill in this year's numbers"])
        task.advance_step()
        said = step_with_place(task.first_step, plan_place(task))
        self.assertIn("step 2 of 3", said)
        self.assertNotIn("left", said)
        self.assertNotIn("remaining", said)


def _display_available():
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_display_available(), "tkinter display not available")
class EverySurfaceSaysItTests(unittest.TestCase):
    """The net. A surface that names a step names the place with it."""

    #: name -> what that surface is showing, read after a session has started
    #: on a task sitting on step 2 of 3.
    SURFACES = {
        "the list row": lambda app: app.task_list.get(0),
        "the focus card": lambda app: app.focus_task_var.get(),
        "the pop-out": lambda app: app._focus_window.step_var.get(),
        # Read before the session starts, and stored: a block running on the
        # only task rightly empties the strip — "what should I start?" is
        # never answered by the thing you are already doing — so reading it
        # afterwards would be measuring that rule instead of this one.
        "the NEXT UP strip": lambda app: app._next_up_before_the_session,
    }

    #: Surfaces that show a step WITHOUT the place, and why. Emptying this
    #: dict is not the goal — being deliberate about it is.
    EXEMPT = {
        "the NEXT UP strip":
            "an open question for the owner rather than a decision: the strip "
            "is the one card the app keeps deliberately lightest, and 'step 2 "
            "of 3' there would say 'you have already started this', which is "
            "an argument for including it. Not mine to settle.",
    }

    def setUp(self):
        from cognitive_offload.app import CognitiveOffloadApp
        from cognitive_offload.storage import Config

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        config = Config(root / "config.json")
        config.db_path = root / "db"
        config.matrix_db_path = root / "matrix"
        self.app = CognitiveOffloadApp(config=config)
        self.addCleanup(self._destroy)
        self.app.deiconify()
        self.app.capture_entry.insert(0, "Write the quarterly report")
        self.app.add_task_from_capture()
        self.task = self.app.tasks[0]
        self.task.set_current_step("open last year's report")
        self.task.set_rest(["copy the headings across",
                            "fill in this year's numbers"])
        self.task.advance_step()
        self.app.refresh_all()
        self._next_up_before = self.app.next_step_var.get()
        self.app._next_up_before_the_session = self._next_up_before
        self.app.task_list.selection_set(0)
        with mock.patch("cognitive_offload.app.StartFocusDialog") as dialog:
            # The step it was SHOWN, not an empty string: an empty one makes
            # focus_caption fall back to the bare title and the whole net
            # would then be measuring its own fixture.
            dialog.return_value.show.return_value = {
                "minutes": 15, "warmup": None, "first_step": self.task.first_step,
                "steps": [], "popout": True}
            self.app.focus_on_selected()
        self.app.update()
        self.place = plan_place(self.task)
        self.assertEqual(self.place, "step 2 of 3")

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def test_every_surface_naming_a_step_names_the_place(self):
        for name, read in self.SURFACES.items():
            if name in self.EXEMPT:
                continue
            with self.subTest(name):
                self.assertIn(self.place, read(self.app))

    def test_the_surfaces_really_are_showing_the_step(self):
        """Otherwise the net passes by finding nothing at all — a renamed
        widget variable would empty every string and every assertion above
        would still hold if it were written the other way round."""
        for name, read in self.SURFACES.items():
            with self.subTest(name):
                self.assertIn(self.task.first_step, read(self.app))

    def test_the_exempt_surfaces_are_exempt_on_purpose(self):
        for name in self.EXEMPT:
            with self.subTest(name):
                self.assertIn(name, self.SURFACES,
                              "an exemption for a surface that no longer exists")
                self.assertTrue(self.EXEMPT[name].strip(),
                                "an exemption without a reason is an oversight "
                                "wearing a badge")
                self.assertNotIn(self.place, self.SURFACES[name](self.app),
                                 "this surface says the place now — take it "
                                 "off the exempt list")


class DialogsAreAskedForItTests(unittest.TestCase):
    """The two surfaces that are dialogs, checked at the call site.

    Read out of the source, so it runs headless and so a third dialog added
    later is caught the day it appears rather than the day someone opens it.
    """

    DIALOGS = ("StartFocusDialog", "SessionEndDialog")

    def _calls(self, name):
        import ast
        from pathlib import Path as _Path

        tree = ast.parse(_Path("cognitive_offload/app.py").read_text())
        return [node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name]

    def test_every_call_site_passes_the_place(self):
        for name in self.DIALOGS:
            calls = self._calls(name)
            with self.subTest(name):
                self.assertTrue(calls, f"{name} is not called from app.py any "
                                       "more — has this net gone stale?")
                for call in calls:
                    self.assertIn("place", [kw.arg for kw in call.keywords],
                                  f"{name} at line {call.lineno} shows a step "
                                  "without saying where in the plan it is")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
