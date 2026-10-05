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

from progettare.blueprint.size import SizeStageError, classify_size
from progettare.blueprint.slices import SliceStageError, brief_files, slice_briefs
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
    if isinstance(stored, list) and isinstance(recomputed, list):
        if len(stored) != len(recomputed):
            return f"{path or 'the record'} differs"
        for index, (one, other) in enumerate(zip(stored, recomputed, strict=False)):
            found = _first_divergence(one, other, f"{path}[{index}]")
            if found:
                return found
        return None
    # JSON booleans compare equal to integers in Python, so a tampered
    # field's type is checked before its value: a stored true where the
    # run wrote 1 is a divergence at that key path, not a byte footnote.
    if type(stored) is not type(recomputed) or stored != recomputed:
        return f"{path or 'the record'} differs"
    return None


def _audit_briefs(
    run_dir: pathlib.Path,
    stored_blueprint: dict[str, Any],
    size_record: dict[str, Any],
    written_at: str,
    config: Config,
    recomputed: dict[str, dict[str, Any]],
) -> str | None:
    """Recompute the reader briefs and compare them file by file.

    The recomputed briefs come from the stored blueprint and the
    recomputed size record, so a stored brief written by a tampered size
    decision is caught as a divergence, never inherited. A file the
    recomputation does not expect is as much a divergence as a missing
    one: the briefs directory carries exactly the readers the ceremony
    calls for.
    """
    try:
        briefs_record = slice_briefs(
            stored_blueprint, size_record, written_at, config.config_version
        )
    except SliceStageError as error:
        raise ReplayError(f"blueprint.json could not be sliced: {error}") from error
    expected = brief_files(briefs_record)
    recomputed.update(expected)
    for name in sorted(expected):
        path = run_dir / name
        if not path.is_file():
            return f"{name} is missing from the run directory"
        stored_record, raw = _load(path, name)
        found = _first_divergence(stored_record, expected[name])
        if found is None and raw != _bytes(expected[name]):
            found = f"{name} content matches but its bytes differ"
        if found is not None:
            return f"{name}: {found}"
    if (run_dir / "briefs").is_dir():
        for path in sorted((run_dir / "briefs").iterdir()):
            name = path.relative_to(run_dir).as_posix()
            if name not in expected and path.is_file():
                return f"{name} is not part of the recomputed briefs"
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
    try:
        recomputed_size = classify_size(
            stored_blueprint,
            config.size_single_turn_max_milestones,
            config.size_documenter_min_topics,
            written_at,
            config.config_version,
        )
    except SizeStageError as error:
        raise ReplayError(f"blueprint.json could not be sized: {error}") from error
    recomputed: dict[str, dict[str, Any]] = {"size.json": recomputed_size}
    divergence = _first_divergence(stored_size, recomputed_size)
    if divergence is None and raw_size != _bytes(recomputed_size):
        divergence = "size.json content matches but its bytes differ"
    if divergence is None:
        divergence = _audit_briefs(
            run_dir, stored_blueprint, recomputed_size, written_at, config, recomputed
        )
    return ReplayResult(
        identical=divergence is None,
        first_divergence=divergence,
        recomputed=recomputed,
    )
