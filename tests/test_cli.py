"""Tests for the CLI: the blueprint verb, its exit codes, and its stdout.

Every test runs offline: the GitHub call is injected as an already-loaded
issue, the nare subprocess seam is a canned runner, and the orchestration
against the real stages is the thing under test.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from dataclasses import replace
from typing import Any

import pytest

from progettare.cli import BlueprintOutcome, main, run_blueprint
from progettare.config import Config, ModelRail
from progettare.github import Issue, IssueClosedError, IssueComment
from progettare.issue_ref import parse_issue_ref
from progettare.survey.nare import NareError, NareResult, NareUsage

RAIL = ModelRail(
    provider="openai", model="gpt-survey", base_url="http://127.0.0.1:8000"
)
CONFIG_YAML = """\
survey:
  max_questions: 5
  per_question_command_budget: 8
budgets:
  survey_stage_tokens: 12000
  blueprint_stage_tokens: 12000
  run_max_tokens: 50000
models:
  default:
    provider: openai
    model: gpt-survey
  overrides: {}
size:
  single_turn_max_milestones: 8
  documenter_min_topics: 1
"""
CONFIG = Config(
    survey_max_questions=5,
    survey_per_question_command_budget=8,
    budget_survey_stage_tokens=12000,
    budget_blueprint_stage_tokens=12000,
    budget_run_max_tokens=50000,
    size_single_turn_max_milestones=8,
    size_documenter_min_topics=1,
    survey_rail=RAIL,
    blueprint_rail=RAIL,
)
USAGE = NareUsage(input_tokens=10, output_tokens=5, total_tokens=15)
SURVEY_OUTPUT = json.dumps(
    {"commands": ["cat README.md"], "findings": "cli.py is the entry point."}
)
BLUEPRINT_OUTPUT = json.dumps(
    {
        "milestones": [{"title": "t", "changes": ["c"]}],
        "data_model": [],
        "interfaces": [],
        "risks": [],
        "testable_criteria": ["works"],
        "documentation_topics": ["how"],
    }
)


def make_issue(body: str = "Acceptance:\n- Implement X") -> Issue:
    ref = parse_issue_ref("ViviDynamics/progettare#1")
    return Issue(
        owner=ref.owner,
        repo=ref.repo,
        number=ref.number,
        title="M1: cli and release packaging",
        body=body,
        state="OPEN",
        url="https://github.com/ViviDynamics/progettare/issues/9",
        comments=(IssueComment(author="a", body="b", created_at=""),),
    )


class CannedRunner:
    """The NareRunner seam: one canned result per session, in order."""

    def __init__(self, results: list[NareResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def run(self, argv: tuple[str, ...]) -> NareResult:
        self.calls += 1
        if self.calls > len(self.results):
            raise NareError("no canned result left")
        return self.results[self.calls - 1]


def canned_result(output: str, **overrides: Any) -> NareResult:
    document: dict[str, Any] = {
        "status": "done",
        "stop_reason": None,
        "usage": USAGE,
        "output": output,
    }
    document.update(overrides)
    return NareResult(**document)


def make_runner() -> CannedRunner:
    return CannedRunner(
        [
            canned_result(SURVEY_OUTPUT),
            canned_result(BLUEPRINT_OUTPUT),
        ]
    )


def make_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    return repo


def run(
    tmp_path: pathlib.Path,
    issue: Issue,
    runner: Any,
    config: Config = CONFIG,
    refresher: Any = None,
) -> BlueprintOutcome:
    repo = make_repo(tmp_path)
    return run_blueprint(
        parse_issue_ref("ViviDynamics/progettare#9"),
        str(repo),
        config,
        tmp_path / "runs",
        runner,
        issue,
        "20261005T000000Z",
        refresher if refresher is not None else (lambda: None),
    )


def test_a_complete_run_writes_the_whole_artifact_set(
    tmp_path: pathlib.Path,
) -> None:
    outcome = run(tmp_path, make_issue(), make_runner())
    assert outcome.status == "complete"
    assert outcome.failing_stage is None
    names = sorted(path.name for path in outcome.run_dir.iterdir())
    assert names == [
        "blueprint.json",
        "blueprint.schema.json",
        "briefs",
        "intake.json",
        "q1.schema.json",
        "run.json",
        "size.json",
        "survey.json",
    ]
    manifest: dict[str, Any] = json.loads(
        (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert manifest["failing_stage"] is None
    assert manifest["stages"]["survey"]["sessions"] == ["q1-session.json"]
    assert manifest["stages"]["blueprint"]["sessions"] == ["blueprint-session.json"]
    assert manifest["stages"]["size"]["usage"] is None
    size: dict[str, Any] = json.loads(
        (outcome.run_dir / "size.json").read_text(encoding="utf-8")
    )
    assert size["classification"] == "single_turn"
    assert (outcome.run_dir / "briefs" / "documenter.json").is_file()


def test_a_blocked_intake_spends_no_model_calls(tmp_path: pathlib.Path) -> None:
    runner = make_runner()
    outcome = run(tmp_path, make_issue("Acceptance:\n- TBD"), runner)
    assert outcome.status == "blocked"
    assert outcome.failing_stage == "intake"
    assert runner.calls == 0
    manifest: dict[str, Any] = json.loads(
        (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "blocked"
    assert manifest["failing_stage"] == "intake"
    assert manifest["failing_reason"] == outcome.detail
    assert "acceptance criteria" in manifest["failing_reason"].lower()


def test_a_failed_stage_writes_its_ledger_and_names_itself(
    tmp_path: pathlib.Path,
) -> None:
    outcome = run(tmp_path, make_issue(), CannedRunner([]))
    assert outcome.status == "failed"
    assert outcome.failing_stage == "survey"
    manifest: dict[str, Any] = json.loads(
        (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert manifest["failing_stage"] == "survey"
    assert manifest["failing_reason"] == "no canned result left"
    assert manifest["stages"]["survey"]["sessions"] == ["q1-session.json"]
    assert manifest["stages"]["survey"]["usage"] is None


def test_a_partial_survey_blocks_at_survey_and_publishes_no_blueprint(
    tmp_path: pathlib.Path,
) -> None:
    config = replace(CONFIG, budget_survey_stage_tokens=5)
    runner = CannedRunner([canned_result(SURVEY_OUTPUT)])
    outcome = run(
        tmp_path, make_issue("Acceptance:\n- first\n- second"), runner, config
    )
    assert outcome.status == "blocked"
    assert outcome.failing_stage == "survey"
    assert runner.calls == 1
    manifest: dict[str, Any] = json.loads(
        (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "blocked"
    assert manifest["failing_stage"] == "survey"
    assert "budget exhausted" in manifest["failing_reason"]
    assert manifest["failing_reason"] == outcome.detail
    names = [path.name for path in outcome.run_dir.iterdir()]
    assert "blueprint.json" not in names


def test_an_invalid_blueprint_after_its_reask_fails_without_publishing(
    tmp_path: pathlib.Path,
) -> None:
    runner = CannedRunner(
        [
            canned_result(SURVEY_OUTPUT),
            canned_result("not json at all"),
            canned_result("still not json"),
        ]
    )
    outcome = run(tmp_path, make_issue(), runner)
    assert outcome.status == "failed"
    assert outcome.failing_stage == "blueprint"
    manifest: dict[str, Any] = json.loads(
        (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert manifest["failing_stage"] == "blueprint"
    assert "the re-asked blueprint payload is invalid" in manifest["failing_reason"]
    assert manifest["failing_reason"] == outcome.detail
    names = [path.name for path in outcome.run_dir.iterdir()]
    assert "blueprint.json" not in names
    assert "blueprint.schema.json" in names


def test_a_midrun_closure_discards_the_run_directory(
    tmp_path: pathlib.Path,
) -> None:
    calls = 0

    def refresher() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IssueClosedError("the issue closed mid-run")

    outcome = run(tmp_path, make_issue(), make_runner(), refresher=refresher)
    assert outcome.status == "failed"
    assert outcome.failing_stage == "blueprint"
    assert outcome.detail is not None
    assert "closed" in outcome.detail
    assert not outcome.run_dir.exists()


def test_the_refresher_runs_before_every_publishing_stage(
    tmp_path: pathlib.Path,
) -> None:
    calls = 0

    def refresher() -> None:
        nonlocal calls
        calls += 1

    outcome = run(tmp_path, make_issue(), make_runner(), refresher=refresher)
    assert outcome.status == "complete"
    assert calls == 4


def test_exit_codes_distinguish_complete_blocked_and_failed(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(tmp_path)
    (tmp_path / "progettare.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    issue = make_issue()
    monkeypatch.setattr("progettare.cli.load_issue", lambda ref: issue)
    monkeypatch.setattr("progettare.cli.ensure_issue_open", lambda ref: None)
    monkeypatch.setattr("progettare.cli.NareSubprocessRunner", lambda: make_runner())
    argv = [
        "blueprint",
        "--issue",
        "https://github.com/ViviDynamics/progettare/issues/9",
        "--repo",
        str(repo),
        "--config",
        str(tmp_path / "progettare.yaml"),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]
    assert main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "complete"

    blocked = make_issue("Acceptance:\n- TBD")
    monkeypatch.setattr("progettare.cli.load_issue", lambda ref: blocked)
    assert main(argv) == 2
    assert "blocked" in capsys.readouterr().err
    assert capsys.readouterr().out == ""

    monkeypatch.setattr("progettare.cli.load_issue", lambda ref: issue)
    monkeypatch.setattr(
        "progettare.cli.NareSubprocessRunner",
        lambda: CannedRunner([]),
    )
    assert main(argv) == 1
    assert "failed" in capsys.readouterr().err
    assert capsys.readouterr().out == ""


def test_version_prints_the_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    printed = capsys.readouterr().out.strip()
    assert printed
    assert printed != "0.0.0+unknown"
