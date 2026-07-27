# Cognitive Offload

A small desktop "second brain" built around the part that actually hurts: not
knowing what to do, but *starting*. Capture what is in your head, triage it, and
get moving in fifteen-minute blocks. Pure Python — tkinter from the standard
library, no third-party dependencies.

Two tabs:

- **Cognitive Offload** — quick capture, the task list, a scratchpad, and the
  focus session runner.
- **Eisenhower Matrix** — the four urgency/importance quadrants, each backed by a
  folder of task files on disk.

## The starting problem

Planning is not the bottleneck. You can know exactly what to do and still not be
able to begin. The app is built around four things that help with that:

- **A first step on every task.** "Write the report" is hard to start; "open last
  quarter's file" is not. Tasks that name their first move are marked `▸ ready`
  and are ranked first when the app suggests something.
- **Where do I start?** (`Ctrl+G`) asks what you can *face* right now — an urgent
  sprint, a deadline sprint, admin, or something creative — and offers three
  tasks, not forty. "Show me others" reshuffles. Picking badly beats not picking.
- **A warm-up ladder** before each session: two or three small steps between
  whatever you were doing and the task, so starting isn't one big leap from high
  stimulation to a cold start. Ticking them is optional — they're a prompt, not a
  gate.
- **Fifteen-minute sessions** with a visible bar, a break afterwards, and a
  fourteen-day strip of what you actually did. Short blocks close the loop often
  enough to build momentum.

The Schedule quadrant gets special treatment for the same reason. Important but
not urgent work has no deadline to make you start it, so you can **book a time**
on it (`today`, `tomorrow`, `fri`, or a date) and it surfaces on the main tab as
"booked for today".

**On tone:** the app never counts what you missed. There is no streak to break,
empty days on the strip are just empty, pausing is not failing, and tasks without
a first step get no scolding marker. Nothing here is medical advice — these are
common self-management strategies, not treatment, and no claims or statistics are
built into the UI.

## Running it

Requires Python 3.9+ with tkinter.

```bash
python main.py          # or: python -m cognitive_offload
```

Windows users can double-click `run.bat`; on macOS/Linux use `./run.sh`.

If Python was installed without Tcl/Tk, `main.py` says so and tells you what to
install (`sudo apt install python3-tk`, `sudo dnf install python3-tkinter`, or a
reinstall from python.org).

## Features

**Capture**
- Type into the capture box: `Enter` files it as a task, `Ctrl+Enter` drops it in
  the scratchpad with a timestamp.
- The scratchpad is a free-form notepad that is saved with the session. Turn one
  line into a task, or dump every line into the task list at once.

**Tasks**
- Multi-select with Shift/Ctrl; done, priority, tag, move-to-top, delete and
  send-to-matrix all act on the whole selection.
- Each task can carry a first step, a "feels like" category, and a booked date.
- Search across titles, descriptions, first steps and tags; filter by tag or by
  feel; hide completed.
- Sort by priority, creation date, alphabetically, or by completion time.
  Priority sorting keeps open work at the top: unfinished first, flagged first,
  then newest.
- `Ctrl+Z` undoes the last change — deletes, edits, bulk moves and all.

**Focus sessions**
- `Ctrl+G` picks something to start; `Ctrl+R` starts a session on the selection.
- Warm-up ladder, then a countdown with a progress bar, then an offered break.
- Finished sessions are logged to `sessions.json` and drawn as a 14-day strip.

**Matrix**
- Add, edit, delete and move tasks between any two quadrants (not just into
  "Do First").
- "Book a time" on a Schedule task; booked items show up on the main tab.
- Send a selection back to the main task list, or copy a whole quadrant.
- Each quadrant is a folder; each task is a `.task` JSON file, so the data stays
  readable and greppable outside the app.

**Saving**
- Auto-saves every 30s when something changed, and on quit.
- Writes are atomic (temp file + rename) and the previous version is kept as
  `data.json.bak`, so a crash mid-save cannot cost you the file.
- `Export…` writes a copy anywhere; `Open…` loads a session from elsewhere.

Press `F1` in the app for the full keyboard-shortcut list.

## Where the data lives

| What | Default location |
| --- | --- |
| Session (tasks + scratchpad) | `~/.cognitive_offload/data.json` |
| Focus session log | `~/.cognitive_offload/sessions.json` |
| Previous session backup | `~/.cognitive_offload/data.json.bak` |
| Matrix quadrants | `~/MatrixTasks/{DoFirst,Schedule,Delegate,Eliminate}/*.task` |
| Preferences | `~/.cognitive_offload_config.json` |

Both folders can be moved from inside the app ("Change folder"). Sessions saved
by earlier versions — including the old timestamped notes list and plain-text
`.task` files — are read and upgraded automatically.

## Project layout

```
main.py                     launcher (checks Python/tkinter, then starts the app)
cognitive_offload/
    models.py               Task / Note / MatrixTask + serialisation
    queries.py              filtering, sorting, start-ranking, line parsing
    sessions.py             the focus-session log and its day counts
    storage.py              config, atomic session file, matrix file store
    app.py                  the controller: commands, timer, autosave
    main_tab.py             layout of the capture/tasks/scratchpad tab
    matrix_tab.py           layout of the matrix tab
    dialogs.py              modal dialogs (incl. the start picker + warm-up)
    widgets.py              the momentum strip
    theme.py                colours and ttk styles
tests/                      unittest suite (no third-party runner needed)
```

The model, query and storage layers never import tkinter, which is what makes
them testable without a display.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The suite covers the model, filtering/sorting/start-ranking, the session log
and the storage layer. It also
drives the real widgets end to end (capture, edit, filter, matrix moves,
save/load, undo); those tests skip themselves automatically when no display is
available, and run under `xvfb-run` in CI.
