"""Tests for the nare adapter: argv shape, JSONL decode, and typed faults.

The result lines below use nare's real field names, taken from the
`_emit_result` shape in nare's cli.py and the `Usage` dataclass in
nare's session.py: status, stop_reason, usage{input, output}, output.
All tests are offline: the subprocess seam is a fake.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from progettare.config import ModelRail
from progettare.survey.nare import (
    NareError,
    NareResult,
    NareUsage,
    nare_runner,
    session_argv,
)

RAIL = ModelRail(
    provider="openai", model="gpt-survey", base_url="http://127.0.0.1:8000"
)
RAIL_WITHOUT_BASE_URL = ModelRail(
    provider="anthropic", model="claude-sonnet-5", base_url=None
)


def make_result_line(**overrides: Any) -> str:
    """One nare result line, carrying nare's real field names."""
    document: dict[str, Any] = {
        "type": "result",
        "session_id": "1a2b3c",
        "status": "done",
        "questions": [],
        "usage": {"input": 10, "output": 5, "cache_read": 0, "cache_write": 0},
        "stop_reason": None,
        "turns": 2,
        "contract": 1,
        "nare": "0.4.0",
        "output": None,
        "error": None,
    }
    document.update(overrides)
    return json.dumps(document)


class FakeRunner:
    """The subprocess seam, replaying a recorded child process."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.argv: tuple[str, ...] | None = None

    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        self.argv = argv
        return subprocess.CompletedProcess(list(argv), self.returncode, self.stdout, "")


class MissingExecutableRunner:
    """A subprocess seam where the nare binary does not exist."""

    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("No such file or directory: 'nare'")


class HungRunner:
    """A subprocess seam where the nare child hangs until it is killed."""

    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["nare", "run", "question"], timeout=600)


def test_session_argv_carries_every_family_flag_in_order() -> None:
    argv = session_argv(
        prompt="Which files implement the survey stage?",
        system="SYSTEM TEXT",
        root="/repo",
        rail=RAIL,
        schema="/run/schema.json",
        budget_tokens=1200,
        session_path="/run/survey-q1.json",
    )
    assert argv == (
        "nare",
        "run",
        "Which files implement the survey stage?",
        "--system",
        "SYSTEM TEXT",
        "--tools",
        "read",
        "--root",
        "/repo",
        "--provider",
        "openai",
        "--base-url",
        "http://127.0.0.1:8000",
        "--model",
        "gpt-survey",
        "--jsonl",
        "--contract",
        "1",
        "--schema",
        "/run/schema.json",
        "--budget-tokens",
        "1200",
        "--session",
        "/run/survey-q1.json",
        "--yes",
    )


def test_session_argv_omits_base_url_when_the_rail_has_none() -> None:
    argv = session_argv(
        prompt="question",
        system="system",
        root="/repo",
        rail=RAIL_WITHOUT_BASE_URL,
        schema="/run/schema.json",
        budget_tokens=10,
        session_path="/run/session.json",
    )
    assert "--base-url" not in argv
    assert "10" in argv


def test_nare_runner_decodes_the_final_result_line() -> None:
    events = "\n".join(
        [
            json.dumps(
                {
                    "type": "progress",
                    "text": "reading the tree",
                    "detail": {},
                    "timestamp": "t1",
                }
            ),
            json.dumps(
                {
                    "type": "tool_use",
                    "text": "read",
                    "detail": {},
                    "timestamp": "t2",
                }
            ),
            make_result_line(),
        ]
    )
    runner = FakeRunner(stdout=f"{events}\n")
    result = nare_runner(("nare", "run", "question"), run=runner)
    assert runner.argv == ("nare", "run", "question")
    assert result.status == "done"
    assert result.stop_reason is None
    assert result.usage == NareUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    assert result.output is None


def test_result_line_with_an_answer_payload_serializes_the_output() -> None:
    answer = {"commands": ["ls /repo"], "findings": ["cli.py is the entry"]}
    line = make_result_line(output=answer)
    runner = FakeRunner(stdout=f"{line}\n")
    result = nare_runner(("nare", "run", "question"), run=runner)
    assert result.output is not None
    assert json.loads(result.output) == answer


def test_budget_exhaustion_with_a_result_line_is_data_not_a_fault() -> None:
    line = make_result_line(
        status="error", stop_reason="budget", error="token budget exhausted"
    )
    runner = FakeRunner(stdout=f"{line}\n", returncode=1)
    result = nare_runner(("nare", "run", "question"), run=runner)
    assert result.status == "error"
    assert result.stop_reason == "budget"
    assert result.usage == NareUsage(input_tokens=10, output_tokens=5, total_tokens=15)


def test_stdout_without_a_result_line_raises_nare_error() -> None:
    events = json.dumps(
        {"type": "progress", "text": "working", "detail": {}, "timestamp": "t1"}
    )
    runner = FakeRunner(stdout=f"{events}\n")
    with pytest.raises(NareError, match="result line"):
        nare_runner(("nare", "run", "question"), run=runner)


def test_a_stdout_line_that_is_not_json_raises_nare_error() -> None:
    stream = "\n".join([make_result_line(), "nare: not a JSON line"])
    runner = FakeRunner(stdout=stream)
    with pytest.raises(NareError, match="not JSON"):
        nare_runner(("nare", "run", "question"), run=runner)


def test_nonzero_exit_without_a_result_line_names_the_exit() -> None:
    runner = FakeRunner(stdout="", returncode=3)
    with pytest.raises(NareError, match="exited 3"):
        nare_runner(("nare", "run", "question"), run=runner)


def test_usage_absent_in_the_result_line_decodes_to_none() -> None:
    line = make_result_line(usage=None)
    runner = FakeRunner(stdout=f"{line}\n")
    result = nare_runner(("nare", "run", "question"), run=runner)
    assert result == NareResult(
        status="done", stop_reason=None, usage=None, output=None
    )


def test_a_missing_nare_executable_raises_nare_error() -> None:
    with pytest.raises(NareError, match="not on PATH"):
        nare_runner(("nare", "run", "question"), run=MissingExecutableRunner())


def test_a_hung_nare_session_times_out_as_a_typed_nare_error() -> None:
    with pytest.raises(NareError, match=r"timed out after 600"):
        nare_runner(("nare", "run", "question"), run=HungRunner())
