# Mission: MCP Servers

## Why
You've shipped six working MCP servers in `mcp/` (knowledge-graph, codegraph, gitlab, oracle, jira, azure_devops, git) by vibecoding — copying patterns until they worked. You want to understand the protocol and the SDK deeply enough to design and harden these deliberately, not just extend them by trial and error.

## Success looks like
- You can explain, from memory, the host/client/server split and why a tool call is a JSON-RPC round trip — not just recite it.
- Given a new integration to expose to an AI agent, you can decide *tool vs. resource vs. prompt* and *stdio vs. SSE/streamable HTTP* on purpose, and say why.
- You can look at `mcp/jira/jira_mcp/server.py` (low-level `Server` API) and `mcp/src/server.py` (high-level `FastMCP` API) and articulate why each shape was chosen — and refactor one into the other if needed.
- You can review one of your own MCP servers for security issues (input trust, path traversal, credential handling) the way the field's best-practice guides describe, and fix what's wrong.
- You can build a brand-new MCP server for this repo (or elsewhere) without copy-pasting from an existing one first.

## Constraints
- Python only — every existing server in `mcp/` is Python on the official `mcp` SDK (`mcp==1.27.x`), not the standalone PrefectHQ `fastmcp` package. Stay grounded in that SDK unless a gap forces a detour.
- Practical framework level over protocol internals: understand JSON-RPC/transport lifecycle well enough to reason about behavior, but spend most time on SDK idioms, tool/resource design, and auth — not hand-parsing the wire format.
- Bias every lesson toward the real servers already in `mcp/` before inventing toy examples.

## Out of scope (for now)
- Building MCP *clients* or hosts (you're a server author here, not a client integrator).
- The standalone `fastmcp` (PrefectHQ) package — note where it diverges from the SDK's bundled `FastMCP`, but don't teach its extra features as if you depend on them.
- Non-Python SDKs (TypeScript, etc.).
