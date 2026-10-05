"""The conductor adapter: card contexts in, dispatch payloads out.

Conductor and coordinare dispatch the architect stage to progettare and
consume its JSON result; this adapter is the thin mapping layer between
the two contracts, following the nare conductor-adapter sketch pattern.
It holds no business logic: the ceremony's own stages decide everything
worth deciding, and the versioned contract does the compatibility work,
so a record cut by another progettare is refused loudly instead of
interpreted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION

ADAPTER_VERSION = 1


class AdapterError(ValueError):
    """A mapping progettare's adapter refuses, naming the key or version."""


def _text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"the card context has no usable {key}")
    return value


def card_to_input(card: Mapping[str, Any]) -> dict[str, str]:
    """Map the orchestrator's card context onto the ceremony's intake input.

    The card's repo and number become the issue ref; the card's
    repo_path stays the only filesystem assumption. The card's text is
    the issue's business, and the ceremony reads it from GitHub.
    """
    repo = _text(card, "repo")
    number = card.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        raise AdapterError("the card context has no usable number")
    repo_path = _text(card, "repo_path")
    return {"ref": f"{repo}#{number}", "repo_path": repo_path}


def _contract_checked(record: Mapping[str, Any]) -> None:
    version = record.get("artifact_version")
    if version is None:
        raise AdapterError(
            "the briefs record names no artifact_version; this adapter "
            f"speaks contract version {ARTIFACT_VERSION}"
        )
    if version != ARTIFACT_VERSION:
        raise AdapterError(
            f"the briefs record names contract version {version}; "
            f"this adapter speaks contract version {ARTIFACT_VERSION}"
        )


def dispatch_payloads(briefs: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Cut the published briefs record into one payload per milestone.

    Each payload embeds the milestone, the criteria, and the topics the
    record's slices carry, and names the versions it was cut with, so a
    conductor hands one payload to one worker and checks nothing else.
    """
    _contract_checked(briefs)
    slices = briefs.get("briefs")
    if not isinstance(slices, dict):
        raise AdapterError("the briefs record has no briefs mapping")
    implementer = slices.get("implementer")
    if not isinstance(implementer, dict):
        raise AdapterError("the briefs record has no implementer slice")
    milestones = implementer.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise AdapterError("the briefs record's implementer slice has no milestones")
    qa = slices.get("qa")
    criteria = qa.get("testable_criteria") if isinstance(qa, dict) else []
    documenter = slices.get("documenter")
    topics = documenter.get("topics") if isinstance(documenter, dict) else []
    return [
        {
            "version": ADAPTER_VERSION,
            "artifact": "dispatch_payload",
            "artifact_version": ARTIFACT_VERSION,
            "progettare": PROGETTARE_VERSION,
            "milestone": {
                "title": milestone.get("title"),
                "changes": milestone.get("changes"),
            },
            "criteria": list(criteria or []),
            "topics": list(topics or []),
        }
        for milestone in milestones
    ]
