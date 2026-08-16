# Changelog

All of this lives on the branch `claude/program-improvement-uqm40n`.
Newest first. Versions bump with each delivered change-set; the themes
throughout are task *initiation*, honest data, and a tone that never
scolds.

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
