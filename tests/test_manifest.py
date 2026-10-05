"""Tests for the run manifest: stamps, config digest, and stage ledger.

Every test runs offline: the manifest is pure code over a Config and the
ledger a caller assembled from stage results, so no nare and no network
are involved.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from progettare.config import Config, ModelRail
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.manifest import (
    RUN_MANIFEST_VERSION,
    ManifestError,
    StageLedger,
    config_digest,
    run_manifest,
    write_run_manifest,
)
from progettare.survey.nare import NareUsage

RAIL = ModelRail(
    provider="openai", model="gpt-survey", base_url="http://127.0.0.1:8000"
)


def make_config(single_turn: int = 8) -> Config:
    return Config(
        survey_max_questions=5,
        survey_per_question_command_budget=8,
        budget_survey_stage_tokens=1200,
        budget_blueprint_stage_tokens=1200,
        budget_run_max_tokens=10000,
        size_single_turn_max_milestones=single_turn,
        size_documenter_min_topics=0,
        survey_rail=RAIL,
        blueprint_rail=RAIL,
    )


STAGES = {
    "survey": StageLedger(
        sessions=("q1-session.json", "q2-session.json"),
        usage=NareUsage(input_tokens=20, output_tokens=10, total_tokens=30),
    ),
    "blueprint": StageLedger(
        sessions=("blueprint-session.json",),
        usage=NareUsage(input_tokens=100, output_tokens=50, total_tokens=150),
    ),
    "size": StageLedger(),
}


def manifest(
    status: str = "complete",
    failing_stage: str | None = None,
    stages: dict[str, StageLedger] | None = None,
    failing_reason: str | None = None,
) -> dict[str, Any]:
    return run_manifest(
        make_config(),
        status,
        "20261005T000000Z",
        STAGES if stages is None else stages,
        failing_stage=failing_stage,
        failing_reason=failing_reason,
    )


def test_the_digest_is_deterministic_and_config_sensitive() -> None:
    assert config_digest(make_config()) == config_digest(make_config())
    assert config_digest(make_config()) != config_digest(make_config(3))


def test_the_complete_manifest_stamps_the_run() -> None:
    document = manifest()
    assert document["version"] == RUN_MANIFEST_VERSION
    assert document["artifact"] == "run"
    assert document["artifact_version"] == ARTIFACT_VERSION
    assert document["progettare"] == PROGETTARE_VERSION
    assert document["config_digest"] == config_digest(make_config())
    assert document["written_at"] == "20261005T000000Z"
    assert document["status"] == "complete"
    assert document["failing_stage"] is None
    assert document["failing_reason"] is None


def test_the_ledger_names_sessions_and_usage_per_stage() -> None:
    document = manifest()
    assert list(document["stages"]) == ["blueprint", "size", "survey"]
    assert document["stages"]["survey"] == {
        "sessions": ["q1-session.json", "q2-session.json"],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
        },
    }
    assert document["stages"]["size"] == {
        "sessions": [],
        "usage": None,
    }


def test_a_partial_run_names_the_stage_that_stopped_it_and_why() -> None:
    failed = manifest("failed", "blueprint", failing_reason="the validation error")
    assert failed["status"] == "failed"
    assert failed["failing_stage"] == "blueprint"
    assert failed["failing_reason"] == "the validation error"
    blocked = manifest(
        "blocked", "survey", failing_reason="the question went unanswered"
    )
    assert blocked["status"] == "blocked"
    assert blocked["failing_stage"] == "survey"
    assert blocked["failing_reason"] == "the question went unanswered"


def test_a_manifest_refuses_contradictions() -> None:
    with pytest.raises(ManifestError) as raised:
        manifest("aborted", None)
    assert "is not one the manifest records" in str(raised.value)
    with pytest.raises(ManifestError) as raised:
        manifest("complete", "survey")
    assert "names no failing stage" in str(raised.value)
    with pytest.raises(ManifestError) as raised:
        manifest("failed", None)
    assert "names the stage that stopped it" in str(raised.value)
    with pytest.raises(ManifestError) as raised:
        manifest("complete", None, failing_reason="nobody stopped anything")
    assert "names no failing stage" in str(raised.value)
    with pytest.raises(ManifestError) as raised:
        manifest("failed", "blueprint")
    assert "names the reason it stopped" in str(raised.value)
    with pytest.raises(ManifestError) as raised:
        manifest("failed", "blueprint", failing_reason="   ")
    assert "names the reason it stopped" in str(raised.value)


def test_the_manifest_writes_atomically_and_round_trips(
    tmp_path: pathlib.Path,
) -> None:
    written = write_run_manifest(tmp_path, manifest())
    assert written == tmp_path / "run.json"
    on_disk: Any = json.loads(written.read_text(encoding="utf-8"))
    assert on_disk == manifest()
