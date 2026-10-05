"""Tests for the versioned blueprint.json record and its enforced caps."""

from __future__ import annotations

import json
from typing import Any

import pytest

from progettare.blueprint.artifact import (
    BLUEPRINT_RECORD_VERSION,
    BlueprintRecord,
    BlueprintRecordError,
    Milestone,
    blueprint_record,
    write_blueprint,
)

MILESTONE = Milestone(title="Survey stage", changes=("Add the survey session loop",))
RECORD = BlueprintRecord(
    milestones=(MILESTONE,),
    data_model=("answers keyed by question number",),
    interfaces=("run_blueprint_stage(intake, survey, ...)",),
    risks=("the model drifts off schema",),
    testable_criteria=("a valid payload writes the artifact",),
    documentation_topics=("the blueprint stage contract",),
)


def test_record_is_versioned_and_ordered() -> None:
    document = blueprint_record(RECORD)
    assert document["version"] == BLUEPRINT_RECORD_VERSION
    assert document["milestones"] == [
        {"title": "Survey stage", "changes": ["Add the survey session loop"]}
    ]
    assert document["data_model"] == ["answers keyed by question number"]
    assert document["interfaces"] == ["run_blueprint_stage(intake, survey, ...)"]
    assert document["risks"] == ["the model drifts off schema"]
    assert document["testable_criteria"] == ["a valid payload writes the artifact"]
    assert document["documentation_topics"] == ["the blueprint stage contract"]


@pytest.mark.parametrize(
    "record",
    [
        BlueprintRecord(
            milestones=(),
            data_model=(),
            interfaces=(),
            risks=(),
            testable_criteria=(),
            documentation_topics=(),
        ),
        BlueprintRecord(
            milestones=(Milestone(title="  ", changes=("x",)),),
            data_model=(),
            interfaces=(),
            risks=(),
            testable_criteria=(),
            documentation_topics=(),
        ),
        BlueprintRecord(
            milestones=(Milestone(title="t", changes=()),),
            data_model=(),
            interfaces=(),
            risks=(),
            testable_criteria=(),
            documentation_topics=(),
        ),
        BlueprintRecord(
            milestones=(Milestone(title="t", changes=("  ",)),),
            data_model=(),
            interfaces=(),
            risks=(),
            testable_criteria=(),
            documentation_topics=(),
        ),
    ],
)
def test_record_refuses_a_blueprint_that_cannot_exist(
    record: BlueprintRecord,
) -> None:
    with pytest.raises(BlueprintRecordError):
        blueprint_record(record)


def test_write_blueprint_writes_atomically_readable_json(tmp_path: Any) -> None:
    path = tmp_path / "blueprint.json"
    write_blueprint(path, blueprint_record(RECORD))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == BLUEPRINT_RECORD_VERSION
    assert document["milestones"][0]["title"] == "Survey stage"
