"""Tests for the survey stage's single-session layer.

Every test runs offline: the NareRunner seam is a fake that records the
argv it was given and replays a canned NareResult, so no nare binary and
no network are involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from progettare.config import Config, ModelRail
from progettare.survey.artifact import SurveyAnswer
from progettare.survey.nare import NareError, NareResult, NareUsage, session_argv
from progettare.survey.questions import (
    RepoStructure,
    SurveyPlan,
    SurveyQuestion,
)
from progettare.survey.stage import (
    SURVEY_SYSTEM_PROMPT,
    SessionOutcome,
    answer_one_question,
    fair_share,
)

RAIL = ModelRail(
    provider="openai", model="gpt-survey", base_url="http://127.0.0.1:8000"
)
CONFIG = Config(
    survey_max_questions=5,
    survey_per_question_command_budget=8,
    budget_survey_stage_tokens=1200,
    budget_blueprint_stage_tokens=1200,
    budget_run_max_tokens=10000,
    size_single_turn_max_milestones=8,
    size_documenter_min_topics=0,
    survey_rail=RAIL,
    blueprint_rail=RAIL,
)
QUESTION = SurveyQuestion(
    number=1,
    text="Which files implement the survey stage?",
    criterion="the survey stage exists",
    command_budget=8,
)
PLAN = SurveyPlan(
    issue_number=3,
    repo="owner/progettare",
    structure=RepoStructure(
        tree=("cli.py",),
        touched=(),
        entry_points=("cli.py",),
        tests=(),
    ),
    questions=(QUESTION,),
    command_budget=8,
    partial_reason=None,
)
USAGE = NareUsage(input_tokens=10, output_tokens=5, total_tokens=15)
VALID_OUTPUT = json.dumps(
    {
        "commands": ["cat README.md", "grep -rn survey src"],
        "findings": "cli.py loads the survey stage.",
    }
)


def make_result(**overrides: Any) -> NareResult:
    """One canned nare result, carrying the adapter's real field names."""
    document: dict[str, Any] = {
        "status": "done",
        "stop_reason": None,
        "usage": USAGE,
        "output": None,
    }
    document.update(overrides)
    return NareResult(**document)


class CannedRunner:
    """The NareRunner seam: records the argv it was given, replays a result."""

    def __init__(self, result: NareResult) -> None:
        self.result = result
        self.argv: tuple[str, ...] | None = None
        self.calls = 0

    def run(self, argv: tuple[str, ...]) -> NareResult:
        self.calls += 1
        self.argv = argv
        return self.result


class ErrorRunner:
    """The NareRunner seam where nare itself fails loudly."""

    def run(self, argv: tuple[str, ...]) -> NareResult:
        raise NareError("nare is not installed or not on PATH")


def ask(runner: Any, tmp_path: Path) -> SessionOutcome:
    """One call to answer_one_question with the shared plan and question."""
    return answer_one_question(
        plan=PLAN,
        question=QUESTION,
        runner=runner,
        config=CONFIG,
        run_dir=tmp_path,
        repo_path="/repo",
        budget=400,
    )


def collect_keywords(node: Any) -> set[str]:
    keywords: set[str] = set()
    if isinstance(node, dict):
        keywords.update(str(key) for key in node)
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for subschema in value.values():
                    keywords |= collect_keywords(subschema)
            else:
                keywords |= collect_keywords(value)
    elif isinstance(node, list):
        for value in node:
            keywords |= collect_keywords(value)
    return keywords


def assert_unusable(outcome: SessionOutcome) -> None:
    assert outcome.answer is None
    assert outcome.usage == USAGE
    assert outcome.stop_reason is not None
    assert outcome.stop_reason.startswith("unusable_answer")


def test_answer_one_question_passes_the_full_session_shape_to_the_runner(
    tmp_path: Path,
) -> None:
    runner = CannedRunner(make_result(output=VALID_OUTPUT))
    ask(runner, tmp_path)
    assert runner.calls == 1
    assert runner.argv == session_argv(
        prompt=QUESTION.text,
        system=SURVEY_SYSTEM_PROMPT,
        root="/repo",
        rail=RAIL,
        schema=str(tmp_path / "q1.schema.json"),
        budget_tokens=400,
        session_path=str(tmp_path / "q1-session.json"),
    )


def test_the_written_schema_uses_only_nare_supported_keywords(
    tmp_path: Path,
) -> None:
    ask(CannedRunner(make_result(output=VALID_OUTPUT)), tmp_path)
    schema_path = tmp_path / "q1.schema.json"
    assert schema_path.is_file()
    text = schema_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    document = json.loads(text)
    assert collect_keywords(document) <= {
        "type",
        "properties",
        "required",
        "items",
        "additionalProperties",
    }
    assert document["type"] == "object"
    assert set(document["required"]) == {"commands", "findings"}
    assert document["properties"]["commands"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert document["properties"]["findings"] == {"type": "string"}


def test_a_done_result_with_a_valid_output_builds_the_answer(tmp_path: Path) -> None:
    outcome = ask(CannedRunner(make_result(output=VALID_OUTPUT)), tmp_path)
    assert outcome.answer == SurveyAnswer(
        question=1,
        commands=("cat README.md", "grep -rn survey src"),
        findings="cli.py loads the survey stage.",
    )
    assert outcome.usage == USAGE
    assert outcome.stop_reason is None


def test_a_budget_stop_is_recorded_data(tmp_path: Path) -> None:
    runner = CannedRunner(
        make_result(status="error", stop_reason="budget", output=None)
    )
    outcome = ask(runner, tmp_path)
    assert outcome.answer is None
    assert outcome.stop_reason == "budget"
    assert outcome.usage == USAGE


def test_output_that_is_not_json_yields_an_unusable_answer(tmp_path: Path) -> None:
    outcome = ask(CannedRunner(make_result(output="nare: not json")), tmp_path)
    assert_unusable(outcome)


def test_output_that_is_not_an_object_yields_an_unusable_answer(
    tmp_path: Path,
) -> None:
    outcome = ask(CannedRunner(make_result(output='["not an object"]')), tmp_path)
    assert_unusable(outcome)


@pytest.mark.parametrize(
    "payload",
    [
        '{"commands": ["ls /repo"]}',
        '{"findings": "only findings"}',
    ],
)
def test_output_that_lacks_keys_yields_an_unusable_answer(
    payload: str, tmp_path: Path
) -> None:
    outcome = ask(CannedRunner(make_result(output=payload)), tmp_path)
    assert_unusable(outcome)


def test_blank_findings_yield_an_unusable_answer(tmp_path: Path) -> None:
    payload = json.dumps({"commands": ["ls /repo"], "findings": "   "})
    outcome = ask(CannedRunner(make_result(output=payload)), tmp_path)
    assert_unusable(outcome)


@pytest.mark.parametrize(
    "payload",
    [
        '{"commands": "ls /repo", "findings": "f"}',
        '{"commands": [1, 2], "findings": "f"}',
        '{"commands": ["ls /repo"], "findings": 7}',
    ],
)
def test_payload_shape_mismatches_yield_an_unusable_answer(
    payload: str, tmp_path: Path
) -> None:
    outcome = ask(CannedRunner(make_result(output=payload)), tmp_path)
    assert_unusable(outcome)


def test_a_done_result_without_a_payload_yields_an_unusable_answer(
    tmp_path: Path,
) -> None:
    outcome = ask(CannedRunner(make_result(output=None)), tmp_path)
    assert_unusable(outcome)


def test_a_nare_error_from_the_runner_propagates(tmp_path: Path) -> None:
    with pytest.raises(NareError, match="not on PATH"):
        ask(ErrorRunner(), tmp_path)


def test_fair_share_divides_and_rolls_nothing_over() -> None:
    assert fair_share(1200, 3) == 400
    assert fair_share(10, 3) == 3


def test_fair_share_floors_at_one_while_budget_remains() -> None:
    assert fair_share(1, 2) == 1
    assert fair_share(5, 10) == 1


def test_fair_share_is_zero_once_the_budget_is_gone() -> None:
    assert fair_share(0, 3) == 0
    assert fair_share(-40, 3) == 0
