"""Read-only command caps for survey sessions.

Survey sessions answer questions about the repository; they never change
it. Every command a session may run is checked here: the program must be
a reader, its flags must keep it reading, and the command may not pipe,
redirect, substitute, or smuggle a second command past the check. Every
command recorded in an artifact is checked against the same allowlist.
"""

from __future__ import annotations

import re
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

_FORBIDDEN_CHARS = tuple("|;&<>`$")

_FLAG_CHARS = {
    "cat": "nbETAs",
    "grep": "iRnrlvwc",
    "head": "qvs",
    "ls": "aAlCrtSUFdGimnps1",
    "tail": "qvs",
    "wc": "lwcmL",
}

_VALUE_FLAGS = {"head": ("-n", "-c"), "tail": ("-n", "-c")}

_FIND_WRITERS = (
    "-delete",
    "-exec",
    "-execdir",
    "-fls",
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-ok",
    "-okdir",
)

_RG_EXECUTION_FLAGS = ("--pre", "--pre-glob", "--hostname-bin")

_GIT_LISTING_FLAGS = ("--list", "-l", "-a", "-r")


def _is_flag_chars(arg: str, allowed: str) -> bool:
    return (
        arg.startswith("-")
        and not arg.startswith("--")
        and set(arg[1:]) <= set(allowed)
    )


def _check_flagged(program: str, arguments: tuple[str, ...]) -> None:
    allowed = _FLAG_CHARS[program]
    value_flags = _VALUE_FLAGS.get(program, ())
    expect_value = False
    for argument in arguments:
        if expect_value:
            expect_value = False
            continue
        if argument in value_flags:
            expect_value = True
            continue
        if argument.startswith("--"):
            raise SurveyCommandError(
                f"{program} {argument} is not allowed; long flags are refused"
            )
        if argument.startswith("-"):
            if program in ("head", "tail") and re.fullmatch(r"-[nc]\d+", argument):
                continue
            if program in ("head", "tail") and argument[1:].isdigit():
                continue
            if not set(argument[1:]) <= set(allowed):
                raise SurveyCommandError(
                    f"{program} {argument} is not allowed; "
                    f"flag characters allowed: {allowed}"
                )


def _check_find(arguments: tuple[str, ...]) -> None:
    for argument in arguments:
        if argument.startswith("-fp") or argument in _FIND_WRITERS:
            raise SurveyCommandError(
                f"find {argument} writes, executes, or deletes; a survey "
                "session may only read"
            )


def _check_rg(arguments: tuple[str, ...]) -> None:
    for argument in arguments:
        if any(
            argument == flag or argument.startswith(flag + "=")
            for flag in _RG_EXECUTION_FLAGS
        ):
            raise SurveyCommandError(
                f"rg {argument} runs helper programs; a survey session may only read"
            )


def _check_tree(arguments: tuple[str, ...]) -> None:
    for argument in arguments:
        if argument == "-o" or argument.startswith("--output"):
            raise SurveyCommandError(
                f"tree {argument} writes a report file; a survey session may only read"
            )


def _check_git(arguments: tuple[str, ...]) -> None:
    subcommand = arguments[0]
    rest = arguments[1:]
    if subcommand in ("branch", "tag"):
        listing = any(flag in rest for flag in _GIT_LISTING_FLAGS) or (
            subcommand == "tag" and any(f.startswith("-n") for f in rest)
        )
        for argument in rest:
            if not argument.startswith("-") and not listing:
                raise SurveyCommandError(
                    f"git {subcommand} {argument} would create a ref; "
                    "listing flags are required"
                )
        return
    for argument in rest:
        if argument.startswith("--output") or argument == "--ext-diff":
            raise SurveyCommandError(
                f"git {subcommand} {argument} writes or executes; "
                "a survey session may only read"
            )
        if argument in ("--open-files-in-pager", "-O"):
            raise SurveyCommandError(
                f"git {subcommand} {argument} opens a pager program; "
                "a survey session may only read"
            )


def validate_session_command(command: str) -> None:
    """Raise unless ``command`` is a read-only command a session may run."""
    for character in _FORBIDDEN_CHARS:
        if character in command:
            raise SurveyCommandError(
                f"{command!r} uses {character!r}; a survey session may not "
                "pipe, redirect, or substitute, only read"
            )
    if "\n" in command or "\r" in command:
        raise SurveyCommandError(
            f"{command!r} spans lines; a survey session runs one read-only "
            "command per entry"
        )
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise SurveyCommandError(f"unparsable command {command!r}: {error}") from error
    if not tokens:
        raise SurveyCommandError("empty command")
    program, arguments = tokens[0], tuple(tokens[1:])
    if program == "git":
        if not arguments or arguments[0] not in READ_ONLY_GIT_SUBCOMMANDS:
            subcommand = arguments[0] if arguments else "<missing>"
            raise SurveyCommandError(
                f"git {subcommand} is not a read-only git subcommand; "
                f"allowed: {', '.join(READ_ONLY_GIT_SUBCOMMANDS)}"
            )
        _check_git(arguments)
        return
    if program not in READ_ONLY_COMMANDS:
        raise SurveyCommandError(
            f"{program} is not a read-only survey command; "
            f"allowed: {', '.join(READ_ONLY_COMMANDS)}"
        )
    if program in _FLAG_CHARS:
        _check_flagged(program, arguments)
    elif program == "find":
        _check_find(arguments)
    elif program == "rg":
        _check_rg(arguments)
    elif program == "tree":
        _check_tree(arguments)


def validate_session_commands(commands: tuple[str, ...]) -> None:
    """Validate every command in a session, naming the first refusal."""
    for command in commands:
        validate_session_command(command)
