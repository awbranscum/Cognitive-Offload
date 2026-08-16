# Porting Cognitive Offload to another front-end

This describes what a second front-end — a phone app, a web page, a terminal
UI — would have to build, and what it gets to reuse unchanged.

It is written to be checked. `tests/test_porting_doc.py` asserts the specific
claims below against the code, so if someone moves a module across the line or
changes one of the hazards, the test fails and this file gets corrected instead
of quietly becoming fiction.

## Start with the blocking fact

**tkinter cannot ship on Google Play.** That is not a packaging difficulty to
be solved with enough effort; there is no supported Android target for tkinter
at all. Every route for running Python on Android — Kivy with Buildozer,
BeeWare/Briefcase with Toga, Flet, Chaquopy, or a web build wrapped as a TWA —
requires a *different* UI toolkit, and every one of them breaks the
zero-dependency rule stated in the README.

That rule is a real value of this project, not an accident, so the trade is the
owner's to make and it has not been made. Nothing in this document assumes an
answer. What the work described here buys is that whichever toolkit is chosen,
the ranking, the wording, the counting and the design law come across intact
rather than being reimplemented — and subtly changed — inside it.

## What you get for free

Ten modules need no display at all. They import and run on a platform with no
Tk installed, which is enforced by `tests/test_portability.py`: each one is
imported in a subprocess with `tkinter` poisoned out of `sys.modules`, and a
companion test asserts the UI modules *do* fail there, so a blocker that blocks
nothing cannot let the suite pass for the wrong reason.

| module | what it decides |
|---|---|
| `models` | what a task is, how it serialises, how a date is spoken aloud |
| `queries` | filtering, sorting, and the start-ranking behind "Where do I start?" |
| `sessions` | the focus-session log, its day counts and its summary |
| `storage` | config, atomic saves with a backup, the matrix file store, the instance lock |
| `timer` | the focus/break clock as a pure state machine |
| `undo` | the undo stack |
| `viewmodels` | what a row shows, with no opinion on drawing it |
| `rows` | which badges and wording a task has earned |
| `presenter` | what each screen says — the task list, NEXT UP, the banner, Today, the week |
| `ports` | what the app needs from the platform underneath it |

`presenter` is the one to read first. It holds the rules that make this app what
it is — a day with nothing finished shows no counter rather than a zero, an
empty week is omitted instead of listed, a missed booking stops claiming to be
today — as plain functions from data to small view models. A front-end that
calls it inherits the design law instead of having to rediscover it. **Do not
build a second view-model layer beside it.** Two portable presentation layers is
the exact failure this separation exists to prevent.

### Telling the platform where it is

`ports.Locations` is how a platform describes itself: a data directory, a matrix
directory, a config file, and a home used *only* to shorten a path for display.

```python
from cognitive_offload.ports import app_private_locations
from cognitive_offload.storage import Config

config = Config(locations=app_private_locations(context_files_dir)).load()
```

`desktop_locations()` reproduces the layout desktop installs already use, so
existing files are found exactly where they were left. `app_private_locations()`
is the other shape — everything under one directory, no dotfiles, no assumption
that a home folder exists — which is what Android hands an app and what a
portable install wants.

## What you have to build

### 1. The commands

About fifty verbs are wired to buttons and keys today, across the task list, the
scratchpad, the focus timer and the Eisenhower matrix. Three have no button and
exist only as shortcuts — focus the capture box, focus the search box, and pause
the running block — so a front-end without a keyboard needs to decide whether
they need surfaces of their own.

Read them off `main_tab.py`, `matrix_tab.py` and `_bind_shortcuts` in `app.py`
rather than from a list here, which would rot.

### 2. The asks

This is the part that does not port mechanically, and the part worth designing
before writing any code.

There are **8 rich dialogs** — the task editor, "Where do I start?", the start-a-
focus-block dialog, the quadrant picker, the one-line prompt, the session-end
dialog, the week review, and the shortcuts sheet — plus **36 `messagebox` calls**
(13 yes/no, 1 yes/no/cancel, 17 errors, 2 informational, 3 warnings) and **4
`filedialog` calls** (2 for a directory, 1 open, 1 save-as).

The hard part is not their number. It is that a decision and the question it
depends on are currently interleaved in the same method: the code asks, blocks
on a modal, and carries on with the answer. That shape works on a desktop and is
unimplementable on a phone, where a screen can be dismissed, backgrounded, or
destroyed while the question is open. A front-end for a phone needs the engine
to be able to say *"I need an answer"* and be resumed later, rather than to call
a function that blocks until one arrives.

### 3. The face

Roughly 1,600 lines of grid and pack live in `main_tab.py`, `matrix_tab.py`,
`widgets.py` and `theme.py`. No seam makes those portable. This is honest
per-platform work that nobody can shorten, and pretending otherwise is how a
port stalls halfway.

### 4. The pump and the lifecycle

The desktop drives the clock with a `after(250, …)` loop. A front-end supplies
its own tick, plus the lifecycle around it: claim the instance lock, load state,
autosave, and shut down. On Android the last of those is two different events —
the person choosing to leave, and the OS taking the process — and only the first
can be negotiated with.

## Three hazards

These are specific traps, each of which has already caught something.

**The clock stops when the device sleeps.** `app.py` hands `time.monotonic()` to
the focus timer. On Linux, and therefore Android, `CLOCK_MONOTONIC` does not
advance while the device is suspended; `CLOCK_BOOTTIME` does, and both are
reachable from the standard library through `time.clock_gettime`. A fifteen-
minute block on a phone whose screen sleeps would bank fewer minutes than the
person actually did — the precise failure this app spent a release fixing
elsewhere, because the minutes you did are the minutes you keep. A phone host
must supply BOOTTIME. The desktop must keep `time.monotonic`: changing it there
alters behaviour for no benefit.

**`_ask_over_focus()` is not a blanket rule.** It wraps exactly **9** of the
modal sites, not all of them. It exists to keep the always-on-top companion
window from covering a question, and applying it uniformly would fire the
topmost dance in places it never did. Any port that generalises "wrap every
dialog" is making a behaviour change while believing it is making none.

**Config is read from widgets, not from config.** `_save_config` takes the focus
length from the spinbox via `self._minutes()`, along with four other Tk
variables. So writing `config.focus_minutes` and then saving writes the *old*
value back, and the saved session length silently lags a session behind —
invisible until the next launch. A front-end must either set its own equivalent
of that control before saving, or stop reading the control.

## Checking you have not broken it

- `tests/test_portability.py` — every module in the table above imports with no
  Tk present, and the UI modules still fail there.
- `tests/test_porting_doc.py` — the specific claims in this file still match the
  code.
- The whole suite runs headless with no `DISPLAY` set at all; the display-bound
  tests skip and everything else passes. That is the quickest way to see how
  much of the app is already toolkit-free.
