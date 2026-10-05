"""The survey stage's single-session layer: schema, prompt, and outcome.

One survey question gets one bounded nare session. This module prepares
that session's argv, runs it through the injected runner boundary, and
records what came back as data: the answer, the usage, and the stop
reason. The question loop, its token ledger, and the artifact write are
the stage's next layer, not this one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from progettare.config import Config
from progettare.survey.artifact import SurveyAnswer
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
    budget of 0 or less yields a share of 0, and the caller treats that
    share as stage exhaustion.
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
