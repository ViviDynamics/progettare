"""Bounded read-only nare sessions: one per survey question.

Every model call progettare makes goes through the nare CLI, never
directly to a provider. Each question gets its own session limited to
the read tool (nare executes bash itself, so a parent-side check could
only observe a forbidden command after it ran; the only airtight
read-only guarantee is to not give the session a bash tool at all).
This module reads the JSONL stream as it runs: every bash tool_use the
model somehow emits is refused live, and the session is killed the
moment a command or token budget is exceeded. The refusal is recorded
as data and the stage continues, per the family adapter pattern.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from progettare.config import Config, ModelRail
from progettare.survey.artifact import SurveyAnswer
from progettare.survey.commands import SurveyCommandError, validate_session_command
from progettare.survey.questions import SurveyPlan, SurveyQuestion


class SessionProcess(Protocol):
    """The smallest surface the session loop needs from a process."""

    stdout: Iterable[str]
    returncode: int

    def kill(self) -> None: ...

    def wait(self) -> None: ...


READ_ONLY_SYSTEM_PROMPT = (
    "You are a read-only codebase surveyor. You answer one question about "
    "the repository you are rooted in. Your only tool is read: there is no "
    "bash, write, or edit, and you must never try to work around that. The "
    "prompt lists the repository's files; read the ones you need and answer "
    "with specific file paths, symbols, and what the question asked."
)

_READ_ONLY_TOOLS = "read"


class SurveySessionError(ValueError):
    """A survey session progettare cannot run, named loudly."""


@dataclass
class SessionState:
    """The incremental reading of one session's JSONL stream."""

    question: SurveyQuestion
    token_share: int
    input_tokens: int = 0
    output_tokens: int = 0
    commands: tuple[str, ...] = ()
    findings: str | None = None
    partial_reason: str | None = None
    exceeded: bool = False

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens

    def consume(self, line: str) -> None:
        """Incorporate one JSONL event line, refusing loudly on garbage."""
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise SurveySessionError(
                f"nare emitted a non-JSON line: {line!r}: {error}"
            ) from error
        kind = event.get("type")
        if kind == "cost":
            detail = event.get("detail") or {}
            self.input_tokens += int(detail.get("input", 0))
            self.output_tokens += int(detail.get("output", 0))
            if self.tokens_used > self.token_share:
                self._exceed(
                    f"token budget exceeded: {self.tokens_used} tokens "
                    f"against a share of {self.token_share}"
                )
        elif kind == "tool_use":
            tool = event.get("text", "")
            detail = event.get("detail") or {}
            if tool == "bash":
                command = str(detail.get("command", ""))
                validate_session_command(command)
                commands = (*self.commands, command)
                if len(commands) > self.question.command_budget:
                    self._exceed(
                        f"command budget exceeded: {len(commands)} commands "
                        f"against a budget of {self.question.command_budget}"
                    )
                else:
                    self.commands = commands
        elif kind == "output":
            self.findings = event.get("text", "")
        elif kind == "error":
            self.partial_reason = f"nare errored: {event.get('text', '')}"
            self.exceeded = True

    def _exceed(self, reason: str) -> None:
        self.partial_reason = reason
        self.exceeded = True


def prompt_text(question: SurveyQuestion, structure_text: str) -> str:
    """The session prompt: the question plus the repository's file list."""
    files = f"\n\nRepository files:\n{structure_text}" if structure_text else ""
    return f"{question.text}{files}"


def build_session_argv(
    nare_path: str,
    prompt: str,
    rail: ModelRail,
    repo_path: Path,
    session_path: Path,
    token_share: int,
) -> list[str]:
    """The nare invocation for one question's bounded read-only session."""
    argv = [
        nare_path,
        "run",
        prompt,
        "--jsonl",
        "--yes",
        "--tools",
        _READ_ONLY_TOOLS,
        "--root",
        str(repo_path),
        "--system",
        READ_ONLY_SYSTEM_PROMPT,
        "--provider",
        rail.provider,
        "--model",
        rail.model,
        "--max-tokens",
        str(token_share),
        "--session",
        str(session_path),
    ]
    if rail.base_url:
        argv.extend(["--base-url", rail.base_url])
    return argv


@dataclass(frozen=True)
class SurveyOutcome:
    """What the survey stage produced: answers, and why they may be few."""

    answers: tuple[SurveyAnswer, ...] = field(default_factory=tuple)
    partial_reason: str | None = None


def run_session(
    question: SurveyQuestion,
    rail: ModelRail,
    repo_path: Path,
    run_dir: Path,
    token_share: int,
    structure_text: str = "",
    spawn: Callable[[list[str]], SessionProcess] | None = None,
    nare_path: str | None = None,
) -> SessionState:
    """One bounded nare session, read live and killed on refusal.

    ``spawn`` builds the process; the default runs the nare CLI. The
    stream is consumed as it arrives so a forbidden tool call or an
    exhausted budget kills the process at the moment it happens, not
    after. The session transcript is kept at a per-question path for
    replay and audit.
    """
    nare = nare_path or shutil.which("nare")
    if not nare:
        raise SurveySessionError(
            "nare is not installed; every model call must go through nare, "
            "so the survey stage cannot run"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    argv = build_session_argv(
        nare,
        prompt_text(question, structure_text),
        rail,
        repo_path,
        run_dir / f"survey-q{question.number}.json",
        token_share,
    )
    if spawn is None:
        spawn = _default_spawn
    proc = spawn(argv)
    state = SessionState(question, token_share)
    for line in proc.stdout:
        try:
            state.consume(line)
        except SurveyCommandError as error:
            proc.kill()
            state._exceed(f"refused read-only violation: {error}")
            break
        if state.exceeded:
            proc.kill()
            break
    proc.wait()
    if proc.returncode != 0 and not state.exceeded:
        state.partial_reason = (
            f"nare exited {proc.returncode} before answering the question"
        )
    return state


def _default_spawn(argv: list[str]) -> SessionProcess:
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return cast("SessionProcess", proc)


def run_sessions(
    plan: SurveyPlan,
    config: Config,
    repo_path: Path,
    run_dir: Path,
    spawn: Callable[[list[str]], SessionProcess] | None = None,
    nare_path: str | None = None,
) -> SurveyOutcome:
    """One session per question, bounded by the stage's token budget.

    A question whose session cannot start within the stage's remaining
    budget is left unanswered and named in the outcome's partial reason;
    the stage continues with the questions that fit.
    """
    rail = config.survey_rail
    count = len(plan.questions)
    if count == 0:
        return SurveyOutcome((), "no questions were formulated; nothing to ask")
    share = config.budget_survey_stage_tokens // count
    structure_text = "\n".join(plan.structure.tree)
    answers: list[SurveyAnswer] = []
    unanswered: list[int] = []
    stage_used = 0
    for question in plan.questions:
        if stage_used + share > config.budget_survey_stage_tokens:
            unanswered.append(question.number)
            continue
        state = run_session(
            question,
            rail,
            repo_path,
            run_dir,
            share,
            structure_text,
            spawn,
            nare_path,
        )
        stage_used += state.tokens_used
        answers.append(_to_answer(question.number, state))
    partial_reason = plan.partial_reason
    if unanswered:
        partial_reason = "; ".join(
            reason
            for reason in (
                partial_reason,
                f"survey stage budget exhausted; question(s) "
                f"{', '.join(str(n) for n in unanswered)} not asked",
            )
            if reason
        )
    return SurveyOutcome(tuple(answers), partial_reason)


def _to_answer(question_number: int, state: SessionState) -> SurveyAnswer:
    findings = state.findings or state.partial_reason or "no output"
    return SurveyAnswer(
        question=question_number,
        commands=state.commands,
        findings=findings,
        partial_reason=state.partial_reason,
    )
