import json
from pathlib import Path

import pytest

from progettare.contract import ARTIFACT_VERSION
from progettare.engine.intake import assemble
from progettare.engine.run import RunDirectoryError, create_run_dir, write_intake
from progettare.issue_ref import parse_issue_ref
from test_github import canned_issue
from test_intake import make_issue

REF = parse_issue_ref("ViviDynamics/progettare#1")


def test_the_run_dir_lives_outside_the_surveyed_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    base = tmp_path / "runs"
    run_dir = create_run_dir(base, REF, repo)
    assert run_dir.is_dir()
    assert run_dir.name.startswith("2")
    assert REF.slug() in run_dir.name
    assert base in run_dir.parents
    assert repo not in run_dir.parents


def test_a_run_dir_inside_the_surveyed_repo_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    inside = repo / "runs"
    try:
        create_run_dir(inside, REF, repo)
    except RunDirectoryError as exc:
        assert "writes nothing there" in str(exc)
    else:
        raise AssertionError("a run dir inside the repo must be refused")


def test_two_runs_in_the_same_second_do_not_share_a_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import progettare.engine.run as run_module

    monkeypatch.setattr(run_module, "_utc_now", lambda: "20261004T190000Z")
    repo = tmp_path / "repo"
    repo.mkdir()
    first = create_run_dir(tmp_path / "runs", REF, repo)
    second = create_run_dir(tmp_path / "runs", REF, repo)
    assert first != second
    assert first.name == f"20261004T190000Z-{REF.slug()}"
    assert second.name == f"20261004T190000Z-{REF.slug()}-2"
    assert (second / "intake.json").exists() is False


def test_intake_json_is_version_stamped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    issue = make_issue("Acceptance:\n- one\n- two")
    context = assemble(issue, str(repo))
    run_dir = create_run_dir(tmp_path / "runs", REF, repo)
    path = write_intake(run_dir, context, "2026-10-04T00:00:00Z")
    assert path == run_dir / "intake.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["artifact"] == "intake"
    assert payload["artifact_version"] == ARTIFACT_VERSION
    assert payload["progettare"]
    assert payload["written_at"] == "2026-10-04T00:00:00Z"
    assert payload["status"] == "ok"
    assert payload["issue"]["title"] == issue.title
    assert payload["acceptance_criteria"] == ["one", "two"]
    assert payload["clarifications"] == []


def test_a_blocked_intake_still_writes_its_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    context = assemble(make_issue("Acceptance:\n- TBD"), str(repo))
    run_dir = create_run_dir(tmp_path / "runs", REF, repo)
    write_intake(run_dir, context, "2026-10-04T00:00:00Z")
    payload = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["blocked_questions"]


def test_the_surveyed_repo_stays_untouched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = repo / "only-file.txt"
    marker.write_text("untouched")
    before = sorted(p.name for p in repo.iterdir())
    context = assemble(make_issue(canned_issue(1)), str(repo))
    write_intake(create_run_dir(tmp_path / "runs", REF, repo), context, "x")
    after = sorted(p.name for p in repo.iterdir())
    assert before == after == ["only-file.txt"]
    assert marker.read_text(encoding="utf-8") == "untouched"
