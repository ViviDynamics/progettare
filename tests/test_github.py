import json
import os
import stat
from pathlib import Path

import pytest

from progettare.github import (
    Issue,
    IssueClosedError,
    IssueFetchError,
    ensure_issue_open,
    load_issue,
)
from progettare.issue_ref import parse_issue_ref

REF = parse_issue_ref("ViviDynamics/progettare#1")


def canned_issue(number: int, state: str = "OPEN") -> str:
    return json.dumps(
        {
            "number": number,
            "title": "M1: intake and card context assembly",
            "body": "Acceptance:\n- one\n- two",
            "state": state,
            "url": f"https://github.com/ViviDynamics/progettare/issues/{number}",
            "comments": [
                {
                    "author": {"login": "jason"},
                    "body": "Any clarification needed?",
                    "createdAt": "2026-10-04T00:00:00Z",
                },
                {"author": {"login": "jason"}, "body": "No.", "createdAt": ""},
            ],
        }
    )


def install_gh(monkeypatch: pytest.MonkeyPatch, directory: Path, script: str) -> None:
    bin_dir = directory / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "gh"
    fake.write_text(script)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def gh_cat(payload: str) -> str:
    # cat, not echo: dash's echo would interpret the JSON's \n escapes.
    return f"#!/bin/sh\ncat '{payload}'\n"


def test_an_open_issue_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(canned_issue(1))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    issue = load_issue(REF)
    assert isinstance(issue, Issue)
    assert issue.title == "M1: intake and card context assembly"
    assert issue.state == "OPEN"
    assert issue.is_open()
    assert issue.comments[0].author == "jason"
    assert issue.comments[0].body == "Any clarification needed?"


def test_a_closed_issue_raises_its_own_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(canned_issue(1, "CLOSED"))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueClosedError, match="CLOSED"):
        load_issue(REF)


def test_a_gh_failure_is_loud(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install_gh(monkeypatch, tmp_path, "#!/bin/sh\necho 'token expired' >&2\nexit 1\n")
    with pytest.raises(IssueFetchError, match="token expired"):
        load_issue(REF)


def test_a_missing_gh_binary_is_loud(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(IssueFetchError, match="gh is not installed"):
        load_issue(REF)


def test_unreadable_state_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(json.dumps({"state": "MERGED?"}))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueFetchError, match="unreadable issue state"):
        load_issue(REF)


def test_a_null_comment_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(json.dumps({"state": "OPEN", "comments": [None]}))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueFetchError, match="unreadable"):
        load_issue(REF)


def test_a_non_dict_comment_author_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(
        json.dumps({"state": "OPEN", "comments": [{"author": "jason", "body": "text"}]})
    )
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueFetchError, match="unreadable"):
        load_issue(REF)


def test_a_non_object_payload_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text("[]")
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueFetchError, match="unreadable issue payload"):
        load_issue(REF)


def test_the_gh_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import progettare.github as github

    monkeypatch.setattr(github, "GH_TIMEOUT_SECONDS", 0.2)
    install_gh(monkeypatch, tmp_path, "#!/bin/sh\nsleep 5\n")
    with pytest.raises(IssueFetchError, match="timed out"):
        load_issue(REF)


def test_the_state_recheck_passes_an_open_issue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(canned_issue(1))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    ensure_issue_open(REF)


def test_unicode_content_decodes_as_utf8(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    body = "Acceptance:\n- naïve: write artifacts…"
    issue_text = json.dumps(
        {
            "number": 1,
            "title": "M1: intake and card context assembly",
            "body": body,
            "state": "OPEN",
            "url": "https://github.com/ViviDynamics/progettare/issues/1",
            "comments": [],
        },
        ensure_ascii=False,
    )
    payload.write_text(issue_text, encoding="utf-8")
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    issue = load_issue(REF)
    assert issue.body == body


def test_the_state_recheck_aborts_a_closed_issue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = tmp_path / "issue.json"
    payload.write_text(canned_issue(1, "CLOSED"))
    install_gh(monkeypatch, tmp_path, gh_cat(str(payload)))
    with pytest.raises(IssueClosedError, match="CLOSED"):
        ensure_issue_open(REF)
