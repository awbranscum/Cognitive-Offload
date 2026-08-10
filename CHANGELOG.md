# Changelog

All of this lives on the branch `claude/program-improvement-uqm40n`.
Newest first. Versions bump with each delivered change-set; the themes
throughout are task *initiation*, honest data, and a tone that never
scolds.

## 3.19.9 — The layout survives HiDPI screens
- Window sizes, the minimum-size floor, dialog widths and text
  wraplengths now scale with the screen's DPI. They were 96-DPI
  physical constants while fonts scaled with the display — on a 2x
  laptop panel the app opened at half its intended size with the text
  twice as large: truncated buttons, colliding headings, and the
  toolbar a full card-height below its card. One helper (theme.px)
  carries every measured 96-DPI number to the actual screen, and
  returns them unchanged at standard DPI.

## 3.19.8 — The pop-out keeps its promises on screen
- The floating focus window grows to fit a long, wrapping task title
  instead of pushing Pause and the Park row off its bottom edge. It
  re-fits whenever its text actually changes height and holds still
  otherwise — the two things it exists for (pausing, and parking an
  intrusive thought) stay reachable mid-block.

## 3.19.7 — Keyboard focus you can see
- Filled buttons draw their focus ring in the label colour, so keyboard
  focus is visible on the buttons that start things — "Where do I
  start?", "Start this", "Add task", the timer's Start. The inherited
  ring colour was the primary fill's own hex in the light theme, making
  focus on those buttons literally invisible. Outline and ghost buttons
  already showed theirs; the task list's focused border already worked.

## 3.19.6 — Closing the lid still counts
- Quitting mid-focus-block banks the elapsed minutes silently before the
  window goes. The momentum strip, week review and estimate calibration
  keep the time; closing without ceremony is a normal end of day, not a
  forfeit. Breaks and never-started blocks record nothing, and a
  cancelled quit ("save failed — stay?") keeps its block running and
  unbanked.

## 3.19.5 — Controls that show their state
- A checked checkbox is now visibly checked. The clam engine fills the
  box with one colour and draws the tick in another; the theme mapped
  the wrong option, so the tick was white on a white box and Calm mode,
  "Show done" and every dialog checkbox looked permanently off. Both
  themes verified.
- Mid-session, "Not that one" counts the suggestions it can actually
  reach (the in-focus task and snoozed tasks are not in the pool). With
  only one reachable option it says so instead of silently doing
  nothing.

## 3.19.4 — NEXT UP knows what you're doing
- While a focus block is open (running, or paused partway), the NEXT UP
  box never suggests the task the block is on — "what should I start?"
  is not answered by the thing already underway. With nothing else to
  offer it goes quiet instead of pitching a mid-focus task switch, and
  the moment the block ends the task is suggestible again ("another
  round when you're ready" and the box may rightly agree).

## 3.19.3 — A minimum size that means it
- The minimum window size (1160×790) is measured against the worst
  legitimate state — a running session with a long, wrapping NEXT UP
  title — instead of a size where controls quietly clipped off the cards.
- Compact buttons hug their labels: ttk's hidden nine-character minimum
  made "Pin" cost as much as "Clear done", which is what pushed the task
  toolbar and the "Show done" filter off the card at small sizes.
- "Not that one" and "Not today" sit side by side under "Start this" —
  two escape hatches are peers, and the stack was a button-height too tall.
- NEXT UP text wraps to the space it actually has instead of clipping
  mid-word at a fixed width.
- When exactly one tag badge would overflow, it is shown rather than
  summarised — "+1" costs the same space as the badge it hides.

## 3.19.0 — The week, in evidence
- Click the momentum strip (or its summary) for a week review: one line per
  day that had anything — sessions, minutes, and the tasks finished that
  day. Days with nothing are simply omitted, never listed as zeros, and a
  quiet week is called exactly that.

## 3.18.x — Polish
- 3.18.3: the task toolbar is one row of seven and no longer clips off the
  bottom of the card while a session is running.
- 3.18.2: "Where do I start?" sizes to its content instead of forcing a
  fixed height with a dead band above the buttons.
- 3.18.1: the done-today pill disappears entirely at zero (no empty green
  box); the hover highlight survives list re-renders; a block crossing
  midnight says "ends 00:12 *tomorrow*"; a refused timer start can no
  longer clear the running block's parked thoughts.

## 3.18.0 — The focus clock as a pure state machine
- The timer's invariants — never invent minutes, never credit a break as
  focus, never let a stale total fake progress — moved into `timer.py`,
  testable without a display. Thirteen new headless tests; the UI test
  suite passed unchanged.

## 3.17.0 — Internals sweep
- A typed undo stack (`undo.py`), one shared row builder (`rows.py`),
  single sources of truth for the sort-key and kind-label maps, a verified
  dead-code sweep, and the while-typing shortcut guard's missing test.
- Open… applies the same unreadable-records consent rule as startup.

## 3.16.0 — Refuse what would be lost quietly
- A session file saved by a newer version is refused in place instead of
  being silently amputated and re-saved.
- Task records that fail to parse are counted and reported; auto-save
  stays off until an explicit Save consents to the loss.
- A matrix folder that vanishes mid-run (unmounted drive, moved directory)
  is named in the status bar, and writes refuse instead of forking a
  fresh empty tree; session-log quarantines are timestamped.

## 3.15.0 — The session rituals belong to the user
- The warm-up ladder is editable inside the start dialog ("Edit steps…"),
  and a checkbox folds it away — or brings it back.
- "Keep the timer floating over my work": the pop-out opens itself at
  session start, remembered between runs.
- Parked thoughts come back: the session-end dialog counts them and the
  scratchpad scrolls to them once attention is free.

## 3.14.0 — Finish the unfinished styling
- Row state markers at readable contrast; "N done today" as a quiet
  success-tinted pill; spinbox focus ring, tab hover and disabled states;
  ghost buttons on dialog bodies fixed; the start dialog sizes to content;
  the shortcut sheet aligns to one key column.

## 3.13.0 — Give the task list its screen back
- Search and filters share one row, the capture card stops stretching, the
  list gets a minimum height, and NEXT UP sits in a contained border so
  the app's most important element reads as one unit.

## 3.12.0 — Time and gentleness
- A soft landing: the last two minutes of a block announce "a good moment
  to find a stopping point" (amber in the pop-out — never red).
- Booked badges speak temporal distance: "booked tomorrow", "booked Fri",
  "booked in 12 days".
- A snoozed task's editor offers "put it back in the running now".

## 3.11.0 — An "about how long?" guess on every task
- Optional estimate in minutes; a muted `~25 min` badge; "Your guess:
  about 25 min." in the start dialog; and at completion the guess meets
  the real number in the status line — calibration, never a mark.

## 3.10.0 — Booked work starts in one click
- "Focus on this" in every quadrant imports the task and opens the start
  dialog; the booked-today banner selects the actual rows; Ctrl+M lands on
  the destination quadrant with the new rows selected; the date-format
  hint reads in full.

## 3.9.0 — Warm starts and a "Not today" that means it
- Tasks worked in the last two days rank warmer in NEXT UP and the picker
  (the hand-off you wrote finally gets read).
- "Not today" excuses the current suggestion until tomorrow: no badge, no
  counter, silent expiry, Ctrl+Z takes it back.

## 3.8.0 — Two silent data-loss holes closed
- A lock file catches a second copy of the app before the copies silently
  overwrite each other's saves every 30 seconds.
- A failing auto-save says so once, calmly; quitting with a broken save
  offers "save a copy somewhere else first".

## 3.7.x — Trust repairs
- "Move to top" became a real pin: sorts above everything open, survives
  re-sorts and restarts, honest about non-default sort orders.
- Matrix moves can no longer duplicate a task into both stores on an I/O
  error; undo survives files being renamed or moved after the fact.
- Saves survive lone-surrogate unicode; a timer expiring under an open
  dialog waits instead of breaking modality; the pin nudges suggestions
  and survives the matrix round-trip.

## 3.6.0 — Recovery that deserves the name
- An unreadable session file is set aside under a timestamped name, the
  backup is offered for restore, and nothing the app then does can
  destroy either copy. (The old advice destroyed both.)
- Replacing a running session banks the old minutes silently instead of
  opening the old block's end ceremony mid-start.

## 3.5.x — The starting problem, on the front page
- NEXT UP: the app names the next thing on the main screen — task, first
  step, Start — instead of behind a picker.
- Session end became keyboard-safe (Enter keeps your hand-off, never marks
  done by accident); "Done early" works on every block; the minutes
  spinbox can't wipe a paused block.

## Before the loop (the branch's foundation)
- Restructured into a tested package; fixed the original data-loss and
  selection bugs.
- Built the app around task initiation: first steps, "feels like"
  categories, the warm-up ladder, 15-minute sessions, the start picker.
- Ported shadcn/ui's design system to ttk; added dark and calm modes.
- Fixed the audited defect backlog; added the done-today ledger and the
  hand-off prompt; met WCAG contrast targets with computed, not eyeballed,
  colours.
