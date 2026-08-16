"""Read every user-visible modal string out of the source.

The wording *is* the product. A refactor that moves a question from one module
to another is supposed to carry its words across untouched, and the only way to
know it did is to have written them down first.

This extracts them statically rather than by driving the app, deliberately.
Half these strings live on error paths — a corrupt save file, a vanished
folder, a failed rename — which are awkward to reach and easy to leave
uncovered. A parser reaches all of them equally.

Entries are keyed by *what the string is and where it lives*, never by line
number: line numbers churn on every edit above them, and a safety net that
cries wolf is one people stop reading.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "cognitive_offload"

# Keyword arguments that carry words a person reads.
_TEXT_KEYWORDS = ("text", "title", "message", "window_title", "ok_text", "hint")


def _interpolation(node) -> str:
    """Render one ``{…}`` slot of an f-string.

    Usually ``{}``: a path or a count differs every run while the sentence
    around it is what is under review. But an interpolated *call* can carry
    words of its own — ``{_plural(n, 'completed task')}`` puts the noun
    inside the slot — and dropping those would let someone change "task" to
    "item" without the net noticing. So any string literals inside the
    expression come along.
    """
    words = [n.value for n in ast.walk(node)
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value]
    return "{" + " ".join(words) + "}" if words else "{}"


def _flatten(node) -> str | None:
    """A string literal, or the literal skeleton of an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
            else _interpolation(v)
            for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _flatten(node.left), _flatten(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _owners(tree: ast.AST) -> dict[int, str]:
    """Map every node to the function or class it sits inside."""
    owner: dict[int, str] = {}

    def walk(node, name):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, child.name)
            else:
                owner[id(child)] = name
                walk(child, name)
    walk(tree, "<module>")
    return owner


def _entries_for(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    owner = _owners(tree)
    found: list[str] = []

    # Sentences assigned to a name before being asked. A question built as
    # `title = "Already open"` and passed as a variable is invisible at the
    # call site, and that is exactly the shape wording takes as it moves out
    # of the controller — so the net has to see it, or it would quietly stop
    # covering the strings while appearing to still work.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        text = _flatten(node.value) if node.value is not None else None
        if not text or " " not in text.strip():
            continue  # identifiers, style names and sort keys are not wording
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                where = owner.get(id(node), "<module>")
                found.append(f"{path.name} | {target.id}= | {where} | {text}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        where = owner.get(id(node), "<module>")

        func = node.func
        # messagebox.askyesno("Title", "Body") / filedialog.askdirectory(title=…)
        if isinstance(func, ast.Attribute) and \
                getattr(func.value, "id", None) in ("messagebox", "filedialog"):
            kind = f"{func.value.id}.{func.attr}"
            parts = [_flatten(a) for a in node.args]
            parts += [_flatten(k.value) for k in node.keywords
                      if k.arg in ("title", "message")]
            for text in parts:
                if text:
                    found.append(f"{path.name} | {kind} | {where} | {text}")
            continue

        # Dialog titles passed positionally to a superclass constructor.
        if isinstance(func, ast.Attribute) and func.attr == "__init__":
            for arg in node.args[1:]:
                text = _flatten(arg)
                if text:
                    found.append(f"{path.name} | dialog-title | {where} | {text}")

        # Labels, buttons and hints built with a text= keyword.
        for keyword in node.keywords:
            if keyword.arg in _TEXT_KEYWORDS:
                text = _flatten(keyword.value)
                if text and text.strip():
                    found.append(f"{path.name} | {keyword.arg}= | {where} | {text}")

    return found


def snapshot() -> str:
    """The whole wording surface, sorted so the file is stable."""
    entries: list[str] = []
    for name in ("app.py", "dialogs.py"):
        entries += _entries_for(PACKAGE / name)
    # Newlines would break the one-entry-per-line format, and reviewing an
    # escaped blob is worse than reviewing a marker.
    flattened = sorted(e.replace("\n", "\\n") for e in entries)
    header = (
        "# Every user-visible modal string, extracted from the source.\n"
        "# One entry per line: file | kind | enclosing function | text\n"
        "# Interpolations collapse to {}. Newlines are written \\n.\n"
        "#\n"
        "# This file is the safety net for moving wording between modules.\n"
        "# If a test told you to look here: a string changed. If that was\n"
        "# deliberate, regenerate with\n"
        "#     python tests/wording.py --update\n"
        "# and review the diff as a change to what the app SAYS.\n"
    )
    return header + "\n".join(flattened) + "\n"


SNAPSHOT_PATH = Path(__file__).resolve().parent / "wording_snapshot.txt"


if __name__ == "__main__":
    import sys

    if "--update" in sys.argv:
        SNAPSHOT_PATH.write_text(snapshot(), encoding="utf-8")
        lines = len(snapshot().splitlines())
        print(f"wrote {SNAPSHOT_PATH} ({lines} lines)")
    else:
        print(snapshot())
