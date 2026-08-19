"""A stray scroll must never change a value.

ttk binds the mouse wheel to `ttk::combobox::Scroll`, so one notch with the
pointer merely *over* a combobox changed it — no click, no focus. Measured in
the running app with three tasks on screen: one notch over the "feel" filter
moved it to "Urgent sprint" and the list went to **zero rows**, with nothing
saying why. This app's own rule is that hiding a task is the one thing it
will not do.

Fixing that class and stopping was half a fix. `TSpinbox` does exactly the
same thing, and the app has three of them: one notch over the timer's "Min"
box took a session from 15 minutes to 14 and carried it into the running
clock, so the block you agreed to was quietly not the block you got.

So this file does not name the widgets it protects. It **walks the app and
every dialog**, reads the value of anything that has one, and requires every
wheel-bound class it meets to be either checked here or named as one whose
wheel legitimately scrolls. A widget added next year is covered the moment it
exists, and a *class* added to the toolkit fails the suite until someone says
which kind it is — which is the guard that would have caught the spinbox on
the day the combobox was fixed.
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


def _variable_value(widget):
    name = widget.cget("variable")
    return widget.getvar(name) if name else None


#: How to read the value of a widget that holds one, by Tk class name.
#: Anything here is scrolled over and checked.
VALUE_READERS = {
    "TCombobox": lambda w: w.get(),
    "TSpinbox": lambda w: w.get(),
    "TEntry": lambda w: w.get(),
    "Entry": lambda w: w.get(),
    "Spinbox": lambda w: w.get(),
    "TScale": lambda w: w.get(),
    "Scale": lambda w: w.get(),
    "TCheckbutton": _variable_value,
    "TRadiobutton": _variable_value,
}

#: Wheel-bound classes whose binding legitimately SCROLLS, with the reason.
#: A class that is neither here nor in VALUE_READERS fails the net below.
SCROLLS_NOT_A_VALUE = {
    "Text": "its wheel scrolls the text, which is what a wheel is for",
    "Listbox": "as above",
    "TScrollbar": "dragging a scrollbar with the wheel is the same gesture",
    "Treeview": "as above — and the app does not use one",
    "Canvas": "the scrolling surfaces in this app are canvases, and their "
              "wheel handlers are bound per widget rather than per class",
}

WHEEL_EVENTS = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _wheel_bound(widget) -> bool:
    return any(widget.bind_class(widget.winfo_class(), seq)
               for seq in WHEEL_EVENTS)


def _valued(root):
    """Every widget in the tree that holds a readable value."""
    found = []
    for widget in _walk(root):
        reader = VALUE_READERS.get(widget.winfo_class())
        if reader is None:
            continue
        try:
            reader(widget)
        except (tk.TclError, TypeError, ValueError):
            continue
        found.append(widget)
    return found


def _one_notch(widget, up: bool = False) -> None:
    """A single wheel event, delivered where the widget actually is.

    One event, not a sequence: a probe that sends down-then-up measures their
    sum and reports "unchanged" about a widget that moved twice. That very
    mistake nearly filed the combobox bug as safe.
    """
    widget.event_generate("<Button-4>" if up else "<Button-5>", x=5, y=5,
                          rootx=widget.winfo_rootx() + 5,
                          rooty=widget.winfo_rooty() + 5)
    widget.update()


def _scroll_everything(testcase, root, label=""):
    """One notch each way over every widget with a value; nothing may move."""
    widgets = _valued(root)
    testcase.assertTrue(widgets, f"{label}: nothing with a value was found")
    for widget in widgets:
        reader = VALUE_READERS[widget.winfo_class()]
        for up in (False, True):
            before = reader(widget)
            _one_notch(widget, up=up)
            with testcase.subTest(where=label, widget=widget.winfo_class(), up=up):
                testcase.assertEqual(reader(widget), before)
    return widgets


@unittest.skipUnless(_display_available(), "tkinter display not available")
class ClassCoverageTests(unittest.TestCase):
    """The net: every wheel-bound class the app actually contains is either
    checked or named as one that scrolls."""

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
        self.app.update()

    def _destroy(self):
        try:
            self.app.destroy()
        except tk.TclError:
            pass

    def _classes_in(self, root):
        return {w.winfo_class() for w in _walk(root) if _wheel_bound(w)}

    def test_every_wheel_bound_class_present_is_accounted_for(self):
        from cognitive_offload.dialogs import HandoffDialog, TaskEditorDialog

        seen = self._classes_in(self.app)
        for build in (lambda: TaskEditorDialog(self.app, title="t", with_tags=True),
                      lambda: HandoffDialog(self.app, "Chase the claim")):
            dialog = build()
            self.addCleanup(dialog.destroy)
            dialog.update()
            seen |= self._classes_in(dialog)
        known = set(VALUE_READERS) | set(SCROLLS_NOT_A_VALUE)
        self.assertEqual(
            seen - known, set(),
            "a wheel-bound widget class is in the app that nothing has "
            "decided about — read it in VALUE_READERS, or name it in "
            "SCROLLS_NOT_A_VALUE with a reason",
        )

    def test_the_two_that_change_values_are_both_still_neutered(self):
        """Named explicitly as well as walked, because these are the two the
        toolkit gets wrong and the walk would pass if they vanished."""
        from cognitive_offload.theme import VALUE_WHEEL_CLASSES

        self.assertEqual(set(VALUE_WHEEL_CLASSES), {"TCombobox", "TSpinbox"})
        for name in VALUE_WHEEL_CLASSES:
            for sequence in WHEEL_EVENTS:
                with self.subTest(cls=name, sequence=sequence):
                    self.assertTrue(self.app.bind_class(name, sequence),
                                    "ttk's own binding is still in place")

    def test_every_exemption_carries_a_reason(self):
        for reason in SCROLLS_NOT_A_VALUE.values():
            self.assertTrue(reason.strip())

    def test_the_walk_finds_both_kinds_in_the_app(self):
        """Guard the guard: if the walk found neither, every test here would
        pass by looking at nothing."""
        classes = {w.winfo_class() for w in _valued(self.app)}
        self.assertIn("TCombobox", classes)
        self.assertIn("TSpinbox", classes)


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

    def test_nothing_on_the_main_window_changes_when_scrolled(self):
        _scroll_everything(self, self.app, "main window")

    def test_the_task_list_does_not_empty_itself(self):
        """The symptom that matters, asserted as behaviour rather than as a
        widget value: three tasks in, three tasks still on screen."""
        self.assertEqual(self.app.task_list.size(), 3)
        for widget in _valued(self.app):
            _one_notch(widget)
        self.app.update()
        self.assertEqual(self.app.task_list.size(), 3, "a stray scroll hid tasks")

    def test_the_saved_sort_order_is_not_rewritten(self):
        before = self.app.config_store.sort_order
        for widget in _valued(self.app):
            _one_notch(widget)
        self.app.update()
        self.assertEqual(self.app.config_store.sort_order, before)

    def test_the_session_you_agreed_to_is_the_one_you_get(self):
        """The spinbox case: a notch over "Min" took 15 minutes to 14 and
        carried it into the running clock."""
        before_minutes = self.app.work_minutes.get()
        before_total = self.app._timer_total
        for widget in _valued(self.app):
            _one_notch(widget)
        self.app.update()
        self.assertEqual(self.app.work_minutes.get(), before_minutes)
        self.assertEqual(self.app._timer_total, before_total)


@unittest.skipUnless(_display_available(), "tkinter display not available")
class DialogTests(unittest.TestCase):
    def setUp(self):
        from cognitive_offload.theme import apply_theme

        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root, "light")
        self.addCleanup(self.root.destroy)

    def _dialogs(self):
        from cognitive_offload.dialogs import (HandoffDialog, StartFocusDialog,
                                               TaskEditorDialog)

        made = [
            TaskEditorDialog(self.root, title="Write the report",
                             kind="admin", repeat="weekly", with_tags=True),
            HandoffDialog(self.root, "Chase the claim"),
            StartFocusDialog(self.root, task_text="Write the report",
                             first_step="open it", minutes=15),
        ]
        for dialog in made:
            self.addCleanup(dialog.destroy)
            dialog.update_idletasks()
            dialog._fit_to_content()
            dialog.deiconify()
            dialog.update()
        return made

    def test_nothing_in_any_dialog_changes_when_scrolled(self):
        for dialog in self._dialogs():
            _scroll_everything(self, dialog, type(dialog).__name__)

    def test_what_the_editor_collects_is_what_was_set(self):
        """The end of the story rather than the middle: a scrolled dialog
        must save the feel and the repeat it was opened with."""
        editor = self._dialogs()[0]
        for widget in _valued(editor):
            _one_notch(widget)
        editor.update()
        result = editor.collect()
        self.assertEqual(result["kind"], "admin")
        self.assertEqual(result["repeat"], "weekly")

    def test_the_session_length_is_not_shortened_by_a_scroll(self):
        starter = self._dialogs()[2]
        for widget in _valued(starter):
            _one_notch(widget)
        starter.update()
        self.assertEqual(starter.collect()["minutes"], 15)

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
        combo = [w for w in _valued(dialog) if w.winfo_class() == "TCombobox"][0]
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
        from cognitive_offload.theme import WHEEL_EVENTS as APP_EVENTS

        self.assertEqual(set(APP_EVENTS), set(WHEEL_EVENTS))

    def test_it_is_installed_by_applying_the_theme(self):
        """So it is on before any widget exists, and stays on across a theme
        switch."""
        from cognitive_offload.theme import apply_theme

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        for name in ("light", "dark", "light"):
            apply_theme(root, name)
            combo = ttk.Combobox(root, values=["a", "b", "c"], state="readonly")
            combo.set("a")
            combo.pack()
            spin = ttk.Spinbox(root, from_=1, to=120)
            spin.set("15")
            spin.pack()
            root.update()
            _one_notch(combo)
            _one_notch(spin)
            with self.subTest(theme=name):
                self.assertEqual(combo.get(), "a")
                self.assertEqual(spin.get(), "15")
            combo.destroy()
            spin.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
