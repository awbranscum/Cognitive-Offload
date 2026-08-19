# Handing a task to an AI agent

The Eisenhower matrix asks you to *delegate* urgent-but-not-important work.
For a lot of people there is no one to delegate to, so the Delegate quadrant
fills up and stops meaning anything — it becomes a second Do First with a
politer name. An agent is something to delegate *to*.

This document describes what the app actually does, and — just as important —
what it does not.

## What happens when you hand something over

Select a task in **Delegate** and press **Hand off to an agent**. The app:

1. Writes a **brief** — the task's title, your details, the first step, the
   booked date, the estimate and the tags, plus anything you type in the
   dialog — to a file.
2. Puts a **command** on your clipboard.
3. Marks the task **waiting**, with the name of the agent, the day you handed
   it over, and a day to check back.

That third step is the point. Handing a task to something and then forgetting
it is not delegating; it is losing it somewhere more respectable. The task
keeps its `waiting` badge until you mark it done or take it back, and when the
check-back day arrives the badge changes to `check back` — a fact, not a
telling-off.

**The mark follows the task.** Send it to the main list and it arrives still
saying who has it; that used to be a one-click way to lose the handoff
entirely. Both tabs show the same line and the same badge, from the same code.

**A task that is out is not offered as the next thing to start.** It stays in
the list and in every search — hiding it is the one thing this app will not do
— but it stops guarding the NEXT UP slot and "Where do I start?", exactly the
way "Not today" does, because starting it would mean duplicating work someone
else is already doing. On the check-back day it comes back into the running,
since from then on picking it up again is a real option.

**The same treatment works for a person.** Everything on this page about the
waiting mark — the badge, the line under the title, the task stepping out of
the suggestion slot until the check-back day — is written against `handed_to`,
which is free text and has never cared whether it holds "Codex" or "Mum". The
task editor on either tab has a **Waiting on** field and a **check back** date
for exactly that, and no brief is written and no command is copied, because
there is nothing to run. An agent is one thing you can be waiting on; most of
them are people.

**Two ways back.** In Delegate, **Take it back**. Anywhere else, the task
editor offers *"Out with Claude Desktop, checking back Friday — take it back
and do it yourself"*, visible only while a handoff is actually in effect. Both
are undoable with Ctrl+Z, like every other command.

## What it does not do

**Nothing is sent anywhere.** The app makes no network request, opens no
socket, and starts no other program. It writes a file and copies a line of
text. You start the agent.

That is a deliberate limit, for three reasons:

- It keeps the app's zero-dependency, works-offline promise intact.
- A brief written in thirty seconds by someone trying not to lose a thought
  should be **readable and editable before anything acts on it**.
- Auto-running an agent against a task you typed while distracted is the
  wrong default for this audience, and the wrong default for anyone.

Every brief also ends with a line asking the agent to check with you before
spending money, messaging another person, or doing anything that cannot be
undone. It is in both the Markdown and the JSON, from one constant, so the
two cannot drift apart.

## Where the files go

Briefs are written under a **handoff folder**, one subfolder per target:

```
~/CognitiveOffloadHandoff/
    ClaudeDesktop/2026-08-19-chase-the-claim-1a2b3c4d.md
    Codex/2026-08-19-chase-the-claim-1a2b3c4d.md
    OpenClaw/2026-08-19-chase-the-claim-1a2b3c4d.json
```

The folder is deliberately **outside** the app's own data directory. Giving an
agent access to the folder holding all of your tasks and notes is a much
bigger grant than most people realise they are making; giving it access to a
folder containing only what you chose to hand over is not.

Change it with `handoff_root` in the config file.

## The three targets

| Target | Format | Default command |
|---|---|---|
| Claude Desktop | Markdown | `Read {brief} and do what it asks.` |
| Codex | Markdown | `codex "$(cat {brief})"` |
| OpenClaw | JSON | `openclaw run --input {brief}` |

**These commands are conventions, not claims.** This app cannot ask any of
those three products what they currently accept, and it does not try —
guessing wrongly in code would be worse than saying so here. Check the command
against your own installation the first time, and if it is wrong, correct it:

```json
{
  "handoff_commands": {
    "codex": "codex exec --full-auto {brief}"
  }
}
```

Placeholders: `{brief}` (the file), `{dir}` (its folder), `{title}`. If a
template has a typo in it, the command falls back to naming the file that was
written — the brief is the real deliverable, the command is a convenience.

### Quoting

`{brief}` is shell-quoted for **Codex** and **OpenClaw**, which are commands
you run in a terminal, and left as a plain path for **Claude Desktop**, whose
line is pasted into a chat window where shell quoting is only noise. This is
not a detail: a handoff folder like `~/My Documents` is ordinary, and an
unquoted path there produces a command that silently runs against the wrong
thing. The Codex template uses `"$(cat {brief})"` rather than putting the path
inside a prompt string, so `{brief}` stays a single shell word.

### Setting each one up, once

- **Claude Desktop** — give it access to the handoff folder (a filesystem MCP
  server pointed at it, or add the folder to a project), then paste the
  clipboard line into a new chat.
- **Codex** — run the command from the directory you want it to work in. The
  template assumes only that the CLI takes its prompt as the first argument.
- **OpenClaw** — point your runner at the folder, or run the command by hand.
  The brief is JSON so a runner can read it without parsing prose.

## Adding a target

`TARGETS` in `cognitive_offload/handoff.py` is a tuple of `AgentTarget`
records — key, label, format, folder, command template, setup note, and
whether the command is a shell command or something pasted. Adding an entry is
the whole change; nothing else in the app branches on which agent it is.
