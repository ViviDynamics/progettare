"""Issue reference parsing: URL and owner/repo#number forms."""

import re
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

_ACCEPTED_FORMS = (
    "a GitHub issue URL like https://github.com/owner/repo/issues/123, "
    "or the shorthand owner/repo#123"
)

_NAME_CHARS = r"[A-Za-z0-9._-]"
_NUMBER_CHARS = r"[0-9]"
_SHORTHAND_RE = re.compile(rf"({_NAME_CHARS}+)/({_NAME_CHARS}+)#({_NUMBER_CHARS}+)")
_URL_RE = re.compile(rf"/({_NAME_CHARS}+)/({_NAME_CHARS}+)/issues/({_NUMBER_CHARS}+)")


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repo: str
    number: int


class IssueRefError(ValueError):
    pass


def parse_issue_ref(text: str) -> IssueRef:
    stripped = text.strip()
    parsed = urlparse(stripped)
    if parsed.scheme in ("http", "https"):
        return _parse_url(parsed)
    match = _SHORTHAND_RE.fullmatch(stripped)
    if match is None:
        raise IssueRefError(_invalid_message())
    return IssueRef(
        owner=match.group(1), repo=match.group(2), number=int(match.group(3))
    )


def _parse_url(parsed: ParseResult) -> IssueRef:
    path = parsed.path
    if "/pulls/" in path or "/pull/" in path:
        raise IssueRefError(
            f"A pull request is not an issue. Accepted forms: {_ACCEPTED_FORMS}."
        )
    has_extra = bool(parsed.query) or bool(parsed.fragment)
    if has_extra or "@" in parsed.netloc or ":" in parsed.netloc:
        raise IssueRefError(_invalid_message())
    if path.endswith("/"):
        path = path[:-1]
    match = _URL_RE.fullmatch(path)
    if parsed.hostname not in ("github.com", "www.github.com") or match is None:
        raise IssueRefError(_invalid_message())
    return IssueRef(
        owner=match.group(1), repo=match.group(2), number=int(match.group(3))
    )


def _invalid_message() -> str:
    return f"Invalid issue reference. Accepted forms: {_ACCEPTED_FORMS}."
