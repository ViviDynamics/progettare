"""The survey artifact: questions and answers as data.

``survey.json`` is the record a blueprint stage reads, so no stage ever
pays for another stage's conversation history. The schema is versioned,
the caps are enforced at recording time, and every recorded command is
checked against the read-only allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from progettare.engine.run import atomic_write_json
from progettare.survey.commands import SurveyCommandError, validate_session_commands
from progettare.survey.nare import NareUsage
from progettare.survey.questions import SurveyPlan

SURVEY_RECORD_VERSION = 1


class SurveyRecordError(ValueError):
    """An answer set progettare refuses to record, named loudly.

    The record is refused, but the sessions that produced it already
    ran, so the error carries the stage ledger a failed-run manifest
    needs: the session files launched and the usage their JSONL result
    lines reported.
    """

    def __init__(
        self,
        message: str,
        *,
        sessions: tuple[str, ...] = (),
        usage: NareUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.sessions = sessions
        self.usage = usage


@dataclass(frozen=True)
class SurveyAnswer:
    """What one survey session did and found, as data, not conversation."""

    question: int
    commands: tuple[str, ...]
    findings: str


def survey_record(
    plan: SurveyPlan, answers: tuple[SurveyAnswer, ...]
) -> dict[str, Any]:
    """The versioned survey record, with the caps enforced on every answer."""
    by_number = {question.number: question for question in plan.questions}
    seen: set[int] = set()
    validated: list[dict[str, Any]] = []
    for answer in sorted(answers, key=lambda a: a.question):
        if answer.question not in by_number:
            raise SurveyRecordError(
                f"answer names question {answer.question}, which the plan "
                "does not contain"
            )
        if answer.question in seen:
            raise SurveyRecordError(
                f"question {answer.question} has more than one answer"
            )
        seen.add(answer.question)
        question = by_number[answer.question]
        if len(answer.commands) > question.command_budget:
            raise SurveyRecordError(
                f"question {answer.question} ran {len(answer.commands)} "
                f"commands against a budget of {question.command_budget}"
            )
        try:
            validate_session_commands(answer.commands)
        except SurveyCommandError as error:
            raise SurveyRecordError(
                f"question {answer.question} recorded a forbidden command: {error}"
            ) from error
        if not answer.findings.strip():
            raise SurveyRecordError(f"question {answer.question} recorded no findings")
        validated.append(
            {
                "question": answer.question,
                "commands": list(answer.commands),
                "findings": answer.findings,
            }
        )
    return {
        "version": SURVEY_RECORD_VERSION,
        "issue": plan.issue_number,
        "repo": plan.repo,
        "structure": {
            "tree": list(plan.structure.tree),
            "touched": list(plan.structure.touched),
            "entry_points": list(plan.structure.entry_points),
            "tests": list(plan.structure.tests),
        },
        "questions": [
            {
                "number": question.number,
                "text": question.text,
                "criterion": question.criterion,
                "command_budget": question.command_budget,
            }
            for question in plan.questions
        ],
        "answers": validated,
        "partial_reason": plan.partial_reason,
    }


def write_survey(path: Path, record: dict[str, Any]) -> None:
    """Write the record atomically, readable only by its owner.

    Delegates to the engine's atomic writer: the rename is what survives
    a kill, so the blueprint stage never reads a half-written artifact.
    """
    atomic_write_json(path, record)
