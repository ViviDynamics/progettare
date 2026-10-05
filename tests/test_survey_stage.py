"""Tests for the survey stage: the single-session layer and the loop.

Every test runs offline: the NareRunner seam is a fake that records the
argv it was given and replays a canned NareResult, so no nare binary and
no network are involved.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from progettare.config import Config, ModelRail
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.survey.artifact import (
    SURVEY_RECORD_VERSION,
    SurveyAnswer,
    SurveyRecordError,
)
from progettare.survey.nare import NareError, NareResult, NareUsage, session_argv
from progettare.survey.questions import (
    RepoStructure,
    SurveyPlan,
    SurveyQuestion,
)
from progettare.survey.stage import (
    SURVEY_SYSTEM_PROMPT,
    SessionOutcome,
    SurveyStageResult,
    answer_one_question,
    fair_share,
    run_survey_stage,
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


def test_fair_share_is_zero_when_no_questions_remain() -> None:
    assert fair_share(1200, 0) == 0
    assert fair_share(1200, -1) == 0


class StageRunner:
    """The NareRunner seam for the stage: one canned result per session."""

    def __init__(self, results: Sequence[NareResult]) -> None:
        self.results = list(results)
        self.argvs: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> NareResult:
        self.argvs.append(argv)
        return self.results[len(self.argvs) - 1]


def stage_plan(
    numbers: tuple[int, ...],
    *,
    partial_reason: str | None = None,
    command_budget: int = 8,
) -> SurveyPlan:
    """A plan with one question per number, each with the given budget."""
    questions = tuple(
        SurveyQuestion(
            number=number,
            text=f"Question {number}: which files implement the survey stage?",
            criterion=f"criterion {number}",
            command_budget=command_budget,
        )
        for number in numbers
    )
    return SurveyPlan(
        issue_number=3,
        repo="owner/progettare",
        structure=RepoStructure(
            tree=("cli.py",),
            touched=(),
            entry_points=("cli.py",),
            tests=(),
        ),
        questions=questions,
        command_budget=command_budget,
        partial_reason=partial_reason,
    )


def run_stage(
    runner: Any,
    tmp_path: Path,
    plan: SurveyPlan | None = None,
    written_at: str = "20261005T000000Z",
) -> SurveyStageResult:
    """One call to run_survey_stage with the shared config."""
    return run_survey_stage(
        plan=plan if plan is not None else stage_plan((1,)),
        runner=runner,
        config=CONFIG,
        run_dir=tmp_path,
        repo_path="/repo",
        written_at=written_at,
    )


def read_artifact(tmp_path: Path) -> dict[str, Any]:
    """The parsed survey.json, after asserting it exists."""
    path = tmp_path / "survey.json"
    assert path.is_file()
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def test_a_clean_stage_records_every_answer_and_stamps_the_artifact(
    tmp_path: Path,
) -> None:
    runner = StageRunner([make_result(output=VALID_OUTPUT) for _ in range(3)])
    result = run_stage(runner, tmp_path, stage_plan((1, 2, 3)))
    assert isinstance(result, SurveyStageResult)
    assert result.path == tmp_path / "survey.json"
    document = read_artifact(tmp_path)
    assert document["artifact"] == "survey"
    assert document["artifact_version"] == ARTIFACT_VERSION
    assert document["progettare"] == PROGETTARE_VERSION
    assert document["written_at"] == "20261005T000000Z"
    assert document["version"] == SURVEY_RECORD_VERSION
    assert document["partial_reason"] is None
    assert document["answers"] == [
        {
            "question": number,
            "commands": ["cat README.md", "grep -rn survey src"],
            "findings": "cli.py loads the survey stage.",
        }
        for number in (1, 2, 3)
    ]
    assert result.answers == tuple(
        SurveyAnswer(
            question=number,
            commands=("cat README.md", "grep -rn survey src"),
            findings="cli.py loads the survey stage.",
        )
        for number in (1, 2, 3)
    )
    assert result.usage == NareUsage(input_tokens=30, output_tokens=15, total_tokens=45)
    assert result.partial_reasons == ()
    assert len(runner.argvs) == 3


def test_the_result_names_the_sessions_the_stage_ran(tmp_path: Path) -> None:
    runner = StageRunner([make_result(output=VALID_OUTPUT) for _ in range(3)])
    result = run_stage(runner, tmp_path, stage_plan((1, 2, 3)))
    assert result.sessions == (
        "q1-session.json",
        "q2-session.json",
        "q3-session.json",
    )


def test_the_plan_partial_reason_flows_into_the_record(tmp_path: Path) -> None:
    reason = (
        "question cap reached: survey.max_questions is 1, 2 question(s) not formulated"
    )
    runner = StageRunner([make_result(output=VALID_OUTPUT)])
    result = run_stage(runner, tmp_path, stage_plan((1,), partial_reason=reason))
    assert result.partial_reasons == (reason,)
    assert read_artifact(tmp_path)["partial_reason"] == reason


def test_a_budget_stop_on_one_question_continues_the_stage(tmp_path: Path) -> None:
    runner = StageRunner(
        [
            make_result(output=VALID_OUTPUT),
            make_result(status="error", stop_reason="budget", output=None),
            make_result(output=VALID_OUTPUT),
        ]
    )
    result = run_stage(runner, tmp_path, stage_plan((1, 2, 3)))
    assert len(runner.argvs) == 3
    assert [answer.question for answer in result.answers] == [1, 3]
    assert result.partial_reasons == ("question 2: budget",)
    document = read_artifact(tmp_path)
    assert document["partial_reason"] == "question 2: budget"
    assert [answer["question"] for answer in document["answers"]] == [1, 3]


def test_a_plan_reason_and_a_stage_reason_are_combined_in_the_record(
    tmp_path: Path,
) -> None:
    reason = (
        "question cap reached: survey.max_questions is 2, 1 question(s) not formulated"
    )
    plan = stage_plan((1, 2), partial_reason=reason)
    runner = StageRunner(
        [
            make_result(output=VALID_OUTPUT),
            make_result(status="error", stop_reason="budget", output=None),
        ]
    )
    result = run_stage(runner, tmp_path, plan)
    assert result.partial_reasons == (reason, "question 2: budget")
    assert read_artifact(tmp_path)["partial_reason"] == (
        f"{reason}; question 2: budget"
    )


def test_stage_exhaustion_skips_the_rest_and_still_writes(tmp_path: Path) -> None:
    exhausted = NareUsage(input_tokens=1200, output_tokens=0, total_tokens=1200)
    runner = StageRunner(
        [
            make_result(output=VALID_OUTPUT, usage=exhausted),
            make_result(output=VALID_OUTPUT),
        ]
    )
    result = run_stage(runner, tmp_path, stage_plan((1, 2, 3)))
    assert len(runner.argvs) == 1
    assert [answer.question for answer in result.answers] == [1]
    assert result.partial_reasons == (
        "stage token budget exhausted: question(s) 2, 3 not attempted",
    )
    document = read_artifact(tmp_path)
    assert document["partial_reason"] == (
        "stage token budget exhausted: question(s) 2, 3 not attempted"
    )
    assert [answer["question"] for answer in document["answers"]] == [1]


def test_a_session_without_usage_deducts_nothing_and_sums_nothing(
    tmp_path: Path,
) -> None:
    runner = StageRunner(
        [
            make_result(output=VALID_OUTPUT, usage=None),
            make_result(output=VALID_OUTPUT),
        ]
    )
    result = run_stage(runner, tmp_path, stage_plan((1, 2)))
    assert result.usage == USAGE
    second_argv = runner.argvs[1]
    budget_index = second_argv.index("--budget-tokens")
    assert second_argv[budget_index + 1] == "1200"


def test_an_answer_beyond_the_command_budget_fails_the_stage_loudly(
    tmp_path: Path,
) -> None:
    over_budget = json.dumps(
        {"commands": ["cat a", "cat b", "cat c"], "findings": "found"}
    )
    runner = StageRunner([make_result(output=over_budget)])
    with pytest.raises(SurveyRecordError, match="budget of 2"):
        run_stage(runner, tmp_path, stage_plan((1,), command_budget=2))


def test_a_nare_error_from_a_session_propagates(tmp_path: Path) -> None:
    with pytest.raises(NareError, match="not on PATH"):
        run_stage(ErrorRunner(), tmp_path, stage_plan((1,)))


def test_the_written_at_stamp_lands_verbatim(tmp_path: Path) -> None:
    runner = StageRunner([make_result(output=VALID_OUTPUT)])
    run_stage(runner, tmp_path, written_at="20261005T123456Z")
    assert read_artifact(tmp_path)["written_at"] == "20261005T123456Z"


def test_the_package_exports_the_stage_api() -> None:
    import progettare.survey

    for name in (
        "SessionOutcome",
        "SurveyStageResult",
        "answer_one_question",
        "fair_share",
        "run_survey_stage",
    ):
        assert name in progettare.survey.__all__
    assert progettare.survey.run_survey_stage is run_survey_stage
    assert "SURVEY_SYSTEM_PROMPT" not in progettare.survey.__all__
    assert "ANSWER_SCHEMA" not in progettare.survey.__all__
