import json
from pathlib import Path

import pytest

from progettare.engine.issue_fetch import GhError, Runner
from progettare.interfaces.cli import main

ISSUE_URL = "https://github.com/octo/repo/issues/1"


def _issue(body: str, state: str = "OPEN") -> str:
    return json.dumps(
        {
            "url": ISSUE_URL,
            "title": "Intake stage",
            "state": state,
            "stateReason": None,
            "closedAt": None,
            "body": body,
            "comments": [],
        }
    )


def _make_runner(issue: str, second: str | None = None) -> Runner:
    calls = 0

    def run(argv: list[str]) -> str:
        nonlocal calls
        if argv[0] == "gh":
            calls += 1
            if calls == 2 and second is not None:
                return second
            return issue
        if argv[-1] == "--is-inside-work-tree":
            return "true\n"
        if "--abbrev-ref" in argv:
            return "main\n"
        return "abc123\n"

    return run


def test_ok_path_prints_the_artifact_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    run = _make_runner(_issue("Acceptance:\n- Ship the harness\n"))

    exit_code = main(
        [
            "intake",
            "octo/repo#1",
            "--repo",
            str(tmp_path),
            "--run-dir",
            str(tmp_path / "run"),
        ],
        run=run,
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {
        "schema_version": 1,
        "status": "ok",
        "issue": {"url": ISSUE_URL, "title": "Intake stage", "state": "OPEN"},
        "repo": {"path": str(tmp_path), "head": "abc123", "branch": "main"},
        "criteria": [{"id": "c1", "text": "Ship the harness"}],
        "clarifications": [],
        "blocked": None,
    }


def test_blocked_path_returns_zero_and_reports_blocked(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    run = _make_runner(_issue("Just prose, no acceptance section.\n"))

    exit_code = main(
        [
            "intake",
            "octo/repo#1",
            "--repo",
            str(tmp_path),
            "--run-dir",
            str(tmp_path / "run"),
        ],
        run=run,
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["status"] == "blocked"


def test_bad_reference_prints_prefix_and_returns_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    run = _make_runner(_issue(""))

    exit_code = main(["intake", "not a ref", "--repo", str(tmp_path)], run=run)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err.startswith("progettare: ")
    assert captured.out == ""


def test_abort_prints_prefix_and_returns_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    run = _make_runner(
        _issue("Acceptance:\n- Ship the harness\n"),
        second=_issue("", state="CLOSED"),
    )

    exit_code = main(
        [
            "intake",
            "octo/repo#1",
            "--repo",
            str(tmp_path),
            "--run-dir",
            str(tmp_path / "run"),
        ],
        run=run,
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err.startswith("progettare: aborted: ")
    assert captured.out == ""


def test_gh_failure_prints_prefix_and_returns_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def run(argv: list[str]) -> str:
        if argv[0] == "gh":
            raise GhError(argv, 1, "boom")
        raise AssertionError(f"unexpected command: {argv}")

    exit_code = main(
        [
            "intake",
            "octo/repo#1",
            "--repo",
            str(tmp_path),
            "--run-dir",
            str(tmp_path / "run"),
        ],
        run=run,
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err.startswith("progettare: ")
    assert captured.out == ""
