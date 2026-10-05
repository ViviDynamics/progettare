"""The run manifest: the one artifact that names the whole run.

``run.json`` carries the run-level stamps a consumer checks before it
trusts the rest: the release that produced the run, the digest of the
config it ran under, and the ledger of nare sessions and their usage,
stage by stage, taken from the sessions' JSONL result lines. A run that
failed or was blocked still writes its artifacts, and the manifest names
the stage that stopped it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from progettare.config import Config
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.engine.run import atomic_write_json
from progettare.survey.nare import NareUsage

RUN_MANIFEST_VERSION = 2

STATUSES = ("complete", "failed", "blocked")


class ManifestError(ValueError):
    """A manifest progettare refuses to write, named loudly."""


def config_digest(config: Config) -> str:
    """The sha256 of the config's canonical JSON.

    The digest is over the sorted, indented JSON a reader can reproduce
    with the same rule, so two runs under one config share a digest and
    two configs differing in any carried field do not.
    """
    canonical = json.dumps(asdict(config), indent=2, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StageLedger:
    """One stage's sessions and their summed usage, as the run did work."""

    sessions: tuple[str, ...] = ()
    usage: NareUsage | None = None


def run_manifest(
    config: Config,
    status: str,
    written_at: str,
    stages: dict[str, StageLedger],
    failing_stage: str | None = None,
    failing_reason: str | None = None,
) -> dict[str, Any]:
    """The versioned manifest, loud about what stopped an incomplete run.

    A partial run is still a run: its manifest carries every stage that
    did work, the stage that stopped it, and the reason it stopped. A
    complete run names no failing stage and no reason; an incomplete run
    names both, and the reason is a nonempty string, not whitespace;
    anything else is a contradiction a consumer would read as a bug.
    """
    if status not in STATUSES:
        raise ManifestError(
            f"run status {status!r} is not one the manifest records: "
            f"{', '.join(STATUSES)}"
        )
    if status == "complete":
        if failing_stage is not None:
            raise ManifestError("a complete run names no failing stage")
        if failing_reason is not None:
            raise ManifestError("a complete run names no failing stage")
    else:
        if failing_stage is None:
            raise ManifestError(f"a {status} run names the stage that stopped it")
        if failing_reason is None or not failing_reason.strip():
            raise ManifestError(f"a {status} run names the reason it stopped")
    return {
        "version": RUN_MANIFEST_VERSION,
        "artifact": "run",
        "artifact_version": ARTIFACT_VERSION,
        "progettare": PROGETTARE_VERSION,
        "config_digest": config_digest(config),
        "written_at": written_at,
        "status": status,
        "failing_stage": failing_stage,
        "failing_reason": failing_reason,
        "stages": {
            name: {
                "sessions": list(ledger.sessions),
                "usage": asdict(ledger.usage) if ledger.usage is not None else None,
            }
            for name, ledger in sorted(stages.items())
        },
    }


def write_run_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    """Write run.json atomically; the rename is what survives a kill."""
    path = run_dir / "run.json"
    atomic_write_json(path, manifest)
    return path
