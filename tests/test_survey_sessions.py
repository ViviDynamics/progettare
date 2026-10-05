"""Tests for bounded read-only nare sessions and stage budgeting."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable

import pytest

from progettare.config import Config, ModelRail
from progettare.engine.intake import CardContext
from progettare.github import Issue
from progettare.survey.artifact import SurveyAnswer, SurveyRecordError, survey_record
from progettare.survey.commands import SurveyCommandError
from progettare.survey.questions import (
    RepoStructure,
    SurveyPlan,
    SurveyQuestion,
    formulate,
)
from progettare.survey.sessions import (
    READ_ONLY_SYSTEM_PROMPT,
    SessionState,
    SurveySessionError,
    build_session_argv,
    prompt_text,
    render_tree,
    run_session,
    run_sessions,
)

RAIL = ModelRail(provider="p", model="m", base_url=None)
RAIL_PROXY = ModelRail(provider="p", model="m", base_url="http://localhost:8000")
STRUCTURE = RepoStructure(tree=("src/x.py",), touched=(), entry_points=(), tests=())


def make_question(number: int = 1, command_budget: int = 2) -> SurveyQuestion:
    return SurveyQuestion(
        number=number,
        text=f"question {number}",
        criterion=None,
        command_budget=command_budget,
    )


def make_config(tokens: int = 100, max_questions: int = 5) -> Config:
    return Config(
        survey_max_questions=max_questions,
        survey_per_question_command_budget=2,
        budget_survey_stage_tokens=tokens,
        budget_blueprint_stage_tokens=60000,
        budget_run_max_tokens=300000,
        size_single_turn_max_milestones=2,
        size_documenter_min_topics=1,
        survey_rail=RAIL,
        blueprint_rail=RAIL,
    )


def make_plan(max_questions: int = 5) -> SurveyPlan:
    ctx = CardContext(
        issue=Issue(
            owner="acme",
            repo="widgets",
            number=9,
            title="t",
            body="",
            state="OPEN",
            url="u",
            comments=(),
        ),
        repo_path="/tmp/repo",
        acceptance_criteria=("One.", "Two.", "Three."),
        clarifications=(),
        status="ok",
        blocked_questions=(),
    )
    return formulate(ctx, STRUCTURE, make_config(max_questions=max_questions))


def cost_event(input_tokens: int, output: int = 0) -> str:
    return json.dumps(
        {
            "type": "cost",
            "text": f"{input_tokens} in / {output} out",
            "detail": {"input": input_tokens, "output": output},
        }
    )


def bash_event(command: str) -> str:
    return json.dumps(
        {"type": "tool_use", "text": "bash", "detail": {"command": command}}
    )


def read_event(path: str) -> str:
    return json.dumps({"type": "tool_use", "text": "read", "detail": {"path": path}})


def output_event(text: str) -> str:
    return json.dumps({"type": "output", "text": text, "detail": {}})


class FakeProcess:
    def __init__(self, lines: list[str]) -> None:
        self.stdout: Iterable[str] = iter(lines)
        self.returncode = 0
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    def wait(self) -> None:
        pass


def test_cost_events_accumulate_and_overrun_kills() -> None:
    state = SessionState(make_question(), token_share=100)
    state.consume(cost_event(60))
    assert not state.exceeded
    state.consume(cost_event(60, 5))
    assert state.exceeded
    assert state.partial_reason is not None
    assert "token budget exceeded" in state.partial_reason
    assert state.tokens_used == 125


def test_bash_commands_are_allowlisted_live() -> None:
    state = SessionState(make_question(), token_share=100)
    state.consume(bash_event("ls src"))
    assert state.commands == ("ls src",)
    with pytest.raises(SurveyCommandError, match="rm"):
        state.consume(bash_event("rm src/x.py"))
    assert not state.exceeded


def test_command_budget_overrun_kills_the_session() -> None:
    state = SessionState(make_question(command_budget=1), token_share=100)
    state.consume(bash_event("ls"))
    state.consume(bash_event("ls -la"))
    assert state.exceeded
    assert state.partial_reason is not None
    assert "command budget exceeded" in state.partial_reason


def test_read_tool_calls_count_toward_the_command_budget() -> None:
    state = SessionState(make_question(command_budget=1), token_share=100)
    state.consume(read_event("src/x.py"))
    assert not state.exceeded
    assert state.reads == ("src/x.py",)
    state.consume(read_event("src/y.py"))
    assert state.exceeded
    assert state.partial_reason is not None
    assert "command budget exceeded: 2 tool calls against a budget of 1" in (
        state.partial_reason
    )


def test_output_event_becomes_findings() -> None:
    state = SessionState(make_question(), token_share=100)
    state.consume(output_event("x.py defines the loader"))
    assert state.findings == "x.py defines the loader"


def test_error_event_marks_the_session_partial() -> None:
    state = SessionState(make_question(), token_share=100)
    state.consume(json.dumps({"type": "error", "text": "boom", "detail": {}}))
    assert state.exceeded
    assert state.partial_reason is not None
    assert "nare errored: boom" in state.partial_reason


def test_non_json_lines_fail_loudly() -> None:
    state = SessionState(make_question(), token_share=100)
    with pytest.raises(SurveySessionError, match="non-JSON line"):
        state.consume("not json at all")


def test_blank_lines_are_ignored() -> None:
    state = SessionState(make_question(), token_share=100)
    state.consume("")
    assert not state.exceeded


def test_argv_covers_the_family_adapter_flags(
    tmp_path: pathlib.Path,
) -> None:
    argv = build_session_argv(
        "/bin/nare",
        "question 3",
        RAIL,
        tmp_path,
        tmp_path / "session.json",
        500,
    )
    text = " ".join(argv)
    assert "/bin/nare run question 3" in text
    assert "--jsonl" in argv and "--yes" in argv
    assert argv[argv.index("--tools") + 1] == "read"
    assert argv[argv.index("--root") + 1] == str(tmp_path)
    assert argv[argv.index("--system") + 1] == READ_ONLY_SYSTEM_PROMPT
    assert argv[argv.index("--provider") + 1] == "p"
    assert argv[argv.index("--model") + 1] == "m"
    assert argv[argv.index("--max-tokens") + 1] == "500"
    assert argv[argv.index("--session") + 1].endswith("session.json")
    assert "--base-url" not in argv


def test_base_url_is_passed_when_the_rail_has_one(
    tmp_path: pathlib.Path,
) -> None:
    argv = build_session_argv(
        "/bin/nare", "question 1", RAIL_PROXY, tmp_path, tmp_path / "s.json", 100
    )
    assert argv[argv.index("--base-url") + 1] == "http://localhost:8000"


def test_prompt_carries_the_question_and_file_list() -> None:
    prompt = prompt_text(make_question(3), "src/x.py\nsrc/y.py")
    assert prompt.startswith("question 3")
    assert prompt.endswith("Repository files:\nsrc/x.py\nsrc/y.py")


def test_run_session_streams_lines_and_kills_on_refusal(
    tmp_path: pathlib.Path,
) -> None:
    lines = [bash_event("ls src"), bash_event("rm src/x.py"), output_event("x")]
    spawn_calls: list[list[str]] = []

    def spawn(argv: list[str]) -> FakeProcess:
        spawn_calls.append(argv)
        return FakeProcess(lines)

    state = run_session(
        make_question(),
        RAIL,
        tmp_path,
        tmp_path / "run",
        100,
        spawn=spawn,
        nare_path="/bin/nare",
    )
    assert state.exceeded
    assert state.commands == ("ls src",)
    assert spawn_calls and "--jsonl" in spawn_calls[0]


def test_run_session_records_an_early_exit(
    tmp_path: pathlib.Path,
) -> None:
    answered = FakeProcess([output_event("done")])
    answered.returncode = 3
    state = run_session(
        make_question(),
        RAIL,
        tmp_path,
        tmp_path / "run",
        100,
        spawn=lambda argv: answered,
        nare_path="/bin/nare",
    )
    assert not state.exceeded
    assert state.partial_reason == "nare exited 3 after producing an answer"

    silent = FakeProcess([])
    silent.returncode = 3
    state = run_session(
        make_question(),
        RAIL,
        tmp_path,
        tmp_path / "run",
        100,
        spawn=lambda argv: silent,
        nare_path="/bin/nare",
    )
    assert state.partial_reason == "nare exited 3 before answering the question"


def test_run_sessions_answers_every_question_in_budget(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan()
    spawn_calls: list[list[str]] = []

    def spawn(argv: list[str]) -> FakeProcess:
        spawn_calls.append(argv)
        return FakeProcess(
            [cost_event(10), output_event(f"findings {len(spawn_calls)}")]
        )

    config = make_config(tokens=300)
    outcome = run_sessions(
        plan, config, tmp_path, tmp_path / "run", spawn, nare_path="/bin/nare"
    )
    assert outcome.partial_reason is None
    assert [answer.findings for answer in outcome.answers] == [
        "findings 1",
        "findings 2",
        "findings 3",
    ]
    assert len(spawn_calls) == 3
    assert outcome.answers[0].partial_reason is None


def test_stage_budget_exhaustion_skips_and_notes(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan()

    def spawn(argv: list[str]) -> FakeProcess:
        return FakeProcess([cost_event(60), output_event("x")])

    config = make_config(tokens=100)
    outcome = run_sessions(
        plan, config, tmp_path, tmp_path / "run", spawn, nare_path="/bin/nare"
    )
    assert [answer.question for answer in outcome.answers] == [1, 2]
    assert outcome.partial_reason is not None
    assert "survey stage budget exhausted" in outcome.partial_reason
    assert "question(s) 3 not asked" in outcome.partial_reason


def test_zero_token_share_skips_every_question(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan()
    outcome = run_sessions(
        plan,
        make_config(tokens=2),
        tmp_path,
        tmp_path / "run",
        spawn_passthrough,
        nare_path="/bin/nare",
    )
    assert outcome.answers == ()
    assert outcome.partial_reason is not None
    assert "survey stage budget exhausted" in outcome.partial_reason
    assert "question(s) 1, 2, 3 not asked" in outcome.partial_reason


def test_final_session_overrun_marks_the_stage_partial(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan(max_questions=1)
    outcome = run_sessions(
        plan,
        make_config(tokens=100),
        tmp_path,
        tmp_path / "run",
        lambda argv: FakeProcess([cost_event(150)]),
        nare_path="/bin/nare",
    )
    assert len(outcome.answers) == 1
    assert outcome.partial_reason is not None
    assert "survey stage budget exhausted: 150 tokens against 100" in (
        outcome.partial_reason
    )
    assert "not asked" not in outcome.partial_reason


def test_missing_usage_fails_closed(tmp_path: pathlib.Path) -> None:
    plan = make_plan()
    outcome = run_sessions(
        plan,
        make_config(tokens=300),
        tmp_path,
        tmp_path / "run",
        lambda argv: FakeProcess([output_event("done")]),
        nare_path="/bin/nare",
    )
    assert [answer.question for answer in outcome.answers] == [1]
    assert outcome.partial_reason is not None
    assert "usage missing for question(s) 1" in outcome.partial_reason
    assert "question(s) 2, 3 not asked" in outcome.partial_reason


def test_whitespace_output_is_recorded_partial(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan(max_questions=1)
    outcome = run_sessions(
        plan,
        make_config(tokens=300),
        tmp_path,
        tmp_path / "run",
        lambda argv: FakeProcess([cost_event(10), output_event("  \n")]),
        nare_path="/bin/nare",
    )
    reason = "session ended without answering the question"
    assert outcome.answers[0].findings == reason
    assert outcome.answers[0].partial_reason == reason


def test_render_tree_drops_control_char_paths_and_bounds_length() -> None:
    tree = render_tree(("src/x.py", "bad\nname", "src/y.py"))
    assert "src/x.py" in tree
    assert "bad\nname" not in tree
    assert "1 paths with control characters omitted" in tree

    big = tuple(f"src/file-{i:05d}.py" for i in range(10000))
    bounded = render_tree(big)
    assert len(bounded) < 96_000 + 200
    assert "more paths omitted to fit the prompt" in bounded


def test_session_without_output_is_recorded_partial(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan()
    outcome = run_sessions(
        plan,
        make_config(tokens=300),
        tmp_path,
        tmp_path / "run",
        lambda argv: FakeProcess([]),
        nare_path="/bin/nare",
    )
    reason = "session ended without answering the question"
    assert outcome.answers[0].findings == reason
    assert outcome.answers[0].partial_reason == reason


def test_stream_error_reaps_the_child(tmp_path: pathlib.Path) -> None:
    procs: list[FakeProcess] = []

    def spawn(argv: list[str]) -> FakeProcess:
        proc = FakeProcess([bash_event("ls"), "not json at all", output_event("x")])
        procs.append(proc)
        return proc

    with pytest.raises(SurveySessionError, match="non-JSON line"):
        run_session(
            make_question(),
            RAIL,
            tmp_path,
            tmp_path / "run",
            100,
            structure_text="",
            spawn=spawn,
            nare_path="/bin/nare",
        )
    assert procs[0].killed


def test_plan_partial_reason_survives_into_the_outcome(
    tmp_path: pathlib.Path,
) -> None:
    plan = make_plan(max_questions=2)
    config = make_config(tokens=300)
    outcome = run_sessions(
        plan,
        config,
        tmp_path,
        tmp_path / "run",
        spawn_passthrough,
        nare_path="/bin/nare",
    )
    assert outcome.partial_reason is not None
    assert "survey.max_questions is 2" in outcome.partial_reason


def spawn_passthrough(argv: list[str]) -> FakeProcess:
    return FakeProcess([cost_event(10), output_event("findings")])


def test_record_accepts_stage_partial_reason() -> None:
    plan = make_plan(max_questions=1)
    answers = (
        SurveyAnswer(
            question=1, commands=("ls",), findings="f", partial_reason="killed"
        ),
    )
    record = survey_record(plan, answers, "stage budget exhausted")
    assert record["partial_reason"] == "stage budget exhausted"
    assert record["answers"][0]["partial"] == "killed"


def test_record_refuses_silent_command_overruns() -> None:
    plan = make_plan(max_questions=1)
    answers = (SurveyAnswer(question=1, commands=("ls", "cat", "wc"), findings="f"),)
    with pytest.raises(SurveyRecordError, match="without naming the overrun"):
        survey_record(plan, answers)


def test_record_refuses_overruns_named_as_something_else() -> None:
    plan = make_plan(max_questions=1)
    answers = (
        SurveyAnswer(
            question=1,
            commands=("ls", "cat", "wc"),
            findings="f",
            partial_reason="token budget exceeded: 9 tokens against a share of 5",
        ),
    )
    with pytest.raises(SurveyRecordError, match="without naming the overrun"):
        survey_record(plan, answers)
