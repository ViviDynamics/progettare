"""Intake stage: card context assembly, blocked detection, intake.json."""

import json
import os
from dataclasses import dataclass

from progettare.engine.clarifications import Clarification, extract_clarifications
from progettare.engine.criteria import (
    Conflict,
    Criterion,
    find_conflicts,
    parse_criteria,
)
from progettare.engine.issue_fetch import IssueCard, Runner, fetch_issue
from progettare.engine.issue_ref import IssueRef

SCHEMA_VERSION = 1


class IntakeError(RuntimeError):
    pass


class IntakeAborted(IntakeError):
    pass


@dataclass(frozen=True)
class RepoContext:
    path: str
    head: str
    branch: str


@dataclass(frozen=True)
class Blocked:
    reasons: tuple[str, ...]
    questions: tuple[str, ...]


@dataclass(frozen=True)
class IntakeResult:
    status: str
    card: IssueCard
    context: RepoContext
    criteria: tuple[Criterion, ...]
    clarifications: tuple[Clarification, ...]
    conflicts: tuple[Conflict, ...]
    blocked: Blocked | None


def repo_context(path: str, run: Runner) -> RepoContext:
    inside = _rev_parse(
        path, run, ["git", "-C", path, "rev-parse", "--is-inside-work-tree"]
    )
    if inside.strip().casefold() != "true":
        raise IntakeError(_not_a_repository(path))
    head = _rev_parse(path, run, ["git", "-C", path, "rev-parse", "HEAD"])
    branch = _rev_parse(
        path, run, ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]
    )
    return RepoContext(
        path=os.path.abspath(path), head=head.strip(), branch=branch.strip()
    )


def _rev_parse(path: str, run: Runner, command: list[str]) -> str:
    try:
        return run(command)
    except RuntimeError as error:
        raise IntakeError(_not_a_repository(path)) from error


def _not_a_repository(path: str) -> str:
    return f"{path} is not a git repository"


def assemble(card: IssueCard, context: RepoContext) -> IntakeResult:
    criteria = parse_criteria(card.body)
    clarifications = extract_clarifications(card.comments)
    conflicts = find_conflicts(criteria)
    reasons: list[str] = []
    questions: list[str] = []
    if not criteria:
        reasons.append("missing_criteria")
        questions.append(
            "The issue states no acceptance criteria. Add acceptance criteria "
            "to the issue body as a bullet list under Acceptance."
        )
    if conflicts:
        reasons.append("conflicting_criteria")
        for conflict in conflicts:
            questions.append(
                f"Criteria {conflict.first_id} and {conflict.second_id} conflict "
                f"({conflict.kind}): '{conflict.detail}'. Resolve the conflict "
                "in the issue."
            )
    if any(clarification.answer is None for clarification in clarifications):
        reasons.append("unanswered_clarifications")
        for clarification in clarifications:
            if clarification.answer is None:
                questions.append(
                    f"{clarification.question} is unanswered on the issue. "
                    "Answer it or withdraw the question."
                )
    blocked = None
    if reasons:
        blocked = Blocked(reasons=tuple(reasons), questions=tuple(questions))
    return IntakeResult(
        status="blocked" if blocked else "ok",
        card=card,
        context=context,
        criteria=criteria,
        clarifications=clarifications,
        conflicts=conflicts,
        blocked=blocked,
    )


def write_intake(result: IntakeResult, run_dir: str) -> str:
    document = {
        "schema_version": SCHEMA_VERSION,
        "status": result.status,
        "issue": {
            "url": result.card.url,
            "title": result.card.title,
            "state": result.card.state,
        },
        "repo": {
            "path": result.context.path,
            "head": result.context.head,
            "branch": result.context.branch,
        },
        "criteria": [
            {"id": criterion.id, "text": criterion.text}
            for criterion in result.criteria
        ],
        "clarifications": [
            {
                "question": clarification.question,
                "answer": clarification.answer,
                "source": clarification.source,
            }
            for clarification in result.clarifications
        ],
        "blocked": None
        if result.blocked is None
        else {
            "reasons": list(result.blocked.reasons),
            "questions": list(result.blocked.questions),
        },
    }
    os.makedirs(run_dir, exist_ok=True)
    artifact = os.path.join(run_dir, "intake.json")
    with open(artifact, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return artifact


def run_intake(
    ref: IssueRef, repo_path: str, run_dir: str, run: Runner
) -> IntakeResult:
    card = fetch_issue(ref, run)
    context = repo_context(repo_path, run)
    result = assemble(card, context)
    fresh = fetch_issue(ref, run)
    if fresh.is_closed:
        artifact = os.path.join(run_dir, "intake.json")
        if os.path.exists(artifact):
            os.remove(artifact)
        raise IntakeAborted(
            f"issue {ref.owner}/{ref.repo}#{ref.number} closed mid-run, "
            "the run aborted and nothing was written"
        )
    write_intake(result, run_dir)
    return result
