"""Tests for the reader briefs: the slices, the files, and the result.

Every test runs offline and pure: the stage reads the two artifacts the
run already holds and slices them by code, so no nare binary, no model
call, and no network are involved.
"""

import json
import pathlib
from typing import Any

import pytest

from progettare.blueprint.artifact import write_blueprint
from progettare.blueprint.size import classify_size, write_size
from progettare.briefs import (
    BriefsError,
    DocumenterBrief,
    ImplementerBrief,
    QaBrief,
    run_briefs_stage,
    slice_blueprint,
)
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION

WRITTEN_AT = "2026-10-05T06:00:00Z"
READ_AT = "2026-10-05T06:30:00Z"


def a_blueprint() -> dict[str, Any]:
    return {
        "version": 1,
        "milestones": [
            {"title": "first", "changes": ["add the reader", "wire the run dir"]},
            {"title": "second", "changes": ["print the result"]},
        ],
        "data_model": ["the brief record"],
        "interfaces": ["run_briefs_stage"],
        "risks": ["a skipped documenter pass reads as a missing file"],
        "testable_criteria": ["the reader slices three briefs", "the result is typed"],
        "documentation_topics": ["the reader contract", "how briefs map to criteria"],
    }


def a_stamped_blueprint() -> dict[str, Any]:
    return {
        "artifact": "blueprint",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": WRITTEN_AT,
        **a_blueprint(),
    }


def write_inputs(tmp_path: pathlib.Path, documenter: bool = True) -> None:
    write_blueprint(tmp_path / "blueprint.json", a_stamped_blueprint())
    record = classify_size(a_blueprint(), 1, 1, WRITTEN_AT, 1)
    record["documenter"] = documenter
    write_size(tmp_path / "size.json", record)


def test_the_implementer_brief_carries_the_milestones_only() -> None:
    briefs = slice_blueprint(a_blueprint(), True)
    assert isinstance(briefs[0], ImplementerBrief)
    assert briefs[0].milestones == tuple(
        {"title": milestone["title"], "changes": milestone["changes"]}
        for milestone in a_blueprint()["milestones"]
    )


def test_the_qa_brief_quotes_each_criterion_verbatim() -> None:
    qa = slice_blueprint(a_blueprint(), True)[1]
    assert isinstance(qa, QaBrief)
    assert qa.criteria == (
        {"index": 1, "criterion": "the reader slices three briefs"},
        {"index": 2, "criterion": "the result is typed"},
    )


def test_the_documenter_brief_carries_the_topics() -> None:
    briefs = slice_blueprint(a_blueprint(), True)
    assert isinstance(briefs[2], DocumenterBrief)
    assert briefs[2].topics == tuple(a_blueprint()["documentation_topics"])


def test_the_documenter_off_path_writes_two_files(tmp_path: pathlib.Path) -> None:
    write_inputs(tmp_path, documenter=False)
    result = run_briefs_stage(tmp_path, READ_AT)
    names = sorted(child.name for child in (tmp_path / "briefs").iterdir())
    assert names == ["implementer.json", "qa.json"]
    assert result["documenter"] is False
    assert "documenter" not in result["briefs"]


def test_the_result_is_versioned_and_names_the_decision(
    tmp_path: pathlib.Path,
) -> None:
    write_inputs(tmp_path)
    result = run_briefs_stage(tmp_path, READ_AT)
    assert result["schema_version"] == 1
    assert result["documenter"] is True
    assert set(result["briefs"]) == {"implementer", "qa", "documenter"}


def test_the_written_files_parse_back_stamped(tmp_path: pathlib.Path) -> None:
    write_inputs(tmp_path)
    run_briefs_stage(tmp_path, READ_AT)
    for name in ("implementer", "qa", "documenter"):
        payload = json.loads(
            (tmp_path / "briefs" / f"{name}.json").read_text(encoding="utf-8")
        )
        assert payload["artifact"] == "brief"
        assert payload["artifact_version"] == 1
        assert payload["written_at"] == READ_AT


def test_a_missing_blueprint_fails_the_stage_loudly(tmp_path: pathlib.Path) -> None:
    write_inputs(tmp_path)
    (tmp_path / "blueprint.json").unlink()
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "blueprint.json" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_a_missing_size_record_fails_the_stage_loudly(tmp_path: pathlib.Path) -> None:
    write_blueprint(tmp_path / "blueprint.json", a_stamped_blueprint())
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "size.json" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_an_unstamped_blueprint_fails_the_stage_loudly(tmp_path: pathlib.Path) -> None:
    write_blueprint(tmp_path / "blueprint.json", a_blueprint())
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "artifact" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_an_invalid_blueprint_fails_the_stage_loudly(tmp_path: pathlib.Path) -> None:
    write_inputs(tmp_path)
    payload = a_stamped_blueprint()
    payload["milestones"] = []
    (tmp_path / "blueprint.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "milestones" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_a_non_boolean_documenter_fails_the_stage_loudly(
    tmp_path: pathlib.Path,
) -> None:
    write_inputs(tmp_path)
    record = json.loads((tmp_path / "size.json").read_text(encoding="utf-8"))
    record["documenter"] = "yes"
    (tmp_path / "size.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "documenter" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_an_unknown_classification_fails_the_stage_loudly(
    tmp_path: pathlib.Path,
) -> None:
    write_inputs(tmp_path)
    record = json.loads((tmp_path / "size.json").read_text(encoding="utf-8"))
    record["classification"] = "huge"
    (tmp_path / "size.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BriefsError) as raised:
        run_briefs_stage(tmp_path, READ_AT)
    assert "classification" in str(raised.value)
    assert not (tmp_path / "briefs").exists()


def test_two_runs_agree_byte_for_byte(tmp_path: pathlib.Path) -> None:
    write_inputs(tmp_path)
    first = run_briefs_stage(tmp_path, READ_AT)
    second = run_briefs_stage(tmp_path, READ_AT)
    assert first == second
