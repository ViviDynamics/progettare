"""Tests for reader slicing: the three briefs and their versioned contract.

Every test runs offline: slicing never touches a model, so the tests
only feed blueprint and size records and check the derivation, the
per-reader files, and the loud failures.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from progettare.blueprint.slices import (
    BRIEFS_RECORD_VERSION,
    SliceStageError,
    brief_files,
    slice_briefs,
    write_briefs,
)

WRITTEN_AT = "20261005T000000Z"


def make_blueprint(milestone_count: int = 3) -> dict[str, Any]:
    return {
        "version": 1,
        "milestones": [
            {"title": f"m{n}", "changes": [f"c{n}"]} for n in range(milestone_count)
        ],
        "testable_criteria": ["t0", "t1"],
        "documentation_topics": ["d0", "d1", "d2"],
    }


def make_size(documenter: bool = True) -> dict[str, Any]:
    return {"version": 1, "documenter": documenter}


def slice(
    blueprint: dict[str, Any] | None = None,
    size: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return slice_briefs(
        make_blueprint() if blueprint is None else blueprint,
        make_size() if size is None else size,
        WRITTEN_AT,
        1,
    )


def test_the_implementer_brief_carries_the_milestones_only() -> None:
    record = slice()
    assert record["briefs"]["implementer"] == {
        "milestones": [
            {"title": "m0", "changes": ["c0"]},
            {"title": "m1", "changes": ["c1"]},
            {"title": "m2", "changes": ["c2"]},
        ]
    }
    assert "testable_criteria" not in record["briefs"]["implementer"]


def test_the_qa_brief_carries_the_testable_criteria() -> None:
    assert slice()["briefs"]["qa"] == {"testable_criteria": ["t0", "t1"]}


def test_the_documenter_brief_is_conditional_on_sizing() -> None:
    assert slice()["briefs"]["documenter"] == {"topics": ["d0", "d1", "d2"]}
    record = slice(size=make_size(documenter=False))
    assert "documenter" not in record["briefs"]


def test_the_record_is_stamped_and_versioned() -> None:
    record = slice()
    assert record["version"] == BRIEFS_RECORD_VERSION
    assert record["artifact"] == "briefs"
    assert record["artifact_version"] == 1
    assert record["progettare"]
    assert record["config_version"] == 1
    assert record["written_at"] == WRITTEN_AT


def test_the_same_inputs_produce_the_same_record() -> None:
    assert slice() == slice()


def test_brief_files_maps_exactly_the_ceremony_readers() -> None:
    files = brief_files(slice())
    assert sorted(files) == [
        "briefs/documenter.json",
        "briefs/implementer.json",
        "briefs/qa.json",
    ]
    off = brief_files(slice(size=make_size(documenter=False)))
    assert sorted(off) == ["briefs/implementer.json", "briefs/qa.json"]
    assert off["briefs/qa.json"]["artifact"] == "qa_brief"


def test_write_briefs_writes_one_file_per_reader(tmp_path: pathlib.Path) -> None:
    written = write_briefs(tmp_path, slice())
    assert sorted(path.name for path in written) == [
        "documenter.json",
        "implementer.json",
        "qa.json",
    ]
    on_disk = json.loads((tmp_path / "briefs" / "qa.json").read_text(encoding="utf-8"))
    assert on_disk == brief_files(slice())["briefs/qa.json"]


def test_a_malformed_blueprint_is_a_loud_failure() -> None:
    payload: Any = ["not", "a", "mapping"]
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(payload, make_size(), WRITTEN_AT, 1)
    assert "not a JSON object" in str(raised.value)
    payload = {"milestones": "no"}
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(payload, make_size(), WRITTEN_AT, 1)
    assert "milestones" in str(raised.value)
    payload = {"milestones": [], "testable_criteria": "no"}
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(payload, make_size(), WRITTEN_AT, 1)
    assert "testable_criteria" in str(raised.value)
    payload = make_blueprint()
    payload["milestones"][1] = {"title": "m1", "changes": "no"}
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(payload, make_size(), WRITTEN_AT, 1)
    assert "milestones[1].changes" in str(raised.value)


def test_a_malformed_size_record_is_a_loud_failure() -> None:
    size_payload: Any = "no"
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(make_blueprint(), size_payload, WRITTEN_AT, 1)
    assert "size record is not a JSON object" in str(raised.value)
    with pytest.raises(SliceStageError) as raised:
        slice_briefs(make_blueprint(), {"documenter": "yes"}, WRITTEN_AT, 1)
    assert "documenter decision" in str(raised.value)
    with pytest.raises(SliceStageError) as raised:
        brief_files({"briefs": {"implementer": {}}, "written_at": WRITTEN_AT})
    assert "config_version" in str(raised.value)
    with pytest.raises(SliceStageError) as raised:
        brief_files(
            {
                "briefs": {"implementer": {}, "chaos": {}},
                "written_at": WRITTEN_AT,
                "config_version": 1,
            }
        )
    assert "chaos" in str(raised.value)
