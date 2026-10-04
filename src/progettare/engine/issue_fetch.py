"""Issue fetch through the gh CLI, with an injectable command runner."""

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from progettare.engine.issue_ref import IssueRef

Runner = Callable[[list[str]], str]


class GhError(RuntimeError):
    def __init__(self, command: list[str], exit_code: int, stderr: str) -> None:
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"gh failed with exit code {exit_code} for {command}: {stderr}"
        )


@dataclass(frozen=True)
class Comment:
    author: str
    created_at: str
    body: str


@dataclass(frozen=True)
class IssueCard:
    url: str
    title: str
    body: str
    state: str
    state_reason: str | None
    closed_at: str | None
    comments: tuple[Comment, ...]

    @property
    def is_closed(self) -> bool:
        return self.state == "CLOSED"


def fetch_issue(ref: IssueRef, run: Runner) -> IssueCard:
    document = json.loads(run(_gh_command(ref)))
    return IssueCard(
        url=document["url"],
        title=document["title"],
        body=document["body"],
        state=document["state"],
        state_reason=document.get("stateReason"),
        closed_at=document.get("closedAt"),
        comments=tuple(_comment(raw) for raw in document["comments"]),
    )


def gh_runner(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise GhError(command, error.returncode, error.stderr or "") from error
    if completed.returncode != 0:
        raise GhError(command, completed.returncode, completed.stderr)
    return completed.stdout


def _gh_command(ref: IssueRef) -> list[str]:
    return [
        "gh",
        "issue",
        "view",
        str(ref.number),
        "--repo",
        f"{ref.owner}/{ref.repo}",
        "--json",
        "title,body,state,stateReason,url,closedAt,comments",
    ]


def _comment(raw: dict[str, Any]) -> Comment:
    author = raw.get("author") or {}
    login = author.get("login")
    return Comment(
        author=login if login is not None else "",
        created_at=raw["createdAt"],
        body=raw["body"],
    )
