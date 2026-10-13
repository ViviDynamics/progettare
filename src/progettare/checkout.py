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
from pathlib import Path
from typing import Any


class CheckoutRefreshError(RuntimeError):
    """A checkout refresh that cannot complete, named loudly."""


def refresh_checkout(
    repo_path: str,
    repository: str,
    token: Callable[[], str],
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    """Track main: fetch and reset an existing checkout, boot a missing one.

    The token rides the git URLs and is never written to .git/config, so a
    checkout fetched under one ephemeral token still refreshes under every
    token the app mints after that one expires. The cold start inits, then
    fetches by explicit URL instead of cloning: clone persists its
    credential-bearing URL in remote.origin.url, while an explicit-URL fetch
    persists nothing, and fetching main keeps the boot on the branch the
    receiver surveys.
    """
    credential = token()
    if Path(repo_path, ".git").exists():
        _run(
            runner,
            ["git", "-C", repo_path, "fetch", _authed(repository, credential), "main"],
            "fetch",
            credential,
        )
        _run(runner, ["git", "-C", repo_path, "reset", "--hard", "FETCH_HEAD"], "reset")
        return
    _run(runner, ["git", "init", repo_path], "init")
    _run(
        runner,
        ["git", "-C", repo_path, "fetch", _authed(repository, credential), "main"],
        "fetch",
        credential,
    )
    _run(runner, ["git", "-C", repo_path, "reset", "--hard", "FETCH_HEAD"], "reset")
    _run(
        runner,
        ["git", "-C", repo_path, "remote", "add", "origin", _plain(repository)],
        "remote",
    )


def _authed(repository: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repository}.git"


def _plain(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def _run(
    runner: Callable[..., Any], argv: list[str], verb: str, secret: str | None = None
) -> None:
    completed = runner(argv, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        # Git echoes the URL it was handed on transport errors, and the URL
        # carries the token: the detail lands in a posted comment, so the
        # token must never ride along with it.
        stderr = (completed.stderr or "").strip().replace(secret or "", "<redacted>")
        raise CheckoutRefreshError(
            f"git {verb} exited {completed.returncode}: {stderr}"
        )
