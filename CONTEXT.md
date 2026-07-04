# NAA — Knowledge Graph Control Plane

Turns scattered project documentation and external trackers (Git issues, Azure DevOps work items, Jira issues) into a queryable Neo4j knowledge graph and exposes both the graph and the trackers to AI assistants via MCP servers.

## Language

**Issue**:
A unit of tracked work in an external tracker (Git MCP or Jira MCP), identified by a number (Git) or key like `PROJECT-123` (Jira).
_Avoid_: Ticket, story, work item (reserve "work item" for Azure DevOps specifically, where that is the tracker's own term).

**Project** (Jira):
The Jira container for issues, identified by a project key. One Jira MCP instance is fixed to a single project for its lifetime.
_Avoid_: Board, as the scoping unit for the MCP's credentials — the MCP configures against a Project, not a Board.

**Board**:
A Jira Kanban board, backed by a saved filter usually scoped to one Project. The Jira MCP does not address boards directly; it creates and manages issues within a Project, and they appear on the board automatically because the board's filter matches them.

**Parent link**:
The hierarchy relationship attached to a newly created Jira issue via `parent_key`. Resolves to one of three underlying mechanisms depending on the issue types involved: the native `parent` field (only valid when the child is a Sub-task), the Epic Link custom field (only valid when the parent is an Epic), or a fallback `Relates` issue link (any other combination, e.g. Task decomposed from a Story).

**Personal Access Token (PAT)**:
The Jira MCP's auth credential — a bearer token issued per-user from Jira profile settings, distinct from Basic Auth (username/password).
