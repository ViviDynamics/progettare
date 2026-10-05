"""The blueprint stage: one bounded session, one validated blueprint.

The stage turns the intake and survey artifacts into the run's single
structured plan through one bounded nare session. The output is checked
against a code-enforced schema, an unusable payload earns exactly one
bounded re-ask, and anything the stage cannot accept fails the run
loudly, naming the stage and the validation error. No blueprint is ever
published half-checked: the artifact is written only from a payload that
passed every rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from progettare.blueprint.artifact import (
    BlueprintRecord,
    Milestone,
    blueprint_record,
    write_blueprint,
)
from progettare.config import Config
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.survey.nare import NareResult, NareRunner, NareUsage, session_argv

BLUEPRINT_SYSTEM_PROMPT = (
    "You are the blueprint author. Work only from the intake and survey "
    "data in the prompt, with the read tool as your only option beyond "
    "that. Answer with the one JSON object the session's schema requires: "
    "milestones that sequence the work in order, each titled and carrying "
    "the concrete changes it makes, then the data model, the interfaces, "
    "the risks, the testable criteria, and the documentation topics."
)

# The blueprint schema, in nare's validatable subset (type, properties,
# required, items, additionalProperties). That subset cannot express
# minItems or minLength, so the schema alone accepts an empty milestones
# array or a blank title; validate_blueprint is the code-enforced boundary
# that refuses them. Treat this mapping as fixed: it is written verbatim
# as the session's --schema file.
MILESTONE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "changes"],
    "additionalProperties": False,
}

BLUEPRINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "milestones": {"type": "array", "items": MILESTONE_SCHEMA},
        "data_model": {"type": "array", "items": {"type": "string"}},
        "interfaces": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "testable_criteria": {"type": "array", "items": {"type": "string"}},
        "documentation_topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "milestones",
        "data_model",
        "interfaces",
        "risks",
        "testable_criteria",
        "documentation_topics",
    ],
    "additionalProperties": False,
}

_BLUEPRINT_KEYS = (
    "milestones",
    "data_model",
    "interfaces",
    "risks",
    "testable_criteria",
    "documentation_topics",
)

_STRING_SECTIONS = (
    "data_model",
    "interfaces",
    "risks",
    "testable_criteria",
    "documentation_topics",
)

# The prompt is subprocess argv, and argv has a kernel-level ceiling. The
# header (issue, criteria, clarifications, task) is what a blueprint
# cannot be built without, so survey material is what the byte budget
# cuts first.
_MAX_PROMPT_BYTES = 100_000

_TASK_TEXT = (
    "Task: produce the one blueprint JSON object. Sequence the milestones "
    "so each one is a unit of work the previous makes possible. Name the "
    "data model, the interfaces, the risks, the testable criteria, and "
    "the documentation topics. Answer with the JSON object only."
)


class BlueprintStageError(RuntimeError):
    """The blueprint stage failed the run, naming itself and the reason."""


def _check_string_list(section: Any, name: str, errors: list[str]) -> None:
    if not isinstance(section, list):
        errors.append(f"{name} is not an array")
        return
    for position, item in enumerate(section):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{name}[{position}] is not a nonempty string")


def _check_milestone(item: Any, position: int, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"milestones[{position}] is not an object")
        return
    unknown = sorted(set(item) - {"title", "changes"}, key=str)
    if unknown:
        errors.append(
            f"milestones[{position}] carries unknown key(s): {', '.join(unknown)}"
        )
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"milestones[{position}].title is not a nonempty string")
    changes = item.get("changes")
    if not isinstance(changes, list) or not changes:
        errors.append(f"milestones[{position}].changes is not a nonempty array")
    else:
        for change_position, change in enumerate(changes):
            if not isinstance(change, str) or not change.strip():
                errors.append(
                    f"milestones[{position}].changes[{change_position}] "
                    "is not a nonempty string"
                )


def validate_blueprint(payload: object) -> tuple[str, ...]:
    """Every reason the payload is not a valid blueprint; empty means valid.

    This is the code-enforced schema: required fields, types, and
    non-empty milestones, independent of what nare's --schema checked.
    The subset cannot express minItems or minLength, so those rules live
    here. Errors are collected all rather than first-failure, because the
    re-ask hands the model the whole list.
    """
    if not isinstance(payload, dict):
        return ("the blueprint payload is not a JSON object",)
    errors: list[str] = []
    unknown = sorted(set(payload) - set(_BLUEPRINT_KEYS), key=str)
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    missing = [name for name in _BLUEPRINT_KEYS if name not in payload]
    if missing:
        errors.append(f"missing key(s): {', '.join(missing)}")
    if "milestones" in payload:
        milestones = payload["milestones"]
        if not isinstance(milestones, list):
            errors.append("milestones is not an array")
        else:
            if not milestones:
                errors.append(
                    "milestones is an empty array; "
                    "a blueprint sequences at least one milestone"
                )
            for position, item in enumerate(milestones):
                _check_milestone(item, position, errors)
    for name in _STRING_SECTIONS:
        if name in payload:
            _check_string_list(payload[name], name, errors)
    return tuple(errors)


def _build_blueprint(output: str) -> tuple[BlueprintRecord | None, tuple[str, ...]]:
    """The built BlueprintRecord, or (None, every reason the payload fails)."""
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        return None, (f"the blueprint payload is not valid JSON: {error}",)
    errors = validate_blueprint(document)
    if errors:
        return None, errors
    record = BlueprintRecord(
        milestones=tuple(
            Milestone(title=item["title"], changes=tuple(item["changes"]))
            for item in document["milestones"]
        ),
        data_model=tuple(document["data_model"]),
        interfaces=tuple(document["interfaces"]),
        risks=tuple(document["risks"]),
        testable_criteria=tuple(document["testable_criteria"]),
        documentation_topics=tuple(document["documentation_topics"]),
    )
    return record, ()


def _string_items(section: Any) -> list[str]:
    if not isinstance(section, list):
        return []
    return [item for item in section if isinstance(item, str)]


def _header_lines(intake: dict[str, Any]) -> list[str]:
    lines = ["Intake:"]
    issue = intake.get("issue")
    if isinstance(issue, dict):
        title = issue.get("title")
        title_text = title if isinstance(title, str) and title.strip() else "(no title)"
        lines.append(f"Issue #{issue.get('number')}: {title_text}")
    criteria = _string_items(intake.get("acceptance_criteria"))
    if criteria:
        lines.append("Acceptance criteria:")
        lines.extend(f"- {criterion}" for criterion in criteria)
    clarifications = intake.get("clarifications")
    if isinstance(clarifications, list):
        asked = [item for item in clarifications if isinstance(item, dict)]
        if asked:
            lines.append("Clarifications:")
            lines.extend(
                f"- Q: {item.get('question', '')} A: {item.get('answer', '')}"
                for item in asked
            )
    blocked = _string_items(intake.get("blocked_questions"))
    if blocked:
        lines.append("Blocked questions:")
        lines.extend(f"- {question}" for question in blocked)
    return lines


def _findings_lines(survey: dict[str, Any]) -> list[str]:
    answers = survey.get("answers")
    if not isinstance(answers, list):
        return []
    lines: list[str] = []
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        findings = answer.get("findings")
        if isinstance(findings, str) and findings.strip():
            lines.append(f"(question {answer.get('question')}) {findings}")
    return lines


def _tree_line(survey: dict[str, Any]) -> str | None:
    structure = survey.get("structure")
    if not isinstance(structure, dict):
        return None
    tree = structure.get("tree")
    if not isinstance(tree, list) or not tree:
        return None
    names = ", ".join(str(entry) for entry in tree)
    return f"Repository structure: {names}"


def _partial_reason_line(survey: dict[str, Any]) -> str | None:
    reason = survey.get("partial_reason")
    if isinstance(reason, str) and reason.strip():
        return f"Survey partial reason: {reason}"
    return None


def _rejection_text(errors: tuple[str, ...]) -> str:
    return (
        "Your previous answer was rejected as invalid:\n"
        + "; ".join(errors)
        + "\nProduce the corrected blueprint JSON object, and nothing else."
    )


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _assembled(
    header: str, findings: str, tree: str | None, omitted: int, mandatory: str
) -> str:
    blocks = [header]
    if tree is not None:
        blocks.append(tree)
    if findings:
        blocks.append(findings)
    if omitted:
        blocks.append(f"[{omitted} survey finding(s) omitted to fit the prompt budget]")
    return "\n\n".join(blocks) + "\n\n" + mandatory


def _build_prompt(
    intake: dict[str, Any],
    survey: dict[str, Any],
    rejection: tuple[str, ...] | None = None,
) -> str:
    """The one prompt the blueprint session reads, inside the byte budget.

    The task text and the re-ask's error list are mandatory: they are
    never truncated, and the byte budget cuts survey material first --
    findings from the end, then the structure tree, then the header from
    its end -- with every cut marked in the prompt itself. A mandatory
    suffix that alone exceeds the budget is an explicit stage failure,
    not a prompt that silently launches without its instructions.
    """
    header_lines = _header_lines(intake)
    partial = _partial_reason_line(survey)
    if partial is not None:
        header_lines.append(partial)
    header = "\n".join(header_lines)
    tree = _tree_line(survey)
    findings_lines = _findings_lines(survey)
    rejection_text = "" if rejection is None else "\n\n" + _rejection_text(rejection)
    mandatory = _TASK_TEXT + rejection_text
    marker = "\n[header truncated to fit the prompt budget]"
    if _utf8_len(mandatory) + _utf8_len(marker) + 2 > _MAX_PROMPT_BYTES:
        raise BlueprintStageError(
            "blueprint stage: the prompt's mandatory content alone exceeds "
            f"{_MAX_PROMPT_BYTES} bytes"
        )

    omitted = 0
    prompt = _assembled(header, "\n\n".join(findings_lines), tree, 0, mandatory)
    while _utf8_len(prompt) > _MAX_PROMPT_BYTES and findings_lines:
        findings_lines.pop()
        omitted += 1
        prompt = _assembled(
            header, "\n\n".join(findings_lines), tree, omitted, mandatory
        )
    if _utf8_len(prompt) > _MAX_PROMPT_BYTES and tree is not None:
        prompt = _assembled(header, "", None, omitted, mandatory)
    if _utf8_len(prompt) > _MAX_PROMPT_BYTES:
        budget = _MAX_PROMPT_BYTES - _utf8_len(mandatory) - _utf8_len(marker) - 2
        data = header.encode("utf-8")[:budget]
        header = data.decode("utf-8", errors="ignore") + marker
        prompt = _assembled(header, "", None, 0, mandatory)
    return prompt


@dataclass(frozen=True)
class BlueprintStageResult:
    """What the stage produced: the artifact, the plan, and the ledger."""

    path: Path
    blueprint: BlueprintRecord
    usage: NareUsage | None
    reasked: bool


def _summed(usages: list[NareUsage]) -> NareUsage | None:
    if not usages:
        return None
    return NareUsage(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
    )


def _write_schema(run_dir: Path) -> Path:
    schema_path = run_dir / "blueprint.schema.json"
    schema_path.write_text(
        json.dumps(BLUEPRINT_SCHEMA, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return schema_path


def _launch(
    runner: NareRunner,
    config: Config,
    prompt: str,
    schema_path: Path,
    run_dir: Path,
    repo_path: str,
    budget: int,
    session_name: str,
) -> NareResult:
    argv = session_argv(
        prompt=prompt,
        system=BLUEPRINT_SYSTEM_PROMPT,
        root=repo_path,
        rail=config.blueprint_rail,
        schema=str(schema_path),
        budget_tokens=budget,
        session_path=str(run_dir / session_name),
    )
    return runner.run(argv)


def _fail_on_budget(result: NareResult) -> None:
    """Budget exhaustion fails the run instead of publishing a cut-off plan."""
    if result.stop_reason == "budget":
        raise BlueprintStageError(
            "blueprint stage: the nare session exhausted its token budget"
        )


def run_blueprint_stage(
    intake: dict[str, Any],
    survey: dict[str, Any],
    runner: NareRunner,
    config: Config,
    run_dir: Path,
    repo_path: str,
    written_at: str,
) -> BlueprintStageResult:
    """Turn the intake and survey artifacts into the run's one blueprint.

    The first session launches with the whole blueprint-stage budget. A
    payload that fails validate_blueprint earns exactly one bounded
    re-ask, funded by whatever the ledger has left, whose prompt carries
    the full error list; when no budget remains for that re-ask, the run
    fails loudly, naming the stage, the validation error, and the ledger.
    Budget exhaustion in either session fails the run the same way. The
    artifact is written only from a payload that passed every rule, so
    blueprint.json never holds a partial plan. NareError propagates: a
    missing nare binary or a contract refusal is an installation fault,
    not a stage failure.
    """
    budget = config.budget_blueprint_stage_tokens
    prompt = _build_prompt(intake, survey)
    schema_path = _write_schema(run_dir)
    result = _launch(
        runner,
        config,
        prompt,
        schema_path,
        run_dir,
        repo_path,
        budget,
        "blueprint-session.json",
    )
    usages: list[NareUsage] = []
    if result.usage is not None:
        usages.append(result.usage)
    _fail_on_budget(result)
    record, errors = _extract(result)
    reasked = record is None
    if record is None:
        spent = usages[0].total_tokens if usages else 0
        remaining = budget - spent
        if remaining <= 0:
            raise BlueprintStageError(
                "blueprint stage: no budget remains for the bounded re-ask: "
                + "; ".join(errors)
            )
        reask_prompt = _build_prompt(intake, survey, errors)
        reask = _launch(
            runner,
            config,
            reask_prompt,
            schema_path,
            run_dir,
            repo_path,
            remaining,
            "blueprint-reask-session.json",
        )
        if reask.usage is not None:
            usages.append(reask.usage)
        _fail_on_budget(reask)
        record, errors = _extract(reask)
        if record is None:
            raise BlueprintStageError(
                "blueprint stage: the re-asked blueprint payload is invalid: "
                + "; ".join(errors)
            )
    stamped: dict[str, Any] = {
        "artifact": "blueprint",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": written_at,
        **blueprint_record(record),
    }
    path = run_dir / "blueprint.json"
    write_blueprint(path, stamped)
    return BlueprintStageResult(
        path=path,
        blueprint=record,
        usage=_summed(usages),
        reasked=reasked,
    )


def _extract(result: NareResult) -> tuple[BlueprintRecord | None, tuple[str, ...]]:
    """The record from a finished session's output, or the reasons it fails."""
    if result.status != "done" or result.output is None:
        detail = result.stop_reason or f"status {result.status}"
        return (
            None,
            (f"the session ended without a blueprint payload ({detail})",),
        )
    return _build_blueprint(result.output)
