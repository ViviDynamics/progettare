"""Tests for the replay audit: recompute in code, compare bytes.

Every test runs offline: replay takes no runner seam at all, so no model
and no network are involved by construction, and the tests only build
run directories and compare.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from progettare.blueprint.size import classify_size, write_size
from progettare.config import Config, ModelRail
from progettare.engine.replay import ReplayError, replay_run

RAIL = ModelRail(provider="openai", model="m", base_url=None)
CONFIG = Config(
    survey_max_questions=5,
    survey_per_question_command_budget=8,
    budget_survey_stage_tokens=1200,
    budget_blueprint_stage_tokens=1200,
    budget_run_max_tokens=10000,
    size_single_turn_max_milestones=3,
    size_documenter_min_topics=2,
    survey_rail=RAIL,
    blueprint_rail=RAIL,
)
WRITTEN_AT = "20261005T000000Z"


def make_blueprint(milestone_count: int = 3) -> dict[str, Any]:
    return {
        "version": 1,
        "milestones": [
            {"title": f"m{n}", "changes": ["c"]} for n in range(milestone_count)
        ],
        "documentation_topics": ["t0", "t1"],
    }


def make_run_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    blueprint = make_blueprint()
    (tmp_path / "blueprint.json").write_text(
        json.dumps(blueprint, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    record = classify_size(
        blueprint,
        CONFIG.size_single_turn_max_milestones,
        CONFIG.size_documenter_min_topics,
        WRITTEN_AT,
        CONFIG.config_version,
    )
    write_size(tmp_path / "size.json", record)
    return tmp_path


def test_a_faithful_run_dir_replays_byte_identical(tmp_path: pathlib.Path) -> None:
    make_run_dir(tmp_path)
    result = replay_run(tmp_path, CONFIG)
    assert result.identical is True
    assert result.first_divergence is None
    assert result.recomputed["size.json"]["classification"] == "single_turn"


def test_a_tampered_classification_is_named(tmp_path: pathlib.Path) -> None:
    make_run_dir(tmp_path)
    size_path = tmp_path / "size.json"
    record: Any = json.loads(size_path.read_text(encoding="utf-8"))
    record["classification"] = "milestone_loop"
    size_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = replay_run(tmp_path, CONFIG)
    assert result.identical is False
    assert result.first_divergence == "classification differs"


def test_a_tampered_derivation_is_named_by_its_path(
    tmp_path: pathlib.Path,
) -> None:
    make_run_dir(tmp_path)
    size_path = tmp_path / "size.json"
    record: Any = json.loads(size_path.read_text(encoding="utf-8"))
    record["derivation"]["milestone_count"] = 99
    size_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = replay_run(tmp_path, CONFIG)
    assert result.identical is False
    assert result.first_divergence == "derivation.milestone_count differs"


def test_an_extra_stored_key_is_named(tmp_path: pathlib.Path) -> None:
    make_run_dir(tmp_path)
    size_path = tmp_path / "size.json"
    record: Any = json.loads(size_path.read_text(encoding="utf-8"))
    record["extra"] = "suspicious"
    size_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = replay_run(tmp_path, CONFIG)
    assert result.identical is False
    assert result.first_divergence == "extra is absent from the recomputed record"


def test_matching_content_with_differing_bytes_is_a_divergence(
    tmp_path: pathlib.Path,
) -> None:
    make_run_dir(tmp_path)
    size_path = tmp_path / "size.json"
    record = json.loads(size_path.read_text(encoding="utf-8"))
    size_path.write_text(json.dumps(record), encoding="utf-8")
    result = replay_run(tmp_path, CONFIG)
    assert result.identical is False
    assert result.first_divergence == "size.json content matches but its bytes differ"


def test_missing_files_are_loud_failures(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ReplayError) as raised:
        replay_run(tmp_path, CONFIG)
    assert "blueprint.json" in str(raised.value)
    (tmp_path / "blueprint.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReplayError) as raised:
        replay_run(tmp_path, CONFIG)
    assert "size.json" in str(raised.value)


def test_a_written_at_missing_from_the_stored_record_is_a_loud_failure(
    tmp_path: pathlib.Path,
) -> None:
    make_run_dir(tmp_path)
    size_path = tmp_path / "size.json"
    record: Any = json.loads(size_path.read_text(encoding="utf-8"))
    del record["written_at"]
    size_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ReplayError) as raised:
        replay_run(tmp_path, CONFIG)
    assert "no written_at" in str(raised.value)
