"""The GitHub App's trigger core: one run per event, artifacts posted back.

An issue assigned to the app's login, or labeled with the trigger label,
starts exactly one ceremony run; the run's outcome is posted as an issue
comment where the card lives, with the replay artifact attached in a
fenced JSON block. The app's login and trigger label are configuration,
not code, and the delivery ledger is what makes redeliveries harmless.
Deployment and App registration are the app-specific stories.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

APP_LOGIN = "progettare[bot]"
TRIGGER_LABEL = "progettare"


class DeliveryLedger:
    """One run per trigger event, keyed by the delivery GUID.

    The ledger records the delivery before the run starts, so a
    redelivery that arrives while the run is still going finds it here
    and starts nothing. A persistent ledger is the deployment story's
    business; this one is the process-local truth.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def seen(self, delivery_id: str) -> bool:
        return delivery_id in self._seen

    def record(self, delivery_id: str) -> None:
        self._seen.add(delivery_id)


def should_trigger(event: Mapping[str, Any], action: str) -> bool:
    """Whether this event asks the app to run: an open issue, assigned
    to the app's login or labeled with the trigger label."""
    if action not in ("assigned", "labeled"):
        return False
    issue = event.get("issue")
    if not isinstance(issue, dict) or issue.get("state") != "open":
        return False
    assignees = issue.get("assignees")
    if action == "assigned":
        if not isinstance(assignees, list):
            return False
        return any(
            isinstance(a, dict) and a.get("login") == APP_LOGIN for a in assignees
        )
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return False
    return any(
        isinstance(label, dict) and label.get("name") == TRIGGER_LABEL
        for label in labels
    )


def _lead(outcome: Mapping[str, Any]) -> str:
    status = outcome.get("status")
    if status == "complete":
        return "progettare completed the blueprint:"
    stage = outcome.get("failing_stage", "unknown")
    return f"progettare {status} at {stage}:"


def comment_body(outcome: Mapping[str, Any]) -> str:
    """The comment for one run: a lead, the blocked questions if any,
    and the outcome document verbatim as the replay artifact."""
    lines = [_lead(outcome)]
    if outcome.get("status") == "blocked" and isinstance(outcome.get("detail"), str):
        questions = [
            question.strip()
            for question in str(outcome["detail"]).split(";")
            if question.strip()
        ]
        lines.extend(f"- {question}" for question in questions)
    replay = json.dumps(dict(outcome), indent=2, sort_keys=True)
    lines.append("```json")
    lines.append(replay)
    lines.append("```")
    return "\n".join(lines)


def handle_event(
    delivery_id: str,
    action: str,
    event: Mapping[str, Any],
    ceremony: Callable[[str, str], dict[str, Any]],
    ledger: DeliveryLedger,
    poster: Callable[[str], None],
    repo_path: str,
) -> dict[str, Any]:
    """One delivery in, at most one run out.

    The delivery is recorded before anything else, so a redelivery
    finds it here and starts nothing; the ceremony's outcome document
    is posted where the card lives. The repo path is the app's
    configuration: a webhook names no local filesystem.
    """
    if ledger.seen(delivery_id):
        return {"status": "duplicate"}
    ledger.record(delivery_id)
    repository = event.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    if not isinstance(full_name, str) or not full_name:
        return {"status": "skipped", "reason": "the event carries no repository"}
    ref = f"{full_name}#{event['issue']['number']}"
    outcome = ceremony(ref, repo_path)
    poster(comment_body(outcome))
    return {"status": str(outcome.get("status"))}
