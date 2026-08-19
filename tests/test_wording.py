"""The words the app says are pinned, so a refactor cannot quietly reword them.

The plan for lifting decisions out of the controller moves questions between
modules. Every one of them carries wording that was argued over — a booking
that stops claiming to be today, a failure that explains itself without
blaming anyone, an offer to stop that does not read as giving up. Moved code
is reviewed for whether it still *works*; nobody rereads forty strings to see
whether the tone survived.

So this lands first, before anything moves. It is not a test of behaviour: it
is a record of what the app says today, and an alarm when that changes. A
failure here is not a bug — it is a question. If the change was deliberate,
regenerate the snapshot and review the diff as what it is, a change to what a
person reads at a hard moment.
"""

import unittest

from tests.wording import SNAPSHOT_PATH, snapshot


class WordingSnapshotTests(unittest.TestCase):
    def test_the_snapshot_file_is_checked_in(self):
        self.assertTrue(
            SNAPSHOT_PATH.exists(),
            "tests/wording_snapshot.txt is missing — regenerate it with "
            "`python tests/wording.py --update`",
        )

    def test_no_modal_wording_has_changed(self):
        recorded = SNAPSHOT_PATH.read_text(encoding="utf-8")
        current = snapshot()
        if recorded == current:
            return

        def body(text):
            return {line for line in text.splitlines()
                    if line and not line.startswith("#")}

        was, now = body(recorded), body(current)
        removed = sorted(was - now)
        added = sorted(now - was)
        report = ["the app's wording changed."]
        if removed:
            report += ["", "no longer said:"] + [f"  - {line}" for line in removed]
        if added:
            report += ["", "now says:"] + [f"  + {line}" for line in added]
        report += [
            "",
            "If that was deliberate, run `python tests/wording.py --update` and",
            "review the diff as a change to what a person reads. If it was not,",
            "something moved a string it should have carried across untouched.",
        ]
        self.fail("\n".join(report))


class ExtractorTests(unittest.TestCase):
    """Guard the guard: a net that catches nothing would pass silently."""

    def test_the_extractor_actually_finds_the_modal_surface(self):
        entries = snapshot().splitlines()
        strings = [e for e in entries if not e.startswith("#")]
        self.assertGreater(len(strings), 100,
                           "the extractor should be finding the whole surface")

    def test_every_module_with_wording_is_read_not_a_hand_kept_list(self):
        """The net used to read three files by name, and that was the bug.

        Two consequences, both real: SessionLog.summary() sat in
        sessions.py unwatched for its whole life, and — because the
        no-shaming scan reads this same snapshot — every button label and
        hint outside those three files was unchecked for tone as well as
        for drift. Narrowing the list back would restore both holes
        silently, so it is pinned here rather than left to the diff.
        """
        seen = {line.split(" | ", 1)[0] for line in snapshot().splitlines()
                if not line.startswith("#")}
        for name in ("app.py", "dialogs.py", "presenter.py", "main_tab.py",
                     "matrix_tab.py", "widgets.py", "rows.py", "models.py",
                     "storage.py", "queries.py"):
            self.assertIn(name, seen, f"{name} says things to a person and "
                                      "is not being watched")

    def test_the_words_on_the_buttons_are_watched_too(self):
        """Not just dialogs. Most of what this app says, it says on a button.

        These four carry the design: the promise the app makes at the top
        of the window, the question it exists to answer, the way it lets
        you decline without declining forever, and the offer to put a
        thought down instead of holding it.
        """
        text = snapshot()
        for said in ("Get it out of your head, then start one small thing.",
                     "Where do I start?",
                     "Not today",
                     "Something else on your mind? Park it here."):
            self.assertIn(said, text)

    def test_wording_inside_containers_is_read(self):
        """The third axis, and the one that stayed open longest.

        A string that is an element of a dict, list or tuple is not assigned
        to a name, not returned, and not a keyword argument — so widening
        the file list and adding keyword names both missed it. Ninety-two
        strings were sitting there, and they were not offcuts.
        """
        text = snapshot()
        for said in (
            # all four quadrant descriptions lived in a dict
            "Deleting these is progress, not failure",
            "Crises and real deadlines. Do these now.",
            # the shortcuts dialog is a list of tuples
            "Pin to the top (again to unpin)",
            "Undo the last change",
            # the warm-up ladder is a list, and a named feature of the app
            "Clear the desk and close the tabs that are shouting",
            # the presets are dict values
            "Admin sprint",
        ):
            self.assertIn(said, text, f"{said!r} is shown to a person and unwatched")

    def test_wording_passed_positionally_is_read(self):
        """Undo action names are read back in the status bar.

        Nothing about their position said "wording", so none of them were
        watched — the net looked at keywords and returns, and these are
        neither.
        """
        text = snapshot()
        for said in ("mark it done", "send it to the matrix", "clear scratchpad"):
            self.assertIn(said, text)

    def test_a_variables_opening_text_is_read(self):
        """Both of these are on screen the moment the app opens."""
        text = snapshot()
        self.assertIn("Nothing picked yet", text)  # the label above the timer
        self.assertIn("Ready.", text)              # the status bar at rest

    def test_the_snapshot_does_not_claim_to_be_complete(self):
        """It said "Every user-visible string" for many releases and was not.

        About a quarter of the app's wording was outside it. The header is
        the first thing anyone reads on a failure, and a safety net that
        overstates its reach is worse than one that states it plainly:
        it stops people looking for the gap.
        """
        header = snapshot().split("app.py")[0]
        self.assertNotIn("Every user-visible string", header)
        self.assertIn("NOT every string", header)

    def test_it_captures_titles_bodies_and_dialog_labels_alike(self):
        text = snapshot()
        self.assertIn("messagebox.askyesno", text)
        self.assertIn("filedialog.askdirectory", text)
        self.assertIn("dialog-title", text)
        self.assertIn("text=", text)

    def test_interpolations_collapse_so_runtime_values_do_not_churn(self):
        """A path or a count differs per run; the sentence around it does not."""
        self.assertIn("{}", snapshot())

    def test_every_entry_is_one_line(self):
        """Newlines are escaped, or the one-per-line diff becomes unreadable."""
        for line in snapshot().splitlines():
            self.assertNotIn("\n", line)

    def test_the_snapshot_is_stable_across_runs(self):
        self.assertEqual(snapshot(), snapshot(), "extraction must be deterministic")


class ToneTests(unittest.TestCase):
    """The design law, asserted against every string at once.

    These are not style preferences. Shame is the thing that makes someone
    close the app and not come back, and it arrives one word at a time.
    """

    SHAMING = ("failed to", "you didn't", "you did not", "you should have",
               "overdue", "you missed", "still not", "no excuse", "again?")

    def test_nothing_the_app_says_scolds(self):
        offenders = []
        for line in snapshot().splitlines():
            if line.startswith("#"):
                continue
            said = line.split(" | ", 3)[-1].lower()
            offenders += [(word, line) for word in self.SHAMING if word in said]
        self.assertEqual(offenders, [], "a shaming phrase reached the wording")

    def test_nothing_pluralises_with_the_s_form(self):
        """"1 task(s)" reads like output from a machine that did not care.

        v3.26.0 removed it from fifteen status messages, and two survived
        on the brain-dump path until v3.35.0 taught the extractor to read
        positional arguments. Scanning the snapshot rather than the source
        means the next one is caught wherever it is written, provided the
        extractor can see the position at all — which is the standing
        caveat on this whole file.
        """
        offenders = [line for line in snapshot().splitlines()
                     if not line.startswith("#") and "(s)" in line]
        self.assertEqual(offenders, [],
                         "use presenter.plural() rather than the (s) form")

    def test_the_two_folder_pickers_say_which_folder(self):
        """Both buttons read "Change folder"; only the title distinguishes them.

        Compared against just the directory-picker lines, not the whole
        snapshot: an assertion that dumps a hundred and thirty strings on
        failure is one nobody reads, which is the same reason the diff above
        is built by hand.
        """
        pickers = sorted(line for line in snapshot().splitlines()
                         if "filedialog.askdirectory" in line)
        self.assertEqual(pickers, [
            "app.py | filedialog.askdirectory | change_db_folder | "
            "Choose the session folder",
            "app.py | filedialog.askdirectory | change_matrix_db_folder | "
            "Choose the matrix folder",
        ], "each folder picker must name the folder it is changing")


if __name__ == "__main__":
    unittest.main()
