"""Ceremony sizing: pure code that classifies the validated blueprint.

The classification is a deterministic function of the blueprint's shape
and the configured thresholds, never of a model's judgment, so the same
blueprint and the same config always produce the same ``size.json``. A
replay recomputes it with no model and no network and compares bytes.
"""

from __future__ import annotations

import pathlib
from typing import Any

from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.run import atomic_write_json

SIZE_RECORD_VERSION = 1

SINGLE_TURN = "single_turn"
MILESTONE_LOOP = "milestone_loop"


class SizeStageError(ValueError):
    """A size classification progettare refuses to derive, naming the key."""


def _count(blueprint: dict[str, Any], key: str) -> int:
    items = blueprint.get(key)
    if not isinstance(items, list):
        raise SizeStageError(f"the blueprint record has no {key} array")
    return len(items)


def _threshold(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SizeStageError(f"{name} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise SizeStageError(f"{name} must not be negative, got {value}")
    return value


def classify_size(
    blueprint: dict[str, Any],
    single_turn_max_milestones: int,
    documenter_min_topics: int,
    written_at: str,
) -> dict[str, Any]:
    """Classify the ceremony from the blueprint's shape alone.

    The blueprint is the validated record the blueprint stage published;
    anything missing its milestone or documentation-topic arrays is a
    loud failure here rather than a silent default. The thresholds are
    the config values, and both the classification and the inputs that
    produced it are recorded, so a replay can recompute and compare.
    """
    if not isinstance(blueprint, dict):
        raise SizeStageError("the blueprint record is not a JSON object")
    milestone_count = _count(blueprint, "milestones")
    topic_count = _count(blueprint, "documentation_topics")
    _threshold("size.single_turn_max_milestones", single_turn_max_milestones)
    _threshold("size.documenter_min_topics", documenter_min_topics)
    classification = (
        SINGLE_TURN if milestone_count <= single_turn_max_milestones else MILESTONE_LOOP
    )
    return {
        "version": SIZE_RECORD_VERSION,
        "artifact": "size",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": written_at,
        "classification": classification,
        "documenter": topic_count >= documenter_min_topics,
        "derivation": {
            "milestone_count": milestone_count,
            "documentation_topic_count": topic_count,
            "single_turn_max_milestones": single_turn_max_milestones,
            "documenter_min_topics": documenter_min_topics,
        },
    }


def write_size(path: pathlib.Path, record: dict[str, Any]) -> None:
    """Write the size record atomically, readable only by its owner.

    Delegates to the engine's atomic writer: the rename is what survives
    a kill, so no consumer ever reads a half-written size classification.
    """
    atomic_write_json(path, record)
