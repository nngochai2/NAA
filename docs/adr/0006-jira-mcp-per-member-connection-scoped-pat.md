# Per-member Jira authentication via connection-scoped PAT

ADR 0005's shared-PAT-plus-`reporter`-field model has no identity verification: any connected team member could name any other member as `reporter`, and the shared account could not enforce or distinguish individual Jira permissions. This ADR supersedes ADR 0005 with real per-member authentication instead.

Each team member supplies their own Jira PAT in their own `mcp.json`'s `Authorization: Bearer <PAT>` header — the same header and scheme already used for the downstream Bearer-auth call to Jira itself, so one token concept flows straight through. The server reads that header once, at the initial SSE connection (`handle_sse`), builds a `JiraClient` scoped to that member's own PAT, and stores it in a `contextvars.ContextVar` for the lifetime of that connection's async task tree. Every subsequent tool call on that session reuses the stored client without depending on the header being resent on each POST — a known Claude Code limitation (custom headers aren't reliably forwarded on the `/messages` POST requests, only on the initial connection). A connection with a missing or invalid `Authorization` header is rejected outright with an HTTP 401 at connect time; there is no fallback to a shared identity.

Consequence: the server no longer holds a Jira credential of its own. `JIRA_PAT` / `JiraConfig.token` is removed; only `JIRA_URL`, `JIRA_PROJECT_KEY`, and `JIRA_SSL_VERIFY` remain server-level config (ADR 0002's single-project scoping is unaffected). The explicit `reporter` argument added to `jira_create_issue`/`jira_update_issue` (issue #28) is removed — Jira's own Reporter now defaults correctly to whichever member's PAT made the call, and that call is authorized under that member's real Jira permissions, which the shared-PAT model could never enforce.

## Considered Options

- **Keep the `reporter` field + shared PAT (ADR 0005)**: rejected — purely honor-system, no way to verify or enforce identity.
- **Server-side allowlist of known usernames, validated against a free-text `reporter` argument**: rejected — catches typos, but still doesn't stop a member deliberately naming a real teammate as reporter, and still can't enforce that teammate's actual Jira permissions.
