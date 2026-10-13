"""The app's trigger core, tested offline with canned ceremonies."""

from __future__ import annotations

from typing import Any

import pytest

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


def _signature(secret: str, body: bytes) -> str:
    import hashlib
    import hmac

    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _assigned_body() -> bytes:
    import json as jsonlib

    event = {
        "action": "assigned",
        "issue": {
            "number": 7,
            "state": "open",
            "assignees": [{"login": "progettare[bot]"}],
            "labels": [{"name": "bug"}],
        },
        "repository": {"full_name": "o/r"},
    }
    return jsonlib.dumps(event).encode()


def test_a_missing_delivery_id_is_refused() -> None:
    from progettare.app import WebhookConfig, webhook_response

    code, response = webhook_response(
        None, "sha256=x", b"{}", WebhookConfig("s", "/repo"), DeliveryLedger()
    )
    assert code == 400


def test_a_bad_signature_is_refused_before_parsing() -> None:
    from progettare.app import WebhookConfig, webhook_response

    code, response = webhook_response(
        "d1",
        "sha256=deadbeef",
        b"not json",
        WebhookConfig("s", "/repo"),
        DeliveryLedger(),
    )
    assert code == 401


def test_a_verified_trigger_event_runs_and_posts_one_comment() -> None:
    from progettare.app import WebhookConfig, webhook_response

    body = _assigned_body()
    gh_calls: list[list[str]] = []
    code, response = webhook_response(
        "d2",
        _signature("s", body),
        body,
        WebhookConfig("s", "/repo"),
        DeliveryLedger(),
        gh_calls.append,
        lambda ref, repo: {"status": "complete", "issue": ref},
    )
    assert code == 200
    assert response["status"] == "complete"
    assert len(gh_calls) == 1
    argv = gh_calls[0]
    assert argv[2] == "repos/o/r/issues/7/comments"
    assert "```json" in argv[4]


def test_a_redelivered_delivery_starts_no_second_run() -> None:
    from progettare.app import WebhookConfig, webhook_response

    body = _assigned_body()
    signature = _signature("s", body)
    gh_calls: list[list[str]] = []
    ledger = DeliveryLedger()
    webhook_response(
        "d3",
        signature,
        body,
        WebhookConfig("s", "/repo"),
        ledger,
        gh_calls.append,
        lambda ref, repo: {"status": "complete", "issue": ref},
    )
    code, response = webhook_response(
        "d3",
        signature,
        body,
        WebhookConfig("s", "/repo"),
        ledger,
        gh_calls.append,
        lambda ref, repo: {"status": "complete", "issue": ref},
    )
    assert code == 200
    assert response["status"] == "duplicate"
    assert len(gh_calls) == 1


def test_the_default_ceremony_reads_with_the_rotated_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import progettare.app as app_module
    import progettare.mcp as mcp
    from progettare.app import WebhookConfig, webhook_response
    from progettare.auth import InstallationAuth

    body = _assigned_body()
    captured: dict[str, Any] = {}

    def fake_default_ceremony(
        ref: Any, repo_path: Any, runs_base: Any = None, gh_token: Any = None
    ) -> dict[str, Any]:
        captured["gh_token"] = gh_token
        return {"status": "complete"}

    def fake_api(method: str, path: str, jwt: Any = None) -> Any:
        if method == "GET":
            return [{"id": 170440362}]
        return {"token": "tok-1", "expires_at": "2030-01-01T00:00:00Z"}

    gh_auth = InstallationAuth(
        "5280026", "KEY", sign=lambda body: b"sig", api=fake_api, clock=lambda: 1000.0
    )
    monkeypatch.setattr(app_module, "refresh_checkout", lambda *args: None)
    monkeypatch.setattr(mcp, "default_ceremony", fake_default_ceremony)
    gh_calls: list[list[str]] = []
    code, response = webhook_response(
        "d-rotation",
        _signature("s", body),
        body,
        WebhookConfig("s", "/repo", gh_auth=gh_auth),
        DeliveryLedger(),
        gh_calls.append,
    )
    assert code == 200
    assert response["status"] == "complete"
    assert captured["gh_token"]() == "tok-1"
    assert len(gh_calls) == 1


def test_the_default_ceremony_refreshes_the_checkout_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import progettare.app as app_module
    import progettare.mcp as mcp

    calls: list[str] = []

    def fake_refresh(repo_path: Any, repository: Any, token: Any) -> None:
        calls.append(f"refresh:{repo_path}:{repository}:{token()}")

    def fake_ceremony(
        ref: Any, repo_path: Any, runs_base: Any = None, gh_token: Any = None
    ) -> dict[str, Any]:
        calls.append("ceremony")
        return {"status": "complete"}

    monkeypatch.setattr(app_module, "refresh_checkout", fake_refresh)
    monkeypatch.setattr(mcp, "default_ceremony", fake_ceremony)
    outcome = app_module._default_ceremony("o/r#7", "/repo", None, lambda: "tok-1")
    assert calls == ["refresh:/repo:o/r:tok-1", "ceremony"]
    assert outcome["status"] == "complete"


def test_a_failed_refresh_fails_the_ceremony_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import progettare.app as app_module
    import progettare.mcp as mcp
    from progettare.checkout import CheckoutRefreshError

    def fake_refresh(repo_path: Any, repository: Any, token: Any) -> None:
        raise CheckoutRefreshError("git fetch exited 1: fatal: nope")

    def dead_ceremony(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("the ceremony must not run")

    monkeypatch.setattr(app_module, "refresh_checkout", fake_refresh)
    monkeypatch.setattr(mcp, "default_ceremony", dead_ceremony)
    outcome = app_module._default_ceremony("o/r#7", "/repo", None, lambda: "tok-1")
    assert outcome == {
        "status": "failed",
        "run_dir": "",
        "failing_stage": "checkout_refresh",
        "detail": "git fetch exited 1: fatal: nope",
    }


def test_without_a_token_provider_no_refresh_happens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import progettare.app as app_module
    import progettare.mcp as mcp

    calls: list[str] = []

    def dead_refresh(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no refresh without a token provider")

    def fake_ceremony(
        ref: Any, repo_path: Any, runs_base: Any = None, gh_token: Any = None
    ) -> dict[str, Any]:
        calls.append(f"ceremony:{gh_token}")
        return {"status": "complete"}

    monkeypatch.setattr(app_module, "refresh_checkout", dead_refresh)
    monkeypatch.setattr(mcp, "default_ceremony", fake_ceremony)
    outcome = app_module._default_ceremony("o/r#7", "/repo", None, None)
    assert calls == ["ceremony:None"]
    assert outcome["status"] == "complete"


def test_an_unrelated_event_is_ignored() -> None:
    from progettare.app import WebhookConfig, webhook_response

    body = _assigned_body().replace(b'"assigned"', b'"closed"')
    gh_calls: list[list[str]] = []
    code, response = webhook_response(
        "d4",
        _signature("s", body),
        body,
        WebhookConfig("s", "/repo"),
        DeliveryLedger(),
        gh_calls.append,
    )
    assert code == 200
    assert response["status"] == "ignored"
    assert gh_calls == []


def test_the_receiver_serves_signed_deliveries_over_http() -> None:
    import http.client
    import json as jsonlib
    import threading

    from progettare.app import WebhookConfig, build_webhook_server

    body = _assigned_body()
    gh_calls: list[list[str]] = []
    server = build_webhook_server(
        0,
        WebhookConfig("s", "/repo"),
        gh_calls.append,
        lambda ref, repo: {"status": "complete", "issue": ref},
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    connection.request(
        "POST",
        "/webhook",
        body=body,
        headers={
            "X-GitHub-Delivery": "d9",
            "X-Hub-Signature-256": _signature("s", body),
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    document = jsonlib.loads(response.read())
    assert response.status == 200
    assert document["status"] == "complete"
    assert len(gh_calls) == 1
    connection.close()
    server.shutdown()
    server.server_close()
