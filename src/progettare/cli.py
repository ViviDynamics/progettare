"""The command line: one verb today, room for the verbs to come.

``progettare blueprint`` runs the whole planning ceremony for one issue:
intake, survey, blueprint, sizing, briefs, and the manifest, writing
every artifact into the run directory outside the surveyed repository.
Exit codes distinguish the three run outcomes a caller scripts against:
0 complete, 1 failed, 2 blocked. JSON lands on stdout only when the run
completed, so a caller never parses prose out of a partial answer.

The orchestrator is pure wiring: the stages own their budgets and their
errors, the manifest names the stage and the reason that stopped a
partial run, and every model call goes through the nare CLI as a
subprocess. The issue is re-checked before each publishing stage, so a
run whose issue closes mid-flight aborts, discards its state, and posts
nothing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from progettare.blueprint.size import classify_size, write_size
from progettare.blueprint.slices import slice_briefs, write_briefs
from progettare.blueprint.stage import run_blueprint_stage
from progettare.config import Config, ConfigError, load_config
from progettare.engine.intake import assemble
from progettare.engine.manifest import StageLedger, run_manifest, write_run_manifest
from progettare.engine.run import create_run_dir, write_intake
from progettare.github import (
    Issue,
    IssueClosedError,
    IssueFetchError,
    ensure_issue_open,
    load_issue,
)
from progettare.issue_ref import IssueRef, IssueRefError, parse_issue_ref
from progettare.survey.nare import NareResult, nare_runner
from progettare.survey.questions import plan_for, plan_for_followup
from progettare.survey.stage import run_survey_stage

CLI_DESCRIPTION = (
    "A technical-planning agent harness: bounded survey, one blueprint, "
    "ceremony decided by code."
)

EXIT_COMPLETE = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2


class NareSubprocessRunner:
    """The default NareRunner seam: one bounded session per call."""

    def run(self, argv: tuple[str, ...]) -> NareResult:
        return nare_runner(argv)


@dataclass(frozen=True)
class BlueprintOutcome:
    """What one blueprint verb did, as the CLI's return value."""

    status: str
    run_dir: Path
    failing_stage: str | None = None
    detail: str | None = None


def _ledger(error: BaseException) -> StageLedger:
    """The ledger an attached error carries, or the empty one."""
    sessions: tuple[str, ...] = getattr(error, "sessions", ())
    usage = getattr(error, "usage", None)
    return StageLedger(sessions=sessions, usage=usage)


def _read_artifact(path: Path) -> dict[str, Any]:
    """The artifact exactly as the run wrote it, re-read from the bytes."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def run_blueprint(
    ref: IssueRef,
    repo_path: str,
    config: Config,
    runs_base: Path,
    runner: Any,
    issue: Issue,
    written_at: str,
    refresher: Callable[[], None],
) -> BlueprintOutcome:
    """Drive the ceremony stage by stage, writing artifacts as they pass.

    The issue is loaded by the caller and handed in, so the orchestration
    stays testable offline: every stage here runs against the real code,
    with only the nare subprocess and the GitHub call at the seams. The
    refresher runs before each publishing stage, so an issue that closes
    mid-run aborts the run, discards its state, and posts nothing.
    """
    run_dir = create_run_dir(runs_base, ref, Path(repo_path))
    stages: dict[str, StageLedger] = {"intake": StageLedger()}
    stage = "intake"
    try:
        context = assemble(issue, repo_path)
        write_intake(run_dir, context, written_at)
        if context.blocked_questions:
            reason = "; ".join(context.blocked_questions)
            write_run_manifest(
                run_dir,
                run_manifest(config, "blocked", written_at, stages, "intake", reason),
            )
            return BlueprintOutcome(
                status="blocked",
                run_dir=run_dir,
                failing_stage="intake",
                detail=reason,
            )
        plan = plan_for(context, config)
        stage = "survey"
        refresher()
        survey_result = run_survey_stage(
            plan, runner, config, run_dir, repo_path, written_at
        )
        stages["survey"] = StageLedger(
            sessions=survey_result.sessions, usage=survey_result.usage
        )
        if survey_result.partial_reasons:
            reason = "; ".join(survey_result.partial_reasons)
            write_run_manifest(
                run_dir,
                run_manifest(config, "blocked", written_at, stages, "survey", reason),
            )
            return BlueprintOutcome(
                status="blocked",
                run_dir=run_dir,
                failing_stage="survey",
                detail=reason,
            )
        stage = "blueprint"
        refresher()
        blueprint_result = run_blueprint_stage(
            _read_artifact(run_dir / "intake.json"),
            _read_artifact(run_dir / "survey.json"),
            runner,
            config,
            run_dir,
            repo_path,
            written_at,
        )
        stages["blueprint"] = StageLedger(
            sessions=blueprint_result.sessions, usage=blueprint_result.usage
        )
        if blueprint_result.followup is not None:
            stage = "followup"
            refresher()
            followup_plan = plan_for_followup(
                context,
                blueprint_result.followup.section,
                blueprint_result.followup.questions,
                config,
            )
            followup_result = run_survey_stage(
                followup_plan, runner, config, run_dir, repo_path, written_at, round=2
            )
            stages["followup"] = StageLedger(
                sessions=followup_result.sessions, usage=followup_result.usage
            )
            stage = "blueprint"
            refresher()
            blueprint_result = run_blueprint_stage(
                _read_artifact(run_dir / "intake.json"),
                _read_artifact(run_dir / "survey2.json"),
                runner,
                config,
                run_dir,
                repo_path,
                written_at,
                followup_round=True,
            )
            stages["blueprint"] = StageLedger(
                sessions=blueprint_result.sessions, usage=blueprint_result.usage
            )
        stage = "size"
        refresher()
        blueprint_doc = _read_artifact(run_dir / "blueprint.json")
        size_record = classify_size(
            blueprint_doc,
            config.size_single_turn_max_milestones,
            config.size_documenter_min_topics,
            written_at,
            config.config_version,
        )
        write_size(run_dir / "size.json", size_record)
        stages["size"] = StageLedger()
        stage = "briefs"
        refresher()
        write_briefs(
            run_dir,
            slice_briefs(blueprint_doc, size_record, written_at, config.config_version),
        )
        stages["briefs"] = StageLedger()
        write_run_manifest(
            run_dir, run_manifest(config, "complete", written_at, stages)
        )
        return BlueprintOutcome(status="complete", run_dir=run_dir)
    except IssueClosedError as error:
        shutil.rmtree(run_dir, ignore_errors=True)
        return BlueprintOutcome(
            status="failed",
            run_dir=run_dir,
            failing_stage=stage,
            detail=str(error),
        )
    except Exception as error:
        stages[stage] = _ledger(error)
        write_run_manifest(
            run_dir,
            run_manifest(
                config,
                "failed",
                written_at,
                stages,
                failing_stage=stage,
                failing_reason=str(error),
            ),
        )
        return BlueprintOutcome(
            status="failed", run_dir=run_dir, failing_stage=stage, detail=str(error)
        )


def _package_version() -> str:
    """The installed progettare version, which hatch-vcs keeps truthful."""
    try:
        return package_version("progettare")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def main(argv: list[str] | None = None) -> int:
    """The entry point: parse, load the issue, run the ceremony, exit."""
    parser = argparse.ArgumentParser(prog="progettare", description=CLI_DESCRIPTION)
    parser.add_argument("--version", action="version", version=_package_version())
    verbs = parser.add_subparsers(dest="verb", required=True)
    blueprint = verbs.add_parser(
        "blueprint", help="plan one issue: survey, blueprint, sizing, briefs"
    )
    blueprint.add_argument("--issue", required=True, help="issue URL or owner/repo#N")
    blueprint.add_argument("--repo", required=True, help="path to the checkout")
    blueprint.add_argument(
        "--config", default="progettare.yaml", help="path to progettare.yaml"
    )
    blueprint.add_argument(
        "--runs-dir", default="runs", help="where run directories are created"
    )
    verbs.add_parser("serve", help="serve the ceremony over MCP stdio")
    args = parser.parse_args(argv)
    if args.verb == "serve":
        from progettare.mcp import serve

        serve(sys.stdin, sys.stdout)
        return EXIT_COMPLETE
    try:
        ref = parse_issue_ref(args.issue)
        config = load_config(Path(args.config))
    except (IssueRefError, ConfigError) as error:
        print(f"progettare failed: {error}", file=sys.stderr)
        return EXIT_FAILED
    written_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    try:
        issue = load_issue(ref)
    except (IssueFetchError, IssueClosedError) as error:
        print(f"progettare failed: {error}", file=sys.stderr)
        return EXIT_FAILED
    outcome = run_blueprint(
        ref,
        args.repo,
        config,
        Path(args.runs_dir),
        NareSubprocessRunner(),
        issue,
        written_at,
        lambda: ensure_issue_open(ref),
    )
    if outcome.status == "complete":
        print(
            json.dumps(
                {"status": "complete", "run_dir": str(outcome.run_dir)},
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_COMPLETE
    print(
        f"progettare {outcome.status} at {outcome.failing_stage}: {outcome.detail}",
        file=sys.stderr,
    )
    return EXIT_BLOCKED if outcome.status == "blocked" else EXIT_FAILED
