"""Reader slicing: the blueprint cut into exactly three reader briefs.

Pure code, like sizing: each downstream reader gets exactly its own
slice, and nothing the blueprint contains leaks across readers. The
implementer brief carries the milestones to implement, the QA brief the
testable criteria to verify, and the documenter brief the documentation
topics, but only when sizing turned the documenter on. The briefs
record is the versioned JSON contract orchestrators consume; breaking
changes bump its version and are documented here.
"""

from __future__ import annotations

import pathlib
from typing import Any

from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.run import atomic_write_json

BRIEFS_RECORD_VERSION = 1


class SliceStageError(ValueError):
    """A slice progettare refuses to derive, naming the key."""


READERS = ("implementer", "qa", "documenter")


def _array(blueprint: dict[str, Any], key: str) -> list[Any]:
    items = blueprint.get(key)
    if not isinstance(items, list):
        raise SliceStageError(f"the blueprint record has no {key} array")
    return items


def _reader_record(
    reader: str,
    brief: dict[str, Any],
    written_at: str,
    config_version: int,
) -> dict[str, Any]:
    return {
        "version": BRIEFS_RECORD_VERSION,
        "artifact": f"{reader}_brief",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "config_version": config_version,
        "written_at": written_at,
        "brief": brief,
    }


def slice_briefs(
    blueprint: dict[str, Any],
    size: dict[str, Any],
    written_at: str,
    config_version: int,
) -> dict[str, Any]:
    """Slice the validated blueprint into the three reader briefs.

    The blueprint and the size record are the validated artifacts the
    pipeline published; anything missing their arrays or the size
    record's documenter decision is a loud failure here rather than a
    silent default. The documenter brief exists only when sizing turned
    the documenter on, so the briefs directory carries exactly the
    readers the ceremony calls for.
    """
    if not isinstance(blueprint, dict):
        raise SliceStageError("the blueprint record is not a JSON object")
    if not isinstance(size, dict):
        raise SliceStageError("the size record is not a JSON object")
    milestones = _array(blueprint, "milestones")
    for position, milestone in enumerate(milestones):
        if not isinstance(milestone, dict):
            raise SliceStageError(f"milestones[{position}] is not an object")
        title = milestone.get("title")
        changes = milestone.get("changes")
        if not isinstance(title, str) or not title.strip():
            raise SliceStageError(
                f"milestones[{position}].title is not a nonempty string"
            )
        if not isinstance(changes, list) or not changes:
            raise SliceStageError(
                f"milestones[{position}].changes is not a nonempty array"
            )
    criteria = _array(blueprint, "testable_criteria")
    topics = _array(blueprint, "documentation_topics")
    documenter = size.get("documenter")
    if not isinstance(documenter, bool):
        raise SliceStageError("the size record has no documenter decision")
    briefs: dict[str, dict[str, Any]] = {
        "implementer": {
            "milestones": [
                {"title": milestone.get("title"), "changes": milestone.get("changes")}
                for milestone in milestones
            ]
        },
        "qa": {"testable_criteria": list(criteria)},
    }
    if documenter:
        briefs["documenter"] = {"topics": list(topics)}
    return {
        "version": BRIEFS_RECORD_VERSION,
        "artifact": "briefs",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "config_version": config_version,
        "written_at": written_at,
        "briefs": briefs,
    }


def brief_files(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map every brief's file path, relative to the run dir, to its record.

    The three reader briefs live as separate artifacts so each
    downstream reader receives exactly its own slice; this mapping is
    what the writer publishes and the replay audit recomputes.
    """
    written_at = record.get("written_at")
    if not isinstance(written_at, str) or not written_at:
        raise SliceStageError("the briefs record has no written_at")
    config_version = record.get("config_version")
    if not isinstance(config_version, int) or isinstance(config_version, bool):
        raise SliceStageError("the briefs record has no config_version")
    briefs = record.get("briefs")
    if not isinstance(briefs, dict) or not briefs:
        raise SliceStageError("the briefs record has no briefs mapping")
    files: dict[str, dict[str, Any]] = {}
    for reader in READERS:
        if reader in briefs:
            files[f"briefs/{reader}.json"] = _reader_record(
                reader, briefs[reader], written_at, config_version
            )
    unknown = sorted(set(briefs) - set(READERS), key=str)
    if unknown:
        raise SliceStageError(
            "the briefs record carries unknown reader(s): "
            + ", ".join(str(key) for key in unknown)
        )
    return files


def write_briefs(run_dir: pathlib.Path, record: dict[str, Any]) -> list[pathlib.Path]:
    """Write each brief under ``briefs/``, atomically and per reader.

    Delegates to the engine's atomic writer: the rename is what survives
    a kill, so no consumer ever reads a half-written brief.
    """
    (run_dir / "briefs").mkdir(exist_ok=True)
    written: list[pathlib.Path] = []
    for name, brief_record in brief_files(record).items():
        path = run_dir / name
        atomic_write_json(path, brief_record)
        written.append(path)
    return written
