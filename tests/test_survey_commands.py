"""Tests for the read-only survey command allowlist."""

from __future__ import annotations

import re

import pytest

from progettare.survey.commands import (
    SurveyCommandError,
    validate_session_command,
    validate_session_commands,
)


@pytest.mark.parametrize(
    "command",
    [
        "cat src/progettare/config.py",
        "ls",
        "ls -la",
        "head -n 20 README.md",
        "tail -n 5 pyproject.toml",
        "wc -l src/**/*.py",
        "grep -rn 'config' src",
        "rg --files",
        "find . -name '*.py'",
        "tree src",
        "git status",
        "git log --oneline -5",
        "git diff main",
        "git show HEAD",
        "git ls-files",
        "git grep 'TODO'",
        "git rev-parse HEAD",
        "git branch --list",
        "git tag --list 'v*'",
    ],
)
def test_read_only_commands_are_allowed(command: str) -> None:
    validate_session_command(command)


@pytest.mark.parametrize(
    ("command", "refusal"),
    [
        ("git push", "git push is not a read-only git subcommand"),
        ("git add src/progettare/config.py", "git add is not a read-only"),
        ("git commit -m 'nope'", "git commit is not a read-only"),
        ("git checkout -b feat", "git checkout is not a read-only"),
        ("git clean -fd", "git clean is not a read-only"),
        ("mv a b", "mv is not a read-only survey command"),
        ("rm -rf /", "rm is not a read-only survey command"),
        ("python script.py", "python is not a read-only survey command"),
        ("touch newfile", "touch is not a read-only survey command"),
        ("echo hi > out.txt", "uses '>'"),
        ("cat in > out", "uses '>'"),
        ("cat a; rm b", "uses ';'"),
        ("cat a && rm b", "uses '&'"),
        ("cat a | grep b", "uses '|'"),
        ("echo $(date)", "uses '$'"),
        ("echo `date`", "uses '`'"),
        ("cat < in", "uses '<'"),
    ],
)
def test_writes_and_mutations_are_refused(command: str, refusal: str) -> None:
    with pytest.raises(SurveyCommandError, match=re.escape(refusal)):
        validate_session_command(command)


def test_empty_command_is_refused() -> None:
    with pytest.raises(SurveyCommandError, match="empty command"):
        validate_session_command("")


def test_unbalanced_quote_is_refused() -> None:
    with pytest.raises(SurveyCommandError, match="unparsable command"):
        validate_session_command("cat 'unterminated")


def test_every_command_in_a_session_is_validated() -> None:
    with pytest.raises(SurveyCommandError, match="git push"):
        validate_session_commands(("cat README.md", "git push"))


def test_the_allowlist_is_read_only_by_construction() -> None:
    for command in ("mv", "rm", "rmdir", "cp", "touch", "mkdir", "tee", "sed"):
        with pytest.raises(SurveyCommandError, match="is not a read-only survey"):
            validate_session_command(command)
