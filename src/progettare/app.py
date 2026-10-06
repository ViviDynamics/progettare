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
from http.server import HTTPServer
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


def should_trigger(
    event: Mapping[str, Any],
    action: str,
    login: str = APP_LOGIN,
    label: str = TRIGGER_LABEL,
) -> bool:
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
        return any(isinstance(a, dict) and a.get("login") == login for a in assignees)
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return False
    return any(
        isinstance(label_dict, dict) and label_dict.get("name") == label
        for label_dict in labels
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


class WebhookConfig:
    """The receiver's configuration: login, label, secret, repo path.

    All four are configuration, not code; the deployment names them in
    the environment and nothing app specific is in the source.
    """

    def __init__(
        self,
        secret: str,
        repo_path: str,
        login: str = APP_LOGIN,
        trigger_label: str = TRIGGER_LABEL,
    ) -> None:
        self.secret = secret
        self.repo_path = repo_path
        self.login = login
        self.trigger_label = trigger_label


def _signed(secret: str, body: bytes, signature: str | None) -> bool:
    import hashlib
    import hmac

    if signature is None:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def webhook_response(
    delivery_id: str | None,
    signature: str | None,
    body: bytes,
    config: WebhookConfig,
    ledger: DeliveryLedger,
    gh_call: Callable[[list[str]], None] | None = None,
    ceremony: Callable[[str, str], dict[str, Any]] | None = None,
) -> tuple[int, dict[str, Any]]:
    """One webhook delivery in, an HTTP status and a status document out.

    The signature is verified against the raw bytes before anything is
    parsed, so unauthenticated bytes never reach the dispatcher. The
    delivery GUID feeds the ledger, so one event is one run even when
    the platform retries.
    """
    if delivery_id is None:
        return 400, {"status": "refused", "reason": "the delivery carries no id"}
    if not _signed(config.secret, body, signature):
        return 401, {"status": "refused", "reason": "the signature does not verify"}
    try:
        payload: Any = json.loads(body)
    except ValueError:
        return 400, {"status": "refused", "reason": "the payload did not parse"}
    if not isinstance(payload, dict):
        return 400, {"status": "refused", "reason": "the payload is not an object"}
    raw_action = payload.get("action")
    action = raw_action if isinstance(raw_action, str) else ""
    if not should_trigger(
        payload, action, login=config.login, label=config.trigger_label
    ):
        return 200, {"status": "ignored"}
    issue = payload.get("issue")
    repository = payload.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    number = issue.get("number") if isinstance(issue, dict) else None
    if not isinstance(full_name, str) or not isinstance(number, int):
        return 200, {"status": "ignored"}

    dispatch = gh_call if gh_call is not None else _post_gh

    def post(comment: str) -> None:
        dispatch(
            [
                "gh",
                "api",
                f"repos/{full_name}/issues/{number}/comments",
                "-f",
                f"body={comment}",
            ]
        )

    run_ceremony = ceremony if ceremony is not None else _default_ceremony
    outcome = handle_event(
        delivery_id, action, payload, run_ceremony, ledger, post, config.repo_path
    )
    return 200, outcome


def _default_ceremony(ref: str, repo_path: str) -> dict[str, Any]:
    from progettare.mcp import default_ceremony as run_ceremony

    return run_ceremony(ref, repo_path)


def _post_gh(argv: list[str]) -> None:
    """The default gh seam: the App's token arrives in the environment."""
    import subprocess

    subprocess.run(argv, check=False)


def build_webhook_server(
    port: int,
    config: WebhookConfig,
    gh_call: Callable[[list[str]], None] | None = None,
    ceremony: Callable[[str, str], dict[str, Any]] | None = None,
) -> HTTPServer:
    """The receiver's HTTP shell around the dispatch seam.

    One process keeps the delivery ledger in memory, so the deployment
    runs one replica and replacements redo nothing that wrote artifacts.
    """
    from http.server import BaseHTTPRequestHandler

    ledger = DeliveryLedger()
    dispatch = gh_call if gh_call is not None else _post_gh

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            delivery_id = self.headers.get("X-GitHub-Delivery")
            signature = self.headers.get("X-Hub-Signature-256")
            code, response = webhook_response(
                delivery_id, signature, body, config, ledger, dispatch, ceremony
            )
            document = json.dumps(response).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

    return HTTPServer(("0.0.0.0", port), Receiver)


def serve_webhook(
    port: int,
    config: WebhookConfig,
    gh_call: Callable[[list[str]], None] | None = None,
) -> None:
    """Serve POST /webhook until the process is stopped."""

    server = build_webhook_server(port, config, gh_call)
    server.serve_forever()
