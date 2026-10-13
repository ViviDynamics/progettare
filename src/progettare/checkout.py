"""The surveyed checkout's freshness, owned by the receiver.

A deployment-managed checkout must track main before a ceremony surveys it.
The fetch authenticates with the installation token the app already mints,
passed by URL and never persisted: the init container this replaces baked
the token into .git/config at clone time, which is how a lapsed token
silently froze the checkout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any


class CheckoutRefreshError(RuntimeError):
    """A checkout refresh that cannot complete, named loudly."""


def refresh_checkout(
    repo_path: str,
    repository: str,
    token: Callable[[], str],
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    """Track main: fetch and reset an existing checkout, clone a missing one.

    The token rides the git URLs and is never written to .git/config, so a
    checkout cloned under one ephemeral token still refreshes under every
    token the app mints after that one expires.
    """
    if _has_git_dir(repo_path):
        _run(
            runner,
            ["git", "-C", repo_path, "fetch", _authed(repository, token()), "main"],
            "fetch",
        )
        _run(runner, ["git", "-C", repo_path, "reset", "--hard", "FETCH_HEAD"], "reset")
        return
    _run(runner, ["git", "clone", _authed(repository, token()), repo_path], "clone")
    _run(
        runner,
        ["git", "-C", repo_path, "remote", "set-url", "origin", _plain(repository)],
        "set-url",
    )


def _has_git_dir(repo_path: str) -> bool:
    from pathlib import Path

    return Path(repo_path, ".git").exists()


def _authed(repository: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repository}.git"


def _plain(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def _run(runner: Callable[..., Any], argv: list[str], verb: str) -> None:
    completed = runner(argv, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise CheckoutRefreshError(
            f"git {verb} exited {completed.returncode}: {stderr}"
        )
