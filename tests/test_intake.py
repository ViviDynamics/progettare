from pathlib import Path

import pytest

from progettare.engine.intake import (
    assemble,
    find_conflicts,
    pair_clarifications,
    parse_acceptance_criteria,
)
from progettare.github import Issue, IssueComment
from progettare.issue_ref import parse_issue_ref


def make_issue(body: str, comments: tuple[IssueComment, ...] = ()) -> Issue:
    ref = parse_issue_ref("ViviDynamics/progettare#1")
    return Issue(
        owner=ref.owner,
        repo=ref.repo,
        number=ref.number,
        title="M1: intake and card context assembly",
        body=body,
        state="OPEN",
        url="https://github.com/ViviDynamics/progettare/issues/1",
        comments=comments,
    )


def test_the_family_issue_shape_parses() -> None:
    body = "\n".join(
        [
            "Assemble card context from a GitHub issue and the repository checkout.",
            "",
            "Acceptance:",
            "- Accepts an issue by URL or owner/repo#number, plus a repo path",
            "- Parses acceptance criteria into a stable list",
            "",
            "Rationale:",
            "Intake is code only.",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == (
        "Accepts an issue by URL or owner/repo#number, plus a repo path",
        "Parses acceptance criteria into a stable list",
    )


def test_a_markdown_heading_marker_parses() -> None:
    body = "## Acceptance criteria\n\n- [x] one\n- [ ] two\n\n## Done When\n- three"
    assert parse_acceptance_criteria(body) == ("one", "two")


def test_numbered_items_and_continuations_parse() -> None:
    body = "Acceptance:\n1. first\n2. second\n   wrapped on the next line\n\nDone."
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("first", "second wrapped on the next line")


def test_a_body_without_a_marker_yields_no_criteria() -> None:
    assert parse_acceptance_criteria("A plain body with no acceptance section") == ()


def test_exact_duplicates_are_dropped_in_order() -> None:
    body = "Acceptance:\n- same\n- other\n- same\n- Other"
    assert parse_acceptance_criteria(body) == ("same", "other", "Other")


def test_placeholder_criteria_read_as_missing() -> None:
    body = "Acceptance:\n- TBD\n- TODO"
    issue = make_issue(body)
    context = assemble(issue, "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    assert "acceptance criteria" in context.blocked_questions[0]


def test_a_placeholder_among_actionable_criteria_blocks() -> None:
    body = "Acceptance:\n- Implement X\n- TBD"
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert context.acceptance_criteria == ("Implement X",)
    assert len(context.blocked_questions) == 1
    assert "criterion 2 is a placeholder" in context.blocked_questions[0]
    assert "TBD" in context.blocked_questions[0]


def test_a_duplicate_does_not_shift_reported_positions() -> None:
    body = "Acceptance:\n- one\n- one\n- TBD"
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert context.acceptance_criteria == ("one",)
    assert len(context.blocked_questions) == 1
    assert "criterion 3 is a placeholder" in context.blocked_questions[0]


def test_a_conflict_reports_the_body_positions() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- The run must write artifacts",
            "- TBD",
            "- The run must not write artifacts",
        ]
    )
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 2
    assert "criteria 1 and 3" in context.blocked_questions[1]


def test_a_conflict_names_both_criteria() -> None:
    body = (
        "Acceptance:\n"
        "- The run must write artifacts\n"
        "- The run must not write artifacts"
    )
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    question = context.blocked_questions[0]
    assert "criteria 1 and 2" in question
    assert "must write artifacts" in question


def test_a_duplicate_before_a_conflict_does_not_shift_positions() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- The run must write artifacts",
            "- The run must write artifacts",
            "- The run must not write artifacts",
        ]
    )
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    question = context.blocked_questions[0]
    assert "criteria 1 and 3" in question
    assert "(3) The run must not write artifacts" in question


def test_a_blank_bullet_blocks_as_a_placeholder() -> None:
    body = "Acceptance:\n- Implement X\n- "
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert context.acceptance_criteria == ("Implement X",)
    assert len(context.blocked_questions) == 1
    assert "criterion 2 is a placeholder" in context.blocked_questions[0]


def test_an_all_blank_section_asks_the_general_question() -> None:
    context = assemble(make_issue("Acceptance:\n- \n- "), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    assert "acceptance criteria" in context.blocked_questions[0]


def test_a_bare_checkbox_blocks_as_a_placeholder() -> None:
    body = "Acceptance:\n- Implement X\n- [ ]"
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    assert "criterion 2 is a placeholder" in context.blocked_questions[0]


def test_a_standalone_marker_blocks_as_a_placeholder() -> None:
    body = "Acceptance:\n- Implement X\n-"
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    assert "criterion 2 is a placeholder" in context.blocked_questions[0]


def test_does_and_does_not_conflict() -> None:
    body = (
        "Acceptance:\n- The run does write artifacts\n- The run doesn't write artifacts"
    )
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert len(context.blocked_questions) == 1
    assert "criteria 1 and 2" in context.blocked_questions[0]


def test_the_na_spelling_blocks_as_a_placeholder() -> None:
    body = "Acceptance:\n- Implement X\n- N.A."
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "blocked"
    assert "criterion 2 is a placeholder" in context.blocked_questions[0]


def test_different_modals_do_not_conflict() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- The run can write artifacts",
            "- The run should not write artifacts",
        ]
    )
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "ok"
    assert context.blocked_questions == ()


def test_find_conflicts_stays_narrow() -> None:
    criteria = (
        "The loop must stop after one turn",
        "The loop should stop after one turn",
        "The loop must not stop after two turns",
        "The documenter writes the README",
        "The run is bounded",
        "The run is not bounded",
    )
    conflicts = find_conflicts(tuple(enumerate(criteria)))
    assert len(conflicts) == 1
    assert conflicts[0].first == 4
    assert conflicts[0].second == 5


def test_a_bold_label_terminates_the_section() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- ships intake.json",
            "",
            "**Implementation Notes:**",
            "- use a temporary file",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("ships intake.json",)


def test_clarifications_pair_questions_with_answers() -> None:
    comments = (
        IssueComment(
            author="jason", body="Should the briefs live in the run dir?", created_at=""
        ),
        IssueComment(author="jason", body="Yes, under briefs/.", created_at=""),
        IssueComment(author="jason", body="Is replay model-free?", created_at=""),
    )
    paired = pair_clarifications(comments)
    assert len(paired) == 2
    assert paired[0].answer == "Yes, under briefs/."
    assert paired[1].answer is None


def test_assemble_reports_ok_when_the_card_is_actionable() -> None:
    body = "Acceptance:\n- Intake writes intake.json\n- Intake spends no model calls"
    context = assemble(make_issue(body), "/tmp")
    assert context.status == "ok"
    assert context.blocked_questions == ()
    assert context.acceptance_criteria == (
        "Intake writes intake.json",
        "Intake spends no model calls",
    )
    assert context.repo_path == str(Path("/tmp").resolve())


def test_a_relative_repo_path_is_stored_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    body = "Acceptance:\n- Intake writes intake.json"
    monkeypatch.chdir(tmp_path)
    context = assemble(make_issue(body), ".")
    assert context.repo_path == str(tmp_path.resolve())


def test_a_two_character_label_terminates_the_section() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- ships intake.json",
            "",
            "QA:",
            "- survives a second run",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("ships intake.json",)


def test_a_lowercase_label_terminates_the_section() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- ships intake.json",
            "",
            "notes:",
            "- survives a second run",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("ships intake.json",)


def test_a_single_character_label_terminates_the_section() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- ships intake.json",
            "",
            "A:",
            "- survives a second run",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("ships intake.json",)


def test_an_indented_word_line_keeps_feeding_the_criterion() -> None:
    body = "\n".join(
        [
            "Acceptance:",
            "- ships intake.json",
            "  note: the file lands in the run directory",
        ]
    )
    criteria = parse_acceptance_criteria(body)
    assert criteria == ("ships intake.json note: the file lands in the run directory",)
