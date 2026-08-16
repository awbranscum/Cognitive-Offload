"""The porting guide has to stay true, so the code checks it.

A document describing an interface is worth having only while it is accurate.
Left unchecked it decays quietly: someone moves a module across the line, or
fixes one of the hazards, and the file keeps confidently describing a codebase
that no longer exists — which is worse than having no guide, because a reader
trusts it.

So the specific, checkable claims in ``docs/PORTING.md`` are asserted here
against the source. When one of them stops being true this fails, and the
choice becomes explicit: correct the document, or reconsider the change.

Only claims a porter would be *harmed* by getting wrong are pinned. Line counts
and rough totals are deliberately left loose — they drift for good reasons, and
a test that fails on every honest addition is a test people learn to delete.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "PORTING.md"
APP = REPO / "cognitive_offload" / "app.py"
DIALOGS = REPO / "cognitive_offload" / "dialogs.py"


def doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


class PortingDocExistsTests(unittest.TestCase):
    def test_the_guide_is_present_and_says_something(self):
        self.assertTrue(DOC.exists(), "docs/PORTING.md is referenced by the tests")
        self.assertGreater(len(doc_text()), 2000)


class PortableSetTests(unittest.TestCase):
    """The table of display-free modules must match the enforced list."""

    def test_the_table_names_exactly_the_guarded_portable_modules(self):
        from tests.test_portability import PORTABLE

        text = doc_text()
        # The table rows look like: | `models` | what a task is ... |
        listed = set(re.findall(r"^\| `([a-z_]+)` \|", text, re.M))
        self.assertEqual(
            listed, set(PORTABLE),
            "docs/PORTING.md's table and tests/test_portability.PORTABLE "
            "disagree about which modules need no display",
        )

    def test_the_guide_points_at_presenter_as_the_one_to_read_first(self):
        self.assertIn("presenter", doc_text())
        # Whitespace-tolerant: the sentence is allowed to wrap.
        self.assertRegex(
            " ".join(doc_text().split()),
            r"[Dd]o not build a second view-model layer",
            "the warning against a rival presentation layer must survive",
        )


class HazardTests(unittest.TestCase):
    """Each hazard is a real property of the code, not a general caution."""

    def test_the_ask_over_focus_count_is_still_nine(self):
        """Stated exactly, because a porter builds a set from it.

        Generalising this wrapper to every modal site is a behaviour change
        dressed as a refactor, so the number has to be right.
        """
        actual = len(re.findall(r"with self\._ask_over_focus\(\)", APP.read_text()))
        claimed = int(re.search(r"It wraps exactly \*\*(\d+)\*\* of the",
                                doc_text()).group(1))
        self.assertEqual(actual, claimed)

    def test_the_ask_surface_counts_match_the_code(self):
        app = APP.read_text()
        # Flattened so the counts can be stated across a line break.
        text = " ".join(doc_text().split())

        def claimed(pattern):
            return int(re.search(pattern, text).group(1))

        dialogs = len(re.findall(r"^class \w+Dialog", DIALOGS.read_text(), re.M)) - 1
        self.assertEqual(dialogs, claimed(r"\*\*(\d+) rich dialogs\*\*"),
                         "dialog count excludes the shared ModalDialog base")
        self.assertEqual(len(re.findall(r"messagebox\.\w+", app)),
                         claimed(r"\*\*(\d+) `messagebox` calls\*\*"))
        self.assertEqual(len(re.findall(r"filedialog\.\w+", app)),
                         claimed(r"\*\*(\d+) `filedialog` calls\*\*"))

    def test_save_config_really_does_read_the_spinbox(self):
        """If this stops being true the hazard section is misleading."""
        self.assertIn("self.config_store.focus_minutes = self._minutes()",
                      APP.read_text())
        self.assertIn("_save_config", doc_text())

    def test_the_clock_hazard_names_both_clocks(self):
        text = doc_text()
        self.assertIn("CLOCK_BOOTTIME", text)
        self.assertIn("time.monotonic", text)
        # And the desktop really does still hand monotonic to the timer.
        self.assertIn("time.monotonic()", APP.read_text())


class ReadmeLayoutTests(unittest.TestCase):
    """The README's project layout must list every module that exists.

    It had quietly fallen three modules behind before this test existed, which
    is the same decay the porting guide is guarded against — a reader trusts a
    layout diagram precisely because it looks exhaustive.
    """

    def test_every_module_appears_in_the_project_layout(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        layout = readme.split("## Project layout")[1].split("```")[1]
        modules = {p.stem for p in (REPO / "cognitive_offload").glob("*.py")
                   if p.stem not in {"__init__", "__main__"}}
        missing = sorted(m for m in modules if f"{m}.py" not in layout)
        self.assertEqual(missing, [],
                         "modules exist but are absent from the README layout")

    def test_the_layout_lists_nothing_that_has_been_deleted(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        layout = readme.split("## Project layout")[1].split("```")[1]
        listed = set(re.findall(r"^\s{4}(\w+)\.py", layout, re.M))
        actual = {p.stem for p in (REPO / "cognitive_offload").glob("*.py")}
        self.assertEqual(sorted(listed - actual), [],
                         "the README layout names modules that no longer exist")


class HonestyTests(unittest.TestCase):
    def test_the_blocking_fact_is_stated_not_buried(self):
        """The guide must not imply a phone build is a packaging exercise."""
        head = doc_text().split("## What you get for free")[0]
        self.assertIn("cannot ship on Google Play", head)
        self.assertIn("zero-dependency", head)

    def test_the_layout_is_named_as_work_nobody_can_shorten(self):
        self.assertRegex(doc_text(), r"No seam makes those portable")


if __name__ == "__main__":
    unittest.main()
