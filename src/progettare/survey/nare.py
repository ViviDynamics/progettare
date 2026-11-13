"""The nare adapter: one bounded, read-only session.

progettare launches each survey question, and the blueprint, as its own
`nare run` with read-only tools confined to the surveyed repository (read,
and for a survey question list and search too), a token budget, nare's
own wall clock, and a JSON schema for the answer. The adapter builds that
argv, executes it through an injectable runner boundary, and decodes
nare's JSONL stdout: every line must parse as JSON, and the terminal
`result` line is required.
nare's field names are matched verbatim (status, stop_reason, usage with
input/output/cache_read/cache_write/total, output), so the decode never
guesses a shape. Budget exhaustion arrives as a nonzero exit beside a
parseable result line, which is data a caller records, not an adapter
fault.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from progettare.config import ModelRail

# The nare machine contract this adapter reads. nare speaks exactly one
# version and refuses any other with exit 2 before starting, so a nare that
# moved on fails the first session loudly instead of being mis-read. The
# release workflow checks the nare it pins against this number before it
# mints, so a release never ships a pair that cannot talk.
NARE_CONTRACT = 3

# A survey session is a model loop bounded by its own --budget-tokens, so a
# legitimate run finishes well inside ten minutes; a child that outlives this
# is hung, and a hung child fails loudly here instead of stalling the stage.
SURVEY_SESSION_TIMEOUT_SECONDS = 600

# nare's own wall clock, a minute inside the kill above. At it nare stops
# the call in flight, saves the session, and writes a result line with
# stop_reason `timeout`, so the stage records the usage the session spent.
# The kill stays as the backstop for a nare that hangs while stopping.
NARE_TIMEOUT_SECONDS = SURVEY_SESSION_TIMEOUT_SECONDS - 60

# The tools a session may call when its stage names none: read alone.
READ_ONLY_TOOLS = ("read",)

# Every tool a session may be offered. Each is read-only, confined to
# --root, and starts no process; anything else is refused before launch.
ALLOWED_TOOLS = frozenset({"read", "list", "search"})


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
    """One session's token counts. `total_tokens` is what the ledger adds.

    It is nare's own `usage.total`, the number `--budget-tokens` counts:
    nare's `input` excludes cache reads and writes, so `input + output`
    would undercount any session that hit a prompt cache. The cache counts
    are kept beside it, so the four counters add up to the total in run.json.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def sum_usage(usages: Sequence[NareUsage]) -> NareUsage | None:
    """The sessions' summed usage, or None when no session reported any."""
    if not usages:
        return None
    return NareUsage(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
        cache_read_tokens=sum(usage.cache_read_tokens for usage in usages),
        cache_write_tokens=sum(usage.cache_write_tokens for usage in usages),
    )


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
    tools: tuple[str, ...] = READ_ONLY_TOOLS,
    cited_reads: tuple[str, ...] = (),
    max_tool_calls: int | None = None,
) -> tuple[str, ...]:
    """The argv for one bounded, read-only nare session, in nare's order.

    ``tools`` names nare's read-only tools only (read, list, search): none
    of them runs a process or writes. ``cited_reads`` are JSON pointers
    into the schema answer; nare holds an answer until the session has
    read every path they find, and ends ``reads_required`` if the model
    still cites an unread file after its correction. ``max_tool_calls``
    caps the calls the session makes; at the cap nare tells the model to
    answer.
    """
    if not tools or not set(tools) <= ALLOWED_TOOLS:
        allowed = ", ".join(sorted(ALLOWED_TOOLS))
        raise ValueError(
            f"a session is offered read-only tools only ({allowed}), not {tools!r}"
        )
    argv = [
        "nare",
        "run",
        prompt,
        "--system",
        system,
        "--tools",
        ",".join(tools),
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
            str(NARE_CONTRACT),
            "--schema",
            schema,
        ]
    )
    for pointer in cited_reads:
        argv.extend(["--require-cited-reads", pointer])
    if max_tool_calls is not None:
        argv.extend(["--max-tool-calls", str(max_tool_calls)])
    argv.extend(
        [
            "--budget-tokens",
            str(budget_tokens),
            "--timeout",
            str(NARE_TIMEOUT_SECONDS),
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
    return NareUsage(
        input_tokens=_int_field(raw, "input"),
        output_tokens=_int_field(raw, "output"),
        total_tokens=_int_field(raw, "total"),
        cache_read_tokens=_int_field(raw, "cache_read"),
        cache_write_tokens=_int_field(raw, "cache_write"),
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
