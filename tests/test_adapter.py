"""The conductor adapter, tested against the versioned contract alone."""

from __future__ import annotations

from typing import Any

import pytest

from progettare.adapter import AdapterError, card_to_input, dispatch_payloads
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION

BRIEFS: dict[str, Any] = {
    "version": 1,
    "artifact": "briefs",
    "artifact_version": ARTIFACT_VERSION,
    "progettare": PROGETTARE_VERSION,
    "config_version": 1,
    "written_at": "20261005T000000Z",
    "briefs": {
        "implementer": {
            "milestones": [
                {"title": "first", "changes": ["a", "b"]},
                {"title": "second", "changes": ["c"]},
            ]
        },
        "qa": {"testable_criteria": ["works", "does not break"]},
        "documenter": {"topics": ["how"]},
    },
}


def test_a_card_context_maps_to_the_intake_input() -> None:
    assert card_to_input({"repo": "o/r", "number": 7, "repo_path": "/repo"}) == {
        "ref": "o/r#7",
        "repo_path": "/repo",
    }


def test_a_card_missing_its_number_is_refused() -> None:
    with pytest.raises(AdapterError) as raised:
        card_to_input({"repo": "o/r", "repo_path": "/repo"})
    assert "number" in str(raised.value)


def test_a_card_with_an_empty_repo_path_is_refused() -> None:
    with pytest.raises(AdapterError) as raised:
        card_to_input({"repo": "o/r", "number": 7, "repo_path": "  "})
    assert "repo_path" in str(raised.value)


def test_briefs_cut_into_one_payload_per_milestone() -> None:
    payloads = dispatch_payloads(BRIEFS)
    assert [p["milestone"]["title"] for p in payloads] == ["first", "second"]
    assert payloads[0]["milestone"] == {"title": "first", "changes": ["a", "b"]}
    assert payloads[0]["criteria"] == ["works", "does not break"]
    assert payloads[0]["topics"] == ["how"]


def test_payloads_carry_the_versions_they_were_cut_with() -> None:
    for payload in dispatch_payloads(BRIEFS):
        assert payload["artifact_version"] == ARTIFACT_VERSION
        assert payload["progettare"] == PROGETTARE_VERSION
        assert payload["artifact"] == "dispatch_payload"


def test_a_briefs_record_from_another_contract_version_is_refused() -> None:
    older = {**BRIEFS, "artifact_version": ARTIFACT_VERSION - 1}
    with pytest.raises(AdapterError) as raised:
        dispatch_payloads(older)
    assert str(ARTIFACT_VERSION - 1) in str(raised.value)
    assert str(ARTIFACT_VERSION) in str(raised.value)


def test_a_briefs_record_without_its_artifact_version_is_refused() -> None:
    naked = {"version": 1, "artifact": "briefs", "briefs": BRIEFS["briefs"]}
    with pytest.raises(AdapterError) as raised:
        dispatch_payloads(naked)
    assert "artifact_version" in str(raised.value)


def test_a_documenter_off_briefs_record_cuts_empty_topics() -> None:
    record = {key: value for key, value in BRIEFS.items() if key != "briefs"}
    record["briefs"] = {
        "implementer": BRIEFS["briefs"]["implementer"],
        "qa": BRIEFS["briefs"]["qa"],
    }
    payloads = dispatch_payloads(record)
    assert payloads[0]["topics"] == []
