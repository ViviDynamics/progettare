"""The survey stage: one bounded session per question, one ledger, one artifact.

Each formulated question gets its own bounded nare session. The stage
hands every session its fair share of the survey-stage token budget,
keeps the ledger as sessions report their usage, notes each question the
budget or its session left unanswered, and records the answers as data
in the run's versioned survey.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from progettare.config import Config
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.survey.artifact import SurveyAnswer, survey_record, write_survey
from progettare.survey.nare import NareRunner, NareUsage, session_argv
from progettare.survey.questions import SurveyPlan, SurveyQuestion

SURVEY_SYSTEM_PROMPT = (
    "You are a read-only code surveyor. Investigate the repository with "
    "the read tool only. Answer with the JSON object the session's schema "
    "requires. Record in commands the read trace as allowlisted command "
    "lines, one per line you actually consulted, within the session's "
    "budget. Write findings that answer the question concretely, naming "
    "files and code paths."
)

# The answer schema, in nare's validatable subset (type, properties,
# required, items, additionalProperties). That subset cannot express
# minLength, so the schema alone accepts a blank findings string; the
# stage code refuses an answer whose findings strip to nothing when it
# builds the SurveyAnswer, and artifact.survey_record re-checks it.
# Treat this mapping as fixed: it is written verbatim as the session's
# --schema file.
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "commands": {"type": "array", "items": {"type": "string"}},
        "findings": {"type": "string"},
    },
    "required": ["commands", "findings"],
    "additionalProperties": False,
}


def fair_share(remaining_tokens: int, questions_remaining: int) -> int:
    """The per-question token budget: the remaining tokens split evenly.

    The share is ``remaining_tokens // questions_remaining`` with nothing
    rolled over; unused share stays in the caller's ledger. While
    questions remain and budget remains, the share is never less than 1,
    so a late question still gets a real chance to answer. A remaining
    budget of 0 or less yields a share of 0, and so does a
    questions_remaining of 0 or less; the caller treats a share of 0 as
    stage exhaustion.
    """
    if remaining_tokens <= 0 or questions_remaining <= 0:
        return 0
    return max(1, remaining_tokens // questions_remaining)


@dataclass(frozen=True)
class SessionOutcome:
    """What one bounded session produced, as data for the stage ledger."""

    answer: SurveyAnswer | None
    usage: NareUsage | None
    stop_reason: str | None


def _unusable(detail: str) -> str:
    return f"unusable_answer: {detail}"


def _build_answer(output: str, number: int) -> tuple[SurveyAnswer | None, str | None]:
    """The built SurveyAnswer, or (None, the reason the payload is unusable).

    This is the shape check that lets a well-typed SurveyAnswer exist, not
    the enforcing boundary: commands are neither budget-checked nor
    allowlisted here, because artifact.survey_record is the boundary that
    refuses over-budget or forbidden traces.
    """
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        return None, _unusable(f"the answer payload is not valid JSON: {error}")
    if not isinstance(document, dict):
        return None, _unusable("the answer payload is not a JSON object")
    commands = document.get("commands")
    findings = document.get("findings")
    if not isinstance(commands, list) or not all(
        isinstance(command, str) for command in commands
    ):
        return None, _unusable("commands is not an array of strings")
    if not isinstance(findings, str) or not findings.strip():
        return None, _unusable("findings is not a nonempty string")
    answer = SurveyAnswer(question=number, commands=tuple(commands), findings=findings)
    return answer, None


def answer_one_question(
    plan: SurveyPlan,
    question: SurveyQuestion,
    runner: NareRunner,
    config: Config,
    run_dir: Path,
    repo_path: str,
    budget: int,
) -> SessionOutcome:
    """Run the one bounded session for ``question`` and record what it did.

    The prompt is the question's text, which already carries the plan's
    hints. The answer schema is written to ``q<N>.schema.json`` in the run
    directory and the session lands in ``q<N>-session.json``. The runner
    is called exactly once. Usage is recorded regardless of status. A done
    result with a usable payload yields the SurveyAnswer and a stop reason
    of None; a payload that is missing or unusable yields answer None with
    an ``unusable_answer:`` stop reason; a nare stop reason such as
    ``budget`` is recorded as it arrived. The plan names the question set
    the question belongs to; its caps are enforced by artifact.survey_record,
    which the stage calls when it writes the artifact. NareError propagates:
    a missing nare binary or a contract refusal is an installation fault,
    not budget exhaustion.
    """
    schema_path = run_dir / f"q{question.number}.schema.json"
    schema_path.write_text(
        json.dumps(ANSWER_SCHEMA, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    session_path = run_dir / f"q{question.number}-session.json"
    argv = session_argv(
        prompt=question.text,
        system=SURVEY_SYSTEM_PROMPT,
        root=repo_path,
        rail=config.survey_rail,
        schema=str(schema_path),
        budget_tokens=budget,
        session_path=str(session_path),
    )
    result = runner.run(argv)
    usage = result.usage
    if result.status == "done" and result.output is not None:
        answer, reason = _build_answer(result.output, question.number)
        if answer is not None:
            return SessionOutcome(answer=answer, usage=usage, stop_reason=None)
        return SessionOutcome(answer=None, usage=usage, stop_reason=reason)
    if result.status == "done":
        stop_reason = result.stop_reason or _unusable(
            "the session ended without an answer payload"
        )
        return SessionOutcome(answer=None, usage=usage, stop_reason=stop_reason)
    return SessionOutcome(answer=None, usage=usage, stop_reason=result.stop_reason)


@dataclass(frozen=True)
class SurveyStageResult:
    """What the stage produced: the artifact, the answers, and the ledger."""

    path: Path
    answers: tuple[SurveyAnswer, ...]
    usage: NareUsage | None
    partial_reasons: tuple[str, ...]


def _aggregate_usage(usages: list[NareUsage]) -> NareUsage | None:
    """The sessions' summed usage, or None when no session reported any."""
    if not usages:
        return None
    input_total = sum(usage.input_tokens for usage in usages)
    output_total = sum(usage.output_tokens for usage in usages)
    return NareUsage(
        input_tokens=input_total,
        output_tokens=output_total,
        total_tokens=sum(usage.total_tokens for usage in usages),
    )


def run_survey_stage(
    plan: SurveyPlan,
    runner: NareRunner,
    config: Config,
    run_dir: Path,
    repo_path: str,
    written_at: str,
) -> SurveyStageResult:
    """Answer every question in the plan, one bounded session each.

    Each session launches with its fair share of the stage's token
    budget, and the usage the session reports is deducted from the ledger
    before the next question launches; a session that reports no usage
    deducts nothing. The first question the ledger cannot fund ends the
    loop: the questions it did not attempt are named in the stage's
    partial reason, and the artifact is still written. A session that ran
    but produced no usable answer marks only its own question partial,
    and the stage continues with the next question.

    The record is built through survey_record, so an over-budget or
    non-allowlisted command trace, a duplicate or unknown question
    number, or empty findings raise SurveyRecordError instead of being
    recorded; NareError from a session propagates, an installation fault
    rather than budget exhaustion. The written artifact carries the same
    stamps as intake.json: artifact, artifact_version, progettare,
    written_at, with the record's own version key kept as survey_record
    wrote it.
    """
    reasons: list[str] = []
    if plan.partial_reason is not None:
        reasons.append(plan.partial_reason)
    answers: list[SurveyAnswer] = []
    usages: list[NareUsage] = []
    remaining = config.budget_survey_stage_tokens
    questions_remaining = len(plan.questions)
    for position, question in enumerate(plan.questions):
        share = fair_share(remaining, questions_remaining)
        if share == 0:
            unattempted = ", ".join(
                str(skipped.number) for skipped in plan.questions[position:]
            )
            reasons.append(
                f"stage token budget exhausted: question(s) {unattempted} not attempted"
            )
            break
        outcome = answer_one_question(
            plan=plan,
            question=question,
            runner=runner,
            config=config,
            run_dir=run_dir,
            repo_path=repo_path,
            budget=share,
        )
        if outcome.usage is not None:
            remaining -= outcome.usage.total_tokens
            usages.append(outcome.usage)
        questions_remaining -= 1
        if outcome.answer is not None:
            answers.append(outcome.answer)
        else:
            reasons.append(f"question {question.number}: {outcome.stop_reason}")
    combined = "; ".join(reasons) if reasons else None
    record = survey_record(replace(plan, partial_reason=combined), tuple(answers))
    stamped: dict[str, Any] = {
        "artifact": "survey",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": written_at,
        **record,
    }
    path = run_dir / "survey.json"
    write_survey(path, stamped)
    return SurveyStageResult(
        path=path,
        answers=tuple(answers),
        usage=_aggregate_usage(usages),
        partial_reasons=tuple(reasons),
    )
