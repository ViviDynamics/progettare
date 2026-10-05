"""The reader briefs: code-sliced views of the blueprint, per role.

The blueprint is one document, but each downstream reader only needs its
own slice: the implementer works from the milestones, the QA gate checks
the testable criteria verbatim, and the documenter writes to the topics.
Slicing in code, never by a model, keeps the three views byte-stable
across replays, and the pure ``slice_blueprint`` keeps that promise test
without a run directory or a clock.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from progettare.blueprint.size import MILESTONE_LOOP, SINGLE_TURN
from progettare.blueprint.stage import validate_blueprint
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.run import atomic_write_json


class BriefsError(RuntimeError):
    """A briefs stage progettare refuses to run, naming the artifact."""


@dataclass(frozen=True)
class ImplementerBrief:
    """The milestones, and nothing else: what to build, in order."""

    milestones: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class QaBrief:
    """The testable criteria, 1-based and quoted, never paraphrased."""

    criteria: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DocumenterBrief:
    """The topics the documentation pass must cover."""

    topics: tuple[str, ...]


def _milestone_slicer(blueprint: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"title": milestone["title"], "changes": milestone["changes"]}
        for milestone in blueprint["milestones"]
    )


def _criteria_slicer(blueprint: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"index": position + 1, "criterion": criterion}
        for position, criterion in enumerate(blueprint["testable_criteria"])
    )


def slice_blueprint(
    blueprint: dict[str, Any], documenter: bool
) -> tuple[ImplementerBrief | QaBrief | DocumenterBrief, ...]:
    """The role slices of a validated blueprint, in reading order.

    The blueprint is the record the blueprint stage already validated;
    the caller's ``documenter`` decision is the size stage's, carried,
    never recomputed. With the documenter off, the third slice is
    absent, not empty: a reader must not mistake a skipped pass for an
    assigned one.
    """
    briefs: tuple[ImplementerBrief | QaBrief | DocumenterBrief, ...] = (
        ImplementerBrief(milestones=_milestone_slicer(blueprint)),
        QaBrief(criteria=_criteria_slicer(blueprint)),
    )
    if documenter:
        briefs += (DocumenterBrief(topics=tuple(blueprint["documentation_topics"])),)
    return briefs


def _payload(brief: Any, written_at: str) -> dict[str, Any]:
    return {
        "artifact": "brief",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": written_at,
        "brief": dataclasses.asdict(brief),
    }


# The validator checks the model payload shape; the file carries that
# payload plus the record version and the stamps it does not know.
_STRIP_KEYS = ("artifact", "artifact_version", "progettare", "written_at", "version")


def _read_record(path: pathlib.Path, name: str, artifact: str) -> dict[str, Any]:
    if not path.exists():
        raise BriefsError(
            f"briefs stage: {name} is missing; the stage that writes it must run first"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BriefsError(
            f"briefs stage: {name} is not readable JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise BriefsError(f"briefs stage: {name} is not a JSON object")
    if payload.get("artifact") != artifact:
        raise BriefsError(
            f"briefs stage: {name} does not carry the {artifact} artifact stamp"
        )
    return payload


def _validated_size(record: dict[str, Any]) -> bool:
    classification = record.get("classification")
    if classification not in (SINGLE_TURN, MILESTONE_LOOP):
        raise BriefsError(
            "briefs stage: size.json holds an unknown classification "
            + repr(classification)
        )
    documenter = record.get("documenter")
    if not isinstance(documenter, bool):
        raise BriefsError(
            "briefs stage: size.json documenter must be a boolean, "
            f"got {type(documenter).__name__}"
        )
    return documenter


def run_briefs_stage(run_dir: pathlib.Path, written_at: str) -> dict[str, Any]:
    """Slice, stamp, and publish the reader briefs for one run directory.

    Reads ``blueprint.json`` and ``size.json`` from the run, re-checks
    the blueprint against the code schema, and writes the brief files
    only after every slice is computed, so a failure above leaves no
    partial publication behind. The result is versioned for the stdout
    contract and states the documenter decision, because the engine and
    the next run read the decision, not the directory listing.
    """
    blueprint = _read_record(run_dir / "blueprint.json", "blueprint.json", "blueprint")
    stamped = {key: value for key, value in blueprint.items() if key not in _STRIP_KEYS}
    errors = validate_blueprint(stamped)
    if errors:
        raise BriefsError(
            "briefs stage: blueprint.json is not a valid blueprint: "
            + "; ".join(errors)
        )
    documenter = _validated_size(
        _read_record(run_dir / "size.json", "size.json", "size")
    )
    briefs = slice_blueprint(blueprint, documenter)
    names = ("implementer", "qa", "documenter")
    payloads = {
        name: _payload(brief, written_at)
        for name, brief in zip(names, briefs, strict=False)
    }
    target = run_dir / "briefs"
    target.mkdir(exist_ok=True)
    for name, payload in payloads.items():
        atomic_write_json(target / f"{name}.json", payload)
    return {
        "schema_version": ARTIFACT_VERSION,
        "documenter": documenter,
        "briefs": payloads,
    }
