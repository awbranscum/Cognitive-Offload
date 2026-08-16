"""The undo stack, tested without a display."""

import unittest

from cognitive_offload.undo import UndoStack


class UndoStackTests(unittest.TestCase):
    def test_push_pop_round_trip(self):
        stack = UndoStack()
        stack.push("delete", ["snapshot"])
        entry = stack.pop()
        self.assertEqual(entry.label, "delete")
        self.assertEqual(entry.snapshot, ["snapshot"])
        self.assertIsNone(entry.restore)

    def test_pop_on_empty_is_none_not_an_error(self):
        self.assertIsNone(UndoStack().pop())

    def test_attach_pairs_a_side_effect_with_the_latest_entry(self):
        stack = UndoStack()
        ran = []
        stack.push("first", [])
        stack.push("second", [])
        stack.attach(lambda: ran.append("side effect"))
        stack.pop().restore()
        self.assertEqual(ran, ["side effect"])
        self.assertIsNone(stack.pop().restore)  # first entry untouched

    def test_attach_on_empty_is_a_quiet_no_op(self):
        UndoStack().attach(lambda: None)  # must not raise

    def test_the_limit_drops_the_oldest(self):
        stack = UndoStack(limit=3)
        for n in range(5):
            stack.push(str(n), [])
        self.assertEqual(len(stack), 3)
        labels = [stack.pop().label for _ in range(3)]
        self.assertEqual(labels, ["4", "3", "2"])

    def test_clear_and_truthiness(self):
        stack = UndoStack()
        self.assertFalse(stack)
        stack.push("x", [])
        self.assertTrue(stack)
        stack.clear()
        self.assertFalse(stack)
        self.assertEqual(len(stack), 0)


if __name__ == "__main__":
    unittest.main()
