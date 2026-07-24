# Notes

- User's own repo (`mcp/`) is the primary example bank — always check there before inventing a toy example. Servers: `knowledge-graph` (FastMCP high-level, port 8000), `codegraph` (port 8001), `gitlab` (port 8002), `oracle` (port 8003), `jira` (low-level `Server` API + Starlette SSE), `azure_devops`, `git`.
- Depth preference: practical/framework level over protocol internals (confirmed 2026-07-13). Still cover JSON-RPC/lifecycle basics once, lightly, so behavior is reasoned about rather than memorized.
- Goal is both refactor-existing and build-new, biased toward the existing codebase (confirmed 2026-07-13).
- Watch the terminology trap: "FastMCP" refers to two different things — the class bundled in the official `mcp` SDK (`mcp.server.fastmcp.FastMCP`, what the user's code imports) and the standalone PrefectHQ `fastmcp` PyPI package (a superset, not a current dependency). Always disambiguate explicitly.
