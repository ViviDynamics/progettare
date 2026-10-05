"""Question formulation: code decides what the survey asks.

Determinism is the contract. The same intake context and repository tree
produce the same questions in the same order, so a survey can be replayed
and audited without another model call. Questions come from the acceptance
criteria first, then from the repository structure: entry points and test
layout. The question cap in config truncates the list, and the truncation
is recorded, never silent.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from progettare.config import Config
from progettare.engine.intake import CardContext


class SurveyError(ValueError):
    """A survey progettare cannot formulate, named loudly."""


@dataclass(frozen=True)
class RepoStructure:
    """What the repository looks like, as observed by read-only commands."""

    tree: tuple[str, ...]
    touched: tuple[str, ...]
    entry_points: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True)
class SurveyQuestion:
    """One bounded question, traced to the criterion that motivated it."""

    number: int
    text: str
    criterion: str | None
    command_budget: int


@dataclass(frozen=True)
class SurveyPlan:
    """The formulated question set, its caps, and why it is partial."""

    issue_number: int
    repo: str
    structure: RepoStructure
    questions: tuple[SurveyQuestion, ...]
    command_budget: int
    partial_reason: str | None


_TOP_LEVEL_ENTRY_POINTS = {
    "cargo.toml",
    "go.mod",
    "makefile",
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}
_ENTRY_POINT_NAMES = {
    "__main__.py",
    "app.py",
    "asgi.py",
    "cli.py",
    "index.js",
    "main.py",
    "manage.py",
    "mod.rs",
    "server.py",
    "wsgi.py",
}
_TEST_DIR_PARTS = {"test", "tests", "spec", "specs"}
_PATHISH = re.compile(r"[\w][\w./-]*")
_MAX_HINTS = 3


def _is_test_file(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in _TEST_DIR_PARTS for part in parts[:-1]):
        return True
    name = parts[-1].lower()
    if name.startswith(("test_", "spec_")):
        return True
    stem, dot, _suffix = name.rpartition(".")
    if not dot:
        return False
    return stem.endswith(("_test", ".test", ".spec"))


def _is_entry_point(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if len(parts) == 1:
        name = parts[0].lower()
        return name in _TOP_LEVEL_ENTRY_POINTS or name in _ENTRY_POINT_NAMES
    first = parts[0].lower()
    if first in ("bin", "cmd"):
        return len(parts) == 2
    return parts[-1].lower() in _ENTRY_POINT_NAMES


def structure_from_files(files: tuple[str, ...] | list[str]) -> RepoStructure:
    """Classify an observed file list into the structure the survey reads."""
    tree = tuple(sorted(set(files)))
    return RepoStructure(
        tree=tree,
        touched=(),
        entry_points=tuple(f for f in tree if _is_entry_point(f)),
        tests=tuple(f for f in tree if _is_test_file(f)),
    )


def observe_repo(repo_path: Path) -> RepoStructure:
    """Observe the repository tree with one read-only git command.

    NUL-delimited output keeps unusual filenames verbatim; without it,
    git quotes paths and the classifier would store quoted names.
    """
    listing = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if listing.returncode == 0:
        files = tuple(
            entry.decode("utf-8", "surrogateescape")
            for entry in listing.stdout.split(b"\0")
            if entry
        )
        return structure_from_files(files)
    if listing.returncode == 128:
        raise SurveyError(f"{repo_path} is not a git repository; refusing to walk it")
    raise SurveyError(
        f"git ls-files failed in {repo_path}: "
        f"{listing.stderr.decode('utf-8', 'replace').strip()}"
    )


def _touched_for(criterion: str, tree: tuple[str, ...]) -> tuple[str, ...]:
    """Path-like tokens in the criterion that name files in the tree.

    Suffix matches must start at a path-component boundary, so prose
    words and filename fragments never consume the hint budget.
    """
    touched: list[str] = []
    for token in re.findall(_PATHISH, criterion):
        token = token.rstrip(".,;:!?")
        for entry in tree:
            if entry == token or entry.endswith("/" + token):
                if entry not in touched:
                    touched.append(entry)
            if len(touched) >= _MAX_HINTS:
                return tuple(touched)
    return tuple(touched)


def _criterion_question(
    number: int, criterion: str, tree: tuple[str, ...], command_budget: int
) -> SurveyQuestion:
    hints = _touched_for(criterion, tree)
    hint_text = ""
    if hints:
        hint_text = "\nStarting points in the tree: " + ", ".join(hints) + "."
    return SurveyQuestion(
        number=number,
        text=(
            f"Acceptance criterion {number}: {criterion}\n"
            "Identify the files and code paths that must change to satisfy "
            f"it, and what each change is.{hint_text}"
        ),
        criterion=criterion,
        command_budget=command_budget,
    )


def formulate(ctx: CardContext, structure: RepoStructure, config: Config) -> SurveyPlan:
    """The bounded question set for this card, derived without a model."""
    if ctx.status == "blocked":
        raise SurveyError(
            "intake blocked the card; the survey formulates no questions "
            "until the blockers are answered"
        )
    cap = config.survey_max_questions
    budget = config.survey_per_question_command_budget
    draft: list[SurveyQuestion] = []
    for position, criterion in enumerate(ctx.acceptance_criteria, start=1):
        draft.append(_criterion_question(position, criterion, structure.tree, budget))
    if structure.entry_points:
        draft.append(
            SurveyQuestion(
                number=0,
                text=(
                    "Which of these files are the entry points of this "
                    "repository, what do they load, and how is the "
                    "project invoked?\nEntry candidates: "
                    + ", ".join(structure.entry_points)
                ),
                criterion=None,
                command_budget=budget,
            )
        )
    if structure.tests:
        draft.append(
            SurveyQuestion(
                number=0,
                text=(
                    "What is the test layout: which suites cover what, "
                    "and how are they invoked?\nTest files observed: "
                    + ", ".join(structure.tests[:_MAX_HINTS])
                    + (
                        f" and {len(structure.tests) - _MAX_HINTS} more"
                        if len(structure.tests) > _MAX_HINTS
                        else ""
                    )
                ),
                criterion=None,
                command_budget=budget,
            )
        )
    questions = tuple(
        replace(question, number=position)
        for position, question in enumerate(draft[:cap], start=1)
    )
    touched: list[str] = []
    for criterion in ctx.acceptance_criteria:
        for entry in _touched_for(criterion, structure.tree):
            if entry not in touched:
                touched.append(entry)
    plan_structure = replace(structure, touched=tuple(touched))
    partial_reason = None
    if len(draft) > cap:
        partial_reason = (
            f"question cap reached: survey.max_questions is {cap}, "
            f"{len(draft) - cap} question(s) not formulated"
        )
    return SurveyPlan(
        issue_number=ctx.issue.number,
        repo=f"{ctx.issue.owner}/{ctx.issue.repo}",
        structure=plan_structure,
        questions=questions,
        command_budget=budget,
        partial_reason=partial_reason,
    )


def plan_for(ctx: CardContext, config: Config) -> SurveyPlan:
    """Observe the repository, then formulate. The engine's entry point."""
    return formulate(ctx, observe_repo(Path(ctx.repo_path)), config)
