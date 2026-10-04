"""Tests for deterministic survey question formulation and caps."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from progettare.config import Config, ModelRail
from progettare.engine.intake import CardContext
from progettare.github import Issue
from progettare.survey.questions import (
    RepoStructure,
    SurveyError,
    formulate,
    observe_repo,
    structure_from_files,
)


def make_config(max_questions: int = 5, budget: int = 8) -> Config:
    rail = ModelRail(provider="p", model="m", base_url=None)
    return Config(
        survey_max_questions=max_questions,
        survey_per_question_command_budget=budget,
        budget_survey_stage_tokens=150000,
        budget_blueprint_stage_tokens=60000,
        budget_run_max_tokens=300000,
        size_single_turn_max_milestones=2,
        size_documenter_min_topics=1,
        survey_rail=rail,
        blueprint_rail=rail,
    )


def make_ctx(
    criteria: tuple[str, ...] = ("Ship the thing.",),
    status: str = "ok",
    repo_path: str = "/tmp/repo",
) -> CardContext:
    issue = Issue(
        owner="acme",
        repo="widgets",
        number=7,
        title="t",
        body="",
        state="OPEN",
        url="https://github.com/acme/widgets/issues/7",
        comments=(),
    )
    return CardContext(
        issue=issue,
        repo_path=repo_path,
        acceptance_criteria=tuple(criteria),
        clarifications=(),
        status=status,
        blocked_questions=(),
    )


TREE = (
    "bin/pg",
    "docs/CONFIG.md",
    "pyproject.toml",
    "src/progettare/__init__.py",
    "src/progettare/cli.py",
    "src/progettare/engine/tests/test_run.py",
    "tests/test_config.py",
    "web/src/main.js",
    "web/src/foo.test.ts",
)

STRUCTURE = RepoStructure(
    tree=TREE,
    touched=(),
    entry_points=("bin/pg", "pyproject.toml", "src/progettare/cli.py"),
    tests=(
        "src/progettare/engine/tests/test_run.py",
        "tests/test_config.py",
        "web/src/foo.test.ts",
    ),
)


def test_structure_classifies_tests_entry_points(tmp_path: pathlib.Path) -> None:
    structure = structure_from_files(TREE)
    assert structure.entry_points == (
        "bin/pg",
        "pyproject.toml",
        "src/progettare/cli.py",
    )
    assert structure.tests == (
        "src/progettare/engine/tests/test_run.py",
        "tests/test_config.py",
        "web/src/foo.test.ts",
    )


def test_deep_test_directories_and_naming_conventions() -> None:
    structure = structure_from_files(
        (
            "pkg/src/tests/unit/test_deep.py",
            "src/spec/user_story_spec.py",
            "src/mod/python_test.py",
            "src/mod/foo.spec.ts",
            "top_level_test.py",
            "src/plain.py",
        )
    )
    assert structure.tests == (
        "pkg/src/tests/unit/test_deep.py",
        "src/mod/foo.spec.ts",
        "src/mod/python_test.py",
        "src/spec/user_story_spec.py",
        "top_level_test.py",
    )
    assert "src/plain.py" not in structure.tests


def test_touched_files_come_from_criteria_text() -> None:
    structure = structure_from_files(("src/progettare/config.py", "src/other.py"))
    question = formulate(
        make_ctx(criteria=("Update src/progettare/config.py to load faster.",)),
        structure,
        make_config(),
    )
    hints = question.questions[0].text
    assert "src/progettare/config.py" in hints
    assert "src/other.py" not in hints


def test_one_question_per_criterion_then_structural_questions() -> None:
    plan = formulate(
        make_ctx(criteria=("First.", "Second.")),
        STRUCTURE,
        make_config(),
    )
    assert [q.criterion for q in plan.questions[:2]] == ["First.", "Second."]
    texts = [q.text for q in plan.questions]
    assert any("entry points" in t for t in texts)
    assert any("test layout" in t for t in texts)
    assert plan.partial_reason is None


def test_cap_truncates_and_marks_the_plan_partial() -> None:
    plan = formulate(
        make_ctx(criteria=("One.", "Two.", "Three.")),
        RepoStructure(tree=TREE, touched=(), entry_points=(), tests=()),
        make_config(max_questions=2),
    )
    assert len(plan.questions) == 2
    assert plan.partial_reason is not None
    assert "survey.max_questions is 2" in plan.partial_reason
    assert "1 question(s) not formulated" in plan.partial_reason


def test_budget_from_config_is_attached_to_every_question() -> None:
    plan = formulate(make_ctx(), STRUCTURE, make_config(budget=4))
    assert plan.command_budget == 4
    assert all(q.command_budget == 4 for q in plan.questions)


def test_blocked_context_formulates_nothing() -> None:
    with pytest.raises(SurveyError, match="intake blocked the card"):
        formulate(make_ctx(status="blocked"), STRUCTURE, make_config())


def test_formulation_is_deterministic() -> None:
    ctx = make_ctx(criteria=("First.", "Second."))
    first = formulate(ctx, STRUCTURE, make_config())
    second = formulate(ctx, STRUCTURE, make_config())
    assert first == second
    assert first.questions == second.questions


def test_plan_carries_issue_identity() -> None:
    plan = formulate(make_ctx(), STRUCTURE, make_config())
    assert plan.issue_number == 7
    assert plan.repo == "acme/widgets"


def test_observe_repo_runs_read_only_git_ls_files(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_x(): pass\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    structure = observe_repo(repo)
    assert structure.tree == ("pyproject.toml", "tests/test_x.py")
    assert structure.tests == ("tests/test_x.py",)
    assert structure.entry_points == ("pyproject.toml",)


def test_observe_repo_refuses_a_non_git_directory(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(SurveyError, match="not a git repository"):
        observe_repo(tmp_path)
