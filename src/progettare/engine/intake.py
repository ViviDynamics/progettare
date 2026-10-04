"""Intake: the card context, assembled by code alone.

Intake is the pipeline's first stage and spends no model calls. It fetches
the issue text, parses acceptance criteria into a stable list, pairs
clarifying questions with their answers, and decides from that material
whether planning can start. When the context is missing or contradictory it
returns `blocked` with the specific questions a human must answer; nothing
downstream runs on a guessed card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from progettare.github import Issue, IssueComment

# A criterion that names no work. Whichever of these reaches the survey
# stage, the survey would be planning from nothing, so they read as missing.
_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "?",
    "…",
    "...",
    "n/a",
    "n.a.",
    "na",
    "tbd",
    "tba",
    "tbc",
    "todo",
    "none",
    "no criteria",
    "no acceptance criteria",
    "to be decided",
    "to be defined",
    "to be determined",
    "see below",
}

# A line that opens the acceptance section. A markdown heading prefix is
# accepted because issue bodies write "## Acceptance criteria" as often as
# the bare label.
_MARKER_RE = re.compile(
    r"^#{0,6}\s*acceptance(\s+criteria)?\s*:?\s*$",
    re.IGNORECASE,
)

# A line that closes the section: a markdown heading, or a "Label:" line of
# the shape the family writes ("Done When:", "Implementation Notes:").
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_LABEL_RE = re.compile(r"^\s*[A-Z][A-Za-z0-9 ' /_-]{2,40}:$")

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)")
_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s*")
_CONTINUATION_RE = re.compile(r"^\s+\S")

# Modal constructions are the one contradiction shape a code-only stage can
# decide on: the same subject and predicate asserted both positively and
# negatively. Anything subtler is the human's call, and intake asks.
_MODAL_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<modal>must|should|shall|will|can|may)\s+"
    r"(?P<neg>not\s+)?(?P<predicate>.+)$",
)
_COPULA_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<modal>is|are|was|were)\s+"
    r"(?P<neg>not\s+)?(?P<predicate>.+)$",
)
_CONTRACTIONS = {
    "doesn't": "does not",
    "isn't": "is not",
    "aren't": "are not",
    "won't": "will not",
    "can't": "can not",
    "cannot": "can not",
    "shouldn't": "should not",
    "mustn't": "must not",
}


class RepoPathError(ValueError):
    """A repository path progettare cannot survey, named loudly."""


@dataclass(frozen=True)
class Clarification:
    question: str
    answer: str | None


@dataclass(frozen=True)
class Conflict:
    first: int
    second: int
    first_text: str
    second_text: str


@dataclass(frozen=True)
class CardContext:
    """What the survey and blueprint stages consume. Survey and blueprint
    read the criteria and clarifications as data; nothing downstream parses
    the issue body again."""

    issue: Issue
    repo_path: str
    acceptance_criteria: tuple[str, ...]
    clarifications: tuple[Clarification, ...]
    status: str
    blocked_questions: tuple[str, ...]


def _normalize_criterion(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_placeholder(text: str) -> bool:
    return _normalize_criterion(text).rstrip(".!").lower() in _PLACEHOLDERS


def parse_acceptance_criteria(body: str) -> tuple[str, ...]:
    """The acceptance section as a stable list, in body order.

    Deterministic by construction: the first acceptance-style marker line
    opens the list, the next heading or labeled section closes it, and list
    items are extracted with their original order. Exact duplicates are
    dropped after normalization; two identical bullets carry no second
    requirement, and the survey should not pay for one twice.
    """
    lines = body.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if _MARKER_RE.match(line.strip())),
        None,
    )
    if start is None:
        return ()
    items: list[str] = []
    current: str | None = None
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if _HEADING_RE.match(line) or (
            _LABEL_RE.match(stripped) and not _MARKER_RE.match(stripped)
        ):
            break
        if _LIST_ITEM_RE.match(line):
            if current is not None:
                items.append(current)
            current = _LIST_ITEM_RE.sub("", line, count=1).strip()
        elif stripped and _CONTINUATION_RE.match(line) and current is not None:
            current = f"{current} {stripped}"
        elif stripped and current is None:
            # The marker carried the first criterion on its own line, or the
            # section runs as prose before its bullets. Either way the text
            # belongs to the list.
            current = _CHECKBOX_RE.sub("", stripped).strip()
    if current is not None:
        items.append(current)
    seen: set[str] = set()
    stable: list[str] = []
    for item in items:
        normalized = _normalize_criterion(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        stable.append(normalized)
    return tuple(stable)


def _key_of(criterion: str) -> tuple[str, str, bool] | None:
    """The (subject, predicate, negated) triple behind a modal claim."""
    normalized = _normalize_criterion(criterion).rstrip(".!").lower()
    for contraction, expansion in _CONTRACTIONS.items():
        normalized = normalized.replace(contraction, expansion)
    match = _MODAL_RE.match(normalized) or _COPULA_RE.match(normalized)
    if match is None:
        return None
    subject = re.sub(r"\s+", " ", match.group("subject").strip())
    predicate = re.sub(r"\s+", " ", match.group("predicate").strip())
    if not subject or not predicate:
        return None
    return (subject, predicate, match.group("neg") is not None)


def find_conflicts(criteria: tuple[str, ...]) -> tuple[Conflict, ...]:
    """Criteria that assert the same requirement both positively and negatively.

    Deliberately narrow: a contradiction is reported only when subject and
    predicate are identical under normalization and the negation flips.
    Near-misses stay unanswered here; inventing a semantic-conflict oracle
    would spend a model call on intake's job.
    """
    keys = [(index, _key_of(criterion)) for index, criterion in enumerate(criteria)]
    conflicts: list[Conflict] = []
    for left_position in range(len(keys)):
        for right_position in range(left_position + 1, len(keys)):
            left_key, right_key = keys[left_position][1], keys[right_position][1]
            if left_key is None or right_key is None:
                continue
            if (
                left_key[0] == right_key[0]
                and left_key[1] == right_key[1]
                and left_key[2] != right_key[2]
            ):
                conflicts.append(
                    Conflict(
                        first=keys[left_position][0],
                        second=keys[right_position][0],
                        first_text=criteria[keys[left_position][0]],
                        second_text=criteria[keys[right_position][0]],
                    )
                )
    return tuple(conflicts)


def pair_clarifications(
    comments: tuple[IssueComment, ...],
) -> tuple[Clarification, ...]:
    """Each comment that asks a question, paired with the answer that follows it.

    A question is a comment containing "?"; its answer is the next comment
    that does not ask one. Unanswered questions keep their place with no
    answer, so the blocked report can say what a human still owes.
    """
    paired: list[Clarification] = []
    pending: list[IssueComment] = []
    for comment in comments:
        if "?" in comment.body:
            pending.append(comment)
            continue
        if pending and comment.body.strip():
            for question in pending:
                paired.append(
                    Clarification(question=question.body, answer=comment.body)
                )
            pending.clear()
    for question in pending:
        paired.append(Clarification(question=question.body, answer=None))
    return tuple(paired)


def _validate_repo_path(repo_path: str) -> Path:
    path = Path(repo_path).expanduser()
    if not path.is_dir():
        raise RepoPathError(f"repo path {repo_path} is not a directory")
    return path


def assemble(issue: Issue, repo_path: str) -> CardContext:
    """The card context, or `blocked` with the questions that unblock it.

    Blocked is an outcome, not an error: no model call is spent, and the
    run directory records why the run stopped here.
    """
    resolved = _validate_repo_path(repo_path)
    criteria = parse_acceptance_criteria(issue.body)
    actionable = tuple(c for c in criteria if not _is_placeholder(c))
    questions: list[str] = []
    if not actionable:
        questions.append(
            "What are the acceptance criteria for this issue? The body has "
            "no acceptance section, or none with actionable items."
        )
    for conflict in find_conflicts(actionable):
        questions.append(
            f"Acceptance criteria {conflict.first + 1} and "
            f"{conflict.second + 1} contradict each other:\n"
            f"  ({conflict.first + 1}) {conflict.first_text}\n"
            f"  ({conflict.second + 1}) {conflict.second_text}\n"
            "Which one governs?"
        )
    status = "blocked" if questions else "ok"
    return CardContext(
        issue=issue,
        repo_path=str(resolved),
        acceptance_criteria=actionable,
        clarifications=pair_clarifications(issue.comments),
        status=status,
        blocked_questions=tuple(questions),
    )
