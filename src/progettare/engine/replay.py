"""The replay audit: recompute the run's pure-code artifacts, compare bytes.

``replay`` feeds the stored blueprint through the same pure functions the
pipeline ran, with no model and no network, and reports whether the
recomputed artifacts are byte-identical with the run's. A mismatch names
the first divergence by key path, so the audit pinpoints the change
instead of just failing.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from progettare.blueprint.size import classify_size
from progettare.config import Config


class ReplayError(ValueError):
    """A run directory replay refuses to audit, naming the file."""


@dataclass(frozen=True)
class ReplayResult:
    """What the replay audit found: identity, and where it broke first."""

    identical: bool
    first_divergence: str | None
    recomputed: dict[str, dict[str, Any]]


def _load(path: pathlib.Path, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ReplayError(f"{name} could not be read: {error}") from error
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReplayError(f"{name} is not valid JSON: {error}") from error
    if not isinstance(record, dict):
        raise ReplayError(f"{name} is not a JSON object")
    return record, raw


def _bytes(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _first_divergence(stored: Any, recomputed: Any, path: str = "") -> str | None:
    if isinstance(stored, dict) and isinstance(recomputed, dict):
        for key in sorted(set(stored) | set(recomputed), key=str):
            here = f"{path}.{key}" if path else key
            if key not in stored:
                return f"{here} is absent from the stored record"
            if key not in recomputed:
                return f"{here} is absent from the recomputed record"
            found = _first_divergence(stored[key], recomputed[key], here)
            if found:
                return found
        return None
    if stored != recomputed:
        return f"{path or 'the record'} differs"
    return None


def replay_run(run_dir: pathlib.Path, config: Config) -> ReplayResult:
    """Recompute the run's pure-code artifacts and compare bytes.

    The stored blueprint is the input, the live config supplies the
    thresholds, and the stored record's own written_at is reused, since
    the comparison is against what the run actually wrote. Nothing here
    calls a model or the network; a recomputation that cannot proceed
    fails loudly naming the file.
    """
    stored_blueprint, _ = _load(run_dir / "blueprint.json", "blueprint.json")
    stored_size, raw_size = _load(run_dir / "size.json", "size.json")
    written_at = stored_size.get("written_at")
    if not isinstance(written_at, str) or not written_at:
        raise ReplayError("size.json has no written_at to replay with")
    recomputed = classify_size(
        stored_blueprint,
        config.size_single_turn_max_milestones,
        config.size_documenter_min_topics,
        written_at,
        config.config_version,
    )
    divergence = _first_divergence(stored_size, recomputed)
    if divergence is None and raw_size != _bytes(recomputed):
        divergence = "size.json content matches but its bytes differ"
    return ReplayResult(
        identical=divergence is None,
        first_divergence=divergence,
        recomputed={"size.json": recomputed},
    )
