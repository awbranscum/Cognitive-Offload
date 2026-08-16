"""The line between the app's brain and its face, enforced.

The model, query, storage, timer and row-building layers were written to
need no display — that is what lets them be tested headless, and it is the
only reason a front-end on another platform could ever reuse them instead
of reimplementing the ranking, the timer rules and the save format.

A property nothing checks is a property that decays: one convenience
import of tkinter inside a core module would cost nothing that day and
quietly end the app's portability. These tests import each core module in
a subprocess with tkinter made unavailable, exactly as it would be on a
platform that has no Tk, and fail if any of them needs it.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The brain: decisions, data and rules that any front-end would reuse.
PORTABLE = [
    "models",      # what a task is, and how it serialises
    "queries",     # filtering, sorting, and the start-ranking
    "sessions",    # the focus-session log and its day counts
    "storage",     # config, atomic saves, the matrix file store
    "timer",       # the focus/break clock as a pure state machine
    "undo",        # the undo stack
    "viewmodels",  # what a row shows, with no opinion on drawing
    "rows",        # which badges and wording a task has earned
]

# The face: allowed — indeed expected — to need tkinter.
TK_BOUND = ["theme", "widgets", "main_tab", "matrix_tab", "dialogs", "app"]

# Poison the module slot before anything can import it. Blocking via a
# meta-path finder is easy to get wrong: the pre-3.12 find_module/
# load_module protocol is gone, so a finder written that way silently
# blocks nothing and the test passes for the wrong reason.
PROBE = """
import sys
for name in ("tkinter", "tkinter.ttk", "tkinter.font",
             "tkinter.messagebox", "tkinter.filedialog"):
    sys.modules[name] = None
sys.path.insert(0, {repo!r})
import importlib
importlib.import_module("cognitive_offload.{module}")
print("imported")
"""


def _import_without_tk(module: str):
    """Import one module in a fresh interpreter that has no tkinter."""
    return subprocess.run(
        [sys.executable, "-c", PROBE.format(repo=str(REPO), module=module)],
        capture_output=True, text=True, timeout=60,
    )


class PortabilityTests(unittest.TestCase):
    def test_the_core_needs_no_display_toolkit(self):
        """Every brain module imports on a platform with no Tk at all."""
        for module in PORTABLE:
            with self.subTest(module=module):
                result = _import_without_tk(module)
                self.assertEqual(
                    result.returncode, 0,
                    f"cognitive_offload.{module} now needs tkinter, directly or "
                    f"through an import. That ends its portability — move the "
                    f"toolkit-dependent part into the UI layer instead.\n"
                    f"{result.stderr}",
                )

    def test_the_probe_itself_actually_blocks_tkinter(self):
        """Guard the guard: a blocker that blocks nothing passes everything.

        If this fails, the test above proves nothing — it would be importing
        modules with tkinter perfectly available.
        """
        for module in TK_BOUND:
            with self.subTest(module=module):
                result = _import_without_tk(module)
                self.assertNotEqual(
                    result.returncode, 0,
                    f"cognitive_offload.{module} imported without tkinter, so the "
                    f"probe is not blocking anything and the portability test "
                    f"above is meaningless.",
                )

    def test_row_building_runs_with_no_toolkit_present(self):
        """Not just importable — usable. The badge decisions are the part a
        second front-end would reuse, so prove they produce data headless."""
        probe = PROBE.format(repo=str(REPO), module="rows") + """
from cognitive_offload.rows import task_row
from cognitive_offload.models import Task
row = task_row(Task(text="write the appeal", first_step="find the form"))
assert row.title == "write the appeal", row.title
assert any(b.text == "ready" for b in row.badges), row.badges
assert "find the form" in row.as_text()
print("row built with no toolkit")
"""
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("row built with no toolkit", result.stdout)


if __name__ == "__main__":
    unittest.main()
