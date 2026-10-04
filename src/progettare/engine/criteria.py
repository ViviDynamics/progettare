"""Acceptance criteria parsing: a stable, id-assigned list."""

import itertools
import re
from dataclasses import dataclass

_WORDS = r"acceptance(?: criteria)?"
_HEADER_RE = re.compile(
    rf"(?:#+\s+)?(?:\*\*{_WORDS}:?\*\*|{_WORDS}:?)",
    re.IGNORECASE,
)
_SETTING_RE = re.compile(r"([A-Za-z][A-Za-z0-9_.-]*)\s*[:=]\s*(\S+)")


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str


@dataclass(frozen=True)
class Conflict:
    kind: str
    first_id: str
    second_id: str
    detail: str


def parse_criteria(body: str) -> tuple[Criterion, ...]:
    lines = body.splitlines()
    header = _find_header(lines)
    if header is None:
        return ()
    criteria: list[Criterion] = []
    for line in lines[header + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            criteria.append(
                Criterion(id=f"c{len(criteria) + 1}", text=stripped[2:].strip())
            )
        else:
            break
    return tuple(criteria)


def find_conflicts(criteria: tuple[Criterion, ...]) -> tuple[Conflict, ...]:
    conflicts = _duplicates(criteria) + _setting_conflicts(criteria)
    return tuple(conflicts)


def _duplicates(criteria: tuple[Criterion, ...]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    for first, second in itertools.combinations(criteria, 2):
        normalized = _normalize(first.text)
        if normalized != _normalize(second.text):
            continue
        conflicts.append(
            Conflict(
                kind="duplicate",
                first_id=first.id,
                second_id=second.id,
                detail=_shared_text(normalized),
            )
        )
    return conflicts


def _setting_conflicts(criteria: tuple[Criterion, ...]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    settings = [_settings(criterion.text) for criterion in criteria]
    for first, second in itertools.combinations(range(len(criteria)), 2):
        for key, value in settings[first].items():
            other = settings[second].get(key)
            if other is not None and other != value:
                conflicts.append(
                    Conflict(
                        kind="setting",
                        first_id=criteria[first].id,
                        second_id=criteria[second].id,
                        detail=f"{key}: '{value}' vs '{other}'",
                    )
                )
                break
    return conflicts


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _shared_text(normalized: str) -> str:
    if len(normalized) > 60:
        return normalized[:60] + "..."
    return normalized


def _settings(text: str) -> dict[str, str]:
    return {
        match.group(1).casefold(): match.group(2)
        for match in _SETTING_RE.finditer(text)
    }


def _find_header(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _HEADER_RE.fullmatch(line.strip()):
            return index
    return None
