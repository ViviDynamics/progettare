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

_MAX_PROMPT_BYTES = 96_000


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
    reads: tuple[str, ...] = ()
    tool_calls: int = 0
    findings: str | None = None
    partial_reason: str | None = None
    exceeded: bool = False
    usage_reported: bool = False
    usage_malformed: bool = False

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
        if not isinstance(event, dict):
            raise SurveySessionError(f"nare emitted a non-object JSON line: {line!r}")
        kind = event.get("type")
        if kind == "cost":
            detail = event.get("detail")
            if not isinstance(detail, dict):
                # A malformed usage event makes this session's totals
                # untrustworthy: never charged, and the stage fails
                # closed on it just like missing usage. With no live
                # token accounting the session cannot be allowed to
                # keep spending, so it is killed like an overrun.
                self.usage_malformed = True
                self._exceed(
                    "token budget exceeded: cost event has no usable usage object"
                )
                return
            raw_input = detail.get("input")
            raw_output = detail.get("output")
            if not (
                isinstance(raw_input, int)
                and isinstance(raw_output, int)
                and not isinstance(raw_input, bool)
                and not isinstance(raw_output, bool)
                and raw_input >= 0
                and raw_output >= 0
            ):
                self.usage_malformed = True
                self._exceed(
                    "token budget exceeded: cost event has malformed usage values"
                )
                return
            self.usage_reported = True
            self.input_tokens += raw_input
            self.output_tokens += raw_output
            if self.tokens_used > self.token_share:
                self._exceed(
                    f"token budget exceeded: {self.tokens_used} tokens "
                    f"against a share of {self.token_share}"
                )
        elif kind == "tool_use":
            tool = event.get("text", "")
            detail = event.get("detail")
            if not isinstance(detail, dict):
                raise SurveySessionError(
                    f"nare emitted a tool_use event without an object payload: {line!r}"
                )
            if tool == "bash":
                command = str(detail.get("command", ""))
                validate_session_command(command)
                self.commands = (*self.commands, command)
            elif tool == "read":
                self.reads = (*self.reads, str(detail.get("path", "")))
            else:
                raise SurveyCommandError(
                    f"tool {tool!r} is outside the read-only allowlist"
                )
            self.tool_calls += 1
            if self.tool_calls > self.question.command_budget:
                self._exceed(
                    f"command budget exceeded: {self.tool_calls} tool "
                    f"calls against a budget of {self.question.command_budget}"
                )
        elif kind == "output":
            text = event.get("text")
            if not isinstance(text, str):
                raise SurveySessionError(
                    f"nare emitted an output event without text: {line!r}"
                )
            self.findings = text
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


def render_tree(paths: tuple[str, ...], limit: int = 96_000) -> str:
    """The prompt's file list: renderable paths, bounded to fit argv.

    Git paths may contain newlines or be surrogateescaped non-UTF-8
    names, so paths progettare cannot render unambiguously are dropped
    rather than joined or crashed on, and the list is truncated before
    it can outgrow the OS per-argument limit. ``limit`` is in UTF-8
    encoded bytes, which is what argv measures, not code points.
    """

    def renderable(path: str) -> bool:
        try:
            path.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return all(ord(char) >= 32 for char in path)

    clean = [path for path in paths if path and renderable(path)]
    dropped = len(paths) - len(clean)
    kept: list[str] = []
    used = 0
    budget = max(0, limit - 200)
    for path in clean:
        size = len(path.encode("utf-8")) + 1
        if used + size > budget:
            break
        kept.append(path)
        used += size
    truncated = len(clean) - len(kept)
    text = "\n".join(kept)
    notes = []
    if dropped:
        notes.append(f"{dropped} unrenderable paths omitted")
    if truncated:
        notes.append(f"{truncated} more paths omitted to fit the prompt")
    if notes:
        note = "\n" + "; ".join(notes) + "."
        if len(text.encode("utf-8")) + len(note.encode("utf-8")) <= limit:
            text += note
    return text


def bound_prompt(question: SurveyQuestion, structure_text: str) -> str:
    """The complete prompt, bounded to the argument limit no matter what.

    The tree is budgeted around the question, but an oversized question
    text alone can still exceed the limit, so the bound is enforced on
    the final prompt with an explicit truncation note.
    """
    prompt = prompt_text(question, structure_text)
    data = prompt.encode("utf-8")
    if len(data) <= _MAX_PROMPT_BYTES:
        return prompt
    head = data[: _MAX_PROMPT_BYTES - 64].decode("utf-8", errors="ignore")
    return head + "\n\n[prompt truncated to fit the argument limit]"


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
    run_resolved = run_dir.expanduser().resolve()
    repo_resolved = repo_path.expanduser().resolve()
    if run_resolved == repo_resolved or repo_resolved in run_resolved.parents:
        raise SurveySessionError(
            f"run directory {run_resolved} is inside the surveyed repository "
            f"{repo_resolved}; progettare writes nothing there"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    argv = build_session_argv(
        nare,
        bound_prompt(question, structure_text),
        rail,
        repo_path,
        run_dir / f"survey-q{question.number}.json",
        token_share,
    )
    if spawn is None:
        spawn = _default_spawn
    proc = spawn(argv)
    state = SessionState(question, token_share)
    try:
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
    finally:
        # Reap the child on every path: a killed session, an already
        # exited one (kill is a no-op then), or a malformed stream that
        # is about to fail loudly.
        proc.kill()
        proc.wait()
    if proc.returncode != 0 and not state.exceeded:
        state.partial_reason = f"nare exited {proc.returncode} " + (
            "after producing an answer"
            if (state.findings or "").strip()
            else "before answering the question"
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
    answers: list[SurveyAnswer] = []
    unanswered: list[int] = []
    missing_usage: list[int] = []
    stage_used = 0
    for question in plan.questions:
        if share <= 0 or stage_used + share > config.budget_survey_stage_tokens:
            unanswered.append(question.number)
            continue
        prompt_base = len(prompt_text(question, "").encode("utf-8"))
        structure_text = render_tree(
            plan.structure.tree, max(0, _MAX_PROMPT_BYTES - prompt_base)
        )
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
        if state.usage_reported and not state.usage_malformed:
            stage_used += state.tokens_used
        else:
            # Missing usage is charged the question's full share so the
            # stage's remaining arithmetic stays conservative without
            # reporting synthetic token counts; the stage continues.
            stage_used += share
            missing_usage.append(question.number)
        answers.append(_to_answer(question.number, state))
    partial_reason = plan.partial_reason
    overran = stage_used > config.budget_survey_stage_tokens
    reasons = []
    if overran:
        reasons.append(
            f"survey stage budget exhausted: {stage_used} tokens "
            f"against {config.budget_survey_stage_tokens}"
        )
    if missing_usage:
        reasons.append(
            "usage missing or malformed for question(s) "
            f"{', '.join(str(n) for n in missing_usage)}"
        )
    if unanswered:
        reasons.append(f"question(s) {', '.join(str(n) for n in unanswered)} not asked")
    if reasons:
        partial_reason = "; ".join(
            reason for reason in (partial_reason, *reasons) if reason
        )
    return SurveyOutcome(tuple(answers), partial_reason)


def _to_answer(question_number: int, state: SessionState) -> SurveyAnswer:
    stripped = (state.findings or "").strip()
    if not stripped:
        # A session with no substantive output did not answer the
        # question; record it as partial rather than fabricating a
        # complete answer.
        state.partial_reason = state.partial_reason or (
            "session ended without answering the question"
        )
        findings = state.partial_reason
    else:
        findings = state.findings or ""
    return SurveyAnswer(
        question=question_number,
        commands=state.commands,
        findings=findings,
        partial_reason=state.partial_reason,
        reads=state.reads,
    )
