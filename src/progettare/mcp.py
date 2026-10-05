"""The MCP stdio server: the blueprint ceremony, served as one tool.

Conductor, coordinare, and other agent harnesses speak MCP; the CLI's
versioned JSON contract is the one contract, so the server mirrors the
CLI's outcome shapes instead of inventing a second one. The transport is
newline-delimited JSON-RPC 2.0, and the dispatch is a pure seam, so the
tests feed lines and canned ceremonies offline. The only filesystem
assumption is the caller-supplied repo path: the configuration and the
run directories are resolved under it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from progettare.cli import BlueprintOutcome, run_blueprint
from progettare.config import load_config
from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.github import ensure_issue_open, load_issue
from progettare.issue_ref import IssueRefError, parse_issue_ref

PROTOCOL_VERSION = "2025-06-18"
TOOL_NAME = "plan_blueprint"

ParseError = -32700
MethodNotFound = -32601
InvalidParams = -32602

Ceremony = Callable[[str, str], dict[str, Any]]


def tool_description() -> str:
    """The tool's contract, with the versioned contract version reported."""
    return (
        "Plan one issue with the progettare ceremony: bounded survey, one "
        "blueprint, sizing, briefs. Returns the run's outcome document. "
        f"progettare artifact contract version {ARTIFACT_VERSION}; "
        f"progettare {PROGETTARE_VERSION}."
    )


def _tools_list() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": TOOL_NAME,
                "description": tool_description(),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ref": {
                            "type": "string",
                            "description": "issue URL or owner/repo#N",
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "path to the checkout",
                        },
                    },
                    "required": ["ref", "repo_path"],
                },
            }
        ]
    }


def _error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _outcome_document(outcome: BlueprintOutcome) -> dict[str, Any]:
    document: dict[str, Any] = {
        "status": outcome.status,
        "run_dir": str(outcome.run_dir),
    }
    if outcome.status != "complete":
        document["failing_stage"] = outcome.failing_stage
        document["detail"] = outcome.detail
    return document


def default_ceremony(ref: str, repo_path: str) -> dict[str, Any]:
    """Run the ceremony exactly as the CLI's blueprint verb does."""
    from progettare.cli import NareSubprocessRunner

    written_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    issue_ref = parse_issue_ref(ref)
    root = Path(repo_path)
    config = load_config(root / "progettare.yaml")
    issue = load_issue(issue_ref)
    outcome = run_blueprint(
        issue_ref,
        str(root),
        config,
        root / "runs",
        NareSubprocessRunner(),
        issue,
        written_at,
        lambda: ensure_issue_open(issue_ref),
    )
    return _outcome_document(outcome)


def handle_message(
    message: dict[str, Any] | None, ceremony: Ceremony | None = None
) -> dict[str, Any] | None:
    """One JSON-RPC message in, at most one response out.

    ``None`` stands for a line that did not parse. A notification carries
    no id and gets no response. The ceremony seam defaults to the real
    one; tests inject canned outcomes.
    """
    if message is None:
        return _error(None, ParseError, "the line did not parse as JSON")
    id = message.get("id")
    if id is None:
        return None
    method = message.get("method")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "progettare", "version": PROGETTARE_VERSION},
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": id, "result": _tools_list()}
    if method == "tools/call":
        return _tools_call(
            message, ceremony if ceremony is not None else default_ceremony
        )
    return _error(id, MethodNotFound, f"method {method!r} does not exist")


def _tool_error(id: Any, text: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": {"isError": True, "content": [{"type": "text", "text": text}]},
    }


def _tools_call(message: dict[str, Any], ceremony: Ceremony) -> dict[str, Any]:
    id = message["id"]
    params = message.get("params") or {}
    if params.get("name") != TOOL_NAME:
        return _error(id, InvalidParams, f"tool {params.get('name')!r} does not exist")
    arguments = params.get("arguments") or {}
    missing = [
        name
        for name in ("ref", "repo_path")
        if not isinstance(arguments.get(name), str)
    ]
    if missing:
        return _tool_error(id, f"missing argument(s): {', '.join(missing)}")
    try:
        outcome = ceremony(arguments["ref"], arguments["repo_path"])
    except IssueRefError as error:
        return _tool_error(id, str(error))
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(outcome, sort_keys=True)}],
        },
    }


def serve(stdin: Any, stdout: Any, ceremony: Ceremony | None = None) -> None:
    """Read newline-delimited JSON-RPC, answer what needs answering."""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message: dict[str, Any] | None = json.loads(line)
        except ValueError:
            message = None
        response = handle_message(message, ceremony)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
