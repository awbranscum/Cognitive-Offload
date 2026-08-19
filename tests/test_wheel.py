"""A stray scroll must never change what a task says.

ttk binds the mouse wheel to ``ttk::combobox::Scroll``, so one notch with the
pointer merely *over* a combobox changes its value — no click, no focus.
Measured in the running app with three tasks on screen: one notch over the
"feel" filter moved it to "Urgent sprint" and the list went to **zero rows**,
with nothing saying why. This app's own rule is that hiding a task is the one
thing it will not do.

Three of the six comboboxes change saved data rather than the view, and the
worst is "Repeats": a stray notch there makes a task recur for ever.

So these tests find the comboboxes rather than listing them. A seventh added
next year is covered the moment it exists, which is the whole reason the fix
is a class binding and not six calls — this project has watched four
hand-written per-site lists go stale already.
"""

import tempfile
import unittest
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # pragma: no cover - depends on the interpreter build
    tk = None


def _display_available() -> bool:
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


def _combos(widget) -> list:
    """Every ttk.Combobox anywhere inside, at any depth."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Combobox):
            found.append(child)
        found.extend(_combos(child))
    return found


def _one_notch(widget, up: bool = False) -> None:
    """A single wheel event, delivered where the widget actually is.

    One event, not a sequence: a probe that sends down-then-up measures their
    sum and reports "unchanged" about a widget that moved twice. That very
    mistake nearly filed this bug as safe.
    """
    widget.event_generate("<Button-4>" if up else "<Button-5>", x=5, y=5,
                          rootx=widget.winfo_rootx() + 5,
                          rooty=widget.winfo_rooty() + 5)
    widget.update()


@unittest.skipUnless(_display_available(), "tkinter display not available")
class MainWindowTests(unittest.TestCase):
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
        self.app.withdraw()
        self.addCleanup(self._destroy)
        for text in ("Ring the dentist", "Write the report", "Tidy the desk"):
            self.app.capture_entry.insert(0, text)
            self.app.add_task_from_capture()
        self.app.refresh_tasks()
        self.app.update()

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def test_the_app_still_has_comboboxes_to_protect(self):
        """Guard the guard: if the walk finds none, every test below passes
        by looking at nothing."""
        self.assertGreaterEqual(len(_combos(self.app)), 3)

    def test_no_combobox_changes_when_the_wheel_goes_over_it(self):
        for combo in _combos(self.app):
            for up in (False, True):
                before = combo.get()
                _one_notch(combo, up=up)
                with self.subTest(values=combo.cget("values"), up=up):
                    self.assertEqual(combo.get(), before)

    def test_the_task_list_does_not_empty_itself(self):
        """The symptom that matters, asserted as behaviour rather than as a
        widget value: three tasks in, three tasks still on screen."""
        before = self.app.task_list.size()
        self.assertEqual(before, 3)
        for combo in _combos(self.app):
            _one_notch(combo)
        self.app.update()
        self.assertEqual(self.app.task_list.size(), before,
                         "a stray scroll hid tasks")

    def test_the_saved_sort_order_is_not_rewritten(self):
        before = self.app.config_store.sort_order
        for combo in _combos(self.app):
            _one_notch(combo)
        self.app.update()
        self.assertEqual(self.app.config_store.sort_order, before)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class DialogTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _dialogs(self):
        from cognitive_offload.dialogs import HandoffDialog, TaskEditorDialog

        made = [
            TaskEditorDialog(self.root, title="Write the report",
                             kind="admin", repeat="weekly", with_tags=True),
            HandoffDialog(self.root, "Chase the claim"),
        ]
        for dialog in made:
            self.addCleanup(dialog.destroy)
            dialog.update_idletasks()
            dialog._fit_to_content()
            dialog.deiconify()
            dialog.update()
        return made

    def test_no_dialog_combobox_changes_either(self):
        for dialog in self._dialogs():
            combos = _combos(dialog)
            self.assertTrue(combos, f"{type(dialog).__name__} has none to check")
            for combo in combos:
                for up in (False, True):
                    before = combo.get()
                    _one_notch(combo, up=up)
                    with self.subTest(dialog=type(dialog).__name__, up=up,
                                      values=combo.cget("values")):
                        self.assertEqual(combo.get(), before)

    def test_what_the_editor_collects_is_what_was_set(self):
        """The end of the story rather than the middle: a scrolled dialog
        must save the feel and the repeat it was opened with."""
        editor = self._dialogs()[0]
        for combo in _combos(editor):
            _one_notch(combo)
        editor.update()
        result = editor.collect()
        self.assertEqual(result["kind"], "admin")
        self.assertEqual(result["repeat"], "weekly")

    def test_the_wheel_now_scrolls_the_form_instead(self):
        """The event is not swallowed, it is handed on. Scrolling with the
        pointer over a combobox was a reasonable thing to be doing."""
        from cognitive_offload.dialogs import TaskEditorDialog

        dialog = TaskEditorDialog(self.root, title="t", with_tags=True,
                                  snoozed_until="2099-01-01", content="notes",
                                  first_step="find it",
                                  rest_of_plan=["reread it", "ring them"])
        self.addCleanup(dialog.destroy)
        dialog.update_idletasks()
        dialog._fit_to_content()
        dialog.geometry("520x520")
        dialog.deiconify()
        dialog.update()
        dialog._canvas.yview_moveto(0)
        dialog.update()
        combo = _combos(dialog)[0]
        _one_notch(combo)
        self.assertGreater(dialog._canvas.yview()[0], 0.0,
                           "the wheel was swallowed rather than handed on")

    def test_the_dropdown_list_is_left_alone(self):
        """The popdown is a different class, and it is the one place a wheel
        over a combobox should still do something."""
        self.assertEqual(self.root.bind_class("ComboboxPopdownFrame",
                                              "<MouseWheel>"), "")


@unittest.skipUnless(_display_available(), "tkinter display not available")
class TheFixItselfTests(unittest.TestCase):
    def test_every_wheel_sequence_is_covered(self):
        """X sends Button-4/5 and Windows sends MouseWheel. Covering one and
        not the other fixes the bug on the tester's machine only."""
        from cognitive_offload.theme import WHEEL_EVENTS, apply_theme

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        apply_theme(root, "light")
        self.assertEqual(set(WHEEL_EVENTS),
                         {"<MouseWheel>", "<Button-4>", "<Button-5>"})
        for sequence in WHEEL_EVENTS:
            with self.subTest(sequence=sequence):
                self.assertTrue(root.bind_class("TCombobox", sequence),
                                "ttk's own binding is still in place")

    def test_it_is_installed_by_applying_the_theme(self):
        """So it is on before any combobox exists, and stays on across a
        theme switch."""
        from cognitive_offload.theme import apply_theme

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        for name in ("light", "dark", "light"):
            apply_theme(root, name)
            combo = ttk.Combobox(root, values=["a", "b", "c"], state="readonly")
            combo.set("a")
            combo.pack()
            root.update()
            _one_notch(combo)
            with self.subTest(theme=name):
                self.assertEqual(combo.get(), "a")
            combo.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
