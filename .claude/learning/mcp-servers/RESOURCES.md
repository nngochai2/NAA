# MCP Servers Resources

## Knowledge

- [Specification — Model Context Protocol (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)
  The authoritative spec: JSON-RPC 2.0 base protocol, host/client/server roles, the three server-side features (resources, prompts, tools), the three client-side features (sampling, roots, elicitation), and the security/trust principles section. Use for: anything you need to cite as "the protocol says."
- [Architecture — Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/architecture)
  Deeper dive on the host/client/server topology and the connection lifecycle. Use for: understanding *why* a client exists between host and server, not just that it does.
- [Server Features — Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/server)
  Per-feature detail on tools, resources, and prompts — including who invokes each (model vs. app vs. user) and the JSON-RPC methods involved. Use for: deciding which primitive fits a new capability.
- [The 2026-07-28 MCP Specification Release Candidate — MCP Blog](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
  Upcoming spec changes: protocol goes stateless at the core, an Extensions framework, Tasks, MCP Apps, OAuth 2.1 hardening, formal deprecation policy. Use for: knowing what's about to shift under your servers.
- [Introducing the Model Context Protocol — Anthropic](https://www.anthropic.com/news/model-context-protocol)
  The original announcement — motivation and the "USB-C for AI" framing. Use for: the *why MCP exists at all* narrative.
- [Python SDK — modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
  The actual package your servers import (`mcp==1.27.x`). Contains both the low-level `mcp.server.Server` API (what `jira_mcp/server.py` uses) and the high-level `mcp.server.fastmcp.FastMCP` API (what `mcp/src/server.py` uses) in the same package. Use for: primary source on decorator behavior, transport wiring, schema generation from type hints.
- [FastMCP docs — gofastmcp.com](https://gofastmcp.com/getting-started/welcome)
  Docs for the **standalone PrefectHQ `fastmcp` package**, a superset that inspired and now partially tracks the SDK's bundled `FastMCP`. Not what your servers depend on today (they only pull in `mcp`) — use this only to understand which extra features (auth proxies, richer client testing) would require actually adding the separate dependency.
- [Agentic MCP Security Best Practices Guide — Cloud Security Alliance](https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1/)
  Baseline security checklist for MCP servers: treat tool inputs as untrusted, defense in depth, credential scoping. Use for: reviewing your own servers (jira, oracle, gitlab all touch live credentials).
- [The MCP Security Survival Guide — Towards Data Science](https://towardsdatascience.com/the-mcp-security-survival-guide-best-practices-pitfalls-and-real-world-lessons/)
  Real-world pitfalls including CVE-2025-68143/68144/68145 (path-traversal / command-injection in the official git MCP server via unsanitized repo paths). Use for: concrete cautionary examples directly relevant to your `mcp/git` server.

## Wisdom (Communities)

- [r/mcp](https://reddit.com/r/mcp)
  Active community for MCP server authors trading design patterns and debugging transport/auth issues. Use for: sanity-checking a design decision against how other server authors solved it.
- [Model Context Protocol GitHub Discussions](https://github.com/orgs/modelcontextprotocol/discussions)
  Where spec authors and SDK maintainers actually discuss edge cases. Use for: questions the docs don't answer, e.g. "should this be a resource or a tool?"

## Gaps

- No vetted resource yet on testing MCP servers (unit-testing tool handlers, integration-testing transports). `mcp/jira/tests/` already has real test files worth mining for patterns — check there before searching externally.
- No resource yet specifically on OAuth 2.1 for remote MCP servers (relevant once any of these servers stop being localhost-only).
