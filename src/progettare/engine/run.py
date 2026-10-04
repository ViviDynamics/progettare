"""The run directory: where a run's artifacts live.

Every artifact progettare produces belongs to the run, never to the
repository it surveys. The run directory is created outside the surveyed
repo, and a run that fails or is blocked still writes what it learned,
naming the stage that stopped it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.intake import CardContext
from progettare.issue_ref import IssueRef


class RunDirectoryError(ValueError):
    """A run directory progettare refuses to create, named loudly."""


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def run_dir_name(ref: IssueRef, when: str) -> str:
    return f"{when}-{ref.slug()}"


def create_run_dir(base: Path, ref: IssueRef, repo_path: Path) -> Path:
    """Create the run directory, outside the surveyed repository.

    A run directory inside the checkout it surveys would contradict the
    harness's read-only promise the moment the first artifact landed, so
    that placement fails here rather than later.

    The name has one-second resolution, so two runs starting in the same
    second do not share a directory: creation is exclusive, and a taken
    name retries with a numeric suffix rather than reusing another run's
    artifacts.
    """
    base_resolved = base.expanduser().resolve()
    repo_resolved = repo_path.expanduser().resolve()
    if base_resolved == repo_resolved or repo_resolved in base_resolved.parents:
        raise RunDirectoryError(
            f"run directory base {base_resolved} is inside the surveyed "
            f"repository {repo_resolved}; progettare writes nothing there"
        )
    stem = run_dir_name(ref, _utc_now())
    run_dir = base_resolved / stem
    attempt = 1
    while True:
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            attempt += 1
            if attempt > 99:
                raise RunDirectoryError(
                    f"run directory {run_dir} is taken, and the retry "
                    "suffix budget is spent"
                ) from None
            run_dir = base_resolved / f"{stem}-{attempt}"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically, readable only by its owner.

    NamedTemporaryFile has mkstemp semantics: mode 0600 and a unique name.
    The rename is what survives a kill: a plain write truncates before it
    writes, so a signal in that window leaves a partial artifact and no
    backup.
    """
    directory = path.parent
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        os.replace(handle.name, path)
    except OSError:
        os.unlink(handle.name)
        raise


def intake_payload(context: CardContext, written_at: str) -> dict[str, Any]:
    """The versioned intake artifact: the card context plus its stamps."""
    return {
        "artifact": "intake",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "written_at": written_at,
        "status": context.status,
        "repo_path": context.repo_path,
        "issue": asdict(context.issue),
        "acceptance_criteria": list(context.acceptance_criteria),
        "clarifications": [
            {"question": c.question, "answer": c.answer} for c in context.clarifications
        ],
        "blocked_questions": list(context.blocked_questions),
    }


def write_intake(run_dir: Path, context: CardContext, written_at: str) -> Path:
    """Stamp and write intake.json into the run directory."""
    path = run_dir / "intake.json"
    atomic_write_json(path, intake_payload(context, written_at))
    return path
