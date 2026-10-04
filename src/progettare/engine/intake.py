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
    "n.a",
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
# the shape the family writes ("Done When:", "Implementation Notes:"),
# including the bold-wrapped spelling some bodies use.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_LABEL_RE = re.compile(r"^\s*(?:\*\*)?[A-Z][A-Za-z0-9 ' /_-]{2,40}:\*{0,2}\s*$")

_LIST_ITEM_RE = re.compile(
    r"^\s*(?:[-*+](?:\s+(?:\[[ xX]\]\s*)?|\s*$)|\d+[.)](?:\s+|\s*$))"
)
_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s*")
_CONTINUATION_RE = re.compile(r"^\s+\S")

# Modal constructions are the one contradiction shape a code-only stage can
# decide on: the same subject and predicate asserted both positively and
# negatively. Anything subtler is the human's call, and intake asks.
_MODAL_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<modal>must|should|shall|will|can|may|does|do)\s+"
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


def _parse_section(body: str) -> tuple[tuple[int, str], ...]:
    """The section's items as (body position, text) pairs, deduplicated.

    A position is the item's number among everything the section lists,
    duplicates and blanks included, so a question saying "criterion 3"
    points at the third bullet the reader counts in the issue body. A
    blank item is kept: it names nothing, and that is a placeholder.
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
    stable: list[tuple[int, str]] = []
    for index, item in enumerate(items, start=1):
        normalized = _normalize_criterion(item)
        if normalized in seen:
            continue
        seen.add(normalized)
        stable.append((index, normalized))
    return tuple(stable)


def parse_acceptance_criteria(body: str) -> tuple[str, ...]:
    """The acceptance section as a stable list, in body order.

    Deterministic by construction: the first acceptance-style marker line
    opens the list, the next heading or labeled section closes it, and list
    items are extracted with their original order. Exact duplicates are
    dropped after normalization; two identical bullets carry no second
    requirement, and the survey should not pay for one twice. Blank bullets
    are dropped too: they are data for the blocked report, not requirements.
    """
    return tuple(text for _, text in _parse_section(body) if text)


def _key_of(criterion: str) -> tuple[str, str, str, bool] | None:
    """The (subject, modal, predicate, negated) quadruple behind a claim."""
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
    return (subject, match.group("modal"), predicate, match.group("neg") is not None)


def find_conflicts(
    positioned: tuple[tuple[int, str], ...],
) -> tuple[Conflict, ...]:
    """Criteria that assert the same requirement both positively and negatively.

    Takes criteria paired with their positions in the body, and reports
    conflicts at those positions, so a question can quote the criteria as
    the issue numbered them. Deliberately narrow: a contradiction is
    reported only when subject, modal, and predicate are identical under
    normalization and the negation flips, since capability and policy can
    coexist where the modals differ. Near-misses stay unanswered here;
    inventing a semantic-conflict oracle would spend a model call on
    intake's job.
    """
    keys = [(position, _key_of(criterion)) for position, criterion in positioned]
    conflicts: list[Conflict] = []
    for left_position in range(len(keys)):
        for right_position in range(left_position + 1, len(keys)):
            left_key, right_key = (
                keys[left_position][1],
                keys[right_position][1],
            )
            if left_key is None or right_key is None:
                continue
            if (
                left_key[0] == right_key[0]
                and left_key[1] == right_key[1]
                and left_key[2] == right_key[2]
                and left_key[3] != right_key[3]
            ):
                conflicts.append(
                    Conflict(
                        first=keys[left_position][0],
                        second=keys[right_position][0],
                        first_text=positioned[left_position][1],
                        second_text=positioned[right_position][1],
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
    return path.resolve()


def assemble(issue: Issue, repo_path: str) -> CardContext:
    """The card context, or `blocked` with the questions that unblock it.

    Blocked is an outcome, not an error: no model call is spent, and the
    run directory records why the run stopped here. A placeholder among
    otherwise actionable criteria blocks just as an empty section does:
    the survey must not plan around a requirement nobody wrote.
    """
    resolved = _validate_repo_path(repo_path)
    positioned = _parse_section(issue.body)
    actionable = tuple(
        (position, criterion)
        for position, criterion in positioned
        if not _is_placeholder(criterion)
    )
    questions: list[str] = []
    if not actionable:
        questions.append(
            "What are the acceptance criteria for this issue? The body has "
            "no acceptance section, or none with actionable items."
        )
    else:
        for position, criterion in positioned:
            if not _is_placeholder(criterion):
                continue
            questions.append(
                f"Acceptance criterion {position} is a placeholder "
                f"({criterion!r}); what is the requirement it names?"
            )
    for conflict in find_conflicts(actionable):
        questions.append(
            f"Acceptance criteria {conflict.first} and "
            f"{conflict.second} contradict each other:\n"
            f"  ({conflict.first}) {conflict.first_text}\n"
            f"  ({conflict.second}) {conflict.second_text}\n"
            "Which one governs?"
        )
    status = "blocked" if questions else "ok"
    return CardContext(
        issue=issue,
        repo_path=str(resolved),
        acceptance_criteria=tuple(c for _, c in actionable),
        clarifications=pair_clarifications(issue.comments),
        status=status,
        blocked_questions=tuple(questions),
    )
