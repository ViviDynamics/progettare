import json
import subprocess

import pytest

from progettare.engine.issue_fetch import (
    Comment,
    GhError,
    IssueCard,
    Runner,
    fetch_issue,
    gh_runner,
)
from progettare.engine.issue_ref import IssueRef

EXPECTED_COMMAND = [
    "gh",
    "issue",
    "view",
    "123",
    "--repo",
    "octo-org/repo",
    "--json",
    "title,body,state,stateReason,url,closedAt,comments",
]


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _runner(document: str) -> Runner:
    def run(command: list[str]) -> str:
        return document

    return run


def test_fetch_issue_maps_gh_json_to_card() -> None:
    document = {
        "title": "M1: intake and card context assembly",
        "body": "Build the intake stage.",
        "state": "OPEN",
        "stateReason": None,
        "url": "https://github.com/octo-org/repo/issues/123",
        "closedAt": None,
        "comments": [
            {
                "author": {"login": "octo-user"},
                "body": "First comment.",
                "createdAt": "2026-10-04T10:00:00Z",
            },
            {
                "author": None,
                "body": "Ghost comment.",
                "createdAt": "2026-10-04T11:00:00Z",
            },
        ],
    }
    received: list[list[str]] = []

    def run(command: list[str]) -> str:
        received.append(command)
        return json.dumps(document)

    card = fetch_issue(IssueRef(owner="octo-org", repo="repo", number=123), run)

    assert received == [EXPECTED_COMMAND]
    assert card == IssueCard(
        url="https://github.com/octo-org/repo/issues/123",
        title="M1: intake and card context assembly",
        body="Build the intake stage.",
        state="OPEN",
        state_reason=None,
        closed_at=None,
        comments=(
            Comment(
                author="octo-user",
                created_at="2026-10-04T10:00:00Z",
                body="First comment.",
            ),
            Comment(
                author="",
                created_at="2026-10-04T11:00:00Z",
                body="Ghost comment.",
            ),
        ),
    )


def test_closed_issue_card_is_closed() -> None:
    document = {
        "title": "Done thing",
        "body": "Body text.",
        "state": "CLOSED",
        "stateReason": "completed",
        "url": "https://github.com/octo-org/repo/issues/123",
        "closedAt": "2026-10-04T12:00:00Z",
        "comments": [],
    }

    card = fetch_issue(
        IssueRef(owner="octo-org", repo="repo", number=123),
        _runner(json.dumps(document)),
    )

    assert card.is_closed is True


def test_open_issue_card_is_not_closed() -> None:
    document: dict[str, object] = {
        "title": "Open thing",
        "body": "Body text.",
        "state": "OPEN",
        "stateReason": None,
        "url": "https://github.com/octo-org/repo/issues/123",
        "closedAt": None,
        "comments": [],
    }

    card = fetch_issue(
        IssueRef(owner="octo-org", repo="repo", number=123),
        _runner(json.dumps(document)),
    )

    assert card.is_closed is False


def test_runner_failure_propagates_gh_error() -> None:
    def run(command: list[str]) -> str:
        raise GhError(command, 1, "gh is not authenticated")

    with pytest.raises(GhError):
        fetch_issue(IssueRef(owner="octo-org", repo="repo", number=123), run)


def test_gh_runner_success(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> FakeCompleted:
        received.append(args)
        return FakeCompleted(0, "document body")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert gh_runner(EXPECTED_COMMAND) == "document body"
    assert received == [EXPECTED_COMMAND]


def test_gh_runner_raises_gh_error_on_non_zero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args: list[str], **kwargs: object) -> FakeCompleted:
        raise subprocess.CalledProcessError(1, args, output="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GhError) as excinfo:
        gh_runner(EXPECTED_COMMAND)

    assert excinfo.value.command == EXPECTED_COMMAND
    assert excinfo.value.exit_code == 1
    assert excinfo.value.stderr == "boom"
