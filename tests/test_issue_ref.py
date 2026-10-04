import pytest

from progettare.issue_ref import IssueRef, IssueRefError, parse_issue_ref


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
