"""Read-only command caps for survey sessions.

Survey sessions answer questions about the repository; they never change
it. Every command a session may run is in the allowlist here, and every
command recorded in an artifact is checked against it. Pipes, redirects,
and command substitutions are refused because they carry writes past any
single-command check.
"""

from __future__ import annotations

import shlex


class SurveyCommandError(ValueError):
    """A command a survey session may not run, named loudly."""


READ_ONLY_COMMANDS = (
    "cat",
    "find",
    "grep",
    "head",
    "ls",
    "rg",
    "tail",
    "tree",
    "wc",
    "git",
)

READ_ONLY_GIT_SUBCOMMANDS = (
    "branch",
    "diff",
    "grep",
    "log",
    "ls-files",
    "rev-parse",
    "show",
    "status",
    "tag",
)

_FORBIDDEN_CHARS = set("|;&<>`$")


def validate_session_command(command: str) -> None:
    """Raise unless ``command`` is a read-only command a session may run."""
    for character in _FORBIDDEN_CHARS:
        if character in command:
            raise SurveyCommandError(
                f"{command!r} uses {character!r}; a survey session may not "
                "pipe, redirect, or substitute, only read"
            )
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise SurveyCommandError(f"unparsable command {command!r}: {error}") from error
    if not tokens:
        raise SurveyCommandError("empty command")
    program, arguments = tokens[0], tokens[1:]
    if program == "git":
        if not arguments or arguments[0] not in READ_ONLY_GIT_SUBCOMMANDS:
            subcommand = arguments[0] if arguments else "<missing>"
            raise SurveyCommandError(
                f"git {subcommand} is not a read-only git subcommand; "
                f"allowed: {', '.join(READ_ONLY_GIT_SUBCOMMANDS)}"
            )
        return
    if program not in READ_ONLY_COMMANDS:
        raise SurveyCommandError(
            f"{program} is not a read-only survey command; "
            f"allowed: {', '.join(READ_ONLY_COMMANDS)}"
        )


def validate_session_commands(commands: tuple[str, ...]) -> None:
    """Validate every command in a session, naming the first refusal."""
    for command in commands:
        validate_session_command(command)
