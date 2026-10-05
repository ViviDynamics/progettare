"""Issue references: where the pipeline starts.

An issue reaches progettare as a GitHub URL, as owner/repo#number, or as a
bare number resolved against the surveyed checkout's origin, plus a
repository checkout path. Every spelling resolves to the same structured
reference so the rest of the pipeline never parses text again.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class IssueRef:
    """A resolved reference to one GitHub issue."""

    owner: str
    repo: str
    number: int

    def slug(self) -> str:
        """A filesystem-safe name for run directories and logs."""
        return f"{self.owner}-{self.repo}-{self.number}"

    def repository(self) -> str:
        return f"{self.owner}/{self.repo}"


_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)"
    r"/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/issues/(?P<number>[0-9]+)/?$"
)
_SHORT_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"#(?P<number>[0-9]+)$"
)


class IssueRefError(ValueError):
    """A reference progettare cannot act on, named loudly."""


def parse_issue_ref(text: str) -> IssueRef:
    """Accept an issue by URL or owner/repo#number, nothing else.

    Pull-request URLs are rejected rather than guessed: progettare plans
    work from issues, and a PR number is a different object on the same
    host. A wrong but accepted reference would survey the wrong artifact
    for a whole run, so ambiguity fails here.
    """
    if not text or not text.strip():
        raise IssueRefError("an issue reference is required")
    candidate = text.strip()
    url = urlparse(candidate)
    if url.scheme in ("http", "https"):
        match = _URL_RE.match(candidate)
        if match is None:
            if re.match(r"^https://github\.com/[^/]+/[^/]+/pull/[0-9]+/?$", candidate):
                raise IssueRefError(
                    f"{candidate} is a pull request; progettare plans work "
                    "from issues, not pull requests"
                )
            raise IssueRefError(
                f"{candidate} is not a GitHub issue URL of the form "
                "https://github.com/owner/repo/issues/123"
            )
        number = int(match.group("number"))
        if number < 1:
            raise IssueRefError(
                f"{candidate} names issue {number}; GitHub numbers start at 1"
            )
        return IssueRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            number=number,
        )
    match = _SHORT_RE.match(candidate)
    if match is None:
        raise IssueRefError(
            f"{candidate} is not an issue reference of the form "
            "owner/repo#123 or an issue URL"
        )
    number = int(match.group("number"))
    if number < 1:
        raise IssueRefError(
            f"{candidate} names issue {number}; GitHub numbers start at 1"
        )
    return IssueRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=number,
    )


_REMOTE_RE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def resolve_issue_ref(text: str, repo_path: str) -> IssueRef:
    """Resolve a URL, an owner/repo#number, or a bare issue number.

    A bare number is only an issue reference once the checkout says which
    repository it belongs to, so it is resolved against the origin remote
    and refused when that remote is absent or not GitHub.
    """
    candidate = text.strip() if text else ""
    if candidate and candidate.isdigit():
        if int(candidate) < 1:
            raise IssueRefError(
                f"{candidate} names issue {candidate}; GitHub numbers start at 1"
            )
        command = ["git", "-C", repo_path, "remote", "get-url", "origin"]
        fetch = subprocess.run(command, capture_output=True, text=True)
        if fetch.returncode != 0:
            raise IssueRefError(
                f"{candidate} is a bare issue number and {repo_path} has no "
                "origin remote to resolve it against"
            )
        remote = fetch.stdout.strip()
        match = _REMOTE_RE.match(remote)
        if match is None:
            raise IssueRefError(
                f"{repo_path}'s origin remote {remote} is not a GitHub "
                "repository, so the bare issue number cannot be resolved"
            )
        return IssueRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            number=int(candidate),
        )
    return parse_issue_ref(candidate)
