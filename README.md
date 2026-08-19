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
- **The app names the next thing.** Opening it shows a "NEXT UP" line — the
  task, its first step, and a Start button. No picker, no dialog, no second
  decision. "Not that one" walks to the next suggestion; "Not today" excuses
  a task you cannot face until tomorrow — it keeps its place on the list, gets
  no badge and no count, and the snooze expires silently. Repeated forced
  contact with a dreaded task builds avoidance, not willpower. The strip stays
  visible in Calm mode, because it is the thing Calm mode is for.
- **Yesterday's task comes back warm.** The session log remembers which task
  each block was on, and anything worked in the last two days ranks higher in
  NEXT UP and "Where do I start?". Re-entry is cheaper than a cold start — and
  it is what makes the hand-off step you wrote at the last session end
  actually get read.
- **Where do I start?** (`Ctrl+G`) asks what you can *face* right now — an urgent
  sprint, a deadline sprint, admin, or something creative — and offers three
  tasks, not forty. "Show me others" reshuffles. Picking badly beats not picking.
- **A warm-up ladder** before each session: two or three small steps between
  whatever you were doing and the task, so starting isn't one big leap from high
  stimulation to a cold start. Ticking them is optional — they're a prompt, not a
  gate. The steps are yours: "Edit steps…" in the start dialog rewrites them in
  place (a fixed ladder habituates within days), and a checkbox folds the ladder
  away — or brings it back — for good.
- **Fifteen-minute sessions** with a visible bar, a break afterwards, and a
  fourteen-day strip of what you actually did. Short blocks close the loop often
  enough to build momentum.

The Schedule quadrant gets special treatment for the same reason. Important but
not urgent work has no deadline to make you start it, so you can **book a time**
on it (`today`, `tomorrow`, `fri`, or a date) and it surfaces on the main tab as
"booked for today".

**What you actually finished.** The app used to count only what was left. It
now shows "N done today" beside the task counts — click it for the list, plus
the minutes you focused. It appears only when there is something in it; there is
no "0 done today". Clearing completed tasks does not reset it: what you finished
is kept in a small ledger in the session file, so tidying up never erases the
evidence of the day. When a session ends, it asks whether the task is finished, so
closing it out happens at the moment you are already thinking about it instead
of being one more thing to remember.

**The hand-off.** When a session ends and the task is not finished, its first
step is spent — you already opened the doc. The end-of-session prompt asks where
it picks up next time and shows the old step underneath, so tomorrow's start is
written while it is still obvious. Blank is a fine answer. Pressing Enter there
keeps the step and carries on — marking the task done is a deliberate click,
never a keyboard accident.

**Park it.** The pop-out can open by itself when a session starts ("keep the
timer floating over my work", remembered between runs — the person least likely
to notice the timer is missing is the one who needed it). It has a one-line
box: a thought that arrives mid-block
("email Dana about the invoice") goes to the scratchpad in two seconds without
pausing the timer, opening the main window, or making you decide anything. It
lands in the scratchpad rather than the task list on purpose — the list is a
commitment, and deciding is what you are trying not to do right then.

**Where the block lands on the clock.** The timer shows "ends 15:42" under the
countdown as well as the time remaining — a duration is exactly the
representation that time blindness struggles with, and a clock time is
something you can anchor to. Booked dates speak the same language: badges say
"booked tomorrow" or "booked Fri", not a raw date that needs arithmetic.

**A soft landing.** In the last two minutes of a block the timer line (and the
pop-out, in amber — never red) adds "a good moment to find a stopping point".
An unannounced hard stop is the most expensive kind of transition, and a
stopping point you chose is what makes "where does it pick up next time?"
answerable.

**Less on screen when you need less.** *Calm mode* (top right) folds away
search, filters, sort and the task toolbar, leaving a capture box, the list, and
the button that starts something. Nothing is deleted — untick it and everything
is back.

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
- Multi-select with Shift/Ctrl (or the arrow keys); done, priority, tag,
  pin, delete and send-to-matrix all act on the whole selection.
- Pin a task (`Ctrl+Up`, again to unpin) and it stays above everything open
  under the default sort — an anchor for the thing you are afraid of losing
  track of, one that survives every re-sort, save and restart.
- Each task can carry a first step, a "feels like" category, a booked date,
  and an "about how long?" guess in minutes. The guess shows as a quiet
  `~25 min` badge and in the start dialog; when the task is finished, the
  status line sets the guess beside what the sessions actually took — as
  calibration, never as a mark. Time-sense only improves when the guess
  meets the real number somewhere visible and kind.
- Search across titles, descriptions, first steps and tags; filter by tag or by
  feel; hide completed.
- Anything captured today is nudged up the "Where do I start?" ranking — it is
  what is on your mind, and the age tiebreak would otherwise bury it.
- Sort by priority, creation date, alphabetically, or by completion time.
  Priority sorting keeps open work at the top: unfinished first, pinned first,
  then flagged, then newest.
- **Break a task into steps.** A task can carry a plan — one step per line in
  the editor — and the row shows where in it you are (`→ copy the headings
  across · step 2 of 4`). Ticking a step off moves you down the list and the
  status line names the next one, so finishing a step is never followed by
  deciding what to do. There is still only one "what next" on a task: with a
  plan, the first step **is** the step you are on, so everything that already
  read the first step — the row, the start dialog, the ranking — keeps
  working without knowing plans exist. A repeating task with steps is a
  routine: the plan comes back each round, your place in it does not. Every
  step is searchable, and handing the task to an agent sends the whole plan
  with the finished steps ticked. At the end of a focus session the app asks
  what the step you were on says now, and offers to move you to the next one.
- **Waiting on someone.** Say who has a task and when you will check back, in
  the task editor on either tab. It keeps its badge, its place in the list and
  its place in every search — and stops being offered as the next thing to
  start, because starting it would duplicate what someone else is already
  doing. On the check-back day the badge changes to `check back` and it is in
  the running again. A fact, not a telling-off. Blank date means three days.
  A person, an agent, a landlord, a GP surgery: the app does not care which,
  and neither does the badge.
- `Ctrl+Z` undoes the last change — deletes, edits, bulk moves and all.

**Focus sessions**
- `Ctrl+G` picks something to start; `Ctrl+R` starts a session on the selection.
- Warm-up ladder, then a countdown with a progress bar, then an offered break.
- "Pop out" opens a small always-on-top window with just the task, the first
  step and the clock — for when the countdown needs to be visible over whatever
  you are actually working in. "Done early" banks the minutes you did do.
- Finished sessions are logged to `sessions.json` and drawn as a 14-day strip.
- Click the strip (or its summary) for **the week, in evidence**: one line per
  day that had anything — sessions, minutes, and the tasks finished that day —
  with days that had nothing simply left out. "I did nothing this week" is a
  distortion, and the correction is not motivation; it is the record.

**Look and feel**
- The interface is a port of [shadcn/ui](https://ui.shadcn.com)'s design system:
  its zinc token palette, radius and type scale, and its button variants
  (default / secondary / outline / ghost / destructive). shadcn itself is React
  and Tailwind, so none of its code is used — `theme.py` reimplements the tokens
  for ttk, which is what keeps this a dependency-free Python app.
- Light and dark themes, toggled in the header and remembered between runs.
  Dark is not decoration: a bright white slab at 11pm is its own barrier.
- Colour choices are checked, not eyeballed: body text meets WCAG 4.5:1 and
  focus rings meet 3:1 in both themes, the keyboard focus ring is visible on
  the task list and on the filled primary buttons (drawn in the label colour,
  so it contrasts with the fill by construction), and there are no unstyled
  Tk dialogs or dropdowns left.
- Window sizes, the minimum window size, dialog widths and text wrap widths
  all scale with the screen's DPI, so a HiDPI laptop panel gets the same
  layout as a standard display instead of a half-sized window with
  double-sized text.
- Tasks are rows, not lines of text — title, the first step underneath, and
  colour-coded badges for feel, readiness, bookings and tags. The row widgets
  are pooled and refilled rather than rebuilt, so a 300-task list re-renders in
  ~50ms instead of locking the window for a second on every keystroke.

- **Repeating tasks** — daily, weekdays, weekly, fortnightly or monthly, set
  in the task editor. Finishing one **completes that round and books the next**
  rather than resetting the date, so doing the bins six weeks running looks
  like six things done in the week review instead of one task that is somehow
  never finished. A missed repeat **never piles up**: the next date is worked
  out from today whenever the booking has passed, so two weeks off the bins
  gets you one task, not fourteen. Do it early and the rhythm holds — a Friday
  task stays a Friday task.

- **The first launch starts calm.** A brand-new install opens in Calm mode:
  17 things you can click instead of 32, with the capture box and "Where do I
  start?" carrying the screen. The checkbox that turns it off is in plain
  sight, one flat sentence in the status bar says where the rest went, and the
  choice is remembered from then on. An existing install is never rearranged.
- **Nothing is offered while it cannot act.** Every task action needs a
  selection, so they stay greyed until there is one — and then seven of them
  come on at once, which teaches what they apply to without a sentence and
  without a failed click. Greyed rather than hidden, so nothing moves.

**Matrix**
- Add, edit, delete and move tasks between any two quadrants (not just into
  "Do First").
- "Book a time" on a Schedule task; booked items show up on the main tab, and
  the "booked for today" banner lands on the actual rows, not just the tab.
- "Focus on this" starts a session straight from a quadrant: one click moves
  the task to the main list, opens the start dialog, and runs the warm-up —
  instead of the four manual steps that booked work used to need on its day.
- **"Hand off to an agent"** turns Delegate into a quadrant you can actually
  use. It writes a brief — title, details, first step, booked date, estimate,
  tags, plus whatever you add — to a file for **Claude Desktop**, **Codex** or
  **OpenClaw**, and puts the command to run it on your clipboard. The task then
  then wears a `waiting` badge on **both tabs** until you take it back or mark
  it done, so a handoff cannot quietly become a disappearance — and it stops
  being offered as the next thing to start, since starting it would duplicate
  the agent's work. Nothing is sent anywhere: the app writes a file, you start
  the agent. See [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md).
- Send a selection back to the main task list, or copy a whole quadrant.
- Each quadrant is a folder; each task is a `.task` JSON file, so the data stays
  readable and greppable outside the app.

**Saving**
- Auto-saves every 30s when something changed, and on quit. If an auto-save
  fails (disk full, folder on a paused sync drive), the app says so once,
  calmly, instead of failing silently for hours — and quitting with a broken
  save offers to write a copy somewhere else first.
- Quitting mid-session keeps the minutes: closing the window during a focus
  block banks the elapsed time to the session log before the app goes, so
  closing the laptop lid without ceremony is a normal end of day, not a
  forfeit. Breaks and blocks that never started record nothing.
- A second copy of the app opening the same session folder is caught before it
  can silently overwrite the first copy's saves. The lock is held by the
  operating system on an open handle rather than being a file that merely
  exists, so a copy that crashed or was force-closed leaves nothing behind to
  ask about — the next launch takes the folder over without a question. You
  are asked only when a copy really is running, or when the folder cannot
  answer the question at all (network and synced folders often cannot).
- `Ctrl+Z` reaches across the task list and the matrix. Adding, editing,
  moving, booking a time for and deleting a matrix task are all undoable, just
  as they are in the list. So are the moves between the two: undoing a "to
  matrix" move deletes the file it created, and undoing the reverse writes it
  back, so a task is never left in both places or neither.
- The `.bak` is written once per run, so it still holds the session as you
  opened it rather than being overwritten by an autosave 30 seconds later.
- Writes are atomic (temp file + rename) and the previous version is kept as
  `data.json.bak`, so a crash mid-save cannot cost you the file.
- `Export…` writes a copy anywhere; `Open…` loads a session from elsewhere.

Press `F1` in the app for the full keyboard-shortcut list. `CHANGELOG.md`
tracks what changed, version by version.

## Where the data lives

| What | Default location |
| --- | --- |
| Session (tasks + scratchpad) | `~/.cognitive_offload/data.json` |
| Focus session log | `~/.cognitive_offload/sessions.json` |
| Previous session backup | `~/.cognitive_offload/data.json.bak` |
| Matrix quadrants | `~/MatrixTasks/{DoFirst,Schedule,Delegate,Eliminate}/*.task` |
| Agent handoff briefs | `~/CognitiveOffloadHandoff/{ClaudeDesktop,Codex,OpenClaw}/` |
| Preferences | `~/.cognitive_offload_config.json` |

A session file that is valid JSON but not a Cognitive Offload session is
refused rather than loaded as empty — and left exactly where it is. The same
goes for a file saved by a newer version of the app (loading it here would
silently drop what the newer format added), and if individual task records
can't be read, the app says how many, keeps auto-save off, and waits for an
explicit Save as your consent before anything is overwritten. A matrix folder
that disappears mid-run (unmounted drive, moved directory) is named in the
status bar, and nothing is written until it returns — no silently forked
fresh tree. An
unreadable `data.json` is set aside under a timestamped `.corrupt-` name
(never deleted, never overwritten) and the app offers to restore the `.bak`
on the spot; declining starts fresh while the backup stays protected for the
rest of the run. An unreadable `sessions.json` is likewise moved to
`sessions.json.corrupt` instead of being silently overwritten.

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
    app.py                  the controller: commands, autosave, Tk wiring
    timer.py                the focus/break clock as a pure state machine
    presenter.py            what each screen says, with nothing to say it on
    viewmodels.py           what a row shows, with no opinion on drawing it
    rows.py                 how a task renders as a row (shared by both tabs)
    ports.py                what the app needs from the platform underneath it
    handoff.py              briefs for an AI agent: targets, rendering, files
    undo.py                 the Ctrl+Z stack, UI-free
    main_tab.py             layout of the capture/tasks/scratchpad tab
    matrix_tab.py           layout of the matrix tab
    dialogs.py              modal dialogs (incl. the start picker + warm-up)
    widgets.py              badges, the task row list, momentum strip, focus window
    theme.py                shadcn design tokens and the ttk styles built from them
tests/                      unittest suite (no third-party runner needed)
```

Ten of those modules never import tkinter — the model, query, session, storage,
timer, undo, view-model, row, presenter and ports layers — which is what makes
them testable without a display. That boundary is not a convention but a test:
`tests/test_portability.py` imports each of them in a subprocess with tkinter
made unavailable, and fails if any of them needs it.

[`docs/PORTING.md`](docs/PORTING.md) describes what a second front-end would
have to build and what it would reuse unchanged — including why tkinter itself
cannot ship on Android.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The suite covers the model, filtering/sorting/start-ranking, the session log
and the storage layer. It also
drives the real widgets end to end (capture, edit, filter, matrix moves,
save/load, undo); those tests skip themselves automatically when no display is
available. The GitHub Actions workflow in `.github/workflows/tests.yml` runs
the whole suite under `xvfb-run` on every push and pull request.
