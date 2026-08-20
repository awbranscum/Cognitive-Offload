"""Handing a task to an agent: the brief, the command, and the waiting mark.

No display needed — this is all decisions and files, which is the point of
keeping the transport out of the UI.
"""

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cognitive_offload import handoff
from cognitive_offload.models import MatrixTask
from cognitive_offload.rows import matrix_row, waiting_line


def a_task(**kw):
    fields = dict(
        title="Chase the insurance claim appeal",
        content="They rejected it on 2 Aug.\nSecond line.",
        category="delegate",
        first_step="find the claim number",
        scheduled_for="2026-08-22",
        estimate_minutes=25,
        tags=["admin"],
    )
    fields.update(kw)
    return MatrixTask(**fields)


class BriefTests(unittest.TestCase):
    def test_the_brief_carries_what_the_person_already_wrote(self):
        """Retyping context you have already typed is the tax that stops
        people delegating at all."""
        brief = handoff.build_brief(a_task(), note="Draft the letter.",
                                    today="2026-08-19")
        text = handoff.render_markdown(brief)
        for expected in ("Chase the insurance claim appeal", "Draft the letter.",
                         "They rejected it on 2 Aug.", "find the claim number",
                         "2026-08-22", "25 minutes", "admin"):
            self.assertIn(expected, text, expected)

    def test_the_two_formats_ask_for_the_same_thing(self):
        """The promise IS an agreement between the two renderings, so assert
        the agreement rather than hard-coding either side."""
        brief = handoff.build_brief(a_task(), note="Draft it.", today="2026-08-19")
        data = json.loads(handoff.render_json(brief))
        markdown = handoff.render_markdown(brief)
        self.assertEqual(data["instructions"], handoff.REPORT_BACK)
        self.assertIn(handoff.REPORT_BACK, markdown)
        for value in (data["title"], data["note"], data["detail"].splitlines()[0],
                      data["first_step"], data["due"]):
            self.assertIn(value, markdown, value)

    def test_an_empty_task_still_produces_a_usable_brief(self):
        brief = handoff.build_brief(MatrixTask(title=""), today="2026-08-19")
        self.assertEqual(brief.title, "Untitled task")
        text = handoff.render_markdown(brief)
        self.assertIn("Untitled task", text)
        self.assertIn(handoff.REPORT_BACK, text)
        json.loads(handoff.render_json(brief))  # must still be valid JSON

    def test_the_handover_never_lets_an_agent_act_irreversibly_unasked(self):
        """The one instruction that must survive any rewording of the rest."""
        for renderer in (handoff.render_markdown, handoff.render_json):
            text = renderer(handoff.build_brief(a_task()))
            self.assertIn("Ask before", text)
            for irreversible in ("spends money", "another person", "cannot be undone"):
                self.assertIn(irreversible, text, irreversible)

    def test_the_brief_says_nothing_that_scolds(self):
        brief = handoff.build_brief(a_task(), note="", today="2026-08-19")
        text = handoff.render_markdown(brief).lower()
        for scold in ("overdue", "late", "failed", "you should", "still not",
                      "finally", "at last"):
            self.assertNotIn(scold, text, scold)


class FilenameTests(unittest.TestCase):
    def test_the_filename_carries_no_spaces_because_commands_quote_it(self):
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        name = brief.filename("md")
        self.assertNotIn(" ", name)
        self.assertTrue(name.startswith("2026-08-19-"), name)
        self.assertTrue(name.endswith(".md"), name)

    def test_two_tasks_with_one_title_do_not_share_a_file(self):
        one, two = a_task(), a_task()
        self.assertNotEqual(
            handoff.build_brief(one, today="2026-08-19").filename("md"),
            handoff.build_brief(two, today="2026-08-19").filename("md"),
        )

    def test_json_targets_get_json_and_markdown_targets_get_md(self):
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        for target in handoff.TARGETS:
            suffix = handoff.suffix_for(target)
            self.assertEqual(suffix, "json" if target.fmt == "json" else "md")
            self.assertTrue(handoff.brief_path("/tmp", target, brief)
                            .name.endswith("." + suffix))


class CommandTests(unittest.TestCase):
    """A handoff folder with a space in it is ordinary (``~/My Documents``)."""

    SPACED = "/home/me/My Documents/Hand Off"

    def test_every_shell_command_survives_a_folder_with_a_space_in_it(self):
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        for target in handoff.TARGETS:
            if not target.shell:
                continue
            path = handoff.brief_path(self.SPACED, target, brief)
            command = handoff.command_for(target, path)
            words = shlex.split(command)  # raises if the quoting is broken
            self.assertTrue(
                any(str(path) in word for word in words),
                f"{target.key}: the path did not survive as one word: {words}",
            )

    def test_the_codex_command_really_hands_over_the_whole_brief(self):
        """Not "it looks right": run it against a stub and read argv."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "My Hand Off"
            target = handoff.target_for("codex")
            brief = handoff.build_brief(a_task(), note="Draft it.",
                                        today="2026-08-19")
            path = handoff.write_brief(root, target, brief)
            command = handoff.command_for(target, path)
            # Replace the CLI with something that prints what it received.
            stub = command.replace("codex ", f"{shlex.quote(sys.executable)} -c "
                                             f"'import sys; print(sys.argv[1])' ", 1)
            out = subprocess.run(["sh", "-c", stub], capture_output=True,
                                 text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Chase the insurance claim appeal", out.stdout)
            self.assertIn(handoff.REPORT_BACK, out.stdout)

    def test_a_pasted_target_is_not_shell_quoted(self):
        """Claude Desktop's line goes into a chat box, where shell quoting is
        noise the agent has to read past."""
        target = handoff.target_for("claude_desktop")
        self.assertFalse(target.shell)
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        path = handoff.brief_path(self.SPACED, target, brief)
        command = handoff.command_for(target, path)
        self.assertIn(str(path), command)
        self.assertNotIn("'", command)

    def test_a_broken_template_still_names_the_file_it_wrote(self):
        """The brief is the deliverable; the command is a convenience. A typo
        in an overridden template must not swallow the path."""
        target = handoff.target_for("codex")
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        path = handoff.brief_path("/tmp", target, brief)
        command = handoff.command_for(target, path, template="run {nonsense}")
        self.assertIn(str(path), command)

    def test_an_override_replaces_the_default(self):
        target = handoff.target_for("openclaw")
        brief = handoff.build_brief(a_task(), today="2026-08-19")
        path = handoff.brief_path("/tmp", target, brief)
        self.assertEqual(handoff.command_for(target, path, template="mine {brief}"),
                         f"mine {shlex.quote(str(path))}")


class WriteTests(unittest.TestCase):
    def test_the_brief_lands_exactly_where_brief_path_said_it_would(self):
        with tempfile.TemporaryDirectory() as tmp:
            for target in handoff.TARGETS:
                brief = handoff.build_brief(a_task(), today="2026-08-19")
                expected = handoff.brief_path(tmp, target, brief)
                written = handoff.write_brief(tmp, target, brief)
                self.assertEqual(written, expected)
                self.assertTrue(written.is_file())
                self.assertEqual(written.read_text(encoding="utf-8"),
                                 handoff.render(brief, target))

    def test_each_target_keeps_its_own_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = handoff.build_brief(a_task(), today="2026-08-19")
            folders = {handoff.write_brief(tmp, t, brief).parent
                       for t in handoff.TARGETS}
            self.assertEqual(len(folders), len(handoff.TARGETS))


class TargetTests(unittest.TestCase):
    def test_an_unknown_target_falls_back_instead_of_raising(self):
        """A config naming a target that no longer exists is not a reason to
        refuse to hand anything over."""
        self.assertEqual(handoff.target_for("gone"), handoff.TARGETS[0])
        self.assertEqual(handoff.target_for(""), handoff.TARGETS[0])

    def test_the_three_targets_the_owner_asked_for_are_all_present(self):
        self.assertEqual(set(handoff.TARGET_KEYS),
                         {"claude_desktop", "codex", "openclaw"})

    def test_labels_and_keys_agree_in_both_directions(self):
        for target in handoff.TARGETS:
            self.assertIn(target.label, handoff.TARGET_LABELS)
            self.assertEqual(handoff.TARGET_KEY_BY_LABEL[target.label], target.key)


class FollowUpTests(unittest.TestCase):
    def test_a_handoff_always_gets_a_day_it_comes_back_on(self):
        self.assertEqual(handoff.follow_up_date("2026-08-19", 3), "2026-08-22")
        self.assertEqual(handoff.follow_up_date("2026-08-30", 3), "2026-09-02")

    def test_a_nonsense_date_still_produces_a_real_follow_up(self):
        """Losing the follow-up is the failure this whole feature exists to
        avoid, so it must not depend on a parseable input."""
        for junk in ("", "not a date", None):
            self.assertRegex(handoff.follow_up_date(junk), r"^\d{4}-\d{2}-\d{2}$")

    def test_zero_and_negative_days_still_mean_a_later_day(self):
        for days in (0, -5):
            self.assertGreater(handoff.follow_up_date("2026-08-19", days),
                               "2026-08-19")


class WaitingTests(unittest.TestCase):
    def handed(self, **kw):
        fields = dict(handed_to="Claude Desktop", handed_off_on="2026-08-19",
                      follow_up_on="2026-08-22")
        fields.update(kw)
        return a_task(**fields)

    def test_a_task_that_is_out_says_who_has_it_and_when_it_comes_back(self):
        line = waiting_line(self.handed(), on="2026-08-19")
        self.assertIn("Claude Desktop", line)
        self.assertIn("check back", line)

    def test_a_task_that_is_not_out_says_nothing_at_all(self):
        self.assertEqual(waiting_line(a_task()), "")
        self.assertEqual(waiting_line(MatrixTask(title="x")), "")

    def test_the_waiting_line_wins_the_subtitle_from_the_first_step(self):
        """The first step belongs to whoever has the task now; showing it
        here would read as something still sitting on your own plate."""
        row = matrix_row(self.handed())
        self.assertIn("Waiting on", row.subtitle)
        self.assertNotIn("find the claim number", row.subtitle)
        # ...and it comes straight back when the task does.
        self.assertIn("find the claim number",
                      matrix_row(a_task()).subtitle)

    def test_a_follow_up_that_has_arrived_says_check_back_not_overdue(self):
        overdue = self.handed(handed_off_on="2026-08-01", follow_up_on="2026-08-04")
        texts = [b.text for b in matrix_row(overdue).badges]
        self.assertIn("check back", texts)
        for scold in ("overdue", "late", "missed", "failed"):
            self.assertNotIn(scold, " ".join(texts).lower())

    def test_the_waiting_badge_leads_the_row(self):
        self.assertEqual(matrix_row(self.handed()).badges[0].text, "waiting")

    def test_is_due_back_stays_inclusive_of_the_past(self):
        """Same rule as is_due: a follow-up you missed still deserves a route
        back rather than silently expiring."""
        task = self.handed(follow_up_on="2026-08-22")
        self.assertFalse(task.is_due_back("2026-08-21"))
        self.assertTrue(task.is_due_back("2026-08-22"))
        self.assertTrue(task.is_due_back("2027-01-01"))

    def test_a_task_never_handed_over_is_never_due_back(self):
        self.assertFalse(a_task().is_due_back("2030-01-01"))


class PersistenceTests(unittest.TestCase):
    def test_the_waiting_mark_survives_a_round_trip(self):
        task = a_task(handed_to="Codex", handed_off_on="2026-08-19",
                      follow_up_on="2026-08-22")
        back = MatrixTask.from_dict(task.to_dict(), "delegate")
        self.assertEqual((back.handed_to, back.handed_off_on, back.follow_up_on),
                         ("Codex", "2026-08-19", "2026-08-22"))

    def test_a_file_written_before_this_feature_still_loads(self):
        old = {"title": "Older task", "content": "", "category": "delegate"}
        task = MatrixTask.from_dict(old, "delegate")
        self.assertEqual(task.handed_to, "")
        self.assertFalse(task.is_waiting())

    def test_the_store_can_mark_a_task_and_take_it_back(self):
        from cognitive_offload.storage import MatrixStore

        with tempfile.TemporaryDirectory() as tmp:
            store = MatrixStore(Path(tmp))
            store.ensure()
            task = store.create("delegate", "Chase the claim")
            store.set_handoff(task, "OpenClaw", "2026-08-19", "2026-08-22")
            reloaded = store.list("delegate")[0]
            self.assertTrue(reloaded.is_waiting())
            self.assertEqual(reloaded.handed_to, "OpenClaw")

            store.set_handoff(reloaded, "", "", "")
            self.assertFalse(store.list("delegate")[0].is_waiting())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class HandoffDocTests(unittest.TestCase):
    """A stale interface document is worse than none, so the doc is pinned
    against the code the same way docs/PORTING.md is."""

    DOC = Path(__file__).resolve().parent.parent / "docs" / "AGENT_HANDOFF.md"

    def doc(self):
        return self.DOC.read_text(encoding="utf-8")

    def test_every_target_is_documented_with_its_real_command(self):
        text = self.doc()
        for target in handoff.TARGETS:
            self.assertIn(target.label, text, target.label)
            self.assertIn(target.command, text,
                          f"{target.key}: the doc shows a different command")
            self.assertIn(target.folder, text, target.folder)

    def test_the_doc_names_no_target_the_code_does_not_have(self):
        """The failure that matters here is the doc promising an agent that
        was removed, which no count of the code would catch."""
        table = self.doc().split("## The three targets", 1)[1].split("##", 1)[0]
        for line in table.splitlines():
            if not line.startswith("| ") or line.startswith("| Target") \
                    or set(line) <= set("| -"):
                continue
            label = line.split("|")[1].strip()
            self.assertIn(label, handoff.TARGET_LABELS,
                          f"the doc lists {label!r}, which the code does not have")

    def test_the_documented_default_folder_is_the_real_default(self):
        import tempfile as _tf

        from cognitive_offload.storage import Config

        with _tf.TemporaryDirectory() as tmp:
            default = Config(Path(tmp) / "c.json").handoff_root.name
        self.assertIn(default, self.doc(),
                      "the doc names a different default handoff folder")

    def test_the_doc_states_the_limit_rather_than_burying_it(self):
        """The one thing a reader must not be able to miss."""
        self.assertIn("Nothing is sent anywhere", self.doc())


class BriefCompletenessTests(unittest.TestCase):
    """The brief is a hand-written list of fields read off a task, and this
    project has already watched three of those go stale: both conversions,
    the per-round resets, and the editor's three call sites. This is the
    fourth, and it went stale on schedule — a task broken into four steps was
    handed over carrying only the first, with the rest nowhere in the file.

    So it is keyed on ``dataclasses.fields(MatrixTask)``: every field must
    either reach the agent or be **named below as deliberately not sent**,
    with a reason. Several genuinely are not the agent's business, and saying
    so out loud is the point — an unwritten decision is the thing that rots.
    """

    # Not sent, each with the reason it is not.
    NOT_SENT = {
        "id": "sent as `task_id`, which is checked separately — the raw field "
              "name never appears",
        "path": "the file backing the task; assigned by the store, never data",
        "created_at": "a storage timestamp, not something the person wrote",
        "updated_at": "as above",
        "category": "which quadrant you filed it in is your triage, not the "
                    "work — and 'urgent but not important' is a judgement "
                    "about your day, not about this job",
        "kind": "how it FEELS to start is about the person, not the task; an "
                "agent has no state of mind to match it to",
        "priority": "your flag, on your list",
        "pinned": "as above",
        "snoozed_until": "'not today' is a decision about your day",
        "repeat": "the agent is doing this round; that it comes back weekly "
                  "is your arrangement, not part of the job",
        "handed_to": "the handoff marks describe THIS handoff and are written "
                     "after the brief is; putting them in it would be the "
                     "brief describing its own delivery",
        "handed_off_on": "as above",
        "follow_up_on": "as above — and the brief already asks to be reported "
                        "back on, in REPORT_BACK",
    }

    def full_task(self):
        """Every field set to something distinctive, so a field that is
        dropped cannot pass by matching something else in the output."""
        return MatrixTask(
            title="Chase the insurance claim appeal",
            content="They rejected it on 2 Aug; the deadline is in the email.",
            category="delegate",
            created_at="2026-01-02T03:04:05",
            updated_at="2026-01-02T03:04:06",
            first_step="find the claim number",
            kind="admin",
            scheduled_for="2026-08-21",
            tags=["admin", "phone"],
            priority=1,
            pinned=True,
            estimate_minutes=25,
            repeat="weekly",
            # Far future on purpose. This was a date near the day the test
            # was written, and the day the clock reached it the brief's own
            # "handed over on <today>" line contained the same string — so
            # `test_nothing_exempt_leaks_in_anyway` failed on exactly one day
            # and passed on every other. A fixture date that can become today
            # is a test that fails on a schedule.
            snoozed_until="2099-03-04",
            handed_to="Claude Desktop",
            handed_off_on="2026-08-19",
            follow_up_on="2026-08-22",
            steps=["find the claim number", "reread the rejection letter",
                   "ring them and ask for a supervisor"],
            steps_done=1,
        )

    def rendered(self):
        brief = handoff.build_brief(self.full_task())
        return handoff.render_markdown(brief) + "\n" + handoff.render_json(brief)

    def test_every_field_is_sent_or_deliberately_not(self):
        import dataclasses

        task = self.full_task()
        text = self.rendered().lower()
        for field in dataclasses.fields(MatrixTask):
            if field.name in self.NOT_SENT:
                continue
            value = getattr(task, field.name)
            parts = value if isinstance(value, list) else [value]
            for part in parts:
                with self.subTest(field=field.name, value=part):
                    self.assertIn(
                        str(part).lower(), text,
                        f"{field.name} never reaches the agent — send it, or "
                        f"add it to NOT_SENT with a reason",
                    )

    def test_the_exemptions_name_only_real_fields(self):
        import dataclasses

        names = {f.name for f in dataclasses.fields(MatrixTask)}
        self.assertEqual(set(self.NOT_SENT) - names, set())

    def test_every_exemption_carries_a_reason(self):
        for reason in self.NOT_SENT.values():
            self.assertTrue(reason.strip())

    def test_the_id_does_reach_the_agent_under_its_own_name(self):
        brief = handoff.build_brief(self.full_task())
        self.assertIn(brief.task_id, handoff.render_json(brief))
        self.assertIn(brief.task_id[:8], handoff.render_markdown(brief))

    def test_nothing_exempt_leaks_in_anyway(self):
        """The other direction: a field decided against must not arrive
        through some other line. 'Not the agent's business' is a promise."""
        task = self.full_task()
        text = self.rendered()
        for name in ("snoozed_until", "pinned", "repeat"):
            with self.subTest(field=name):
                self.assertNotIn(str(getattr(task, name)).lower(),
                                 text.lower().replace(task.title.lower(), ""))


class PlanInTheBriefTests(unittest.TestCase):
    """What the completeness net found: the plan was not being sent."""

    def planned(self):
        task = a_task(title="Write the quarterly report")
        task.first_step = "open last year's report"
        task.set_rest(["copy the headings across", "fill in this year's numbers"])
        return task

    def test_the_markdown_carries_every_step(self):
        text = handoff.render_markdown(handoff.build_brief(self.planned()))
        for step in ("open last year's report", "copy the headings across",
                     "fill in this year's numbers"):
            self.assertIn(step, text)

    def test_the_markdown_says_which_step_to_start_at(self):
        """Marked, and marked on exactly one line. An agent that starts at
        the top of a plan redoes work someone has already done, which is
        worse than doing nothing."""
        task = self.planned()
        task.advance_step()
        text = handoff.render_markdown(handoff.build_brief(task))
        marked = [line for line in text.splitlines()
                  if handoff.START_HERE.strip() in line]
        self.assertEqual(len(marked), 1, "the start is unmarked or marked twice")
        self.assertIn("copy the headings across", marked[0])
        self.assertIn("[x] open last year's report", text,
                      "a step already done should read as done")
        self.assertNotIn("[ ] open last year's report", text)

    def test_the_json_carries_the_plan_as_data(self):
        import json as _json

        task = self.planned()
        task.advance_step()
        data = _json.loads(handoff.render_json(handoff.build_brief(task)))
        self.assertEqual(data["steps"], task.steps)
        self.assertEqual(data["steps_done"], 1)

    def test_a_task_with_no_plan_says_nothing_about_one(self):
        """An empty "The plan" heading on a one-step task is noise in a
        document whose whole job is being quick to read."""
        text = handoff.render_markdown(handoff.build_brief(a_task()))
        self.assertNotIn("The plan", text)
