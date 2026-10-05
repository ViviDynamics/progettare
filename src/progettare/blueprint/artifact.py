"""The blueprint artifact: the one structured plan as versioned data.

``blueprint.json`` is the record the sizing stage and the briefs read, so
no stage ever parses a conversation. The record is versioned, and the
recording boundary re-checks the shape a consumer would rely on: a
blueprint with no milestones, an untitled milestone, or a milestone that
changes nothing is refused here, whatever the session claimed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from progettare.engine.run import atomic_write_json

BLUEPRINT_RECORD_VERSION = 2


class BlueprintRecordError(ValueError):
    """A blueprint progettare refuses to record, named loudly."""


@dataclass(frozen=True)
class Milestone:
    """One sequenced unit of work: a title and the changes it makes."""

    title: str
    changes: tuple[str, ...]


@dataclass(frozen=True)
class BlueprintRecord:
    """The structured plan, as data, not conversation."""

    milestones: tuple[Milestone, ...]
    data_model: tuple[str, ...]
    interfaces: tuple[str, ...]
    risks: tuple[str, ...]
    testable_criteria: tuple[str, ...]
    documentation_topics: tuple[str, ...]


def blueprint_record(record: BlueprintRecord) -> dict[str, Any]:
    """The versioned blueprint record, with the non-empty caps enforced.

    The stage's validate_blueprint is the first boundary; this one
    re-checks what a consumer of blueprint.json reads before it trusts
    the file: at least one milestone, every milestone titled, every
    milestone carrying at least one concrete change.
    """
    if not record.milestones:
        raise BlueprintRecordError("a blueprint records at least one milestone")
    for position, milestone in enumerate(record.milestones):
        if not milestone.title.strip():
            raise BlueprintRecordError(f"milestone {position} has an empty title")
        if not milestone.changes:
            raise BlueprintRecordError(f"milestone {position} records no changes")
        for change in milestone.changes:
            if not change.strip():
                raise BlueprintRecordError(
                    f"milestone {position} records an empty change"
                )
    return {
        "version": BLUEPRINT_RECORD_VERSION,
        "milestones": [
            {"title": milestone.title, "changes": list(milestone.changes)}
            for milestone in record.milestones
        ],
        "data_model": list(record.data_model),
        "interfaces": list(record.interfaces),
        "risks": list(record.risks),
        "testable_criteria": list(record.testable_criteria),
        "documentation_topics": list(record.documentation_topics),
    }


def write_blueprint(path: Path, record: dict[str, Any]) -> None:
    """Write the record atomically, readable only by its owner.

    Delegates to the engine's atomic writer: the rename is what survives
    a kill, so no consumer ever reads a half-written blueprint.
    """
    atomic_write_json(path, record)
