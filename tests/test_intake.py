import json
from pathlib import Path
from typing import Any

import pytest

from progettare.engine.intake import (
    IntakeAborted,
    IntakeError,
    repo_context,
    run_intake,
)
from progettare.engine.issue_fetch import Runner
from progettare.engine.issue_ref import IssueRef

REF = IssueRef(owner="octo", repo="repo", number=1)
ISSUE_URL = "https://github.com/octo/repo/issues/1"


def _issue(
    body: str, state: str = "OPEN", comments: list[dict[str, Any]] | None = None
) -> str:
    return json.dumps(
        {
            "url": ISSUE_URL,
            "title": "Intake stage",
            "state": state,
            "stateReason": None,
            "closedAt": None,
            "body": body,
            "comments": comments or [],
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


def _comment(body: str) -> dict[str, Any]:
    return {
        "author": {"login": "octo"},
        "createdAt": "2026-10-01T10:00:00Z",
        "body": body,
    }


def test_ok_status_writes_intake_json_with_exact_shape(tmp_path: Path) -> None:
    run = _make_runner(_issue("Acceptance:\n- Ship the harness\n"))
    run_dir = tmp_path / "run"

    result = run_intake(REF, str(tmp_path), str(run_dir), run)

    assert result.status == "ok"
    raw = (run_dir / "intake.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    lines = raw.splitlines()
    assert lines[0] == "{"
    assert lines[1] == '  "blocked": null,'
    document = json.loads(raw)
    assert document == {
        "schema_version": 1,
        "status": "ok",
        "issue": {"url": ISSUE_URL, "title": "Intake stage", "state": "OPEN"},
        "repo": {"path": str(tmp_path), "head": "abc123", "branch": "main"},
        "criteria": [{"id": "c1", "text": "Ship the harness"}],
        "clarifications": [],
        "blocked": None,
    }


def test_blocked_on_missing_criteria(tmp_path: Path) -> None:
    run = _make_runner(_issue("Just prose, no acceptance section.\n"))
    run_dir = tmp_path / "run"

    result = run_intake(REF, str(tmp_path), str(run_dir), run)

    assert result.status == "blocked"
    document = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    assert document["blocked"] == {
        "reasons": ["missing_criteria"],
        "questions": [
            "The issue states no acceptance criteria. Add acceptance criteria "
            "to the issue body as a bullet list under Acceptance."
        ],
    }


def test_blocked_on_duplicate_conflict(tmp_path: Path) -> None:
    run = _make_runner(_issue("Acceptance:\n- Ship the harness\n- ship the harness\n"))
    run_dir = tmp_path / "run"

    result = run_intake(REF, str(tmp_path), str(run_dir), run)

    assert result.status == "blocked"
    document = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    assert document["blocked"] == {
        "reasons": ["conflicting_criteria"],
        "questions": [
            "Criteria c1 and c2 conflict (duplicate): 'ship the harness'. "
            "Resolve the conflict in the issue."
        ],
    }


def test_blocked_on_unanswered_clarification(tmp_path: Path) -> None:
    run = _make_runner(
        _issue(
            "Acceptance:\n- Ship the harness\n",
            comments=[_comment("Q: What about Windows?\n")],
        )
    )
    run_dir = tmp_path / "run"

    result = run_intake(REF, str(tmp_path), str(run_dir), run)

    assert result.status == "blocked"
    document = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    assert document["clarifications"] == [
        {
            "question": "What about Windows?",
            "answer": None,
            "source": "comment by octo on 2026-10-01T10:00:00Z",
        }
    ]
    assert document["blocked"] == {
        "reasons": ["unanswered_clarifications"],
        "questions": [
            "What about Windows? is unanswered on the issue. "
            "Answer it or withdraw the question."
        ],
    }


def test_blocked_reasons_accumulate_in_order(tmp_path: Path) -> None:
    run = _make_runner(
        _issue(
            "Acceptance:\n- Ship the harness\n- ship the harness\n",
            comments=[_comment("Q: What about Windows?\n")],
        )
    )
    run_dir = tmp_path / "run"

    result = run_intake(REF, str(tmp_path), str(run_dir), run)

    assert result.status == "blocked"
    document = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    assert document["blocked"]["reasons"] == [
        "conflicting_criteria",
        "unanswered_clarifications",
    ]
    assert document["blocked"]["questions"] == [
        "Criteria c1 and c2 conflict (duplicate): 'ship the harness'. "
        "Resolve the conflict in the issue.",
        "What about Windows? is unanswered on the issue. "
        "Answer it or withdraw the question.",
    ]


def test_repo_context_raises_for_a_non_repo_path(tmp_path: Path) -> None:
    def run(argv: list[str]) -> str:
        if argv[0] == "gh":
            return _issue("Acceptance:\n- Ship the harness\n")
        if argv[-1] == "--is-inside-work-tree":
            return "false\n"
        raise AssertionError(f"unexpected command: {argv}")

    with pytest.raises(IntakeError) as excinfo:
        repo_context(str(tmp_path), run)

    assert "not a git repository" in str(excinfo.value)
    assert str(tmp_path) in str(excinfo.value)


def test_run_intake_aborts_when_the_second_fetch_is_closed(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "intake.json").write_text("stale\n", encoding="utf-8")
    run = _make_runner(
        _issue("Acceptance:\n- Ship the harness\n"),
        second=_issue("", state="CLOSED"),
    )

    with pytest.raises(IntakeAborted) as excinfo:
        run_intake(REF, str(tmp_path), str(run_dir), run)

    assert not (run_dir / "intake.json").exists()
    message = str(excinfo.value)
    assert "octo/repo#1" in message
    assert "aborted" in message
    assert "nothing was written" in message


def test_run_intake_abort_writes_nothing_new(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run = _make_runner(
        _issue("Acceptance:\n- Ship the harness\n"),
        second=_issue("", state="CLOSED"),
    )

    with pytest.raises(IntakeAborted):
        run_intake(REF, str(tmp_path), str(run_dir), run)

    assert not (run_dir / "intake.json").exists()
