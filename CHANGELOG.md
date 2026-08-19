# Changelog

All of this lives on the branch `claude/program-improvement-uqm40n`.
Newest first. Versions bump with each delivered change-set; the themes
throughout are task *initiation*, honest data, and a tone that never
scolds.

## 3.46.0 — Moving a task between the tabs no longer loses part of it
Two docstrings promised totality and neither kept it. `add_from_task` said it
moved a task *"without dropping any fields"*; `to_task` said it kept *"every
field"*. Both were true when written, and both were made false by later
commits on this same branch — the failure this branch keeps finding, this
time in its own new code.

- **Four fields were being dropped.** Measured on a real round trip:
  `repeat` (added v3.45.0), the three handoff marks `handed_to` /
  `handed_off_on` / `follow_up_on` (added v3.44.0), and `snoozed_until`
  (pre-existing). Both conversions are hand-written lists of assignments and
  **nothing checked the list against the models**.

- **The worst case was a regression in a feature one release old.** Hand a
  task to Claude Desktop, press **Send to tasks**, and it left Delegate
  entirely and arrived in the main list with no waiting state, no badge and
  no subtitle — while the brief sat on disk and the agent may have been
  working on it. That is exactly the disappearance the handoff exists to
  prevent, walked in through a different door, in one click, with no warning.
  The `repeat` case was the same shape quieter: the row said "every week",
  and a trip through the matrix took that away with nothing connecting the
  loss to the action.

- **The fix leads with the test, because the symptom was four fields and the
  disease was that the next one would go the same way.**
  `tests/test_conversions.py` is keyed on `dataclasses.fields()` of both
  models: a field on one side with a home on the other must be carried, or
  **named in an exemption list with a reason**. Four are named — the id and
  `created_at` (a move makes a new record) and `done`/`completed_at` (a
  quadrant has no finished state) — and each exemption has its own test, so
  the list cannot become a place to hide a bug. It is not silenceable either:
  adding a genuinely-lost field to the exemption list still fails, because a
  separate test compares the two models' fields directly.

- **The fixture is guarded too.** A field left at its default compares equal
  after being dropped entirely, so a fixture built from defaults would pass
  no matter how broken the conversion was. A test asserts every field of both
  fixtures is set away from its default, and another checks the round trip
  **through the disk** — a field carried by the conversion but missing from
  `to_dict` would pass in memory and still be gone by morning.

- **Both docstrings now state what is actually true**, and a test refuses the
  unbounded phrasings that caused this, so the claim cannot loosely return.

- **The waiting mark now follows the task**, and both tabs say the same thing
  from the same code: the badge and the "Waiting on …" line moved into the
  shared row helpers rather than living only in `matrix_row`.

- **A task that is out with an agent is no longer offered as the next thing
  to start.** *Found by looking at the running app, not by a failing test:*
  NEXT UP was showing **"Start this"** over a task that was out with Codex —
  the app inviting you to duplicate work someone else was already doing. It
  now gets the same treatment as "Not today": it stays in the list and in
  every search, and only stops guarding the suggestion slot. On the
  check-back day it returns to the running, because from then on picking it
  up again is a real option.

- **A way back that does not depend on which tab you are on.** Carrying the
  mark onto the main list would otherwise have left a task marked as out with
  nothing able to clear it. The task editor now offers *"Out with Claude
  Desktop, checking back Friday — take it back and do it yourself"*, built
  exactly like the existing exit from "Not today" and visible only while a
  handoff is actually in effect.

- 630 → 651 tests, Xvfb (`skipped=2`) and headless (`skipped=264`). **Fourteen
  promises broken on purpose and all fourteen caught**, including reverting
  each half of the fix to confirm the new tests reproduce the original bug,
  and an attempt to silence the completeness guard by widening its own
  exemption list.

## 3.45.0 — Things that come back round
The app could not hold a recurring task at all. Every task was one-shot,
which leaves out bins, meds, bills and standing appointments — precisely the
things this audience loses, and precisely the things an external memory is
supposed to be for.

- **Repeats: daily, weekdays, weekly, fortnightly, monthly**, set in the task
  editor beside the estimate. Deliberately a small vocabulary — a recurrence
  grammar with "every 3rd Tuesday" in it is a second app, and this list covers
  what actually goes missing.

- **Finishing one completes that round and books the next.** It does not reset
  the date. Resetting would quietly delete the evidence that you did it, and
  the week review — the screen whose entire job is answering *"I did nothing
  this week"* — reads exactly that evidence. Doing the bins six weeks running
  should look like six things done, not like one task that is somehow never
  finished. There is a test named for that sentence.

- **A missed repeat never becomes a backlog.** The next date is worked out
  from **today** whenever the booking has already passed, so two weeks off the
  bins gets you one task asking about the next collection — not fourteen
  copies of a task you already feel bad about. A pile of overdue duplicates is
  the most reliable way to make someone stop opening an app, and this
  application cannot afford it.

- **The rhythm holds when you are on time.** If the booking is still ahead
  because you did it early, the next one counts from the booking rather than
  from today, so a Friday task stays a Friday task instead of drifting a day
  earlier every week. Those are two different rules and both are pinned:
  making the code always count from today fails three tests, and making it
  always count from the booking fails one.

- **Weekdays skips the weekend; monthly does not skip February.** 31 January
  repeats to 28 February rather than overflowing, and Friday repeats to Monday.

- **A repeating task is visibly different from a one-off**, because otherwise
  the reasonable thing to do with a finished one is delete it — taking the
  recurrence with it. The badge uses the same quiet grey as the estimate and
  the tags: "this comes back" is information, not a signal.

- **A snooze does not carry into the next round.** "Not today" was about
  today, not about every future Tuesday.

- **Two new status sentences were nearly shipped watched by nothing.** They
  were built with `status += ...`, and the wording extractor cannot see an
  augmented assignment — the snapshot diff showed the *old* sentence moving
  category and no sign of the new ones. Both are now their own `status =`,
  which is a smaller change than it sounds and the difference between a
  sentence that is checked for tone and one that is not.

- 605 → 630 tests, Xvfb (`skipped=2`) and headless (`skipped=259`). **Nine
  promises broken on purpose; eight caught, and the ninth found a test that
  could not fail.** `test_reopening_a_repeating_task_does_not_book_another`
  asserted a count that was the same under both implementations, because
  `target` is only true when something selected is still open — so a lone
  finished task takes the no-op branch either way. The guard only bites on a
  **mixed selection**, one finished task and one open one. Rewritten to that
  shape, it fails against its mutant; the old single-selection version was the
  "input where every implementation agrees" trap for the third time on this
  branch.

## 3.44.0 — Delegate is a quadrant you can actually use now
"Give it to someone else" needs a someone else. For a lot of people there
isn't one, so Delegate fills up and becomes a second Do First with a politer
name. An agent is something to delegate *to*.

- **"Hand off to an agent"**, the primary button in Delegate — the same way
  "Book a time" is the primary button in Schedule, because each quadrant's own
  verb should lead rather than sit among the ghosts. It writes a **brief** —
  the title, your details, the first step, the booked date, the estimate and
  the tags, plus anything you type — and puts the command to run it on your
  clipboard. Targets: **Claude Desktop** (Markdown), **Codex** (Markdown),
  **OpenClaw** (JSON).

- **Nothing is sent anywhere.** No network request, no socket, no subprocess:
  the app writes a file and copies a line of text, and the person starts the
  agent. That keeps the zero-dependency promise, keeps the app working
  offline, and — the real reason — means a brief written in thirty seconds by
  someone trying not to lose a thought is **readable and editable before
  anything acts on it**. Every brief also asks the agent to check first before
  spending money, messaging another person, or doing anything that cannot be
  undone; it comes from one constant, so the Markdown and the JSON cannot
  drift into asking for different things.

- **A handoff is not allowed to become a disappearance.** This is the half
  that usually gets lost, and losing it is the ADHD failure mode of delegating
  in the first place: hand it over, forget it, discover three weeks later that
  nobody did it. The task stays in Delegate carrying **who has it, since when,
  and a day to check back**. It wears a `waiting` badge, and on the check-back
  day that becomes `check back` — a fact, not a telling-off, and never
  "overdue". The waiting line takes the subtitle from the first step, because
  the first step belongs to whoever has the task now. **Take it back** clears
  it, and says "Back with you" rather than anything about failing. Both
  actions are undoable with Ctrl+Z, like every other matrix command.

- **The quoting is structural, not hopeful.** A handoff folder called
  `~/My Documents` is ordinary, and an unquoted path there produces a command
  that silently runs against the wrong thing. Shell targets get `shlex.quote`;
  Claude Desktop's line is pasted into a chat window, where shell quoting is
  only noise, so it gets the plain path. Codex uses `"$(cat {brief})"` rather
  than embedding the path inside a prompt string, so `{brief}` stays a single
  shell word — the first draft nested quotes and produced a broken command,
  which is why there is now a test that **runs** the generated command against
  a stub and reads `argv[1]`. Handoff filenames are hyphenated rather than
  reusing `storage.slugify`, which keeps spaces on purpose and is right where
  it lives — the same "correct at one boundary, wrong at another" trap as the
  estimate coercion in v3.42.0.

- **What this app cannot verify, it does not claim.** It cannot ask Claude
  Desktop, Codex or OpenClaw what they currently accept, so the commands are
  **conventions, stated as conventions** in `docs/AGENT_HANDOFF.md`, and every
  one is overridable through `handoff_commands` in the config without editing
  source. A template with a typo in it falls back to naming the file that was
  written: the brief is the deliverable, the command is a convenience.

- **The briefs live outside the app's data folder**, in
  `~/CognitiveOffloadHandoff/`. Giving an agent access to the folder holding
  all of your tasks and notes is a much bigger grant than most people realise
  they are making; giving it access to a folder holding only what you chose to
  hand over is not.

- **One duplicated sentence collapsed on the way through.** `rows.py` exists
  because the two tabs' subtitles were copy-pasted — and the drift arrived
  exactly as predicted: moving the matrix subtitle into a conditional dropped
  `→ {}` off the wording snapshot while the identical string in the main list
  kept it looking covered. Both now come from one `_step_or_summary`.

- 564 → 605 tests, Xvfb (`skipped=2`) and headless (`skipped=249`). **Fifteen
  promises broken on purpose and all fifteen caught**: unquoted shell paths,
  spaces back in filenames, the two formats asking for different things, an
  unknown target raising instead of falling back, a follow-up date that never
  moves, zero-day follow-ups, the first step beating the waiting line, "check
  back" reworded to "overdue", `handed_to` not persisted, an exclusive
  `is_due_back`, the task never marked waiting, the command never reaching the
  clipboard, the handoff not registering an undo, marking a task waiting after
  the write failed, and a cancelled dialog handing over anyway. The doc is
  pinned to the code four ways and verified by corrupting each. The
  cancellation test patches the confirmation dialog it asserts is never
  reached — unpatched, that regression **hung** instead of failing.

## 3.43.0 — The week review can no longer run off the bottom of the screen
The one screen whose whole job is to say "you did more than you think"
was the one that could hide its own answer.

- **A busy week rendered taller than the screen.** *This week* fits itself
  to its content and is not resizable, by design: a fixed height leaves a
  dead band on a quiet week. But the content has no upper bound — it grows
  with every finished task, and long titles wrap to two or three lines
  each. Measured on a seven-day week of long titles: 508px for one task a
  day, 718 for two, **928 for three, 1138 for four**. On a 1366×768 laptop,
  three finished tasks a day put the window 160px past the bottom edge.

- **What fell off was the point of the screen.** Bottom-up, the first
  things past the edge were the totals line — *"14 sessions · 350 minutes
  across the week"*, the single most reassuring number this app produces —
  and then the Close button. So the failure was worst on exactly the week
  that had earned the number, and it left someone in a modal with no
  visible way out. Escape still closed it, but only if you knew.

- **The days scroll; the total and the way out do not.** The day list moved
  into a canvas with a ceiling of 80% of screen height, with the totals
  label and Close pinned below it on the dialog itself. The scrollbar packs
  itself only when there is something to scroll, so an ordinary week grows
  no furniture it does not need, and the canvas asks for exactly the height
  the days want up to that ceiling — otherwise the fix would have traded a
  window that overflows for a window that scrolls when it has one day in
  it. Mouse wheel and Button-4/5 scroll it.

- **Three copies of the fit-to-content line had drifted apart.**
  `self.geometry(f"{self._fit_width}x{self.winfo_reqheight()}")` appeared
  in `show()`, in the suggestion refresh and in the ladder editor. A
  ceiling added to one would have silently missed the other two, so all
  three now call one `ModalDialog._fit_to_content()`, which is where the
  `_max_height` opt-in lives. Every fit-to-content dialog can now take a
  ceiling; only this one asks for one.

- 562 → 564 tests, Xvfb (`skipped=2`) and headless (`skipped=243`). Both
  new tests were checked against four separate mutants — no ceiling, an
  unbounded canvas, a canvas that always takes the ceiling, and a scrollbar
  that is always packed — and each mutant fails the suite. The busy-week
  fixture is deliberately larger than a real week, because a test screen
  taller than a laptop would otherwise have passed it for the wrong reason.

## 3.42.0 — "20 mins" is now an estimate, not a discarded keystroke
The time-estimate field understands what people actually type.

- **Everything except a bare integer used to become "no guess".** Silently:
  `"20 mins"`, `"20m"`, `"1h"`, `"~15"` and `"1.5"` all landed as **0**.

  The label is *"About ⬚ minutes, at a guess"* with the word **minutes
  printed to the right of the box**, so typing "20 mins" into it is the
  natural thing to do — and it was the input most reliably thrown away.

  The cost is invisible and arrives a week later. `estimate_minutes = 0`
  means "no guess", so a discarded estimate is indistinguishable from a
  blank field, and the calibration line — *"You guessed ~20 min; it took
  about 35 across your sessions"* — then never appears, with nothing to
  connect that silence to what was typed. Estimating exists here for
  time-blindness calibration, so this quietly switched the feature off for
  anyone who typed a unit.

- **The fix understands more rather than complaining more.** The dialog
  carried the comment *"junk is just 'no guess', never an error dialog"* —
  a deliberate decision, and the right one: an optional guess is not worth
  stopping someone with a modal. So no warning was added. Instead
  `parse_estimate_input` reads a bare number, an optional `~` or "about",
  and a unit — `m`, `min`, `mins`, `minutes`, `h`, `hr`, `hours` — while
  anything it still cannot read stays a silent "no guess", exactly as
  before. `"2 hours"` is 120; `"1.5h"` is 90; `"9999"` still clamps to the
  same eight-hour ceiling the store uses.

- **The persistence coercion was left exactly alone.** `models._as_minutes`
  keeps its docstring, *"junk becomes no guess"*, because that is right
  where it is used: a corrupt file must not crash. What was wrong was
  reusing a persistence coercion as an **input validator** — silently
  accepting junk from a file protects the user; silently discarding what
  they just typed does not.

- 555 → 562 tests, Xvfb (`skipped=2`) and headless (`skipped=241`). Pinned
  at both layers, and the dialog test fails if the old `int()` coercion
  comes back. A test also pins that unreadable input raises **no** modal,
  so the decision that was kept cannot be undone by accident. pyflakes
  clean, snapshot unchanged.

## 3.41.0 — a long task stops being cut off in the list
The list can now show the whole of what you captured.

- **About two thirds of a long task was simply missing.** A 137-character
  task showed roughly 78 characters. Not scrolled off, not shortened with
  an ellipsis — absent, ending mid-word, behind a scrollbar that only goes
  down. Nothing indicated there was more, so two tasks beginning the same
  way ("ring the council about the bins…" / "…about the tax…") looked
  identical on the list.

  The title label had `wraplength=0`, the row frame is clamped to the
  canvas width, and the list has only a vertical scrollbar. Titles and
  subtitles now wrap to the width actually available, recomputed when the
  window resizes and applied to rows built later from the pool.

- **The app already did this everywhere else.** The pop-out window has
  wrapped its task and step labels all along, with a test of its own. The
  main list — the surface people actually work in — never got the same
  treatment. The capture card's hint is *"Anything in your head — it does
  not have to be tidy"*: it invites the long untidy thought, so the list
  has to be able to show it.

- **Short rows do not pay for it.** A one-line task stays one line and the
  row stays 35px; the long one grows to two lines and 52px. Wrapping is
  the fix rather than an ellipsis because it makes the whole task readable
  where it is, and it costs vertical space only on the tasks that need it.

- **Nothing got slower.** 300 tasks still paint in about 0.7s and a search
  keystroke still costs about 50ms — unchanged either side of this.

- 554 → 555 tests, Xvfb (`skipped=2`) and headless (`skipped=239`). The new
  test fails if the wrap width goes back to zero. pyflakes clean, snapshot
  unchanged.

## 3.40.0 — the day you booked a task for now counts
**This changes which task "Where do I start?" offers.** It is a small,
deliberate behaviour change to the flagship feature, not a pure fix.

- **The day you booked a task for was invisible to the ranking.** `is_due`
  is inclusive of the past on purpose — a booking you missed still deserves
  a route back — but that made a booking *for today* and one missed a month
  ago score identically, and the order then fell through to the created-at
  tiebreak and finally to **the first letter of the text**. Two tasks alike
  in every way except when they were booked came out alphabetically.

  Someone who misses bookings accumulates them, so without this their
  backlog competes with today's plan and wins on spelling. The feature got
  noisier for exactly the person who needs it most.

  The booked day is now a **tiebreak** among work that is otherwise equal:
  today's plan first, missed bookings keeping their own order, oldest
  first. Missed bookings are not demoted or hidden — they still score the
  full arrived-booking weight.

  **What this changes in practice:** on a realistic list, a task booked for
  today now comes before one that merely has a written first step, where
  before the older capture won. Those two *tie* on score, so this only
  settles what used to be settled by the alphabet — but it is a visible
  difference in what the app suggests.

- **A wrong version was tried first and rejected.** As a weighted score
  term rather than a tiebreak, a booking for today beat a written first
  step outright — a different and much larger claim, and one the module's
  own docstring does not make. **The whole suite passed under both
  versions**, which is why the difference had to be found by reading the
  output rather than the result.

- **A ranking test passed on the alphabet.**
  `test_a_booked_task_that_is_due_comes_first` put an overdue booking
  against a task with a first step and asserted the booking won. Both score
  −3, so the tie fell to text sort — and "booked" precedes "plain". Renaming
  the two fixtures reversed the result: the property it named was never
  true. **Every fixture in that group is now named so the alphabet argues
  against the thing being asserted**, which means passing can only be the
  ranking's doing.

- **An open question is recorded rather than answered.** `is_ready` and
  `is_due` are both weight 3, so a written first step and an arrived
  booking are *equal* — while the docstring lists them in an order that
  reads like a priority. Which should win is the owner's call, so a test
  now pins the current behaviour honestly (the tie is broken by age) and
  says in its own docstring that it is describing, not endorsing.

- 551 → 554 tests, Xvfb (`skipped=2`) and headless (`skipped=238`).
  pyflakes clean, snapshot unchanged.

## 3.39.0 — the pop-out's clock could have frozen and nothing would say
No behaviour changes. A second mutation sweep ran over ten promises the
first one did not touch; **nine were caught** — the instance lock's
certain/uncertain split, autosave blocking after unreadable records, the
matrix undo helper's drop-before-restore ordering, the calibration line,
NEXT UP excluding the block you are already in, "today" meaning today
rather than "today or earlier", the warm-up plural, calm mode clearing
filters before hiding them, and `is_due` staying inclusive of the past.
Across both sweeps: twenty promises, seventeen guarded. This closes the
one survivor.

- **The pop-out's clock was never checked for counting down.** Making
  `_sync_focus_window` read the block's *total* instead of its *remaining*
  time left all 551 tests passing. What that looks like:

        main window | pop-out
        14:00       | 15:00
        13:00       | 15:00
        12:00       | 15:00

  The pop-out freezes at its starting time while the main window counts
  down — and the pop-out is the always-on-top window someone stares at
  *during* a block. It exists so the countdown stays visible while you
  work in another app, so a frozen clock is the feature failing silently
  at the only moment it is used, with the main window looking fine.

- **The test named "updates" was checking the wrong thing.**
  `test_focus_window_opens_updates_and_closes` ticked the clock forward
  and asserted `time_var != "00:00"` — which a clock stuck at 15:00
  satisfies. It checked the string was not zero, never that it *changed*.
  That is the same shape as the rounding test fixed in v3.38.0: a
  predicate that cannot distinguish the implementations, sitting under a
  name that claims it can.

  It now ticks three times and asserts the pop-out **agrees with the main
  window** at each tick, and that the main window actually counts down.
  Asserting the agreement rather than either clock's value means a change
  on **either** side is caught — verified both ways: breaking the pop-out's
  sync fails it, and breaking the main window's label fails it too.

- **One promise was checked and needed nothing.** The pop-out's
  Pause/Resume button is already guarded — freezing its text fails
  `test_pausing_updates_the_pop_out_button`. Worth stating, because the
  useful result of a sweep is as often "this is covered" as "this is not",
  and inventing a second test for it would have been noise.

- 551 tests, unchanged in number; Xvfb (`skipped=2`) and headless
  (`skipped=238`). pyflakes clean, snapshot unchanged, no source file
  touched.

## 3.38.0 — two promises nothing was guarding, found by breaking them
No behaviour changes; no source file changed at all. Ten of the app's
stated design promises were broken one at a time and the suite run against
each. **Eight were caught** — plural, the no-zero momentum line, the
empty-list branch, the after-midnight "tomorrow", the year on past dates,
the "(0)" quadrant tab, undo registration on add, and the zero-pill day
counter. This release closes the two that were not.

- **A test guarding the snooze was checking one layer below where it
  breaks.** `Task.snoozed_until` promises "Never filters the task list
  itself", and a test is named for it —
  `test_a_snoozed_task_leaves_the_suggestions_but_not_the_list`, whose own
  comment reads "The list itself never hides it." It asserted on
  `filter_tasks`.

  But the screen does not read `filter_tasks`. `task_list_view` calls
  **`visible_tasks`**, which wraps it — so a snooze filter added in the
  wrapper, the one place someone would plausibly add it, left all 549
  tests green. Shipped, that would make "Not today" take the task off your
  list for a day: the "my work disappeared" moment v3.34.0 was written to
  prevent.

  The original assertion stays; two more join it, at `visible_tasks` and
  through `task_list_view`, so a filter introduced anywhere between the
  data and the rows is caught.

- **The rounding promise was only ever tested where every rule agrees.**
  v3.28.0 promised the replace-a-block question names the number that
  actually gets banked. Both sides use `max(1, round(…))`. The two tests
  covering it use 300 and 20 seconds — and **300 seconds is five minutes
  exactly**, where `round` and floor division give the same answer. Swapping
  one for the other was invisible, so the question could drift away from
  the log unnoticed: the same defect, in the other direction.

  The new test uses **342 seconds — 5.7 minutes, where `round` says 6 and
  floor says 5** — and asserts the question and `bank_early` **agree**
  rather than hard-coding six. The promise is the agreement; pinning the
  arithmetic would only restate the implementation. It now catches a change
  on *either* side, verified by flooring each in turn.

- **The method is worth keeping**, and the harness is saved. Breaking a
  promise on purpose and watching for red is the only way to tell a guard
  from a decoration — it has now found three things this branch believed
  were covered: the quadrant-to-tab pairing, the capture guard, and these
  two. Every mutant restores from a pristine copy, because a run that hangs
  takes its own cleanup down with it.

- 549 → 551 tests, Xvfb (`skipped=2`) and headless (`skipped=238`).
  pyflakes clean; the snapshot is unchanged, as no wording moved.

## 3.37.0 — a test that could not fail, and a key nobody was told about
No behaviour changes. One test starts working for the first time, and the
keyboard cheat-sheet stops being a promise nothing checks.

- **A test guarding capture passed with the guard deleted.**
  `test_typing_in_the_capture_box_never_triggers_task_shortcuts` says in
  its own docstring "capture must never fight your fingers": it types
  `Delete`, `Ctrl+P`, `Ctrl+T` and `Ctrl+Up` into the capture box and
  asserts nothing was deleted, prioritised or pinned. Removing the
  while-typing guard entirely left it **passing**.

  The cause was that `setUp` withdraws the window, and a withdrawn window
  receives no key events at all — so "nothing happened" was true for the
  wrong reason. The window is now mapped, focus is waited for, and **a
  probe key is proved to arrive before any negative result is believed**;
  if the display will not cooperate the test skips rather than pretends.
  With the guard broken it now fails in a quarter of a second: priority
  becomes 1 and the task becomes pinned, from four keystrokes of ordinary
  typing.

  What it protects earns the ceremony. Typing "Delete the old files" into
  the capture box must not delete the selected task.

  The dialogs are patched inside the test — not to weaken it, since with
  the guard working none is ever reached, but so that a regression
  **fails instead of hanging**: `Ctrl+T` opens a modal prompt, and a
  blocked CI runner is a far worse signal than a red one. That was found
  the hard way, by hanging.

- **Enter opens the task editor, and the help never said so.** It has been
  bound since the list widget was written. `Ctrl+D` and a double click
  were documented; the key a keyboard-first user actually reaches for, and
  the only editing route needing no chord to remember, was not. The row
  now reads "Enter / Double click / Ctrl+D".

- **The cheat-sheet is pinned in both directions**, in the idiom the
  README fix established: every shortcut the help lists must be bound, and
  every global binding must be listed. Both were already true — this
  records it. Verified by corrupting each way: a row naming a key nothing
  binds, and a binding the sheet never mentions. A help page is read by
  someone who could not remember the key, which is exactly the person who
  will not work out that it is wrong.

- 546 → 549 tests, Xvfb (`skipped=2`) and headless (`skipped=237`).
  pyflakes clean. Snapshot stays at 410 entries, one replaced.

## 3.36.0 — "1 line(s)", on the feature that matters most
A small user-facing fix, and the clearest evidence yet that the coverage
work was worth doing.

- **Two status messages still said "(s)".** The brain dump reported
  *"Moved 1 line(s) into tasks."* and the Line → task button reported
  *"Sent 1 line(s) to the task list."* Both now use `presenter.plural`:
  "Moved 1 line into tasks.", "Moved 3 lines into tasks."

  v3.26.0 removed "1 task(s)" from fifteen status messages, and
  `presenter.plural`'s own docstring says it "reads like output from a
  machine that did not care enough to look". These two survived on the
  **brain dump** — the feature that most directly serves "get it out of
  your head" — and for the Line → task button the singular is not an edge
  case, it is *the* case: the button sends one line.

- **They survived because they are passed positionally**, to
  `_add_tasks(lines, "…")`. That is exactly the blind spot closed in
  v3.35.0; these two entered the snapshot for the first time in that
  release, as kind `arg`. The wider net found a live instance of a defect
  the project believed it had eliminated, one release after being widened.

- **The next one is guarded generically.** A test now fails if `(s)` appears
  anywhere in the snapshot, so the form is caught wherever it is written —
  subject to the standing caveat that the extractor has to be able to see
  the position at all.

- `_add_tasks` now offers templates a pluralised `{lines}` beside the bare
  `{count}`, and a template using neither passes through untouched —
  "Captured as task." is unaffected, and a test pins that.

- 541 → 546 tests. Restoring either "(s)" fails three behavioural tests and
  the generic guard. Xvfb (`skipped=2`) and headless (`skipped=234`).
  pyflakes clean; the snapshot stays at 410 entries, two replaced.

## 3.35.0 — the third axis, and a claim this file had to stop making
No behaviour changes. The wording net grows by nearly half, and the
snapshot stops saying something untrue about itself.

- **A quarter of the app's wording was never watched.** Coverage has three
  independent axes and only two had ever been fixed: which **files** are
  read (v3.33.0), which **keyword arguments** count as wording (v3.34.0),
  and which **syntactic positions** are looked at at all. The third was
  still wide open. A string that is an element of a dict, list or tuple —
  or passed positionally — is not an assignment, not a return and not a
  keyword, so neither earlier fix could reach it.

  Ninety-two strings were sitting there, and they were not offcuts:

  - **all four Eisenhower quadrant descriptions**, including *"Not urgent,
    not important. Deleting these is progress, not failure — a shorter
    list is easier to face."*
  - **the entire keyboard-shortcuts dialog**, every row of it
  - **the warm-up ladder steps** — a named feature — such as "Clear the
    desk and close the tabs that are shouting"
  - the preset names, and about twenty-five **undo action names** passed
    positionally ("mark it done", "send it to the matrix") which are read
    back to a person in the status bar

  Since the no-shaming scan reads this same snapshot, every one of them
  was unchecked for tone as well. Checked before widening, as last time:
  **zero shaming hits** across all 92, so no wording had to change first.
  283 → 410 entries, nothing removed.

- **`value=` joined the watched keywords**, which caught "Nothing picked
  yet" — the label above the timer — and "Ready.", the status bar at
  rest. Both are on screen the moment the app opens, and neither had ever
  been watched.

- **The inverted extractor was prototyped and rejected.** Capturing every
  prose literal and excluding known noise gives 474 entries against 410,
  but most of the surplus are *fragments* of f-strings the extractor
  already assembles whole — `" min logged, and that one is done."` beside
  the complete `"{} min logged, and that one is done."`. Readability is
  the point of this file; a diff nobody can read is a net nobody checks.
  Recorded here so the idea is not re-attempted from scratch.

- **The snapshot stopped claiming to be complete.** Its header opened with
  "Every user-visible string, extracted from the source" and the module
  docstring said "Read every user-visible string". Neither was true, for
  many releases. Both now say what is actually read and note plainly that
  anything outside those positions is unwatched — a net that overstates
  its reach is worse than one that states it plainly, because it stops
  people looking for the gap. A test fails if the old claim comes back.

- 537 → 541 tests. Each new rule was verified by deleting it: removing the
  container pass fails the container guard, removing the positional pass
  fails the positional guard, and neither masks the other. Xvfb
  (`skipped=2`) and headless (`skipped=230`). pyflakes clean.

## 3.34.0 — an empty list stops telling you to stop
The first change in a while that a person will actually see, and it fixes
the app telling you the opposite of the truth at a bad moment.

- **A filtered list said "take the win and stop" over work you had not
  done.** Type a search that matches nothing and the list empties. It then
  showed *"Nothing here. Capture a thought above — or take the win and
  stop."* — congratulating you on a finished day with three tasks still
  outstanding behind a search term you had already forgotten. The only
  evidence to the contrary was a muted "· 3 hidden" in the far corner of
  the heading.

  For this app that is worse than untidy. "Put it down and it will be
  there" is the whole promise, and a list gone empty where your work was
  reads as loss rather than as a filter — this is not an audience that
  calmly goes hunting for the cause. It was also the app breaking its own
  rule about assembling state from two places at a hard moment.

  It now says **"3 tasks still here — the filters above are hiding them."**
  Nothing is asked and nothing is offered to click: an empty list is
  already a moment of doubt, and a decision on top of it is the last thing
  that helps. There is no clear-filters control to point at, so it does
  not invent one — it says what is true and where to look.

- **The case that is right was left exactly alone.** Finish everything and
  untick "show done" and the list also empties — but nothing is
  outstanding, so "take the win and stop" is correct there, and it still
  says that. The distinguishing signal is the open count, which
  `task_list_view` already had in hand and was throwing away into a
  summary string. Both branches are pinned behaviourally, because the
  wording snapshot cannot see which of two existing sentences is reached.

- **The app already believed this, in one place.** Calm mode clears every
  filter *before* hiding the filter row, with the comment "never hide a
  control that is still filtering the list: a shorter list with no visible
  reason why is worse than the clutter". The same rule, finally applied to
  the screen that was still breaking it — and the reason naming the
  filters is safe, since when they are hidden they are also empty.

- **The sentence at the centre of this bug was itself unwatched.** It
  reached `RowList` as `empty_text=`, and that keyword was not one the
  extractor read — the same class of hole as `tab=` in v3.33.0, and not
  something widening the *file* list could have caught. It is now a
  presenter constant, so `main_tab.py` and the presenter cannot drift into
  two different sentences. Adding `empty_text` to the watched keywords
  immediately turned up a second uncovered string: the matrix quadrant's
  **"Empty. That is allowed."** 280 → 283 entries.

- **Three labels nobody was checking now have a test.** Cross-referencing
  every controller-written variable against the suite found `path_var`,
  `matrix_path_var` and `counts_var` read by no test at all. Checked for a
  real defect first and found none — every folder-change path does refresh
  its label — but the "which folder am I in" label is one this branch
  already spent a commit on, and a label whose variable quietly stops
  updating looks exactly like a label that is correct.

- 526 → 537 tests, all passing under Xvfb (`skipped=2`) and headless
  (`skipped=230`). Restoring the bug fails six of them. pyflakes clean.

## 3.33.0 — the net stops reading a list, and a past date says which year
One visible change, and it is a small one: a booking from another year
now shows that year.

- **The wording net read three files by name, and that was the bug.**
  Widening it to the whole package added **55 strings that were watched
  by nothing** — including the app's own tagline ("Get it out of your
  head, then start one small thing."), the buttons the whole design rests
  on ("Where do I start?", "Not that one", "Not today", "Start this"),
  the park hints, and the instance-lock dialog's interpolated tail.

  **This was a hole in the shame guard, not only in the drift alarm.**
  `test_nothing_the_app_says_scolds` iterates the same snapshot, so every
  one of those strings was unchecked for tone as well. Checked before
  widening: the shaming phrases score **zero hits** across all 55, so
  nothing had to be reworded first. Six modules contribute no strings at
  all, so the wider net costs no noise. 225 → 280 entries.

  Pinned so it cannot be narrowed back, and verified by narrowing it
  back: three tests fail when the hand-kept list returns.

- **A past date in another year now says which year.** `humanize_date`
  rendered anything older than yesterday as "22 Dec" with no year, so a
  booking from last December read as the *coming* December — and a
  two-year-old task was indistinguishable from a two-week-old one, on a
  screen that also says "in 7 days". The function's own comment states
  its purpose: "a date you cannot place is the thing this function exists
  to prevent." This was that.

  The year is carried **only when it differs**, so "1 Aug" in August is
  untouched — every extra token on a row is one more thing to read past.
  It stays a fact, not a mark: a test asserts the output contains no
  "overdue", "late", "missed", "still" or "should". This app is for
  people who keep tasks around, so a stale booking is the ordinary case.

- **`matrix_view` completes the presenter's stage two**, and brought a
  rule out with it that had been buried in a refresh method and tested
  nowhere: **an empty quadrant shows no number on its tab**, not "(0)".
  Four zeroed tabs read as a verdict on the week. The count *inside* the
  quadrant still says "0 tasks" — you are already looking at the empty
  list there, so it describes what is on screen rather than following you
  around.

- **Two of this branch's own lessons caught two of this pass's own
  mistakes.** Moving the tab text into a `tab=` keyword took it off the
  net — the extractor does not watch that keyword — and the entry count
  did not notice, because fifty-five strings arrived in the same commit.
  Reading the diff caught it; it is now a returned sentence. Separately,
  the new end-to-end test claimed to pin the quadrant-to-tab pairing and
  **passed with the order reversed**, because it used `assertIn` over the
  whole list. Both were found by corrupting the thing on purpose and
  checking the guard screamed.

- 514 → 526 tests, all passing under Xvfb (`skipped=2`) and headless
  (`skipped=226`). The midnight band re-checked at 23:53 and 23:59 and
  still clean. pyflakes clean.

## 3.32.0 — the midnight flake's twin, and two sentences nobody was watching
Nothing on screen changes. A test that could only fail after 23:50 is
fixed, and the last of the session wording moves under the net.

- **The same wall-clock bug, pointing the other way.** 3.31.0 fixed a
  test that assumed a 15-minute block never crosses midnight. Its twin
  survived: `test_finish_time_is_shown_while_running_and_cleared_when_not`
  asserted `^ends \d{2}:\d{2}$` — anchored, so the legitimate
  " tomorrow" suffix broke it. A ten-minute block started at 23:50 or
  later fails the suite. CI runners are UTC, and the previous run had
  started at 23:47:14 UTC: under three minutes from going red for a
  reason nobody would have found by reading the diff.

  The assertion was relaxed, not deleted — it still requires a time
  while running and nothing when paused. Which sentence appears is
  pinned against a fixed clock in `test_presenter`, where it belongs.
  Verified by shifting local time with a computed POSIX `TZ` offset and
  running the whole suite at 23:50, 23:53, 23:57, 23:59, 00:02 and
  12:00. The band is clean.

- **Two sentences a person meets every session, watched by nothing.**
  `SessionLog.summary()` — "No sessions yet today" and
  "2 sessions today · 30 min" — lived in `sessions.py`, which the
  wording extractor does not read. Not a blind spot in the net's logic,
  but in its reach: a file was never added. The wording is now
  `presenter.momentum_view`, and the rule underneath it has a test of
  its own: an empty day must never render as a zero. "0 sessions today"
  reads as a score you are losing, on the morning you least need to be
  told that.

- **`replace_running_question` moves too**, completing the session
  wording. The promise that makes it non-shaming — "Those minutes are
  kept, not lost" — now has a test asserting it is present and that
  "Drop it" is not, because the snapshot cannot tell which branch of a
  two-branch question is reached. Same reason the break/focus split and
  the untitled-block fallback are pinned behaviourally.

- 511 → 514 tests, all passing under Xvfb (`skipped=2`) and headless
  (`skipped=225`). Snapshot 223 → 225 entries. pyflakes clean.

## 3.31.0 — the session's last words move, and a blind spot gets named
Nothing on screen changes. The words a block ends with — the rotating
finish message, the break offer, the finished-and-calibrated line, the
three pop-out captions — now live in `presenter.py` beside the timer's.

- **The move was preceded by a test, because the net could not have
  caught this one.** The snapshot watches which strings *exist*, not
  which one is *shown*. `DONE_MESSAGES[count % 3]` is read after the
  session count has already been incremented, so the first block after
  opening the app gets the **second** sentence, not the first. Writing
  `done_message(count - 1, …)` looks like an obvious off-by-one fix; it
  would quietly change the line every person meets first, at the most
  loaded moment the app has, and the snapshot diff would come back
  empty because all three sentences still exist.

  So the rotation was pinned as behaviour *first*, against the old code,
  and it still passes against the new. Both halves were checked: the
  deliberate off-by-one fails the behavioural test, and leaves the
  snapshot byte-identical.

- **A hole opened and was closed in the same pass.** Moving
  `break_offer` out of a `messagebox` call and into `return f"…"` took
  it off the net, because a bare return was not something the extractor
  read — and the entry count did not fall, because two other strings
  arrived at the same moment and masked it. Returned sentences are now
  watched, which also picked up seven strings that had never been
  covered anywhere. 215 → 222.

  The lesson is narrower than "check the count": the count is necessary
  and not sufficient. The diff has to be read.

- **A latent flake surfaced and was fixed with the tool this refactor
  built.** Running the suite at 23:45 failed:
  `test_the_ends_line_says_tomorrow_across_midnight` asserted that an
  ordinary fifteen-minute block says nothing about tomorrow — which is
  false in the last quarter hour of any day. It has been wrong since it
  was written and would have failed CI at that hour on any recent
  release; it simply had not been run then. The same-day property is now
  asserted in `test_presenter` against a **fixed** clock, which is
  precisely what giving `timer_view` a `now` parameter was for, and the
  app-level test keeps only the wiring check it can make honestly.

506 tests pass, up from 498. Eight new. One existing test lost its
wall-clock dependency, deliberately. Every rendered string was compared
in the running app — the finish status, the calibration tail, the
captions, and the task-less break offer are identical to before.

## 3.30.0 — the clock's words move somewhere they can be tested
Nothing on screen changes. The timer line — "ends 15:42", "break ends
09:05 tomorrow", "· a good moment to find a stopping point" — was
computed inside the method that also writes the widgets, calling the
system clock as it went. It now lives in `presenter.timer_view()`, which
takes the current time as an argument and returns what to display.

- **Two soul features had no test anywhere that runs headless.** The
  after-midnight clause exists because a clock time you cannot place on
  a day is precisely the ambiguity the line was added to remove; the
  soft landing exists because a transition costs less when it is
  announced. Reaching either meant building a real window *at the right
  time of day*, so in practice neither was covered. With the clock
  passed in, both are ordinary assertions — and there are now ten of
  them, running in about a millisecond.

- **`plural` and `batch_status` moved too**, so the counting words a
  second front-end needs are no longer stranded in the tkinter
  controller. Twenty call sites now go through the presenter.

- **The wording net was taught about `presenter.py` first, deliberately.**
  It only read `app.py` and `dialogs.py`, so every string that moved out
  would have vanished from the snapshot while the tests stayed green —
  the net losing coverage at the exact moment it is most needed. Adding
  the file *before* moving anything meant the diff could be read for
  what it was.

  And it read correctly: `ends {%H:%M}` and `break ends {%H:%M}` changed
  file and nothing else. Four passes of correcting wording before
  starting to move it is what made that diff worth trusting — content
  changes and location changes never mixed. The count went **up**, 214
  to 215, because `presenter.py` had two strings of its own that had
  never been watched at all.

  One entry dropped: the bare `{02d}:{02d}` clock format, which has no
  words in it and was already on the list of low-signal skeletons.

498 tests pass, up from 484. Fourteen new, no existing test changed.

## 3.29.0 — the README stops promising the wrong things
Two of the README's safety claims had gone out of date, in the two
places where being wrong actually costs something.

- **It told you to answer a question that no longer appears.** "(After a
  crash, answering 'open anyway' takes over cleanly.)" — since 3.23.0 a
  crashed copy is taken over *without asking*, so that instruction
  describes an impossible action. It also said the second copy is
  "caught by a lock file", when the whole point of that release was that
  the file existing decides nothing: the lock is held by the operating
  system on an open handle. Both corrected, including when you *are*
  still asked — a copy genuinely running, or a folder that cannot answer
  the question at all.

- **It undersold what Ctrl+Z covers.** The README described undo as
  reaching only the moves between the two tabs. Since 3.24.0 the
  matrix's own five commands — add, edit, move, book a time, delete —
  are undoable too. A reader would have concluded that deleting a matrix
  task is unrecoverable and been more careful than the app requires,
  which is the opposite of the reassurance 3.24.0 exists to give, and it
  matters more now that 3.28.0 stopped asking before a single delete.

  Prose cannot be pinned the way strings can, so the *property* it
  describes is pinned instead: a test drives all five matrix commands
  and fails if any of them stops registering an undo. A sixth command
  added without one would make the README wrong again silently — which
  is exactly how it went wrong the first time.

- **The status bar joined the wording net, which had never watched it.**
  Seventy-three status messages, none of them covered. That is where
  most of what this app says is actually said — every command reports
  there — and both of the last two releases' wording defects lived in
  it and had to be found by hand. The snapshot goes from 136 strings to
  **214**.

  Doing it properly needed the extractor to read sentences that are
  *assembled* rather than written out: `_batch_status(…) + "."` says
  words, and `a if cond else b` says two different things, so a
  conditional inside a concatenation is now distributed into the
  separate sentences it really is rather than mashed into one
  unreadable blob.

- **One of those newly-watched strings was wrong.** Deleting a matrix
  task reported "Deleted 1 matrix task Ctrl+Z undoes it." — a run-on,
  because `_batch_status` deliberately leaves its sentence unfinished
  for each caller to close and this one forgot. The task list one line
  away has always said "Deleted 1 task. Ctrl+Z undoes it."

484 tests pass, up from 483. One new, no existing test changed.

## 3.28.0 — switching no longer claims to throw your minutes away
- **"Drop it" was never true, and it was the worst possible thing to
  say.** Starting a block while one is already running asked: *"You are
  8 minutes into 'the report'. Drop it and start a new one?"* Twelve
  lines below, on the path taken when you say yes, the code reads
  `# Bank what was actually done rather than dropping those minutes on
  the floor`. Since 3.21.0 the replaced block banks its minutes; the
  question in front of it still said they were dropped.

  Telling someone they are about to lose the eight minutes they managed
  is exactly the fear that keeps a person pinned inside a block they
  cannot work in — and it contradicts the one promise this app has been
  making all along, that the minutes you did are the minutes you keep.
  It now says: *"Those minutes are kept, not lost — starting something
  else banks them. Start something else instead?"*

  True on both branches, which is why it can be said plainly: answer yes
  and they are banked, cancel the next dialog and the block simply keeps
  running, untouched.

- **The number in that question is now the number that gets logged.** It
  counted with floor division while the timer banks with `max(1,
  round(…))`, so twenty seconds in it said "0 minutes" and then recorded
  one. A promise about "those minutes" is worth nothing if it names a
  different figure.

- **Deleting one matrix task no longer asks first.** *Proposed, not an
  obvious correction — this removes a dialog.* The task list has always
  confirmed for a batch and not for a single item, because Ctrl+Z covers
  the single case. The matrix asked every time, which was right while it
  had no undo and the dialog was the only thing standing between you and
  a deleted file. 3.24.0 gave it undo, restoring title and content
  alike, so the question now guards nothing that Ctrl+Z does not while
  costing a decision on every deletion. Deleting one thing in a quadrant
  is now exactly as cheap, and as recoverable, as deleting one thing in
  the list — and the status line says so. Deleting several still asks.

Left alone deliberately: "Copy N tasks from Do First?" confirms
unconditionally, but it copies the whole quadrant, so its count is
something you want to know rather than a guard; clearing the scratchpad
and clearing completed are bulk by definition, which is already the
rule; and the quadrant picker is required input, not a question.

483 tests pass, up from 478. Five new, no existing test changed. Each
was checked against the old behaviour first — including the rounding,
whose failure reads "You are 0 minutes into… Those minutes are kept."

## 3.27.0 — the "already running" dialog stops giving dangerous advice
- **It no longer tells you it is safe when it is not.** The dialog that
  appears when a second copy cannot claim the session folder used to end
  with *"Open here anyway? (That is safe if the other copy crashed or
  was force-closed.)"* — and until 3.23.0 that was both true and kind,
  because a crashed copy and a running one were indistinguishable and
  the crashed case was the common one.

  3.23.0 changed which case is common and did not change the words. A
  crashed copy is now claimed silently and never reaches this dialog, so
  what is left is almost always a copy that is *genuinely running* —
  where "that is safe if the other one crashed" is false, and following
  it causes exactly the silent overwrite the dialog's own second line
  warns about. The dialog was arguing with itself.

  It now says what it actually knows. When a copy really is holding the
  folder: *"Cognitive Offload is already open with this session folder…
  Both copies save to the same file every thirty seconds, so whichever
  you type in second quietly undoes the other. The window you want is
  already open — switch to it."* The override is still there, because a
  hung process is a real thing; it is simply no longer described as
  safe. Where the folder genuinely cannot tell — network and synced
  folders often cannot — the old reassurance is kept word for word,
  because there it is still true.

- **The status bar speaks with one voice.** Fifteen messages said
  "1 task(s)" while the matrix commands, going through a helper written
  for the job, said "1 matrix task". Same bar, two voices. In an app
  whose whole difference is that the words were written for a person,
  "1 task(s)" reads like output from something that did not care enough
  to look. All fifteen now pluralise properly. One of them also said
  "Pinned 3 tasks — shows at the top", which agreed with nothing once
  the count was fixed; it names what shows instead.

- **The wording net had two blind spots, and this pass found them by
  using it.** Regenerating the snapshot showed the new lock dialog had
  *vanished* from it: the strings are built into variables now rather
  than passed inline, and the extractor only saw literals at the call
  site. That is precisely the shape wording takes as it moves out of the
  controller — so the net would have quietly stopped covering strings
  while still appearing to work. It now reads sentences assigned to a
  name too, which immediately picked up five more user-visible strings
  that were never covered: the break-is-running question, the
  drop-it-and-start-a-new-one question, the couldn't-write-the-session-
  log note, and two more.

  The second blind spot: `{_plural(n, 'completed task')}` collapsed the
  noun into `{}`, so "task" could have become "item" unnoticed. String
  literals inside an interpolation now come along.

478 tests pass, up from 471. Seven new. One existing test changed
deliberately: it pinned "Pinned 1 task(s) to the top."

## 3.26.0 — the folder picker says which folder, and the wording is pinned
- **"Change folder" now tells you which one.** There are two buttons with
  that exact label — one in the header for your tasks and sessions, one
  in the matrix tab for the quadrant files — and both opened a directory
  picker with no title at all, the only two of the app's forty modal
  sites without one. On screen each button sits beside the path it
  changes, which is fine; then the picker covers the screen and that
  context is gone. They now read "Choose the session folder" and "Choose
  the matrix folder". The buttons themselves are unchanged: beside their
  paths they are already clear, and two differently-worded buttons would
  be a bigger change than the problem.

- **Every word the app says is now written down and watched.** The next
  piece of work moves questions between modules, and each one carries
  wording that was argued over — a booking that stops claiming to be
  today, a failure that explains itself without blaming anyone, an offer
  to stop that does not read as giving up. Moved code gets reviewed for
  whether it still works; nobody rereads forty strings to check the tone
  survived. So `tests/wording_snapshot.txt` records all 129 of them and
  `tests/test_wording.py` fails if any changes.

  A failure there is not a bug, it is a question: the message names
  exactly what the app no longer says and what it says instead, and
  points at `python tests/wording.py --update` for when the change was
  the point.

  Read out of the source rather than by driving the app, deliberately —
  half these strings live on error paths (a corrupt save, a vanished
  folder, a failed rename) that are awkward to reach, and a parser
  reaches all of them equally. Interpolated values collapse to `{}`,
  because a path or a count differs every run while the sentence around
  it is the thing under review. Entries are keyed by what a string is
  and where it lives, never by line number: a net that cries wolf on
  every edit above it is one people stop reading.

- **The design law is asserted against all of it at once.** One test
  scans every string for phrases that scold — "you didn't", "you should
  have", "overdue", "still not". Shame is what makes someone close the
  app and not come back, and it arrives one word at a time.

471 tests pass, up from 462. Nine new, no existing test changed. The net
was checked against three deliberate corruptions first: a reworded
question, a shaming title, and the folder title from this same release
removed again.

## 3.25.0 — the porting guide, and tests that keep it honest
Nothing changes on screen. This writes down what a second front-end — a
phone app, a web page, a terminal UI — would have to build and what it
would reuse unchanged, which is the last piece of the portability work
that does not require carving `app.py`.

`docs/PORTING.md` opens with the blocking fact rather than burying it:
**tkinter cannot ship on Google Play**, and every route for running
Python on Android needs a different toolkit and breaks the
zero-dependency rule this project states in its README. That trade is
the owner's to make and has not been made. What the work buys is that
whichever toolkit is eventually chosen, the ranking, the wording, the
counting and the design law come across intact instead of being
reimplemented — and subtly changed — inside it.

It then covers the ten modules that need no display, the roughly fifty
commands and the ask surface a front-end has to supply, the ~1,600 lines
of layout that no seam makes portable, and three specific hazards.

- **The guide is tested.** A document describing an interface is worth
  having only while it is accurate, and left alone it decays quietly:
  someone moves a module across the line, and the file keeps confidently
  describing a codebase that no longer exists — worse than no guide,
  because a reader trusts it. So `tests/test_porting_doc.py` asserts its
  checkable claims against the source. Deliberately only the claims a
  porter would be *harmed* by getting wrong; line counts and rough
  totals are left loose, because a test that fails on every honest
  addition is one people learn to delete.
- **The hazards are real properties, not general cautions.** The clock
  stops when a device sleeps, so a phone must supply `CLOCK_BOOTTIME` or
  silently bank fewer minutes than the person did. `_ask_over_focus()`
  wraps exactly nine of the modal sites, so generalising it to all of
  them is a behaviour change dressed as a refactor — a mistake already
  made once, in a design plan that put the number at ten. And
  `_save_config` reads the focus length from the spinbox, so writing
  config and then saving writes the old value back.
- **The README had quietly fallen three modules behind.** `presenter`,
  `viewmodels` and `ports` were missing from its project layout, and its
  claim that "the model, query and storage layers never import tkinter"
  understated an enforced boundary now covering ten modules. Both fixed,
  and two tests now keep the layout from drifting again in either
  direction — listing a module that no longer exists, or omitting one
  that does.

462 tests pass, up from 451. Eleven are new; none of the existing ones
changed. Each new test was checked against a deliberately corrupted copy
of the documents first, including the exact nine-versus-ten trap.

## 3.24.0 — Ctrl+Z means the same thing in both tabs
**Undo now covers the Eisenhower Matrix.** It never did, and the effect
was worse than nothing happening.

No matrix action told the undo stack anything, so pressing Ctrl+Z after
deleting a matrix task popped whatever older entry happened to be
sitting there. The deleted task stayed deleted, and *a change you were
not thinking about* was reverted instead. Reproduced exactly: capture a
task and flag it, delete a task in the matrix, press Ctrl+Z — the matrix
task is still gone, the flag is quietly off again, and the status line
says "Undid: toggle priority." Press it again, which is what anyone does
when the first press appears not to have worked, and it walks further
back through unrelated work, hunting for a restore that was never
coming.

That mattered here more than it would elsewhere, because the app teaches
the habit itself: deleting from the task list sets the status "Deleted 1
task(s). Ctrl+Z undoes it." The expectation was trained in one tab and
broken in the other. And a confirmation dialog is the weakest protection
there is for someone who deletes on impulse and clicks *Yes* on reflex —
which is exactly why every one of the sixteen task-list commands already
had undo behind it. There was also an inversion: the matrix asked "are
you sure?" for *every* delete while the task list only asks when more
than one is selected, so the surface you could not recover from leaned
on the weaker guard.

Adding, editing, moving, booking a time, and deleting are all undoable
now, in the matrix as in the list, and deleting says so on the status
line the way the task list always has.

- The machinery was already there, which is the frustrating part:
  `MatrixStore.restore()` has carried the docstring "the undo half of
  delete" all along, and sending a task to the matrix already registered
  its own undo. The matrix tab's own commands simply never called any of
  it. One helper now covers all five, because they are the same sentence:
  *these tasks ended up in some state, and this is the state they were in
  before.*
- Restoring drops what is on disk now before writing back what was
  there. An edit or a move renames the file, so writing the old copy
  without clearing the new one would show the task twice — the failure
  the existing send-to-matrix undo was already careful about.
- A copy of a matrix task now carries the file it came from. That is not
  part of what a task *says*, so it is not in the saved record, but an
  undo that wrote the old wording to a freshly chosen filename would
  leave a duplicate behind.
- Nothing is promised that did not happen: if a delete fails outright,
  the status line does not offer Ctrl+Z.

451 tests pass, up from 444 — seven new, none of which pass against the
old code, and no existing test changed.

## 3.23.0 — a crash no longer costs you a question at the next launch
- **The app opens.** If it crashed, was force-quit, or the battery ran
  out, the next launch used to stop and ask: *"Another copy looks open
  with this session folder… open here anyway?"* — before the window
  appeared. That is a decision at the exact moment the app promises to
  take a thought off your hands, and it is a decision nobody can
  actually make: you cannot know whether the process that wrote a pid
  two days ago is still alive. Now you are only asked when a second copy
  really is running.

  The lock file's *existence* no longer decides anything. Ownership is
  an operating-system lock held on the open handle, which the kernel
  drops when the holding process dies, however it dies. So a crash
  leaves nothing to ask about, while the case the guard exists for —
  two copies autosaving the same file and silently overwriting each
  other every thirty seconds — is refused exactly as before. There is a
  regression test that starts a real second process, confirms it blocks,
  `SIGKILL`s it so no cleanup can possibly run, and asserts the next
  launch opens anyway.

  Deliberately *not* done by checking whether the recorded pid is alive:
  on Windows `os.kill(pid, 0)` terminates the target process. Nor by
  `fcntl.lockf`, whose locks belong to the process rather than the open
  file, so a second copy inside one process would take it and the guard
  would quietly stop guarding. On a filesystem that cannot lock at all —
  network and synced folders often cannot — it falls back to the old,
  careful behaviour and asks, because there the guess is all there is.

- **Where the files live is now something the platform says, not
  something the code assumes.** A new `ports` module describes a
  platform as `Locations` — data directory, matrix directory, config
  file, and a home used only to shorten a path for display. `storage.py`
  takes one instead of computing four paths from `Path.home()` at import
  time. `desktop_locations()` reproduces the existing layout exactly, so
  an install finds its files precisely where it left them; a test pins
  that, and another pins the unchanged `~/.cognitive_offload/data.json`
  label. `app_private_locations()` is the other shape: everything under
  one directory, no dotfiles, no assumption that a home folder exists —
  which is what Android hands an app, and what a portable install wants.

  `ports` joins the portability guard: ten of the sixteen modules the
  guard covers now need no display at all.

444 tests pass, up from 431: 13 new, 430 untouched, and one rewritten.
That one asserted an unreadable lock file blocked startup on its own —
it encoded the rule this release replaces, so it now pins the refusal
where it belongs, against a copy that really is running.

## 3.22.0 — what the app says, decided without a screen to say it on
Groundwork for running this on a phone. Nothing on screen changes; where
the words come from does.

A new `presenter` module now holds the decisions behind the task list,
the NEXT UP card, the "booked for today" banner, the Today summary and
the week review. Each is a plain function from data to a small view
model — `TaskListView`, `NextUpView`, `DueView`, `TodayView`, `WeekView`
— and none of them can draw anything. The controller reads its widget
variables, hands the values over, and writes the answers back; it makes
no decisions in between. Six query functions left `app.py` entirely.

This matters beyond tidiness. The rules that make this app what it is
were living inside methods that also called `.grid()`: a day with
nothing finished shows no counter rather than a zero, an empty week is
omitted instead of listed, a missed booking stops claiming to be today.
Checking any of those used to mean building a window and reading a
label. There are now 27 tests that assert them directly, in under half a
second, with tkinter made unavailable — so a second front-end inherits
the design law instead of having to rediscover it.

- **The banner and the click can no longer disagree.** `refresh_due` and
  `show_booked` each worked out "what is booked for today" separately,
  and in 3.21.0 they had drifted — the banner counted today while the
  click selected the oldest overdue task. Both now call one function and
  use its answer, including which Schedule rows get highlighted, which
  were still being re-derived from the date a third time. The fix in
  3.21.0 corrected the answer; this removes the second place it could go
  wrong again.
- **The week review takes a typed view model, not dictionaries.**
  `WeekReviewDialog` was reading `entry["label"]` out of hand-built
  dicts. Stringly-typed keys are exactly what a second front-end gets
  subtly wrong, so it takes `WeekDay` objects now. Two tests were
  updated to construct the new type; both assert the same behaviour as
  before.
- **The portability guard covers the new module.** `presenter` joins the
  eight core modules imported in a subprocess with tkinter poisoned —
  nine of the fifteen modules the guard covers now need no display at
  all.

Behaviour is unchanged. 431 tests pass, up from 404: 27 are new, 402 are
untouched, and 2 were rewritten to construct `WeekDay` instead of a
dict — same assertions, new type.

## 3.21.0 — "today" means today, Reset keeps your minutes, and NEXT UP
## stops interrupting
Three findings from walking the app as the person it is for, rather than
as its author.
- **A booking says when it was actually for.** Only a task booked for
  today itself wears the `today` badge; earlier ones keep the quiet
  `booked yesterday` / `booked 16 Jun` wording a future booking already
  uses. The banner counts today's bookings, and clicking it now lands on
  one of them instead of the oldest missed one. Twelve rows all claiming
  "today" when two of them were today made the badge carry no
  information — and the honest response to a badge that lies is to stop
  believing all of them, which quietly broke booking for the people who
  used it most. Missed bookings keep their place and their weight in the
  ranking; they lose only the false claim on today. Nothing turns red,
  nothing says "overdue", nothing is counted.
- **Reset banks the minutes you actually did.** Quitting mid-block
  already kept them, and so did "Done early" — but "Done early" lives in
  the pop-out, which is off by default, so the main window's only honest
  stop was a Reset that silently binned the work. That credited the
  person who closed the laptop and charged the person who tidied up
  first. On an afternoon when four minutes are the only thing the day
  produced, those four minutes are the whole point. Replacing a *paused*
  block now banks its minutes too. An untouched timer, a second press,
  and a break still record nothing.
- **NEXT UP steps out of sight while a block runs.** The largest button
  on the window read "Start this" — on a different task — for the whole
  fifteen minutes, and pressing it raised a "drop it and start a new
  one?" question the app had invented for itself. It returns the moment
  you pause, finish, or reset; pausing is exactly when "what should I do
  instead?" is a fair question. The keyboard shortcut is unchanged.

## 3.20.0 — A brain that can outlive its face
First step toward running on more than one kind of screen.
- The types describing what a row *shows* moved out of the tkinter widget
  module into `viewmodels.py`, which imports no UI toolkit. That frees
  `rows.py` — the logic deciding which badges and wording a task has
  earned — to run anywhere. Importing a GUI toolkit to learn that a task
  is flagged was coupling that quietly limited what this app could ever
  run on.
- The boundary is now a tested invariant, not a habit: `test_portability`
  imports every core module (task model, ranking, sessions, storage,
  timer, undo, row building) in a subprocess with tkinter made
  unavailable, and fails if any of them needs it. A companion test guards
  the guard — it asserts the UI modules *do* fail there, so a blocker
  that blocked nothing could never let the first test pass for the wrong
  reason.
- No behaviour changes. Eight of fourteen modules are now provably
  display-free.

## 3.19.14 — No version left unwritten
- Backfilled the missing 3.19.1–3.19.2 entries: the six-badge cap that
  keeps a tag flood from squeezing a task's title to nothing had
  shipped with no changelog trace beyond a later refinement note.
  Every version since this changelog began (3.5.x) now has an entry;
  versions 2.0.0–3.4.0 predate it and are summarised in "Before the
  loop" at the bottom — the git history is the full record there.

## 3.19.13 — "Moved" means moved
- "Line → task" and "All → tasks" now actually move: the converted
  lines leave the scratchpad, matching the arrows on the buttons and
  the "Sent/Moved" status text that always claimed they did. A repeated
  brain dump no longer duplicates every task, and the pad stays what it
  is for — the things you haven't decided about yet. Ctrl+Z reverses
  the whole move, pad and list together.

## 3.19.12 — F1 under test
- One smoke test: the keyboard-shortcuts dialog was the only dialog no
  flow test ever constructed, so a constructor regression would have
  broken F1 unnoticed. Tests only.

## 3.19.11 — The rescue paths are pinned
- Tests only, no behavior changes: the first measured coverage run
  (89% overall) showed the two deepest data-safety flows had never
  been executed by a test. Now pinned: changing the session folder
  migrates the lock and the logs (and backs off when the new folder is
  already claimed), and the double-failure path — data.json AND its
  backup both unreadable — blocks auto-save while preserving every
  file on disk. The matrix add/edit dialogs are covered too, including
  the save-failure path. app.py coverage 81% → 85%.

## 3.19.10 — The README tells the truth
- The README claimed the suite "runs under xvfb-run in CI" while the
  repository had no CI at all; a GitHub Actions workflow now exists, so
  the sentence is true instead of deleted. It runs the full suite under
  a virtual display on every push and pull request.
- Documented three shipped promises: quitting mid-session banks the
  minutes, layouts scale with screen DPI, and the keyboard focus ring
  is visible on the filled primary buttons.

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

## 3.19.1–3.19.2 — The title survives a tag flood
- 3.19.2: a task's badges cap at six, with the rest folded into one
  quiet "+k" pill — a 15-tag task used to render as tags and no title
  at all, on both the task list and the matrix rows. The title is the
  row; badges are garnish.
- 3.19.1: this changelog was introduced.

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

## Before the loop (versions 2.0.0–3.4.0, the branch's foundation)
- Restructured into a tested package; fixed the original data-loss and
  selection bugs.
- Built the app around task initiation: first steps, "feels like"
  categories, the warm-up ladder, 15-minute sessions, the start picker.
- Ported shadcn/ui's design system to ttk; added dark and calm modes.
- Fixed the audited defect backlog; added the done-today ledger and the
  hand-off prompt; met WCAG contrast targets with computed, not eyeballed,
  colours.
