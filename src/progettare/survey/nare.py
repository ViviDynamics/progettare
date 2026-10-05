"""The nare adapter: one bounded, read-only survey session.

progettare launches each survey question as its own `nare run` with the
read tool confined to the surveyed repository, a token budget, and a JSON
schema for the answer. The adapter builds that argv, executes it through
an injectable runner boundary, and decodes nare's JSONL stdout: every
line must parse as JSON, and the terminal `result` line is required.
nare's field names are matched verbatim (status, stop_reason, usage with
input/output, output), so the decode never guesses a shape. Budget
exhaustion arrives as a nonzero exit beside a parseable result line,
which is data a caller records, not an adapter fault.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from progettare.config import ModelRail

# A survey session is a model loop bounded by its own --budget-tokens, so a
# legitimate run finishes well inside ten minutes; a child that outlives this
# is hung, and a hung child fails loudly here instead of stalling the stage.
SURVEY_SESSION_TIMEOUT_SECONDS = 600


class NareError(RuntimeError):
    """A nare run progettare cannot use, named loudly.

    A stage boundary may re-raise it with the stage ledger attached: the
    sessions that launched and the usage their result lines reported.
    """

    def __init__(
        self,
        message: str,
        *,
        sessions: tuple[str, ...] = (),
        usage: NareUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.sessions = sessions
        self.usage = usage


@dataclass(frozen=True)
class NareUsage:
    """One session's token counts. `total_tokens` is what the ledger adds."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class NareResult:
    """The decoded `result` line from nare's stdout.

    `output` carries the schema-validated answer object serialized as
    text when nare reports one, else None.
    """

    status: str
    stop_reason: str | None
    usage: NareUsage | None
    output: str | None


class Runner(Protocol):
    """The subprocess seam: argv in, the completed child process out."""

    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]: ...


class NareRunner(Protocol):
    """The injection seam for launching one bounded nare session."""

    def run(self, argv: tuple[str, ...]) -> NareResult: ...


def session_argv(
    prompt: str,
    system: str,
    root: str,
    rail: ModelRail,
    schema: str,
    budget_tokens: int,
    session_path: str,
) -> tuple[str, ...]:
    """The argv for one bounded, read-only nare session, in nare's order."""
    argv = [
        "nare",
        "run",
        prompt,
        "--system",
        system,
        "--tools",
        "read",
        "--root",
        root,
        "--provider",
        rail.provider,
    ]
    if rail.base_url is not None:
        argv.extend(["--base-url", rail.base_url])
    argv.extend(
        [
            "--model",
            rail.model,
            "--jsonl",
            "--contract",
            "1",
            "--schema",
            schema,
            "--budget-tokens",
            str(budget_tokens),
            "--session",
            session_path,
            "--yes",
        ]
    )
    return tuple(argv)


class _Subprocess:
    """The default Runner: the real nare child process, captured."""

    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=SURVEY_SESSION_TIMEOUT_SECONDS,
            check=False,
        )


def _int_field(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise NareError(f"nare's usage carries an unreadable {key}: {value!r}")
    return int(value)


def _decode_usage(raw: Any) -> NareUsage:
    if not isinstance(raw, dict):
        raise NareError(f"nare's usage is an unreadable shape: {raw!r}")
    input_tokens = _int_field(raw, "input")
    output_tokens = _int_field(raw, "output")
    return NareUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _decode_output(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return json.dumps(raw)


def _decode_result_line(document: dict[str, Any]) -> NareResult:
    status = document.get("status")
    if not isinstance(status, str):
        raise NareError(f"nare's result line carries an unreadable status: {status!r}")
    stop_reason = document.get("stop_reason")
    if stop_reason is not None and not isinstance(stop_reason, str):
        raise NareError(
            f"nare's result line carries an unreadable stop_reason: {stop_reason!r}"
        )
    raw_usage = document.get("usage")
    usage = None if raw_usage is None else _decode_usage(raw_usage)
    return NareResult(
        status=status,
        stop_reason=stop_reason,
        usage=usage,
        output=_decode_output(document.get("output")),
    )


def _decode_stdout(stdout: str) -> dict[str, Any] | None:
    """Every stdout line must be JSON; the final `result` line is returned."""
    documents: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NareError(
                f"nare printed a stdout line that is not JSON: {exc}"
            ) from exc
        if not isinstance(document, dict):
            raise NareError("nare printed a stdout line that is not a JSON object")
        documents.append(document)
    result = next(
        (
            document
            for document in reversed(documents)
            if document.get("type") == "result"
        ),
        None,
    )
    return result


def nare_runner(argv: Sequence[str], *, run: Runner | None = None) -> NareResult:
    """Run one nare session and decode its final `result` line, or fail loudly.

    A nonzero exit beside a parseable result line still returns the result:
    budget exhaustion exits nonzero, and that is recorded data, not a fault.
    A nonzero exit without a result line, a missing result line, a stdout
    line that is not JSON, or a child that outlives the timeout raises
    NareError.
    """
    frozen = tuple(argv)
    executor = _Subprocess() if run is None else run
    try:
        completed = executor.run(frozen)
    except FileNotFoundError as exc:
        raise NareError(
            "nare is not installed or not on PATH; progettare runs survey "
            "sessions through the nare CLI"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        program = frozen[0] if frozen else "nare"
        raise NareError(
            f"{program} timed out after {SURVEY_SESSION_TIMEOUT_SECONDS}s "
            "and was killed"
        ) from exc
    line = _decode_stdout(completed.stdout)
    if line is None:
        detail = completed.stderr.strip()
        if completed.returncode != 0:
            message = f"nare run exited {completed.returncode} without a result line"
            if detail:
                message = f"{message}: {detail}"
        elif detail:
            message = f"nare run printed no result line: {detail}"
        else:
            message = "nare run printed no result line"
        raise NareError(message)
    return _decode_result_line(line)
