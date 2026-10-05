# Issue 13: MCP server interface

## Problem
Conductor, coordinare, and other agent harnesses need the blueprint ceremony
over MCP. The CLI already owns the versioned JSON contract; the server must
mirror it, not invent a second one.

## Rulings
- Hand-rolled JSON-RPC 2.0 over stdio, one object per line (the MCP stdio
  transport's newline-delimited mode). The only runtime dependency stays
  pyyaml; an SDK would not be testable offline.
- `initialize` negotiates the MCP protocolVersion and reports
  `serverInfo{name, version: PROGETTARE_VERSION}`; `tools/list` reports the
  tool with the artifact contract version in its description. The contract
  version is negotiated and reported, per acceptance.
- One tool: `plan_blueprint(ref, repo_path)`. It reuses the CLI's
  `run_blueprint` orchestration with the caller-supplied repo path and a
  runs base under it, so semantics (blocked/failed/complete, manifests,
  discard-on-close) are literally the same code.
- Tool results carry the versioned outcome JSON on complete/blocked/failed
  exactly as the CLI prints it; transport errors (malformed JSON, unknown
  method, unknown tool) are JSON-RPC errors.
- The dispatch is a pure seam (`handle_message`), so tests feed lines and
  canned runners offline; the serve loop is a thin stdin/stdout shell.
- The server never resolves paths beyond the caller-supplied repo_path and
  its run directory.

## Tasks
1. `mcp.py` transport: line reader/writer, JSON-RPC framing, initialize,
   tools/list, tools/call dispatch, error mapping, notifications are silent.
2. `plan_blueprint` tool: seams wired to run_blueprint; outcome JSON mirrors
   the CLI's stdout contract; contract version reported.
3. Tests: initialize handshake version negotiation, tools/list shape,
   complete/blocked/failed calls through canned runners, malformed-line and
   unknown-method errors, notification silence.
