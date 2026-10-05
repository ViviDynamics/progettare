"""The MCP server's dispatch seam: version negotiation and tool calls."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any

from progettare.contract import ARTIFACT_VERSION, PROGETTARE_VERSION
from progettare.mcp import PROTOCOL_VERSION, TOOL_NAME, handle_message

OUTCOME: dict[str, Any] = {"status": "complete", "run_dir": "/repo/runs/0001"}


def call_tool(arguments: dict[str, Any], ceremony: Any = None) -> Any:
    message = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": TOOL_NAME, "arguments": arguments},
    }
    response = handle_message(message, ceremony)
    assert response is not None
    assert response["id"] == 7
    return response["result"]


def test_initialize_negotiates_the_protocol_version() -> None:
    response = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert response is not None
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "progettare"
    assert result["serverInfo"]["version"] == PROGETTARE_VERSION


def test_tools_list_reports_the_tool_and_the_contract_version() -> None:
    response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response is not None
    tools = response["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == TOOL_NAME
    assert str(ARTIFACT_VERSION) in tools[0]["description"]


def test_a_tool_call_returns_the_outcome_document() -> None:
    calls: list[tuple[str, str]] = []

    def ceremony(ref: str, repo_path: str) -> dict[str, Any]:
        calls.append((ref, repo_path))
        return OUTCOME

    result = call_tool(
        {"ref": "ViviDynamics/progettare#9", "repo_path": "/repo"}, ceremony
    )
    assert calls == [("ViviDynamics/progettare#9", "/repo")]
    assert result["isError"] is False
    document: dict[str, Any] = json.loads(result["content"][0]["text"])
    assert document == OUTCOME


def test_a_blocked_outcome_keeps_its_semantics() -> None:
    blocked = {
        "status": "blocked",
        "run_dir": "/repo/runs/0002",
        "failing_stage": "intake",
        "detail": "the acceptance criteria are placeholder text",
    }
    result = call_tool(
        {"ref": "o/r#1", "repo_path": "/repo"}, lambda ref, repo: blocked
    )
    document: dict[str, Any] = json.loads(result["content"][0]["text"])
    assert document == blocked


def test_an_unknown_method_is_a_method_not_found_error() -> None:
    response = handle_message({"jsonrpc": "2.0", "id": 3, "method": "no/such"})
    assert response is not None
    assert response["error"]["code"] == -32601


def test_an_unparseable_line_yields_a_parse_error() -> None:
    response = handle_message(None)
    assert response is not None
    assert response["error"]["code"] == -32700


def test_a_notification_gets_no_response() -> None:
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert handle_message(message) is None


def test_missing_arguments_are_invalid_params() -> None:
    result = call_tool({}, lambda ref, repo: OUTCOME)
    assert result["isError"] is True
    assert "repo_path" in result["content"][0]["text"]


def test_an_unknown_tool_is_an_error() -> None:
    message = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "no_such_tool", "arguments": {}},
    }
    response = handle_message(message, lambda ref, repo: OUTCOME)
    assert response is not None
    assert response["error"]["code"] == -32602


def test_serve_answers_what_needs_answering() -> None:
    from progettare.mcp import serve

    incoming = StringIO(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        + "\n"
        + "not json\n"
        + "\n"
    )
    outgoing = StringIO()
    serve(incoming, outgoing, lambda ref, repo: OUTCOME)
    lines = outgoing.getvalue().splitlines()
    assert len(lines) == 2
    first: dict[str, Any] = json.loads(lines[0])
    assert first["result"]["tools"][0]["name"] == TOOL_NAME
    second: dict[str, Any] = json.loads(lines[1])
    assert second["error"]["code"] == -32700
