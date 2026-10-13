"""Comment-thread participation: the receiver hears the conversation."""

from __future__ import annotations

import json
from typing import Any

from progettare.app import DeliveryLedger, WebhookConfig, webhook_response

SECRET = "s3cret"
OUTCOME: dict[str, Any] = {
    "status": "complete",
    "run_dir": "/repo/runs/0001",
    "artifacts": {},
}


def _signature(body: bytes) -> str:
    import hashlib
    import hmac

    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def payload_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode()


def commented(
    author: str = "owner",
    body: str = "@progettare[bot] please revise",
    number: int = 7,
    state: str = "open",
) -> dict[str, Any]:
    return {
        "action": "created",
        "issue": {"number": number, "state": state},
        "comment": {"user": {"login": author}, "body": body},
        "repository": {"full_name": "o/r", "owner": {"login": "owner"}},
    }


def config(**overrides: Any) -> WebhookConfig:
    return WebhookConfig(
        "s3cret", "/repo", "progettare[bot]", "progettare", **overrides
    )


def respond(
    payload: dict[str, Any],
    ledger: DeliveryLedger,
    seen: list[int],
    delivery: str = "d-1",
    cfg: WebhookConfig | None = None,
) -> tuple[int, dict[str, Any], list[str]]:
    """One comment delivery through the receiver; gh argv lands in `posted`."""
    body = payload_json(payload)
    posted: list[str] = []

    def ceremony(ref: str, path: str, revision: int) -> dict[str, Any]:
        seen.append(revision)
        return dict(OUTCOME)

    status, document = webhook_response(
        delivery,
        _signature(body),
        body,
        cfg if cfg is not None else config(),
        ledger,
        gh_call=lambda argv: posted.append(argv[-1]),
        ceremony=ceremony,
    )
    return status, document, posted


def test_a_maintainers_comment_revises_the_plan() -> None:
    seen: list[int] = []
    ledger = DeliveryLedger()
    status, document, _ = respond(commented(), ledger, seen)
    assert status == 200
    assert document == {"status": "complete"}
    assert seen == [1]


def test_the_bots_own_comment_never_triggers() -> None:
    seen: list[int] = []
    status, document, _ = respond(
        commented(author="progettare[bot]"), ledger=DeliveryLedger(), seen=seen
    )
    assert status == 200
    assert document == {"status": "ignored"}
    assert not seen


def test_an_unauthorized_authors_comment_is_ignored() -> None:
    seen: list[int] = []
    status, document, _ = respond(
        commented(author="random-drive-by"), DeliveryLedger(), seen
    )
    assert status == 200
    assert document == {"status": "ignored"}
    assert not seen


def test_a_configured_reviewer_triggers_where_the_owner_may_not() -> None:
    seen: list[int] = []
    cfg = config(reviewers={"alice"})
    status, document, _ = respond(
        commented(author="alice"), DeliveryLedger(), seen, cfg=cfg
    )
    assert status == 200
    assert document == {"status": "complete"}
    assert seen == [1]
    owner_status, owner_document, _ = respond(
        commented(author="owner"), DeliveryLedger(), seen, cfg=cfg
    )
    assert owner_document == {"status": "ignored"}
    assert seen == [1]


def test_a_comment_without_the_mention_is_ignored() -> None:
    seen: list[int] = []
    status, document, _ = respond(
        commented(body="I disagree with the plan entirely"), DeliveryLedger(), seen
    )
    assert status == 200
    assert document == {"status": "ignored"}
    assert not seen


def test_a_comment_on_a_closed_issue_is_ignored() -> None:
    seen: list[int] = []
    status, _, _ = respond(commented(state="closed"), DeliveryLedger(), seen)
    assert status == 200
    assert not seen


def test_revision_rounds_come_from_the_ledger_counter() -> None:
    seen: list[int] = []
    ledger = DeliveryLedger()
    for delivery in ("d-1", "d-2"):
        respond(commented(), ledger, seen, delivery=delivery)
    assert seen == [1, 2]


def test_the_round_cap_posts_a_note_and_starts_nothing() -> None:
    seen: list[int] = []
    ledger = DeliveryLedger()
    last_status = 0
    last_document: dict[str, Any] = {}
    last_posted: list[str] = []
    for delivery in ("d-1", "d-2", "d-3"):
        last_status, last_document, last_posted = respond(
            commented(), ledger, seen, delivery
        )
    assert seen == [1, 2]
    assert last_status == 200
    assert last_document == {"status": "capped"}
    assert any("exhausted" in p for p in last_posted)


def test_a_redelivered_capped_comment_answers_duplicate() -> None:
    seen: list[int] = []
    ledger = DeliveryLedger()
    for delivery in ("d-1", "d-2", "d-3"):
        respond(commented(), ledger, seen, delivery)
    before = len(seen)
    status, document, _ = respond(commented(), ledger, seen, "d-3")
    assert status == 200
    assert document == {"status": "duplicate"}
    assert len(seen) == before
