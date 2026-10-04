"""Reading an issue from GitHub, through gh, read-only.

progettare shells out to `gh`, the same way it shells out to nare: the CLI
stays the surface, no SDK dependency arrives, and authentication is the
caller's GH_TOKEN. Nothing in this module writes anywhere.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from progettare.issue_ref import IssueRef

GH_TIMEOUT_SECONDS = 30

# The fields progettare consumes from `gh issue view`. Requested explicitly
# so an upgrade that reshapes an unrequested field cannot break the parse.
GH_FIELDS = "number,title,body,state,url,comments"


class IssueFetchError(RuntimeError):
    """gh failed or answered in a shape progettare cannot use."""


class IssueClosedError(RuntimeError):
    """The issue is not open. A run aborts, discards, and posts nothing."""


@dataclass(frozen=True)
class IssueComment:
    author: str
    body: str
    created_at: str


@dataclass(frozen=True)
class Issue:
    """The issue text, as the pipeline received it."""

    owner: str
    repo: str
    number: int
    title: str
    body: str
    state: str
    url: str
    comments: tuple[IssueComment, ...]

    def is_open(self) -> bool:
        return self.state == "OPEN"


def _parse_comment(raw: Any) -> IssueComment:
    if not isinstance(raw, dict):
        raise IssueFetchError("gh returned comments in an unreadable shape")
    author = raw.get("author") or {}
    if not isinstance(author, dict):
        raise IssueFetchError("gh returned a comment author in an unreadable shape")
    return IssueComment(
        author=str(author.get("login") or ""),
        body=str(raw.get("body") or ""),
        created_at=str(raw.get("createdAt") or ""),
    )


def parse_issue_payload(ref: IssueRef, payload: Any) -> Issue:
    """The one place gh's JSON becomes data, checked at the boundary."""
    if not isinstance(payload, dict):
        raise IssueFetchError("gh returned an unreadable issue payload")
    state = payload.get("state")
    if state not in ("OPEN", "CLOSED"):
        raise IssueFetchError(f"gh reported an unreadable issue state: {state!r}")
    raw_comments = payload.get("comments")
    if raw_comments is not None and not isinstance(raw_comments, list):
        raise IssueFetchError("gh returned comments in an unreadable shape")
    return Issue(
        owner=ref.owner,
        repo=ref.repo,
        number=int(payload.get("number") or ref.number),
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
        state=str(state),
        url=str(payload.get("url") or ""),
        comments=tuple(_parse_comment(raw) for raw in (raw_comments or [])),
    )


def load_issue(ref: IssueRef, gh_path: str = "gh") -> Issue:
    """Fetch one issue read-only, or fail loudly.

    A closed issue is not an error in the fetch sense, but a terminal run
    outcome: the caller aborts, discards state, and posts nothing, so it
    gets its own exception.
    """
    command = [
        gh_path,
        "issue",
        "view",
        str(ref.number),
        "--repo",
        ref.repository(),
        "--json",
        GH_FIELDS,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise IssueFetchError(
            "gh is not installed or not on PATH; progettare reads issues "
            "through the gh CLI"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise IssueFetchError(
            f"gh issue view for {ref.repository()}#{ref.number} timed out "
            f"after {GH_TIMEOUT_SECONDS}s"
        ) from exc
    if completed.returncode != 0:
        raise IssueFetchError(
            f"gh issue view for {ref.repository()}#{ref.number} failed: "
            f"{completed.stderr.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise IssueFetchError(f"gh printed an unreadable issue payload: {exc}") from exc
    issue = parse_issue_payload(ref, payload)
    if not issue.is_open():
        raise IssueClosedError(
            f"{ref.repository()}#{ref.number} is {issue.state}; the run "
            "aborts, discards state, and posts nothing"
        )
    return issue


def ensure_issue_open(ref: IssueRef, gh_path: str = "gh") -> None:
    """Reload the issue's state, and abort when it closed mid-run.

    The engine calls this before each stage publishes, so a run whose
    issue closed under it aborts, discards state, and posts nothing,
    exactly as the spec's failure paths require.
    """
    load_issue(ref, gh_path)
