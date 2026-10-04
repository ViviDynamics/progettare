"""Acceptance criteria parsing: a stable, id-assigned list."""

import re
from dataclasses import dataclass

_WORDS = r"acceptance(?: criteria)?"
_HEADER_RE = re.compile(
    rf"(?:#+\s+)?(?:\*\*{_WORDS}:?\*\*|{_WORDS}:?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str


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


def _find_header(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _HEADER_RE.fullmatch(line.strip()):
            return index
    return None
