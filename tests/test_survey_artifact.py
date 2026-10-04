"""Tests for the versioned survey.json record and its enforced caps."""

from __future__ import annotations

import json
import pathlib

import pytest

from progettare.config import Config, ModelRail
from progettare.engine.intake import CardContext
from progettare.github import Issue
from progettare.survey.artifact import (
    SURVEY_RECORD_VERSION,
    SurveyAnswer,
    SurveyRecordError,
    survey_record,
    write_survey,
)
from progettare.survey.questions import RepoStructure, SurveyPlan, formulate

STRUCTURE = RepoStructure(
    tree=("pyproject.toml", "src/x.py"),
    touched=(),
    entry_points=("pyproject.toml",),
    tests=(),
)


def make_config(max_questions: int = 5, budget: int = 2) -> Config:
    rail = ModelRail(provider="p", model="m", base_url=None)
    return Config(
        survey_max_questions=max_questions,
        survey_per_question_command_budget=budget,
        budget_survey_stage_tokens=150000,
        budget_blueprint_stage_tokens=60000,
        budget_run_max_tokens=300000,
        size_single_turn_max_milestones=2,
        size_documenter_min_topics=1,
        survey_rail=rail,
        blueprint_rail=rail,
    )


def make_plan(max_questions: int = 5) -> SurveyPlan:
    ctx = CardContext(
        issue=Issue(
            owner="acme",
            repo="widgets",
            number=7,
            title="t",
            body="",
            state="OPEN",
            url="u",
            comments=(),
        ),
        repo_path="/tmp/repo",
        acceptance_criteria=("One.", "Two."),
        clarifications=(),
        status="ok",
        blocked_questions=(),
    )
    return formulate(ctx, STRUCTURE, make_config(max_questions))


def test_record_is_versioned_and_structured() -> None:
    plan = make_plan(5)
    record = survey_record(
        plan, (SurveyAnswer(question=1, commands=("ls",), findings="found"),)
    )
    assert record["version"] == SURVEY_RECORD_VERSION
    assert record["issue"] == 7
    assert record["repo"] == "acme/widgets"
    assert record["structure"]["tree"] == ["pyproject.toml", "src/x.py"]
    assert record["questions"][0]["number"] == 1
    assert record["questions"][0]["criterion"] == "One."
    assert record["answers"] == [
        {"question": 1, "commands": ["ls"], "findings": "found"}
    ]


def test_answer_commands_over_budget_are_refused() -> None:
    plan = make_plan(5)
    answers = (
        SurveyAnswer(
            question=1, commands=("ls", "cat pyproject.toml", "wc"), findings="f"
        ),
    )
    with pytest.raises(SurveyRecordError, match="budget of 2"):
        survey_record(plan, answers)


def test_answer_for_unknown_question_is_refused() -> None:
    plan = make_plan(5)
    with pytest.raises(
        SurveyRecordError, match="question 9, which the plan does not contain"
    ):
        survey_record(plan, (SurveyAnswer(question=9, commands=(), findings="f"),))


def test_duplicate_answers_are_refused() -> None:
    plan = make_plan(5)
    answers = (
        SurveyAnswer(question=1, commands=("ls",), findings="first"),
        SurveyAnswer(question=1, commands=("ls",), findings="second"),
    )
    with pytest.raises(SurveyRecordError, match="more than one answer"):
        survey_record(plan, answers)


def test_answer_without_findings_is_refused() -> None:
    plan = make_plan(5)
    with pytest.raises(SurveyRecordError, match="recorded no findings"):
        survey_record(
            plan, (SurveyAnswer(question=1, commands=("ls",), findings="  "),)
        )


def test_answer_commands_are_allowlist_checked() -> None:
    plan = make_plan(5)
    with pytest.raises(SurveyRecordError, match="git push"):
        survey_record(
            plan,
            (SurveyAnswer(question=1, commands=("git push",), findings="f"),),
        )


def test_partial_reason_is_recorded() -> None:
    plan = make_plan(1)
    record = survey_record(
        plan, (SurveyAnswer(question=1, commands=("ls",), findings="f"),)
    )
    assert record["partial_reason"] is not None
    assert "survey.max_questions is 1" in record["partial_reason"]


def test_write_survey_round_trips(tmp_path: pathlib.Path) -> None:
    plan = make_plan(5)
    record = survey_record(
        plan, (SurveyAnswer(question=1, commands=("ls",), findings="f"),)
    )
    path = tmp_path / "survey.json"
    write_survey(path, record)
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == record
    assert text.endswith("\n")
    written_again = tmp_path / "again.json"
    write_survey(written_again, record)
    assert written_again.read_text(encoding="utf-8") == text


def test_record_is_deterministic() -> None:
    first = survey_record(
        make_plan(5), (SurveyAnswer(question=1, commands=("ls",), findings="f"),)
    )
    second = survey_record(
        make_plan(5), (SurveyAnswer(question=1, commands=("ls",), findings="f"),)
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
