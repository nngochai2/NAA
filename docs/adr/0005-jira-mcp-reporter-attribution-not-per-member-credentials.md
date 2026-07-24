---
status: superseded by ADR-0006
---

# Attribution via explicit `reporter` field, not per-member Jira credentials

The Jira MCP authenticates every call with one shared service-account PAT, even though multiple team members use the same running instance. To keep issues attributed to the human who actually asked for them — rather than the shared bot account — `jira_create_issue` and `jira_update_issue` accept an explicit `reporter` argument that the assistant fills in per call, instead of each member supplying their own PAT through `mcp.json`.

We rejected per-member credentials because the server is one long-running shared process reached over SSE, with a single client instance servicing every connection. Threading a distinct credential per connection would mean rebuilding that transport around a per-session client, for a benefit (correct Reporter attribution) that an explicit field already achieves more simply.

This depends on the shared service account holding Jira's "Modify Reporter" permission — without it, Jira rejects any `reporter` other than the PAT's own owner. That permission lives in the Jira instance's permission scheme, outside this codebase.

## Considered Options

- **Per-member PAT via `mcp.json`**: each user's client would supply their own token, giving accurate attribution *and* enforcing that user's real Jira permissions. Rejected for this need (attribution only) because it requires reworking the single shared-process/singleton-client architecture for a problem the `reporter` field already solves.
- **Per-connection identity via SSE headers**: server reads a username/token off the initial connection and scopes a client to that session automatically. Same rejection — solves a bigger problem (real per-user authorization) than the one we actually have.
