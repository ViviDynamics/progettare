"""Tests for ceremony sizing: the pure-code classification and its record.

Every test runs offline: sizing never touches a model, so the tests only
feed blueprint records and thresholds and check the derivation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from progettare.blueprint.size import (
    MILESTONE_LOOP,
    SINGLE_TURN,
    SIZE_RECORD_VERSION,
    SizeStageError,
    classify_size,
    write_size,
)

WRITTEN_AT = "2026-10-05T00:00:00Z"


def make_blueprint(milestone_count: int = 3, topic_count: int = 2) -> dict[str, Any]:
    return {
        "version": 1,
        "milestones": [
            {"title": f"m{n}", "changes": ["c"]} for n in range(milestone_count)
        ],
        "documentation_topics": [f"t{n}" for n in range(topic_count)],
    }


def classify(
    blueprint: dict[str, Any] | None = None,
    max_milestones: int = 3,
    min_topics: int = 2,
) -> dict[str, Any]:
    return classify_size(
        make_blueprint() if blueprint is None else blueprint,
        max_milestones,
        min_topics,
        WRITTEN_AT,
    )


def test_at_the_milestone_boundary_the_run_is_a_single_turn() -> None:
    record = classify(max_milestones=3)
    assert record["classification"] == SINGLE_TURN
    assert record["documenter"] is True


def test_above_the_boundary_the_run_is_a_milestone_loop() -> None:
    record = classify(max_milestones=2)
    assert record["classification"] == MILESTONE_LOOP


def test_below_the_documenter_threshold_no_documenter_pass_runs() -> None:
    record = classify(min_topics=3)
    assert record["documenter"] is False
    assert record["classification"] == SINGLE_TURN


def test_the_record_carries_the_derivation_inputs_and_the_stamp() -> None:
    record = classify(max_milestones=3, min_topics=2)
    assert record["derivation"] == {
        "milestone_count": 3,
        "documentation_topic_count": 2,
        "single_turn_max_milestones": 3,
        "documenter_min_topics": 2,
    }
    assert record["version"] == SIZE_RECORD_VERSION
    assert record["artifact"] == "size"
    assert record["artifact_version"] == 1
    assert record["progettare"]
    assert record["written_at"] == WRITTEN_AT


def test_the_same_inputs_produce_the_same_record() -> None:
    assert classify() == classify()


def test_a_malformed_blueprint_is_a_loud_failure() -> None:
    payload: Any = ["not", "a", "mapping"]
    with pytest.raises(SizeStageError) as raised:
        classify_size(payload, 3, 2, WRITTEN_AT)
    assert "not a JSON object" in str(raised.value)
    payload = {"milestones": [], "documentation_topics": "no"}
    with pytest.raises(SizeStageError) as raised:
        classify_size(payload, 3, 2, WRITTEN_AT)
    assert "documentation_topics" in str(raised.value)
    payload = {"documentation_topics": []}
    with pytest.raises(SizeStageError) as raised:
        classify_size(payload, 3, 2, WRITTEN_AT)
    assert "milestones" in str(raised.value)


def test_negative_thresholds_are_a_loud_failure() -> None:
    with pytest.raises(SizeStageError) as raised:
        classify(max_milestones=-1)
    assert "single_turn_max_milestones" in str(raised.value)
    with pytest.raises(SizeStageError) as raised:
        classify(min_topics=-1)
    assert "documenter_min_topics" in str(raised.value)


def test_write_size_round_trips(tmp_path: Path) -> None:
    record = classify()
    path = tmp_path / "size.json"
    write_size(path, record)
    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert json.loads(path.read_text(encoding="utf-8"))["classification"] == (
        SINGLE_TURN
    )
