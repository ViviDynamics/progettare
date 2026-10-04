from dataclasses import FrozenInstanceError

import pytest

from progettare.engine.issue_ref import IssueRef, IssueRefError, parse_issue_ref


def test_https_issue_url_parses() -> None:
    ref = parse_issue_ref("https://github.com/octo-org/repo/issues/123")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=123)


def test_http_issue_url_parses() -> None:
    ref = parse_issue_ref("http://github.com/acme-corp/widgets.rs/issues/456")

    assert ref == IssueRef(owner="acme-corp", repo="widgets.rs", number=456)


def test_www_https_issue_url_parses() -> None:
    ref = parse_issue_ref("https://www.github.com/octo-org/repo/issues/7")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=7)


def test_www_http_issue_url_parses() -> None:
    ref = parse_issue_ref("http://www.github.com/octo-org/repo/issues/8")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=8)


def test_issue_url_with_single_trailing_slash_parses() -> None:
    ref = parse_issue_ref("https://github.com/octo-org/repo/issues/123/")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=123)


def test_shorthand_parses() -> None:
    ref = parse_issue_ref("octo-org/repo#42")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=42)


def test_shorthand_accepts_all_name_characters() -> None:
    ref = parse_issue_ref("o-w1.2_/r-p3.o4#9")

    assert ref == IssueRef(owner="o-w1.2_", repo="r-p3.o4", number=9)


def test_whitespace_padded_shorthand_parses() -> None:
    ref = parse_issue_ref("  octo-org/repo#42\n")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=42)


def test_whitespace_padded_url_parses() -> None:
    ref = parse_issue_ref("\n  https://github.com/octo-org/repo/issues/5 ")

    assert ref == IssueRef(owner="octo-org", repo="repo", number=5)


@pytest.mark.parametrize(
    "text",
    [
        "123",
        "#123",
        "octo-org/repo",
        "octo-org/repo#abc",
        "",
        "   ",
        "  123  ",
        "https://gitlab.com/octo-org/repo/issues/123",
        "ftp://github.com/octo-org/repo/issues/123",
        "https://github.com/octo-org/repo/issues/",
        "https://github.com/octo-org/repo/issues/123//",
    ],
)
def test_invalid_reference_raises(text: str) -> None:
    with pytest.raises(IssueRefError):
        parse_issue_ref(text)


def test_pulls_url_rejects_with_pull_request_message() -> None:
    with pytest.raises(IssueRefError, match="pull request"):
        parse_issue_ref("https://github.com/octo-org/repo/pulls/123")


def test_pull_url_rejects_with_pull_request_message() -> None:
    with pytest.raises(IssueRefError, match="pull request"):
        parse_issue_ref("https://github.com/octo-org/repo/pull/123")


def test_error_message_states_accepted_forms() -> None:
    with pytest.raises(IssueRefError, match="owner/repo#123"):
        parse_issue_ref("not a reference")


def _assign(obj: object, name: str, value: object) -> None:
    setattr(obj, name, value)


def test_issue_ref_is_frozen() -> None:
    ref = IssueRef(owner="octo-org", repo="repo", number=1)

    with pytest.raises(FrozenInstanceError):
        _assign(ref, "owner", "other")


def test_issue_ref_error_is_value_error() -> None:
    assert issubclass(IssueRefError, ValueError)
