import pathlib
import subprocess

import pytest

from progettare.issue_ref import (
    IssueRef,
    IssueRefError,
    parse_issue_ref,
    resolve_issue_ref,
)


def test_a_full_issue_url_parses() -> None:
    ref = parse_issue_ref("https://github.com/ViviDynamics/progettare/issues/1")
    assert ref == IssueRef(owner="ViviDynamics", repo="progettare", number=1)


def test_a_short_reference_parses() -> None:
    ref = parse_issue_ref("ViviDynamics/progettare#1")
    assert ref == IssueRef(owner="ViviDynamics", repo="progettare", number=1)


def test_the_url_is_matched_exactly() -> None:
    with pytest.raises(IssueRefError, match="not a GitHub issue URL"):
        parse_issue_ref("https://github.com/ViviDynamics/progettare/issues/")
    with pytest.raises(IssueRefError, match="not an issue reference"):
        parse_issue_ref("progettare#1")
    with pytest.raises(IssueRefError, match="issue reference is required"):
        parse_issue_ref("")


def test_a_pull_request_is_refused_by_name() -> None:
    with pytest.raises(IssueRefError, match="pull request"):
        parse_issue_ref("https://github.com/ViviDynamics/progettare/pull/42")


def test_the_reference_renders_a_run_directory_slug() -> None:
    ref = parse_issue_ref("https://github.com/ViviDynamics/progettare/issues/1")
    assert ref.slug() == "ViviDynamics-progettare-1"
    assert ref.repository() == "ViviDynamics/progettare"


def test_issue_number_zero_is_refused() -> None:
    with pytest.raises(IssueRefError, match="start at 1"):
        parse_issue_ref("ViviDynamics/progettare#0")
    with pytest.raises(IssueRefError, match="start at 1"):
        parse_issue_ref("https://github.com/ViviDynamics/progettare/issues/0")


def test_a_bare_number_resolves_against_the_checkouts_origin(
    tmp_path: pathlib.Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "https://github.com/ViviDynamics/progettare.git",
        ],
        check=True,
        capture_output=True,
    )
    ref = resolve_issue_ref("9", str(tmp_path))
    assert (ref.owner, ref.repo, ref.number) == ("ViviDynamics", "progettare", 9)


def test_a_bare_number_resolves_an_ssh_origin(tmp_path: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "git@github.com:ViviDynamics/progettare.git",
        ],
        check=True,
        capture_output=True,
    )
    ref = resolve_issue_ref("9", str(tmp_path))
    assert ref.repository() == "ViviDynamics/progettare"


def test_a_bare_number_without_an_origin_is_refused(tmp_path: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    with pytest.raises(IssueRefError, match="no origin remote"):
        resolve_issue_ref("9", str(tmp_path))


def test_a_bare_number_against_a_non_github_origin_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "https://gitlab.com/owner/repo.git",
        ],
        check=True,
        capture_output=True,
    )
    with pytest.raises(IssueRefError, match="not a GitHub repository"):
        resolve_issue_ref("9", str(tmp_path))


def test_urls_and_short_refs_pass_through_resolution() -> None:
    resolved = resolve_issue_ref("ViviDynamics/progettare#9", "/nowhere")
    assert resolved.repository() == "ViviDynamics/progettare"
    url = resolve_issue_ref(
        "https://github.com/ViviDynamics/progettare/issues/9", "/nowhere"
    )
    assert url.number == 9
