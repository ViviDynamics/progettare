"""The checkout refresh, tested offline with a recording git runner."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from progettare.checkout import CheckoutRefreshError, refresh_checkout


class RecordingGit:
    """A recording subprocess.run stand-in that can fail one git verb."""

    def __init__(self, fail_keyword: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_keyword = fail_keyword

    def __call__(self, argv: list[str], **_kwargs: Any) -> Any:
        self.calls.append(argv)
        failed = self.fail_keyword is not None and self.fail_keyword in argv
        if failed:
            # Real git echoes the URL it was handed on transport errors, and
            # the URL carries the token.
            stderr = f"fatal: unable to access {' '.join(argv)}\n"
        else:
            stderr = ""
        return subprocess.CompletedProcess(argv, 1 if failed else 0, stderr=stderr)


def test_an_existing_checkout_fetches_and_resets(tmp_path: Any) -> None:
    (tmp_path / ".git").mkdir()
    git = RecordingGit()
    refresh_checkout(str(tmp_path), "o/r", lambda: "tok-1", runner=git)
    assert git.calls == [
        [
            "git",
            "-C",
            str(tmp_path),
            "fetch",
            "https://x-access-token:tok-1@github.com/o/r.git",
            "main",
        ],
        ["git", "-C", str(tmp_path), "reset", "--hard", "FETCH_HEAD"],
    ]


def test_a_missing_checkout_is_cloned_and_the_token_is_stripped(
    tmp_path: Any,
) -> None:
    repo_path = str(tmp_path / "progettare")
    git = RecordingGit()
    refresh_checkout(repo_path, "o/r", lambda: "tok-1", runner=git)
    assert git.calls == [
        [
            "git",
            "clone",
            "https://x-access-token:tok-1@github.com/o/r.git",
            repo_path,
        ],
        [
            "git",
            "-C",
            repo_path,
            "remote",
            "set-url",
            "origin",
            "https://github.com/o/r.git",
        ],
    ]


def test_a_failed_fetch_fails_loudly_and_stops(tmp_path: Any) -> None:
    (tmp_path / ".git").mkdir()
    git = RecordingGit(fail_keyword="fetch")
    with pytest.raises(CheckoutRefreshError) as raised:
        refresh_checkout(str(tmp_path), "o/r", lambda: "tok-1", runner=git)
    assert "git fetch exited 1" in str(raised.value)
    assert len(git.calls) == 1


def test_a_failed_fetch_never_leaks_the_token(tmp_path: Any) -> None:
    (tmp_path / ".git").mkdir()
    git = RecordingGit(fail_keyword="fetch")
    with pytest.raises(CheckoutRefreshError) as raised:
        refresh_checkout(str(tmp_path), "o/r", lambda: "tok-1", runner=git)
    assert "tok-1" not in str(raised.value)
    assert "<redacted>" in str(raised.value)


def test_a_failed_clone_fails_loudly_and_stops(tmp_path: Any) -> None:
    git = RecordingGit(fail_keyword="clone")
    with pytest.raises(CheckoutRefreshError) as raised:
        refresh_checkout(
            str(tmp_path / "progettare"), "o/r", lambda: "tok-1", runner=git
        )
    assert "git clone exited 1" in str(raised.value)
    assert len(git.calls) == 1
