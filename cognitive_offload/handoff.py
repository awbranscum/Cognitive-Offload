"""Handing a task to an AI agent, which is what makes Delegate usable.

The Delegate quadrant asks you to give a task to someone else. For a lot of
people there is no someone else, so the quadrant fills up and stops meaning
anything — urgent-but-not-important work sits there because "delegate" is a
verb with no object. An agent is an object for that verb.

Two rules shape everything here.

**Nothing in this module touches the network.** It writes a brief to a file
and builds a command string. Delivery is the agent's own runner, started by
the person, on their machine. That keeps the zero-dependency promise, keeps
the app usable offline, and means a handoff can be read and edited before
anything acts on it — which matters when the thing being handed over was
written at speed by someone who was trying not to lose the thought.

**The exact local interface of each agent is not something this app can
verify.** Folder layouts and command names change, and guessing wrongly in
code is worse than saying so. So every target here is *data*: an outbox
folder, a file format and a command template, each overridable. The defaults
are conventions, documented as conventions in ``docs/AGENT_HANDOFF.md``, not
claims about what any product currently does.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from .models import humanize_date, today_iso
from .storage import slugify

# How long a handed-off task waits before it asks to be looked at again.
# Three days is long enough not to nag and short enough that the task is
# still connected to why you wanted it done.
DEFAULT_FOLLOW_UP_DAYS = 3


@dataclass(frozen=True)
class AgentTarget:
    """One place a brief can be sent, described rather than coded.

    ``command`` is a template, not something this app runs. Placeholders:
    ``{brief}`` (the written file), ``{dir}`` (its folder), ``{title}``.

    ``shell`` decides how those paths are quoted, which is not a detail: a
    handoff folder with a space in it is ordinary (``~/My Documents``), and
    an unquoted path there produces a command that silently runs against the
    wrong file. Shell targets get ``shlex.quote``; a target that is pasted
    into a chat window rather than a terminal gets the path as written,
    because shell quoting there is just noise the agent has to see past.
    """

    key: str
    label: str
    fmt: str  # "markdown" or "json"
    folder: str  # subfolder of the handoff root
    command: str
    setup: str  # the one-time thing the person has to do
    shell: bool = True


# Ordered as they appear in the picker: the two that most often already have
# a folder-shaped way in come first.
TARGETS: tuple[AgentTarget, ...] = (
    AgentTarget(
        key="claude_desktop",
        label="Claude Desktop",
        fmt="markdown",
        folder="ClaudeDesktop",
        command="Read {brief} and do what it asks.",
        shell=False,
        setup="Give Claude Desktop access to the handoff folder — a filesystem "
              "MCP server pointed at it, or add it to a project — then paste "
              "the line above into a new chat.",
    ),
    AgentTarget(
        key="codex",
        label="Codex",
        fmt="markdown",
        folder="Codex",
        # "$(cat {brief})" rather than a prompt with the path inside it:
        # {brief} stays a single shell word, so a folder with a space in it
        # cannot split the command. It assumes only that the CLI takes its
        # prompt as the first argument, which is the common shape.
        command='codex "$(cat {brief})"',
        setup="Run the command from the folder you want Codex to work in. "
              "Check it against your own Codex CLI before trusting it — this "
              "app cannot ask the CLI what it accepts.",
    ),
    AgentTarget(
        key="openclaw",
        label="OpenClaw",
        fmt="json",
        folder="OpenClaw",
        command='openclaw run --input {brief}',
        setup="Point your OpenClaw runner at the folder above, or run the "
              "command by hand. The brief is JSON so a runner can read it "
              "without parsing prose.",
    ),
)

TARGET_KEYS = tuple(t.key for t in TARGETS)
TARGETS_BY_KEY = {t.key: t for t in TARGETS}
# What the picker shows, and the reverse map the dialog collects through.
TARGET_LABELS = tuple(t.label for t in TARGETS)
TARGET_KEY_BY_LABEL = {t.label: t.key for t in TARGETS}


def target_for(key: str) -> AgentTarget:
    """The target for ``key``, falling back to the first rather than raising.

    A config file naming a target that no longer exists is not a reason to
    refuse to hand anything over.
    """
    return TARGETS_BY_KEY.get(key, TARGETS[0])


@dataclass(frozen=True)
class Brief:
    """What the agent is being asked to do, before it is written anywhere."""

    title: str
    task_id: str
    body: str
    first_step: str = ""
    due: str = ""
    estimate_minutes: int = 0
    tags: tuple = ()
    note: str = ""
    created_on: str = field(default_factory=today_iso)

    def filename(self, suffix: str) -> str:
        # storage.slugify keeps spaces, which is right for a .task file and
        # wrong here: these names are read aloud in commands and pasted into
        # chats. Hyphenate at this boundary rather than changing a coercion
        # that is correct where it lives.
        stem = slugify(self.title).replace(" ", "-") or "task"
        return f"{self.created_on}-{stem}-{self.task_id[:8]}.{suffix}"


def build_brief(task, note: str = "", today: str | None = None) -> Brief:
    """Turn a matrix task into a brief. Reads a task; writes nothing."""
    today = today or today_iso()
    return Brief(
        title=(task.title or "").strip() or "Untitled task",
        task_id=getattr(task, "id", "") or "",
        body=(getattr(task, "content", "") or "").strip(),
        first_step=(getattr(task, "first_step", "") or "").strip(),
        due=getattr(task, "scheduled_for", "") or "",
        estimate_minutes=int(getattr(task, "estimate_minutes", 0) or 0),
        tags=tuple(getattr(task, "tags", ()) or ()),
        note=note.strip(),
        created_on=today,
    )


def _lines_common(brief: Brief) -> list[str]:
    """The facts an agent needs, in the order it needs them."""
    out = []
    if brief.first_step:
        out.append(f"Start with: {brief.first_step}")
    if brief.due:
        out.append(f"Wanted by: {humanize_date(brief.due, brief.created_on)} "
                   f"({brief.due})")
    if brief.estimate_minutes:
        out.append(f"Rough size: about {brief.estimate_minutes} minutes, "
                   f"as guessed by a human who is bad at guessing.")
    if brief.tags:
        out.append("Tags: " + ", ".join(brief.tags))
    return out


# Said once, in one place, so the markdown and the JSON cannot drift into
# asking for different things.
REPORT_BACK = (
    "When you are done, reply with what you did, anything you could not do, "
    "and anything you need from me. Ask before doing anything that spends "
    "money, sends a message to another person, or cannot be undone."
)


def render_markdown(brief: Brief) -> str:
    """A brief a person can read as easily as an agent can."""
    parts = [f"# {brief.title}", ""]
    if brief.note:
        parts += [brief.note, ""]
    if brief.body:
        parts += ["## Detail", "", brief.body, ""]
    facts = _lines_common(brief)
    if facts:
        parts += ["## What I know", ""] + [f"- {line}" for line in facts] + [""]
    parts += ["## Handing it over", "", REPORT_BACK, ""]
    parts += [f"_Handed over on {brief.created_on} from Cognitive Offload "
              f"(task {brief.task_id[:8]})._", ""]
    return "\n".join(parts)


def render_json(brief: Brief) -> str:
    """The same brief, for a runner that would rather not read prose."""
    return json.dumps(
        {
            "source": "cognitive-offload",
            "task_id": brief.task_id,
            "handed_over_on": brief.created_on,
            "title": brief.title,
            "note": brief.note,
            "detail": brief.body,
            "first_step": brief.first_step,
            "due": brief.due,
            "estimate_minutes": brief.estimate_minutes,
            "tags": list(brief.tags),
            "instructions": REPORT_BACK,
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def render(brief: Brief, target: AgentTarget) -> str:
    return render_json(brief) if target.fmt == "json" else render_markdown(brief)


def suffix_for(target: AgentTarget) -> str:
    return "json" if target.fmt == "json" else "md"


def brief_path(root, target: AgentTarget, brief: Brief) -> Path:
    """Where this brief would be written. Pure — creates nothing."""
    return Path(root) / target.folder / brief.filename(suffix_for(target))


def command_for(target: AgentTarget, path, template: str = "") -> str:
    """The line the person runs or pastes.

    ``template`` lets a config override the default without this module
    knowing anything about what a given agent's CLI is called this month.
    """
    path = Path(path)
    text = template.strip() or target.command
    quote = shlex.quote if target.shell else str
    try:
        return text.format(brief=quote(str(path)), dir=quote(str(path.parent)),
                           title=path.stem)
    except (KeyError, IndexError, ValueError):
        # A template with a typo in it must not stop the handoff: the file is
        # already the real deliverable, and the command is a convenience.
        return f"{text}  # (brief written to {path})"


def write_brief(root, target: AgentTarget, brief: Brief) -> Path:
    """Write the brief and return where it landed.

    Raises ``OSError``; the caller decides what to say about it, because what
    to say depends on whether a person is watching.
    """
    path = brief_path(root, target, brief)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(brief, target), encoding="utf-8")
    return path


def follow_up_date(handed_on: str, days: int = DEFAULT_FOLLOW_UP_DAYS) -> str:
    """When to look at this again — the half of delegating that gets lost.

    Handing something over and then forgetting it is not delegation, it is
    just losing it somewhere more respectable. Every handoff gets a date.
    """
    from datetime import date, timedelta

    try:
        base = date.fromisoformat(handed_on)
    except (TypeError, ValueError):
        base = date.fromisoformat(today_iso())
    return (base + timedelta(days=max(1, days))).isoformat()
