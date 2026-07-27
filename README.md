# Cognitive Offload

A small desktop "second brain": capture what is in your head, triage it, and keep
the active stack visible. Pure Python — tkinter from the standard library, no
third-party dependencies.

Two tabs:

- **Cognitive Offload** — quick capture, the task list, a scratchpad and a focus timer.
- **Eisenhower Matrix** — the four urgency/importance quadrants, each backed by a
  folder of task files on disk.

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
- Search across titles, descriptions and tags; filter by tag; hide completed.
- Sort by priority, creation date, alphabetically, or by completion time.
  Priority sorting keeps open work at the top: unfinished first, flagged first,
  then newest.
- `Ctrl+Z` undoes the last change — deletes, edits, bulk moves and all.

**Matrix**
- Add, edit, delete and move tasks between any two quadrants (not just into
  "Do First").
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
    queries.py              filtering, sorting, scratchpad line parsing
    storage.py              config, atomic session file, matrix file store
    app.py                  the controller: commands, timer, autosave
    main_tab.py             layout of the capture/tasks/scratchpad tab
    matrix_tab.py           layout of the matrix tab
    dialogs.py              modal dialogs
    theme.py                colours and ttk styles
tests/                      unittest suite (no third-party runner needed)
```

The model, query and storage layers never import tkinter, which is what makes
them testable without a display.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The suite covers the model, filtering/sorting, and the storage layer. It also
drives the real widgets end to end (capture, edit, filter, matrix moves,
save/load, undo); those tests skip themselves automatically when no display is
available, and run under `xvfb-run` in CI.
