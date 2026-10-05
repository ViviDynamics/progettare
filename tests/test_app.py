"""The app's trigger core, tested offline with canned ceremonies."""

from __future__ import annotations

from typing import Any

from progettare.app import DeliveryLedger, handle_event, should_trigger

ASSIGNED: dict[str, Any] = {
    "issue": {
        "number": 7,
        "state": "open",
        "assignees": [{"login": "progettare[bot]"}],
        "labels": [{"name": "bug"}],
    },
    "repository": {"full_name": "o/r"},
}


def labeled() -> dict[str, Any]:
    event: dict[str, Any] = {
        "issue": {
            "number": 7,
            "state": "open",
            "assignees": [],
            "labels": [{"name": "progettare"}],
        },
        "repository": {"full_name": "o/r"},
    }
    return event


OUTCOME: dict[str, Any] = {
    "status": "complete",
    "run_dir": "/repo/runs/0001",
    "artifacts": {"milestones": [{"title": "first", "changes": ["a"]}]},
}


def test_an_assignment_to_the_app_login_triggers() -> None:
    assert should_trigger(ASSIGNED, "assigned")
    assert not should_trigger(ASSIGNED, "closed")


def test_an_assignment_to_someone_else_does_not_trigger() -> None:
    event: dict[str, Any] = {
        "issue": {
            "number": 7,
            "state": "open",
            "assignees": [{"login": "someone"}],
            "labels": [{"name": "bug"}],
        },
        "repository": {"full_name": "o/r"},
    }
    assert not should_trigger(event, "assigned")


def test_a_trigger_label_triggers() -> None:
    assert should_trigger(labeled(), "labeled")


def test_another_label_does_not_trigger() -> None:
    event: dict[str, Any] = {
        "issue": {
            "number": 7,
            "state": "open",
            "assignees": [],
            "labels": [{"name": "bug"}],
        },
        "repository": {"full_name": "o/r"},
    }
    assert not should_trigger(event, "labeled")


def test_a_closed_issue_never_triggers() -> None:
    event: dict[str, Any] = {
        "issue": {
            "number": 7,
            "state": "closed",
            "assignees": [{"login": "progettare[bot]"}],
            "labels": [{"name": "bug"}],
        },
        "repository": {"full_name": "o/r"},
    }
    assert not should_trigger(event, "assigned")


def test_one_run_per_trigger_event() -> None:
    calls: list[tuple[str, str]] = []

    def ceremony(ref: str, repo_path: str) -> dict[str, Any]:
        calls.append((ref, repo_path))
        return dict(OUTCOME)

    posted: list[str] = []
    ledger = DeliveryLedger()
    first = handle_event(
        "delivery-1",
        "assigned",
        ASSIGNED,
        ceremony,
        ledger,
        lambda body: posted.append(body),
        "/repo",
    )
    assert first["status"] == "complete"
    assert len(calls) == 1
    second = handle_event(
        "delivery-1",
        "assigned",
        ASSIGNED,
        ceremony,
        ledger,
        lambda body: posted.append(body),
        "/repo",
    )
    assert second["status"] == "duplicate"
    assert len(calls) == 1
    assert len(posted) == 1


def test_the_comment_carries_the_replay_artifact() -> None:
    posted: list[str] = []
    handle_event(
        "delivery-2",
        "labeled",
        labeled(),
        lambda ref, repo: dict(OUTCOME),
        DeliveryLedger(),
        lambda body: posted.append(body),
        "/repo",
    )
    assert len(posted) == 1
    assert "```json" in posted[0]
    assert "/repo/runs/0001" in posted[0]


def test_a_blocked_outcome_posts_the_questions() -> None:
    outcome: dict[str, Any] = {
        "status": "blocked",
        "run_dir": "/repo/runs/0002",
        "failing_stage": "intake",
        "detail": "a; b",
    }
    posted: list[str] = []
    handle_event(
        "delivery-3",
        "assigned",
        ASSIGNED,
        lambda ref, repo: outcome,
        DeliveryLedger(),
        lambda body: posted.append(body),
        "/repo",
    )
    assert "- a" in posted[0]
    assert "- b" in posted[0]
    assert "progettare blocked at intake" in posted[0]
