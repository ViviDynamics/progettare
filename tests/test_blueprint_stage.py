"""Tests for the blueprint stage: the session loop and its loud failures.

Every test runs offline: the NareRunner seam is a fake that records the
argv it was given and replays canned NareResults, so no nare binary and
no network are involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from progettare.blueprint.stage import (
    _MAX_PROMPT_BYTES,
    BLUEPRINT_SCHEMA,
    BLUEPRINT_SYSTEM_PROMPT,
    BlueprintStageError,
    run_blueprint_stage,
    validate_blueprint,
)
from progettare.config import Config, ModelRail
from progettare.survey.nare import NareError, NareResult, NareUsage

RAIL = ModelRail(
    provider="openai", model="gpt-blueprint", base_url="http://127.0.0.1:8000"
)
CONFIG = Config(
    survey_max_questions=5,
    survey_per_question_command_budget=8,
    budget_survey_stage_tokens=1200,
    budget_blueprint_stage_tokens=600,
    budget_run_max_tokens=10000,
    size_single_turn_max_milestones=8,
    size_documenter_min_topics=0,
    survey_rail=RAIL,
    blueprint_rail=RAIL,
)
USAGE = NareUsage(input_tokens=10, output_tokens=5, total_tokens=15)
SPENT_ALL = NareUsage(input_tokens=600, output_tokens=600, total_tokens=1200)
VALID_OUTPUT = json.dumps(
    {
        "milestones": [
            {
                "title": "Blueprint stage",
                "changes": ["Validate the session payload", "Write the artifact"],
            }
        ],
        "data_model": ["one milestone list in order"],
        "interfaces": ["run_blueprint_stage(...)"],
        "risks": ["schema drift"],
        "testable_criteria": ["a valid payload writes blueprint.json"],
        "documentation_topics": ["the blueprint contract"],
    }
)
INVALID_OUTPUT = json.dumps({"milestones": []})


def make_result(**overrides: Any) -> NareResult:
    document: dict[str, Any] = {
        "status": "done",
        "stop_reason": None,
        "usage": USAGE,
        "output": VALID_OUTPUT,
    }
    document.update(overrides)
    return NareResult(**document)


class CannedRunner:
    """The NareRunner seam: records argvs, replays results in order."""

    def __init__(self, *results: NareResult) -> None:
        self.results = list(results)
        self.argvs: list[tuple[str, ...]] = []
        self.calls = 0

    def run(self, argv: tuple[str, ...]) -> NareResult:
        self.calls += 1
        self.argvs.append(argv)
        return self.results.pop(0)


class ErrorRunner:
    """The NareRunner seam where nare itself fails loudly."""

    def run(self, argv: tuple[str, ...]) -> NareResult:
        raise NareError("nare is not installed or not on PATH")


def make_intake() -> dict[str, Any]:
    return {
        "issue": {"number": 4, "title": "blueprint stage"},
        "acceptance_criteria": ["A schema-validated blueprint"],
        "clarifications": [{"question": "size?", "answer": "small"}],
        "blocked_questions": [],
    }


def make_survey() -> dict[str, Any]:
    return {
        "version": 1,
        "structure": {"tree": ["src/x.py"], "touched": [], "tests": []},
        "answers": [{"question": 1, "commands": [], "findings": "x.py is the file."}],
        "partial_reason": None,
    }


def run_stage(runner: Any, tmp_path: Path, survey: dict[str, Any] | None = None) -> Any:
    return run_blueprint_stage(
        intake=make_intake(),
        survey=survey if survey is not None else make_survey(),
        runner=runner,
        config=CONFIG,
        run_dir=tmp_path,
        repo_path="/tmp/repo",
        written_at="2026-10-05T00:00:00Z",
    )


def flag(argv: tuple[str, ...], name: str) -> str:
    return argv[argv.index(name) + 1]


def test_valid_session_writes_the_stamped_artifact(tmp_path: Path) -> None:
    result = run_stage(CannedRunner(make_result()), tmp_path)
    document = json.loads(result.path.read_text(encoding="utf-8"))
    assert document["artifact"] == "blueprint"
    assert document["artifact_version"] == 1
    assert document["written_at"] == "2026-10-05T00:00:00Z"
    assert document["version"] == 1
    assert document["milestones"] == [
        {
            "title": "Blueprint stage",
            "changes": ["Validate the session payload", "Write the artifact"],
        }
    ]
    assert result.reasked is False
    assert result.usage is not None
    assert result.usage.total_tokens == 15
    assert result.blueprint.milestones[0].title == "Blueprint stage"


def test_session_argv_carries_the_stage_contract(tmp_path: Path) -> None:
    runner = CannedRunner(make_result())
    run_stage(runner, tmp_path)
    argv = runner.argvs[0]
    assert argv[0] == "nare"
    assert argv[1] == "run"
    prompt = argv[2]
    assert "Issue #4: blueprint stage" in prompt
    assert "A schema-validated blueprint" in prompt
    assert "x.py is the file." in prompt
    assert BLUEPRINT_SYSTEM_PROMPT in argv
    assert flag(argv, "--tools") == "read"
    schema_path = Path(flag(argv, "--schema"))
    assert schema_path == tmp_path / "blueprint.schema.json"
    assert json.loads(schema_path.read_text(encoding="utf-8")) == BLUEPRINT_SCHEMA
    assert flag(argv, "--budget-tokens") == "600"
    assert Path(flag(argv, "--session")) == tmp_path / "blueprint-session.json"
    assert flag(argv, "--provider") == "openai"
    assert flag(argv, "--model") == "gpt-blueprint"
    assert flag(argv, "--root") == "/tmp/repo"


def test_reask_on_invalid_output(tmp_path: Path) -> None:
    runner = CannedRunner(
        make_result(output=INVALID_OUTPUT), make_result(output=VALID_OUTPUT)
    )
    result = run_stage(runner, tmp_path)
    assert runner.calls == 2
    assert result.reasked is True
    assert json.loads(result.path.read_text(encoding="utf-8"))["milestones"]
    reask_argv = runner.argvs[1]
    assert flag(reask_argv, "--budget-tokens") == "585"
    assert (
        Path(flag(reask_argv, "--session")) == tmp_path / "blueprint-reask-session.json"
    )
    prompt = reask_argv[2]
    assert "Your previous answer was rejected" in prompt
    assert "milestones is an empty array" in prompt


def test_invalid_after_reask_fails_loudly_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    runner = CannedRunner(
        make_result(output=INVALID_OUTPUT), make_result(output=INVALID_OUTPUT)
    )
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    message = str(raised.value)
    assert "blueprint stage" in message
    assert "invalid" in message
    assert "milestones is an empty array" in message
    assert runner.calls == 2
    assert not (tmp_path / "blueprint.json").exists()


def test_no_budget_for_reask_fails_loudly(tmp_path: Path) -> None:
    runner = CannedRunner(make_result(output=INVALID_OUTPUT, usage=SPENT_ALL))
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    message = str(raised.value)
    assert "blueprint stage" in message
    assert "no budget remains for the bounded re-ask" in message
    assert "milestones is an empty array" in message
    assert runner.calls == 1
    assert not (tmp_path / "blueprint.json").exists()


def test_budget_exhaustion_in_the_first_session_fails_the_run(
    tmp_path: Path,
) -> None:
    runner = CannedRunner(make_result(output=None, stop_reason="budget"))
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    assert "blueprint stage" in str(raised.value)
    assert "exhausted its token budget" in str(raised.value)
    assert runner.calls == 1
    assert not (tmp_path / "blueprint.json").exists()


def test_budget_exhaustion_in_the_reask_fails_the_run(tmp_path: Path) -> None:
    runner = CannedRunner(
        make_result(output=INVALID_OUTPUT),
        make_result(output=None, stop_reason="budget"),
    )
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    assert "blueprint stage" in str(raised.value)
    assert "exhausted its token budget" in str(raised.value)
    assert runner.calls == 2
    assert not (tmp_path / "blueprint.json").exists()


def test_missing_payload_after_reask_fails_loudly(tmp_path: Path) -> None:
    runner = CannedRunner(
        make_result(output=INVALID_OUTPUT), make_result(output=None, stop_reason=None)
    )
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    message = str(raised.value)
    assert "blueprint stage" in message
    assert "ended without a blueprint payload" in message
    assert not (tmp_path / "blueprint.json").exists()


def test_nare_faults_propagate(tmp_path: Path) -> None:
    with pytest.raises(NareError):
        run_stage(ErrorRunner(), tmp_path)
    assert not (tmp_path / "blueprint.json").exists()


def test_prompt_bounding_drops_findings_from_the_end(tmp_path: Path) -> None:
    survey = make_survey()
    survey["answers"] = [
        {
            "question": number,
            "commands": [],
            "findings": f"finding {number} " + "x" * 2000,
        }
        for number in range(1, 120)
    ]
    runner = CannedRunner(make_result())
    run_stage(runner, tmp_path, survey)
    prompt = runner.argvs[0][2]
    assert len(prompt.encode("utf-8")) <= _MAX_PROMPT_BYTES
    assert "survey finding(s) omitted to fit the prompt budget" in prompt
    assert "finding 1 " in prompt
    assert "finding 119 " not in prompt


def test_partial_reason_reaches_the_prompt(tmp_path: Path) -> None:
    survey = make_survey()
    survey["partial_reason"] = "stage token budget exhausted: question(s) 2"
    runner = CannedRunner(make_result())
    run_stage(runner, tmp_path, survey)
    assert "stage token budget exhausted: question(s) 2" in runner.argvs[0][2]


def test_oversized_header_truncates_but_keeps_the_task_and_errors(
    tmp_path: Path,
) -> None:
    intake = make_intake()
    intake["acceptance_criteria"] = ["criterion " + "x" * 3000 for _ in range(50)]
    runner = CannedRunner(
        make_result(output=INVALID_OUTPUT), make_result(output=VALID_OUTPUT)
    )
    result = run_blueprint_stage(
        intake=intake,
        survey=make_survey(),
        runner=runner,
        config=CONFIG,
        run_dir=tmp_path,
        repo_path="/tmp/repo",
        written_at="2026-10-05T00:00:00Z",
    )
    first_prompt = runner.argvs[0][2]
    assert len(first_prompt.encode("utf-8")) <= _MAX_PROMPT_BYTES
    assert "[header truncated to fit the prompt budget]" in first_prompt
    assert "Sequence the milestones" in first_prompt
    reask_prompt = runner.argvs[1][2]
    assert len(reask_prompt.encode("utf-8")) <= _MAX_PROMPT_BYTES
    assert "milestones is an empty array" in reask_prompt
    assert result.reasked is True


def test_oversized_tree_is_marked_and_the_prompt_stays_capped(
    tmp_path: Path,
) -> None:
    survey = make_survey()
    survey["structure"]["tree"] = ["f" * 400 for _ in range(300)]
    runner = CannedRunner(make_result())
    run_stage(runner, tmp_path, survey)
    prompt = runner.argvs[0][2]
    assert len(prompt.encode("utf-8")) <= _MAX_PROMPT_BYTES
    assert "[repository structure omitted to fit the prompt budget]" in prompt
    assert "Sequence the milestones" in prompt


def test_reask_errors_too_large_for_the_budget_fail_loudly(
    tmp_path: Path,
) -> None:
    bad = json.dumps(
        {
            "milestones": [{"title": "t", "changes": ["c"]}],
            "data_model": [],
            "interfaces": [],
            "risks": list(range(5000)),
            "testable_criteria": [],
            "documentation_topics": [],
        }
    )
    runner = CannedRunner(make_result(output=bad))
    with pytest.raises(BlueprintStageError) as raised:
        run_stage(runner, tmp_path)
    assert "blueprint stage" in str(raised.value)
    assert "mandatory content alone exceeds" in str(raised.value)
    assert runner.calls == 1
    assert not (tmp_path / "blueprint.json").exists()


VALID: dict[str, Any] = {
    "milestones": [{"title": "t", "changes": ["c"]}],
    "data_model": [],
    "interfaces": [],
    "risks": [],
    "testable_criteria": [],
    "documentation_topics": [],
}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"milestones": []}, ("milestones is an empty array",)),
        (["milestones"], ("the blueprint payload is not a JSON object",)),
        (None, ("the blueprint payload is not a JSON object",)),
        (
            {"milestones": [], "unknown": 1},
            ("unknown key(s): unknown", "milestones is an empty array"),
        ),
        (
            {"milestones": [{"title": "t", "changes": ["c"]}, "nope"]},
            ("milestones[1] is not an object",),
        ),
        (
            {"milestones": [{"title": "  ", "changes": ["c"]}]},
            ("milestones[0].title is not a nonempty string",),
        ),
        (
            {"milestones": [{"title": "t", "changes": []}]},
            ("milestones[0].changes is not a nonempty array",),
        ),
        (
            {"milestones": [{"title": "t", "changes": ["ok", "  "]}]},
            ("milestones[0].changes[1] is not a nonempty string",),
        ),
        (
            {"milestones": [{"title": "t", "changes": ["c"], "extra": 1}]},
            ("milestones[0] carries unknown key(s): extra",),
        ),
        ({"milestones": "no"}, ("milestones is not an array",)),
        ({"milestones": []}, ("missing key(s)",)),
    ],
)
def test_validate_blueprint_enforces_the_schema(
    payload: Any, expected: tuple[str, ...]
) -> None:
    errors = validate_blueprint(payload)
    for reason in expected:
        assert any(reason in error for error in errors), (reason, errors)


def test_validate_blueprint_accepts_a_well_typed_payload() -> None:
    assert validate_blueprint(VALID) == ()
    document = {
        **VALID,
        "milestones": [{"title": "t", "changes": ["c", "d"]}],
        "risks": ["r"],
    }
    assert validate_blueprint(document) == ()
