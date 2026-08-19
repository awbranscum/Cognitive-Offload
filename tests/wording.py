"""Read the user-visible strings out of the source.

Not "every" — that claim stood in this docstring for many releases and was
not true. Coverage has three independent axes, and each was opened
separately, by an incident: which FILES are read, which KEYWORD arguments
count as wording, and which SYNTACTIC POSITIONS are looked at at all.
Fixing one says nothing about the other two. What is watched is listed at
the top of the snapshot; anything outside those positions is not seen, and
saying so plainly is worth more than a comfortable summary.

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
_TEXT_KEYWORDS = ("text", "title", "message", "window_title", "ok_text", "hint",
                  "empty_text", "value")
# Two of those joined late, and each cost a real string. `empty_text` held the
# empty-list sentence; `value` holds a StringVar's opening text — "Nothing
# picked yet" above the timer and "Ready." in the status bar, both on screen
# the moment the app opens. Keeping a hand-written list of keyword names is
# why they were missed, which is what _CONTAINER_KINDS below is about.

# Strings that are not wording however they read: toolkit constants that
# happen to contain a space, and font stacks.
_NOT_WORDING = frozenset({
    "insert lineend", "insert lineend +1c", "insert linestart",
    "DejaVu Sans", "Segoe UI", "SF Pro Text", "Helvetica Neue",
    "Liberation Sans", "All files", "JSON files",
})


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
        left, right = _joined(node.left), _joined(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _joined(node) -> str | None:
    """One side of a concatenation.

    A sentence assembled from a helper — ``_batch_status(...) + "."`` — still
    says words, and the words are in the arguments, so a call gets rendered
    here. Only here: a bare ``PromptDialog(...).show()`` assigned to a name
    says nothing itself, and rendering it would duplicate the dialog's own
    labels as an unreadable blob.
    """
    plain = _flatten(node)
    if plain is not None:
        return plain
    if isinstance(node, ast.Call):
        rendered = _interpolation(node)
        if any(ch.isalpha() for ch in rendered):
            return rendered
    return None


def _texts(node, in_concat: bool = False) -> list[str]:
    """One entry per thing this expression can actually say.

    ``a if cond else b`` is two different sentences, and squashing them into
    one blob makes both unreadable — which is worse than not watching them,
    because an unreadable diff is one nobody checks. A conditional nested
    inside a concatenation is distributed rather than blobbed, so
    ``status(x) + "." + (" Ctrl+Z undoes it." if done else "")`` becomes the
    two sentences it really is.
    """
    if isinstance(node, ast.IfExp):
        return [t for branch in (node.body, node.orelse)
                for t in _texts(branch, in_concat)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        lefts = _texts(node.left, in_concat=True)
        rights = _texts(node.right, in_concat=True)
        return [left + right for left in lefts for right in rights]
    text = _joined(node) if in_concat else _flatten(node)
    return [text] if text else []


def _is_wording(text: str | None) -> bool:
    """Does this literal read as something a person is meant to read?

    A space between words is the whole test, and it is deliberately crude:
    identifiers, style names, sort keys, tk options and dict keys are single
    tokens, and sentences are not. The exceptions that slip through are
    listed in _NOT_WORDING rather than guessed at.
    """
    return bool(text) and " " in text.strip() and text.strip() not in _NOT_WORDING


def _container_texts(tree: ast.AST, path: Path, owner: dict) -> list[str]:
    """Wording that lives inside a dict, list, tuple or set.

    This is the third axis of coverage, and the one that stayed open longest.
    Widening the *file* list (v3.33.0) and adding *keyword* names (v3.34.0)
    both left it untouched, because it is neither: a string here is not
    assigned to a name, not returned, and not passed as a keyword — it is an
    element of a literal collection.

    Ninety-two strings were sitting in these positions unwatched, and they
    were not offcuts. All four Eisenhower quadrant descriptions, including
    "Deleting these is progress, not failure — a shorter list is easier to
    face." The whole keyboard-shortcuts dialog. The warm-up ladder, which is
    a named feature of the app. The preset names. Since the no-shaming scan
    reads this same snapshot, every one of them was unchecked for tone too.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            values = node.values
            kind = "in-dict"
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = node.elts
            kind = "in-list"
        else:
            continue
        for element in values:
            for text in _texts(element):
                if _is_wording(text):
                    where = owner.get(id(node), "<module>")
                    found.append(f"{path.name} | {kind} | {where} | {text}")
    return found


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
    found += _container_texts(tree, path, owner)

    # Sentences assigned to a name before being asked. A question built as
    # `title = "Already open"` and passed as a variable is invisible at the
    # call site, and that is exactly the shape wording takes as it moves out
    # of the controller — so the net has to see it, or it would quietly stop
    # covering the strings while appearing to still work.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for text in _texts(node.value):
            if " " not in text.strip():
                continue  # identifiers, style names and sort keys are not wording
            for target in targets:
                if isinstance(target, ast.Name):
                    where = owner.get(id(node), "<module>")
                    found.append(f"{path.name} | {target.id}= | {where} | {text}")

    # Sentences a function hands back. Once wording lives in the presenter it
    # is usually `return f"..."` rather than an assignment or a call, so
    # without this the net would quietly stop watching every string the
    # moment it finished moving — which is precisely when it matters.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        for text in _texts(node.value):
            if " " in text.strip():
                where = owner.get(id(node), "<module>")
                found.append(f"{path.name} | returns | {where} | {text}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        where = owner.get(id(node), "<module>")

        func = node.func
        # The status bar. Most of what this app says is said here — every
        # command reports to it — and it was invisible to this net until two
        # separate wording defects had to be found in it by hand.
        if isinstance(func, ast.Attribute) and \
                func.attr in ("set_status", "hold_status"):
            for arg in node.args:
                for text in _texts(arg):
                    if text.strip():
                        found.append(f"{path.name} | status | {where} | {text}")
            continue

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

        # Sentences handed to a call with no keyword to name them. The undo
        # stack is the reason: every mutation registers an action name —
        # `_require_selection("mark it done")`, "not today", "send it to the
        # matrix" — and those names are read back to a person in the status
        # bar. Nothing about their position said "wording", so none of them
        # were watched. The three call shapes above have already taken their
        # own positional arguments and moved on, so nothing is counted twice.
        for arg in node.args:
            for text in _texts(arg):
                if _is_wording(text):
                    found.append(f"{path.name} | arg | {where} | {text}")

    return found


def snapshot() -> str:
    """The whole wording surface, sorted so the file is stable."""
    entries: list[str] = []
    # The whole package, not a hand-kept list. The list was how a string
    # moving out of a watched file could vanish from the snapshot while the
    # tests stayed green — and how SessionLog.summary() sat in sessions.py
    # unwatched for its whole life. Worse, the no-shaming scan reads this
    # same snapshot, so an unlisted file was unchecked for tone as well as
    # for drift: the app's tagline, "Where do I start?", "Not today", and
    # the park hints were all outside it.
    #
    # Modules with no user-visible strings contribute nothing, so widening
    # costs no noise. Sorted so the file is stable across filesystems.
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name.startswith("__"):
            continue
        entries += _entries_for(path)
    # Newlines would break the one-entry-per-line format, and reviewing an
    # escaped blob is worse than reviewing a marker.
    flattened = sorted(e.replace("\n", "\\n") for e in entries)
    header = (
        "# The user-visible strings this extractor can see. NOT every string\n"
        "# in the app: it reads assignments, returns, container literals,\n"
        "# positional and text-like keyword arguments, the status bar, and\n"
        "# messagebox/filedialog calls. A string somewhere else is unwatched,\n"
        "# and has been three times so far.\n"
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
