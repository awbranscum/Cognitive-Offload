# Changelog

All of this lives on the branch `claude/program-improvement-uqm40n`.
Newest first. Versions bump with each delivered change-set; the themes
throughout are task *initiation*, honest data, and a tone that never
scolds.

## 3.66.0 — A pasted paragraph now has a ceiling
The capture box says *"Anything in your head — it does not have to be tidy"*,
and a pasted paragraph is exactly what that invites. Nothing stopped one
growing.

Measured on one clean app per length, with the ceiling removed:

| pasted title | list row | NEXT UP strip |
|---|---|---|
| 200 chars | 55px | 95px |
| 1000 chars | 242px | 418px |
| 4000 chars | **939px** | **1653px** |

At 4000 characters the NEXT UP strip alone was more than twice the height of
the whole window at its floor, so the button beside it — and the filters, and
the list — were off the bottom of the screen. That is the same failure
v3.56.0 fixed for the resume caption, arriving through the front door
instead. Past about 8000 characters the X server ran out of pixmap space and
the app went down with it.

**Three hundred characters, and only on what is drawn.** The longest title in
this project's own fixtures is 138 characters, so the ceiling never touches
anything a person typed; it catches the paragraph pasted out of an email. The
task keeps every character: a 40,000-character title saves, reloads
byte-identical, is still found by search, and still opens whole in the editor.

Both rows and the strip are 133px or less now, whatever you paste.

**What this is not.** Whether ordinary titles should wrap or ellipsize is a
separate question and still an open one — the existing test that a long task
*wraps* in the list rather than being cut off still passes, and caught a
mutant that dropped the ceiling to 30 characters. This is a guard rail, not a
policy.

Also here: one cutter, in `rows`, used by the list at 300 characters and by
the resume line at 40. Two copies of a rule is how the two answers drift.

## 3.65.0 — The warm-up ladder can always be refilled
Clearing all three lines is the first thing someone replacing them does. The
**"Edit steps…"** button lives inside the ladder frame, and the frame was
only built when there were already steps — so emptying the ladder took away
the only route back to it for the rest of the session. A control that removes
itself is a dead end, and this app does not have those.

The ladder now appears whenever it is switched on, empty or not, and an empty
one says: *"No rungs on it at the moment. Edit steps to write your own, or
leave it — nothing here is required."*

The supported off-switch is unchanged and still the only one: the **"Show the
warm-up ladder before sessions"** checkbox, which lives outside the frame,
persists, and can be ticked again. Emptying the lines never was an off-switch
— `Config.load` replaces an empty list with the defaults on the next launch,
which is also why the dead end was only ever a session long.

One thing worth recording about how it was written: handing both sentences
straight to `text=` as a conditional made **both of them vanish from the
wording snapshot** — the same disappearing act the matrix row's copy did when
it moved inside a conditional, which `rows.py` still carries a comment about.
Naming each sentence before choosing between them puts them back under the
net. The snapshot caught it, which is what it is for.

## 3.64.0 — A damaged file must not stop the app opening
Found by writing seven kinds of damage to a real `data.json` and opening a
real app on each. Six of the seven were handled beautifully. The seventh was
not handled at all.

- **The app did not open.** If `tasks`, `completed_log` or `steps_log` was a
  **number or a boolean**, the loader raised `TypeError: 'int' object is not
  iterable` — past every `StorageError` the recovery path catches, out of the
  constructor, before there was a window. No quarantine, no "auto-save is
  off", no message: a traceback, and no way in, with the person's work
  sitting on disk beside it. `SessionLog.load` had the same hole, and it also
  runs before the window exists.

  This is the worst shape a bug can take here, and what makes it worth saying
  plainly is that the recovery machinery it bypassed is *good* — it just was
  not reached.

- **And the loss count was invented.** A **string** in those fields was
  walked character by character, so `"tasks": "nope"` was reported as
  *"4 task records in data.json couldn't be read"*. There were no records.
  There was one field of the wrong type, four characters long. In an app
  whose whole promise is telling you the truth about your stuff, a fabricated
  loss count is its own kind of damage. A dict gave the number of its keys;
  a string in `completed_log` or `steps_log` was dropped **silently**.

  Both come from one line — `for record in data.get("tasks") or []` — and one
  helper closes both. **The pattern already existed in this codebase**:
  `models._as_steps` and `_as_tags` have always checked the shape before
  iterating. `models.as_records` now says it once for everybody, and the two
  store loaders use it.

- **Two sentences, because they are two different facts.**
  `presenter.damage_report` says *"3 task records in data.json were
  unreadable and were left out"* when records were lost, and *"The task list
  in data.json is not in a shape this app can read, so it was skipped"* when
  a whole field was the wrong type — with no number, because there is no
  honest number to give. Either way auto-save stays off until an explicit
  Save, which was already the rule and still is.

  Both messages moved out of the controller and into the presenter on the way,
  which is where the app's sentences belong.

## 3.63.0 — A net over Ctrl+Z
No behaviour change. `tests/test_undo_completeness.py` reads `app.py` and
requires that every function opening an undo entry either restores the state
the snapshot does not hold, or is named with the reason it does not have to.

`push_undo` snapshots two things: the task list and the step log. Anything
else an action touches — the quadrant files, the completed-tasks log, the
scratchpad — has to be put back by a callable handed to `attach_undo`, or
Ctrl+Z restores half the change and leaves the other half standing. That is
the same shape as the four stale field lists a few releases back: a
hand-written correspondence with nothing checking it.

**It catches nothing today.** Sixteen functions push an undo entry, seven
reach outside the snapshot, four of those attach a restore and three are
exempt with reasons — copying *from* a quadrant leaves the files alone,
`begin_focus` only reads preferences, and un-banking fifteen minutes you
actually spent is not what Ctrl+Z is for. The point of writing it now is that
the next one is caught the day it appears.

Writing it found a blind spot in itself, which is the part worth recording:
watching for the attribute `note_text` would have missed `clear_notes`, which
writes the scratchpad through `set_scratchpad`. A net that only watches
attribute names lets every method call through. It watches both now, and a
mutation removing that restore is caught — which it would not have been an
hour ago.

## 3.62.0 — The record only corrects a distortion by being true
Two things found by looking at what happens at the *end* of a plan, and at
what a timestamp actually holds.

- **The last step of a plan could be finished for ever.** Ticking *"Done —
  move on to X"* on the last step wrote a finished-step entry and changed
  nothing — every single time it was pressed. Three ticks put the same step
  in the week review three times, and inflated the "N done today" count with
  it.

  `advance_step` is right to refuse at the end: the model's invariant is
  `first_step == steps[steps_done]`, so the cursor may never pass the last
  step. The bug was that the log was written *before* asking, and
  unconditionally. It now records only what the cursor actually passes — and
  it carries the finished step across by hand, because after the move
  `first_step` names the *next* one.

  **Padding the record is not a smaller sin than losing it.** The week review
  exists because *"I did nothing this week"* is a distortion, and it can only
  correct one by being true.

- **A timestamp said "started_at" and held the finish.** `SessionLog.record`
  is called when a block *ends*, and nothing has ever passed a start time, so
  the field stamped itself at the moment of recording. It is `logged_at` now.

  Which day a block counts for is deliberately unchanged: a block finished at
  00:05 belongs to the new day, because someone who stops at five past
  midnight seeing *"1 session today"* is kinder than seeing *"none"* the
  moment after they stopped. Files written before the rename still carry
  `started_at`, mean exactly the same instant, and are read — throwing away a
  year of momentum over a key name would be its own bug.

Left open on purpose: **what finishing the last step should mean.** With the
log honest, the final step of a plan is now recorded nowhere — the task sits
on `step 3 of 3` with no way to say "that's the lot", and the evidence only
returns when the task itself is marked done. The obvious answer is the
already-listed idea of the last step offering to finish the task, and it is
no longer only a nicety; but it is a change to what the app asks you at a
tender moment, so it waits to be asked for.

## 3.61.0 — "step 1 of 3", on the surface you actually look at
A small fix and the net that would have caught it.

- **The pop-out timer now says where you are in the plan.** It is the one
  surface up *while you work*, and it was the only one showing a step without
  saying it was step 2 of 3 — the list row, the focus card, the start dialog
  and the session-end dialog all say it. "of 3" is the difference between a
  step and a step in something finite; being part-way through is cheaper to
  resume than starting, and the number is the evidence.

  This was a promise the code was not keeping rather than an idea:
  `focus_caption`'s docstring opens *"What the focus card **and the pop-out**
  say you are on"*, and calls the place *"the one thing about the plan worth
  showing"* during a session. The pop-out passed its step through raw.

- **One composer, three surfaces.** The sentence was being assembled inline in
  two places, which is how the third came to be missing.
  `rows.step_with_place` now builds it once, and the wording snapshot recorded
  the consolidation exactly: two `{} · {}` entries became one.

- **`tests/test_plan_place.py` is the net.** Every surface that names a step
  is checked for the place, and a surface that leaves it out has to be listed
  with a reason — which the NEXT UP strip now is, marked as an open question
  rather than a decision. Two of the surfaces are dialogs, so their call sites
  are read out of the source with `ast`: a third dialog added later is caught
  the day it appears rather than the day someone opens it.

  It also asserts that each surface really is showing the step, because a net
  that checks strings for a substring passes beautifully when every string is
  empty.

Left for the owner: whether the **NEXT UP strip** should say it too. The
argument for is that "step 2 of 3" there says *you have already started this*,
which is one of the strongest anti-freeze signals there is. The argument
against is that the strip is the one card this app keeps deliberately
lightest. One line of code either way, which is why it should be decided
rather than drifted into.

## 3.60.0 — The other tab
The Eisenhower tab had been the less-audited half of the app for a long time.
Looked at the way a stranger meets it, two things were wrong, and one of them
breaks the rule the whole app is built on.

- **Shortcuts changed the tab you could not see.** `bind_all` means every
  shortcut fires whichever tab is in front. With the matrix up and a
  selection left behind on the task list, **Ctrl+P changed a hidden task's
  priority, Ctrl+Up pinned one, Ctrl+D and Ctrl+T and Ctrl+M opened dialogs
  about one, and Ctrl+B emptied a scratchpad you could not see into tasks you
  could not see.** This app's one inviolable rule is that it never changes
  something you are not looking at, and muscle memory built on the main tab
  is exactly what carries a keystroke to the other one.

  The fix was already in the file: `focus_capture` and `focus_search` select
  the tasks tab before doing anything. That is now a column in the bindings
  table rather than two functions' private habit — every shortcut states
  whether it shows the tab it acts on, and a test reads the table with `ast`
  so a shortcut added next year has to answer the question.

  **Ctrl+Z deliberately does not.** Undo also reverses matrix changes, and
  yanking someone to the other tab to undo what they did on this one is the
  same crime facing the other way. It names what it undid instead.

- **The quadrant greyed nothing.** The main tab has disabled its
  selection-dependent controls since the first-run audit, and the reason is
  written down there: an inert control is still a small decision, and the
  only way to learn a button was not for you was to press it and be told
  "Select a task to…". This tab answered exactly that way for four of its
  buttons, out of eleven live controls.

  Three questions rather than one. Most need a selection. **Copy all to
  tasks** needs the quadrant to have anything in it. And **Take it back**
  needs the selected task to actually be *out* with someone — offering it on
  a task nobody has is offering to undo something that never happened.

  What each button needs is stated beside the button, not in a list of label
  strings somewhere else: a list of names keyed on other names is the disease
  this codebase keeps curing, and renaming a button would have quietly
  dropped it out of the greying.

- **The matrix folder path moved under the quadrants**, the same demotion the
  tasks tab got in 3.59.0.

Also fixed: a test that failed on exactly one day of the year. A fixture
pinned `snoozed_until` to a date near the day it was written, and when the
clock reached it, the handoff brief's own "handed over on <today>" line
contained the same string — so a test asserting the snooze never leaks into a
brief failed, correctly, about the wrong thing. The date is far-future now.

## 3.59.0 — Less on the first screen
From a usability audit of the app as a stranger meets it. The core loop was
already short — open, read one named task, one click, one prefilled dialog,
working — but the screen around it was denser than the person it is for.
Counted on a first run: **33 clickable controls, 24 of them live**.

- **The filter row waits until there is something to filter.** A search box,
  Clear, three dropdowns and "Show done" — six live controls narrowing an
  empty list, on the screen a new person meets first. Nothing there can do
  anything until a task exists, and a control that cannot act is still a
  thing to read and decide about.

  It obeys the rule calm mode already wrote down: **never hide a control that
  is still filtering the list**. So an active filter keeps the row up even
  when nothing is left to show — that is exactly when you need to see the
  filter in order to clear it — and Ctrl+F pins it for the session, because a
  shortcut whose whole job is to put the cursor in that box must not leave
  the box hidden.

- **Where the file lives moved below the capture box.** A JSON path and a
  folder button used to be the third thing on the page, between the title and
  Quick capture. Where the file lives matters once; the capture box matters
  every time. It sits in the dead space under the capture card rather than in
  the footer, which has 345px spare at the window's floor until the status
  line says something long — and a row that fits except when the app has
  something to tell you is a bug this project has already shipped twice.

- **Two buttons said "Clear".** One narrowed a list; the other threw away
  everything you had dumped in the scratchpad. The destructive one is
  **"Clear pad"** now. The filter row keeps the short label because it cannot
  afford the width at the window's floor, where "Show done" is already
  clipped.

- **The help says its key.** Twenty-two keyboard shortcuts, and the app named
  one of them anywhere in context. The link now reads **"Shortcuts (F1)"** —
  no new pixels, and the difference between a feature you have and one you
  use.

Together: **33 controls down to 27 on a first run, 24 live down to 18.**

Not changed, because it is not mine to decide: whether **calm mode should be
the default**. It takes the four-task screen from 39 controls to 25, which is
the strongest single lever here — and it changes what every existing user
sees on next launch.

## 3.58.0 — Said once, and not about what you set aside
Two more places where a rule the app already had was not being asked, found
by following v3.57.0's fix to its other readers.

- **"Booked for today" no longer counts a task you have put down.** Press
  "Not today" on something booked for today and the banner went on saying
  *"1 booked for today →"* — the app contradicting, in the second-most
  prominent slot on the screen, the statement you had just made. The more
  recent of your two statements is the one that means something. A task out
  with someone else was the same error the suggestion slot already avoids:
  the banner's click selects it and says *"Booked for today: X"*, pointing
  you at work that is not yours to do.

  Not a hiding, either way — the task keeps its place in the list and its
  `booked` badge. Only the count changes, exactly as with the suggestion
  slot. Both halves of the banner learned it, the main list and the matrix
  Schedule quadrant.

- **The focus card stopped saying what NEXT UP was already saying.** The
  ranking warms recently-worked tasks on purpose and scores "already names
  its first step" highest — which a task you are mid-plan on always is — so
  the card and NEXT UP naming the same task is the *ordinary* case, not an
  edge one. Measured across three arrangements, the card's second line was
  the same step NEXT UP was showing two hundred pixels below, in larger type,
  with a **Start this** button beside it. In calm mode, whose whole job is
  having less on the screen, that duplicate was the longest text block up.

  Only the repeated half goes: *"Last time: 20 minutes on X — you finished
  Y"* is a record NEXT UP does not carry. It is keyed on what the strip is
  **showing**, not on what the ranking would pick, because the strip steps
  out of sight during a running block while the ranking goes on agreeing —
  and a line dropped for a box that is not there is information lost for
  nothing.

- **One snooze rule, one put-down filter.** `snooze_is_live` takes the date
  rather than the task, so the task editor asks it instead of writing the
  comparison out again, and `rank_for_starting` collapses its two filters
  into `is_put_down`. Four copies of this rule existed a release ago; there
  is one now.

  The editor's copy turned out to be untested as well as duplicated:
  replacing it with `if snoozed_until:` passed the entire suite, so nothing
  checked that a **spent** snooze shows no "Excused from suggestions until…"
  checkbox — an untrue sentence attached to a control that does nothing.

## 3.57.0 — A task you put down stays put down
The focus card learned to say what you were last doing (3.56.0) and then said
it about tasks you had deliberately set aside.

- **"Not today" now means not today on the card as well.** The rules already
  existed and are written down in `rank_for_starting`: a snoozed task *"stays
  on the list and in every search, it just stops guarding the suggestion
  slot"*, and a task out with someone else *"is not yours to start —
  suggesting it is the app inviting you to duplicate work someone else is
  already doing."* The focus card sits **above** the slot those rules protect
  and ignored both. Press "Not today" on the task you just spent twenty
  minutes on and the suggestion slot went quiet while the card went on
  reading *"Next: copy the headings across"* — for the rest of the day, at
  every launch. `snooze_next` says why that matters in its own docstring:
  repeated forced contact with a dreaded task does not build willpower, it
  builds avoidance of the whole app.

  The two halves of the line are not the same kind of sentence, so only one
  of them goes. *"Last time: 20 minutes on X"* is a **fact** — snoozing a
  task does not change what you were doing yesterday, and losing that half
  would answer "what was I doing?" with silence about the very task you spent
  the time on. *"Next: Y"* is an **instruction**, and it now waits until the
  task is a real option again: the morning after a snooze, or the check-back
  day of a handoff.

- **The rule moved onto the model, where it can only be answered once.**
  `is_snoozed` and `is_put_down` sit beside `is_waiting` and `is_due_back`
  on both `Task` and `MatrixTask`, and the ranking now asks the model instead
  of testing the date inline. Two copies of this predicate is exactly how the
  card ended up naming a task the list had already agreed to stop naming, and
  a test asserts directly that the two never disagree — across a plain task, a
  live snooze, a spent snooze, a handoff and a handoff due back.

## 3.56.0 — "What was I doing?", answered from the record
An interruption costs the context, not the intention: you know you were
working, you have lost *what on*. Every piece of the answer was already being
written down and none of it was ever said out loud.

- **The focus card now remembers.** Where it used to read "Nothing picked
  yet" — three words of dead text in the most prominent place on the screen,
  at the exact moment someone is trying to remember — it now says what you
  were last on, how long you spent, the step you actually finished, and the
  step that comes next. Nothing was collected to make this work: the session
  log knew the task, the step log knew the step, the task knew its plan.

  Three rules shape the sentence, and each is tested rather than trusted.
  **It never counts the days** — "Last time", never "six days ago", because
  an elapsed-time figure on a task you have been avoiding is a reproach.
  **It never asks anything** — the point of reading it is to be spared a
  decision, and a prompt at that moment would put one back. **It says nothing
  rather than something empty** — no sessions, or a task since deleted or
  finished, and the card keeps its quiet caption.

  It costs no pixels when there is nothing to say, which is the only kind of
  addition this screen can afford after v3.48.0 spent a release taking things
  off it.

- **Steps now record which task they belonged to.** The step log stored the
  task's *title*, so two tasks with the same words were the same task and a
  renamed task lost its history. Entries written before this release have no
  id and are read as belonging to nothing rather than guessed at.

- **The line is bounded, because the text in it is yours.** The three pieces
  it quotes back are text you typed, and the capture box exists precisely so
  you can type a paragraph into it. Rendered at the window's smallest size, a
  nine-line caption pushed the filter row, the task list and "Where do I
  start?" off the bottom of the panel — where nothing scrolls to reach them.
  Forty characters is enough to recognise a task you were on an hour ago,
  which is all this line is for.

- **A new net over the plan.** `tests/test_first_step_writes.py` reads the
  source and finds every assignment to `first_step` anywhere in the app,
  requiring each one to either go through `set_current_step` or be named with
  a reason. A direct write is silently reverted by the next load — the test
  demonstrates that rather than describing it — and a site added next year
  fails the suite the day it appears.

## 3.55.0 — The other half of the wheel fix, and a door that hid itself
Three things, all of them consequences of the last release rather than new
ground — which is the argument for auditing a release from outside it.

- **The same stray-scroll bug on the timer.** v3.54.0 stopped a wheel notch
  changing a combobox and stopped there. The right question was *which ttk
  classes bind the wheel at all*, and the answer includes `ttk.Spinbox`:
  one notch over the "Min" box took a session from 15 minutes to 14 and
  carried it into the running clock, so the block you agreed to was quietly
  not the block you got. Both spinboxes — the timer and the start dialog's
  session length — are covered now.

  The guard is the part that matters. `tests/test_wheel.py` no longer looks
  for comboboxes: it **walks the app and every dialog**, reads the value of
  anything that has one, and requires every wheel-bound class it meets to be
  either checked or named as one whose wheel legitimately scrolls. A widget
  added next year is covered the moment it exists, and a *class* nobody has
  decided about fails the suite. That version would have caught the spinbox
  on the day the combobox was fixed.

- **"N done today" hid the panel it opens.** v3.54.0 made that panel list
  finished steps as well as finished tasks; the pill went on counting tasks.
  So the number disagreed with what it opened — and on a day spent moving
  through one long task and finishing nothing the count was zero, which
  hides the pill, and the pill is that panel's **only** route. The evidence
  existed and could not be reached. The count is a promise about the panel,
  so it now counts what the panel shows.

- **A fourth place that wrote `first_step` directly.** The editor and the
  session-end dialog were both fixed to go through `set_current_step`; the
  start dialog was not. On a task with a plan, renaming the first move as you
  started a session left `first_step` disagreeing with the plan — and the
  invariant repairs that on the next load, so the rename survived exactly
  until the app was closed.

- **Where you are in the plan, during a session.** The focus card, the
  pop-out and the start dialog now say "step 2 of 4" beside the step. Only
  the place, deliberately — not what is coming, because that is a decision,
  and the start dialog is the screen someone is looking at *because* deciding
  is the part they are stuck on.

## 3.54.0 — A stray scroll cannot hide your tasks, and a finished step counts
Two things, both found by auditing a release from outside it.

### One wheel notch over a combobox changed its value
ttk binds the mouse wheel to `ttk::combobox::Scroll`, and it always has. So
**one notch with the pointer merely over a combobox changed it** — no click,
no focus. Measured in the running app with three tasks on screen:

```
visible before: 3 | kind filter: (any feel)
after ONE wheel notch over the filter combobox:
   filter now: Urgent sprint | visible: 0
```

This app's own rule is that hiding a task is the one thing it will not do,
and that gesture hid all of them, silently, in response to the most ordinary
thing anyone does to a list. Three of the six comboboxes change **saved
data** rather than the view, and the worst of them is "Repeats": a stray
notch there makes a task recur for ever.

The fix is one binding, installed on the **class** rather than on each
widget, because the fault is a dangerous default that anything added later
would inherit too — and this project has already watched four hand-written
per-site lists go stale. It deliberately does not swallow the event: in a
dialog whose form scrolls, the wheel now scrolls the form, which is what the
person was reaching for. The dropdown list is a different class and still
scrolls. `tests/test_wheel.py` finds every combobox in the app rather than
listing them, so a seventh is covered the moment it exists.

### A finished step is evidence, and nothing was writing it down
The week review counts sessions, minutes and *finished tasks*. A step ticked
off is none of those, so a week spent moving through a four-step report
showed effort and no outcome — on the one screen whose stated job is that
*"I did nothing this week is a distortion, and the correction is not
motivation; it is the record."*

The obstacle was that `steps_done` is a **cursor, not a history**: nothing on
the task says when a step was ticked, so unless it is written down at the
moment it happens the evidence does not exist. There is now a step log, the
same shape as the completed-tasks log that already exists so that tidying up
cannot erase the answer to "what did I get done today". A day whose only
outcome was two steps of something long now appears in the week, where
before it read as blank.

The cheaper idea — recording the step on the focus session — was rejected on
purpose: it would credit steps ticked at session end and silently miss those
ticked in the editor, and a record that covers *some* of the thing is worse
than one that admits its scope.

Undo takes the record back with the cursor, which needed the undo stack to
snapshot the log alongside the tasks: restoring the cursor and leaving the
entry behind would leave the week review claiming a step was finished that,
as far as the task is concerned, never was.

## 3.53.0 — The plan reaches the rest of the app
v3.52.0 gave a task a plan. This is the pass that asks where a plan needs to
be visible and finds four places it was not — two of them defects in v3.52.0
itself, which is the whole argument for auditing a release from outside it.

- **Search reads every step.** It read the title, the details, the step you
  are *on* and the tags — so a task whose third step said "ring the insurance
  company about the excess" did not match "insurance". This app says out loud
  that a task stays "in every search" and that hiding one is the thing it will
  not do; a step you typed and cannot find is the search box teaching you to
  distrust it.

- **A handoff brief sends the whole plan**, as a checklist, with the steps
  already done ticked and the one to pick up at marked. It used to send only
  the step you were on, which is the difference between "do this job" and
  "carry on from here" — an agent that redoes step one is doing damage rather
  than work. The JSON carries `steps` and `steps_done` as data.

  **The guard matters more than the fix.** `build_brief` was a *fourth*
  hand-written list of fields read off a model, after the two conversions, the
  per-round resets and the editor's three call sites — and it had gone stale
  on schedule. `tests/test_handoff.py` is now keyed on
  `dataclasses.fields(MatrixTask)`: every field either reaches the agent or is
  named as deliberately not sent, with a reason. Which quadrant you filed it
  in, how it feels to start, your flag, your pin, a "not today" and how often
  it repeats are all decisions about *your* day rather than about the work,
  and the list now says so instead of leaving it unwritten.

- **The end of a session asks a task with a plan a different question.** Two
  things can have happened in the last fifteen minutes — you finished this
  step, or you did not — and one blank field labelled *"Where does it pick up
  next time?"* conflated them: on a task with a plan it invited a description
  of the **next** step while the cursor was still on this one, so typing the
  honest answer overwrote the wrong line. A planned task now sees the step it
  is on, already filled in, with its place underneath and the same *"Done —
  move on to X"* checkbox the editor has. Accepting it unchanged does nothing,
  editing rewords, ticking moves on. A task without a plan is untouched.

  The hint changed with it, because "Leave it blank if you would rather not
  decide now" is an invitation on an empty box and a lie on a filled one.

### Two things v3.52.0's scrolling editor got wrong
- **The wheel scrolled the notes box *and* the whole dialog.** A `Text`'s own
  class binding scrolls it and does not return "break", so the event carried
  on to the window binding as well — measured, one notch moved the text and
  slid the form by the same amount. Scrolling your own notes now moves your
  notes. Over a half-empty box the wheel still moves the form, because a
  wheel that dies in the middle of a dialog is its own small bug.
- **Tab could put the cursor somewhere you cannot see.** Focus moves by widget
  order, not by what is on screen: on a 614px window — the ceiling a 1366x768
  laptop gives this dialog — it walked into the details box at y=583 and the
  tag row at y=732, both below the bottom edge. You typed and nothing
  appeared. The form now follows the keyboard, in both directions, and leaves
  itself alone when focus lands on Save, which is not in the scrolling area.

## 3.52.0 — A task can be a plan instead of a wall
A task held exactly **one** step. The moment it was done the task was a blank
wall again, so every transition charged a fresh decision — the one thing this
app's own rules say not to charge for. "Write the report" is a wall; "open
last year's, copy the headings, fill in the numbers" is three things you can
start.

- **The rest of the plan**, one step per line, in the task editor on both
  tabs. Optional; a task with no plan behaves in every way exactly as it did.
  What you paste in is run through the same coercion the scratchpad uses, so
  bullets, checkboxes and the `[timestamp]` prefix quick capture writes are
  all stripped for you.
- **Ticking a step off** moves you down the plan, and the status line says
  what is *next* rather than how many are left: a count of what remains is a
  debt, and the next step is a way in.
- **The row says where you are** — `→ copy the headings across · step 2 of 4`
  — in the slot the first step already occupied, so it costs no new pixels.
  It counts what exists and never what is missing.
- **A repeating task with steps is a routine.** The plan carries into the next
  round; your place in it does not, so next week's bins start at step one.
  That is not a separate feature, it is what these two fields already mean
  together.

**The design constraint was `first_step`, not the plan.** It has forty-seven
references across seven modules and it is what `is_ready` reads, which is what
the whole "where do I start?" ranking scores highest. A derived `next_step`
would have been a forty-seven-site refactor; a second field holding "what
next" would have been a second source of truth, which is the exact shape of
bug the last four releases have been fixing.

So there is no second answer. A task with a plan **defines** `first_step` as
`steps[steps_done]`, one function says so, and **not one of the forty-seven
readers changed**. `steps_done` is a cursor rather than a tick-list precisely
because a repeat has to hand the whole plan to its next round — steps consumed
destructively could not come back. Editing the step box on a task with a plan
writes through to the plan; a file whose `first_step` has drifted from its
plan is repaired on load rather than believed; and a plan that shrinks to one
step collapses back into a plain first step, because "step 1 of 1" is a
control that tells you nothing.

Both `dataclasses.fields()` completeness nets refused the change until every
new field was classified, which is what they are for. One of them refused
`first_step` as plain setup — correctly, since a plan makes it derived — and
that argument is now a third category in `tests/test_repeat_rounds.py` with
its reason written down.

### Two things found while building it
- **A window shorter than its content stops drawing widgets.** v3.51.0 fixed
  that for Save by capping the height and pinning the button row. Capping
  alone left everything else exposed: on the 1366x768 laptop this app
  supports on purpose, the editor's ceiling is 614px against content wanting
  828, and measured at that size the details box and the tag row were **not
  drawn** — nine controls missing at 520. A ceiling without a scrollbar is a
  quieter version of the bug the ceiling was added to fix. The editor's form
  now scrolls, with Save and Cancel outside it; a form that fits shows no
  scrollbar at all and looks exactly as it did.
- **Handing an already-waiting task to an agent said nothing about who had
  it.** Newest-holder-wins is right; the silence was not. It now says *"Was
  out with Mum; now out with Codex."*

## 3.51.0 — Waiting on a person, and a Save button you can reach
The Delegate quadrant got a way to hand a task to an AI agent in v3.44.0, and
with it the whole *waiting* treatment: a badge, a line under the title saying
who has it and when to check back, and the task quietly stepping out of the
"what should I start?" slot until that day. None of that machinery ever cared
who was holding the task — `handed_to` is free text — but the only way to set
it was to hand something to an agent, from one quadrant of the other tab.

- **You can now say you are waiting on a person.** The task editor gained a
  *Waiting on* field and a *check back* date, on both tabs, alongside the
  take-back checkbox that was already there — one direction visible at a
  time, never both. Blank date means three days, the same default the agent
  handoff uses, because handing something over and then forgetting it is not
  delegating, it is losing it somewhere more respectable.

  Nothing downstream needed changing: the badge, the subtitle, the search,
  the exclusion from the suggestion slot and the return on the check-back day
  were all built already and all agnostic. What was missing was the sentence.
  This matters because "waiting on a reply" is the single most reliable way
  for a task to rot quietly, and this app already had the right treatment for
  it — a fact ("check back Sat"), never a verdict ("overdue").

- **The matrix editor was showing a task that was not the task.** It never
  passed `repeat`, so a quadrant task wearing a `weekly` badge opened saying
  *"Does not repeat"* — and since the result was not applied either, setting
  the combobox to "Does not repeat" changed nothing. It also never passed
  `handed_to`, so the take-back checkbox never appeared there; "Take it back"
  is a **Delegate-only button**, which left a waiting task moved to any other
  quadrant with no way out of the mark at all.

- **Adding a matrix task dropped the estimate and the repeat.** Filled in as
  "about 25 minutes, every week" and saved as neither, without a word. The
  worst shape a data loss can take, because the person watched themselves
  type it.

- **Save and Cancel were not being drawn.** Found by rendering the dialog
  rather than by any test. The task editor opened at a fixed 520px against
  content that wanted **578** with a tag row; Tk lays out in pack order and
  simply stops, so the button row was absent — not clipped, not scrolled off
  — on a window whose only other exit is Escape, which throws the edit away.
  This predates every feature above; each optional row added since had made
  it worse. Two fixes: the dialog now sizes to its content (the mechanism
  `ModalDialog` already had, and whose own comment says *"a fixed height is
  always wrong for someone when the content varies"*), and the button row is
  packed against the bottom of the window **before** the body, so on a screen
  too short for the content the notes box gives up the room rather than the
  way to save.

- **The title measurement no longer crashes a refresh.** `_title_width` built
  its font without `root=`, so it bound to the global default root — a
  *different* app in a process holding two, and `None` once the first is
  destroyed, where it raised rather than laying out approximately. The badge
  measurement thirty lines above has carried both guards from the start.

- The dead `handoff.with_handoff` is gone.

**The guard:** `tests/test_editor_fields.py` reads the dialog's own signature
and the dict `collect()` actually returns, and requires every caller to both
pass and apply every field — or to name the exception with a reason. Three of
the five bugs above were the same disease, a hand-written argument list at
each of three call sites, and it caught two more the moment it was written.

## 3.50.0 — The badges give way before the title does
v3.49.0 stopped badges clipping a long title by letting them narrow it
instead — and left nothing bounding how narrow. This is the other half of
that fix.

- **One task could be taller than the whole visible list.** Measured, one
  138-character task with a full badge load, varying only the window width:
  3 lines at 1600, 4 at 1400, 6 at 1240 (the default), and **11 lines — a
  224px row — at 1120**, which is the app's own minimum width. The task list
  viewport at the minimum window height is 55–103px, so that single row
  filled it and pushed every other task out of view. At the default width it
  was still 139px, more than half a 254px viewport.

  This was the mirror of the bug it fixed rather than a return of it: v3.49.0
  hid *words*, this hid *other tasks*.

- **The strip is the compressible thing, and it already knew.** `MAX_BADGES`
  has always carried the comment *"the rest collapse into one quiet '+k' pill
  instead of squeezing the title to nothing (a 15-tag task used to render as
  tags and no title at all)"*. That intent was right and measured against the
  wrong quantity: a **count** does not bound a **width**. Six wide badges
  cost more room than fifteen narrow ones. The strip now has a width budget
  as well, and the `+k` pill it already owned does the rest. Room is reserved
  for `+k` *before* the last badge is accepted, so the overflow marker can
  never be the thing that busts the budget.

- **The budget is what the title does not want, floored at 42% of the row.**
  A share alone was wrong in the other direction: it collapsed **"Bins"** — a
  four-letter task — down to four badges on a wide screen, for no reason at
  all. A short title now keeps every badge it has room for; a long one gets
  the floor. Measured after: 3 lines at every width from 1600 down to 1240,
  and 4 at the 1120 floor.

- **The cheap test runs first, and that matters.** Measuring a title is a Tcl
  round trip, and almost every row carries one or two badges that fit inside
  the share whatever the title is doing — so the title's width cannot change
  the answer and is not worth asking for. Paying it on every row cost about a
  fifth of the 300-task paint (0.82s → 0.98s). Skipping it when the badges
  already fit puts the documented benchmark back at **0.82s**, unchanged. The
  measurements that are still needed are memoised, which also took a filter
  round trip from 0.132s to 0.108s — better than before, because rows with no
  badges now skip the work entirely. A heavily-badged 300-task list is 1.01s
  against 0.89s: the case where the budget genuinely does work, and the only
  one that pays.

- 683 → 689 tests, Xvfb (`skipped=2`) and headless (`skipped=285`). **Six
  promises broken on purpose; five caught, and the sixth found a gap in the
  tests rather than in the code.** Removing the re-budget on resize passed
  everything, because every test refreshed the list after resizing the
  window. Dragging a window narrower fires a Configure event and *nothing
  else* — no refresh, so the per-row code never runs, and the strip kept the
  room it was given at the old width. There is now a test that resizes and
  does not refresh.

## 3.49.0 — Two regressions this branch caused itself
Both were introduced by earlier work in the arc that has just merged, and
both were found by the research habit rather than by a failing test.

- **A long title was being clipped again, on any row carrying badges.**
  v3.41.0 fixed *"a 137-character task showed about 78 characters: not
  scrolled off, not shortened with an ellipsis — absent, ending mid-word"*.
  It came back through the badge strip. `RowList._rewrap` applied **one**
  `wraplength` to the whole row pool, computed from the row width and a
  constant `TEXT_INSET` whose own comment budgeted *"a little slack for a
  badge strip sitting to its right"* — 40px of slack against a strip that
  reaches 430px. The title wrapped at the full width, was then given only
  what the badges left, and Tk clipped the difference: a Label wraps at
  `wraplength` and does **not** re-wrap to fit its allocation.

  Measured on the same 129-character title, only the badge load changing:
  100% visible with no badges, 91% with a feel set, 81% once booked, 68% with
  an estimate, 52% repeating, **41% fully badged**. The loss began at the
  *second* badge, and it punished using the app properly — every badge is
  something you added by filling the task in, so the tasks you had invested
  most in were the ones that lost their words. Two tasks differing only in
  badges rendered differently.

  The wrap width is now worked out **per row**, from that row's own badges,
  in `_fit_title`. Every badge load is back to 100%: the badged row takes
  more lines, never fewer words.

- **The handoff marks leaked into every future round of a repeating task.**
  `Task.next_instance` clears the state that belonged to the round just
  finished, with the comment *"A snooze belongs to the round it was taken in;
  carrying it forward would silently excuse the next one too."* v3.46.0 added
  the three handoff fields to `Task` and **did not extend that rule**. So
  finishing a repeating task that had been handed to an agent booked the next
  round already claiming to be out with that agent — and every round after
  inherited the claim, because each copies the last.

  The harm was checked rather than assumed, and the first hypothesis was
  wrong. *Always*: every future round displayed a handoff that never
  happened. *Additionally*, only when the stale check-back date was still
  ahead of the new round's own date, the round was also excluded from the
  suggestion slot — measured, a **daily** repeat handed over with a 30-day
  check-back was silently not offered for 30 consecutive rounds, while a
  weekly repeat with a 3-day check-back was unaffected.

- **Both fixes leave a guard behind, because both diseases were the same.**
  A hand-written list with nothing checking it against the model.
  `tests/test_repeat_rounds.py` is keyed on `dataclasses.fields(Task)` and
  requires every field to be classified as *setup, carried forward*,
  *per-round, reset*, or *fresh each round* — with a reason — so the next
  field added has to be decided rather than silently inherited. It also
  asserts the code's own `PER_ROUND_FIELDS` matches the classification, since
  two hand-maintained lists of the same thing is exactly how this happened.

- 667 → 683 tests, Xvfb (`skipped=2`) and headless (`skipped=279`). **Seven
  promises broken on purpose; two initially survived and both were weak
  tests of mine.** A no-badge row was asserted to be *wider than before*
  rather than *the full width*, which a sticky flag satisfied while still
  being wrong. And the choice of `winfo_reqwidth` over `winfo_width` survived
  because every test called `update()` first — which fires a `<Configure>`
  that quietly re-fits the row and hides the bug. Measured at the moment the
  row is applied, the strip's allocated width is **1** while its requested
  width is **188**, so reading the wrong one leaves the title ~187px too wide
  and clips 6–18% of it. Nothing guarantees that corrective `<Configure>`
  arrives — it only fires when the geometry actually changes — so the test
  now reads the decision with no layout pass in between.

## 3.48.0 — Fewer things to decide about, at the moment you have least to spend
Counted rather than guessed: the first screen of a brand-new install offered
**32 clickable controls** before a single task existed — and about half of
them could not do anything at all. Every task action needs a selection, and
there were no tasks. For an app built for people who find a wall of choices
expensive, that is the wrong first impression.

- **A first launch now starts in Calm mode.** A missing config file is the one
  moment the app can know nobody has used this copy, and that screen opens
  with **17 live controls instead of 32**. The capture box and "Where do I
  start?" carry it, which is what the tagline has always said the app is for.
  Calm mode already existed and was already good; it was simply off by
  default on the one screen that most needed it.

- **It is a first impression, not a decision made for you.** The checkbox is
  in plain sight, the choice is remembered from then on, and an existing
  install is never rearranged — the default only applies where there is no
  config file at all. A corrupt config is not treated as a new user either:
  quietly hiding someone's controls on top of a damaged file would be its own
  small betrayal.

- **One flat sentence says where the rest went**, once, on that launch only:
  *"Calm mode is on — fewer controls to begin with. Untick it above for
  filters and task tools."* Hiding controls silently would be a trap; naming
  the way out is not.

- **Nothing is offered while it cannot act.** Priority, Tag, Edit, Pin, To
  matrix, Delete, Focus on selected and Done all need a selection, and
  "Clear done" needs something finished. They are now greyed until they can
  act. A control that looks live and does nothing is a decision that pays
  nothing back, and the only way to learn a button was not for you was to
  press it and be told so.

- **Greyed, not hidden — deliberately.** Nothing moves, the row keeps its
  shape, and the moment you select a task **seven buttons come on at once**.
  That correlation teaches what they apply to without a sentence and without
  a failed click. A row that changes shape under you is its own kind of
  overwhelming, and this app already refuses to hide a control that is still
  doing something.

- **A real bug fell out of it.** Selecting a row *from code* does not fire the
  widget's own callback, so the actions stayed greyed over a visibly selected
  task — reachable today by clicking the "booked for today" banner, which
  selects a row for you. `_select_task` now re-syncs, with a test that fails
  if it stops.

- 656 → 667 tests, Xvfb (`skipped=2`) and headless (`skipped=275`). **Seven
  promises broken on purpose and all seven caught**: never greying, greying
  for ever, dropping the re-sync after a refresh, dropping it after a
  code-driven selection, "Clear done" always live, a first run that is not
  calm, and every launch treated as a first run.

## 3.47.0 — The window now fits the screen it is on
The app opened at a fixed 1240x880 with a floor of 1160x790, and **neither
number was ever compared to the screen**. On a 1366x768 laptop it opened
113px past the bottom edge — and could not be resized to fit, because the
floor of 790 is itself taller than 768.

- **Thirteen controls sat off-screen**, measured: the whole task toolbar
  (Priority, Tag, Edit, Pin, To matrix, Delete, Clear done), the whole footer
  (Save, Open, Export, **Undo**), the **status bar**, and the **momentum
  label**. 1024x768 was 22px too tall, 1280x720 was 70px, 1366x768 was 23px.
  `px()` never shrinks below its design size, so a low-DPI screen got no
  relief and a HiDPI panel scaled the numbers **up**.

- **What that cost is worse than the list suggests.** The status bar carries
  ~73 of the app's messages, so the app was simply silent there.
  `delete_selected` writes *"Deleted N tasks. Ctrl+Z undoes it."* into that
  invisible bar while the Undo button sat in the invisible footer — the
  safety net advertised where it could not be read and offered where it could
  not be clicked. And the momentum label and strip are the week review's
  **only** two entry points, so the dialog v3.43.0 had just made fit could
  not be opened at all.

- **The window now sizes itself from the screen**, capped at the designed
  1240x880 and floored at a measured 1120x700, with room left for a title bar
  and a taskbar. When a screen cannot show even the floor, **the screen
  wins**: a button clipped by a few pixels is still readable and still
  clickable, while a button below the bottom edge of a window that refuses to
  shrink is neither. Measured after: 1366x768, 1024x768 and 1920x1080 are
  completely clean with nothing off the bottom; 1280x720 clips 18px off the
  bottom of the toolbar buttons in the worst legitimate state, which is the
  deliberate trade.

- **The floor is measured, not chosen.** In the worst legitimate state — a
  running session with a NEXT UP title and first step that each wrap —
  nothing overflows its card down to **1100x670**, so 1120x700 keeps 20-30px
  of clearance. The old 790 was ~110px above what the layout needs, and that
  slack is the entire bug on a 768px screen.

- **The width number took two measurements.** The first used
  `reqwidth > width` and reported 930; the second, against the parent card's
  right edge, reported 1100. A widget can be given exactly the width it asked
  for and still sit past its card — which is what "Show done" does at 1060.
  The first measurement was a predicate that never fired where it mattered,
  and the existing floor test is what caught it.

- **The codebase half-knew this already.**
  `test_the_window_floor_is_a_size_the_app_works_at` pinned the floor as an
  exact equality, and its sibling proved the app *works* at 1160x790. Neither
  ever asked whether that floor is a size a **screen can show** — the test
  name says it: *a size the app works at*, not a size that fits. Standing
  lesson one level up, and the third time this codebase has hit the shape
  after the focus pop-out and the week review.

- **The sizing is now a pure function**, `window_bounds`, so the interesting
  resolutions are tested by arithmetic rather than by standing up an X
  display each — which is exactly why this survived so long: every test ran
  on a screen big enough to hide it.

- 651 → 656 tests, Xvfb (`skipped=2`) and headless (`skipped=269`). **Six
  mutants, and two of them initially survived** — both test defects worth
  recording. Replacing the geometry call with the old constant passed
  everything, because the tests checked `window_bounds` and never that
  `_fit_to_screen` **uses** its answer: the wrong-layer trap one level up.
  And dropping the taskbar allowance to zero passed because that test only
  asserted `if opened_h < height`, which is false in precisely the case that
  matters. Both are fixed and both now fail against their mutants.

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
