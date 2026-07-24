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
A bearer token issued per-user from Jira profile settings, distinct from Basic Auth (username/password). Each team member supplies their own PAT to authenticate their own connection to the Jira MCP; the MCP itself holds no PAT of its own.

**Reporter**:
The Jira user recorded as having raised an issue. Determined automatically by whichever member's PAT authenticated the connection that created it — never set independently of the authenticating account.
_Avoid_: Assignee (who currently owns the work) or Author — reserve those for other roles.

**BR (Business Rule)**:
One business requirement extracted from a table row in an FDD or SDD document, identified by an ID such as `BR04`, `BRU01`, or `BRM23`. Parsed by the rule-file-driven `DocxRuleParser` (`webapp/src/docx_generic_parser.py`) per `parsing-rules/*.yml`.

**BR ID prefix**:
The letters before the digits in a BR ID (e.g. `BR`, `BRU`, `BRM`). An FDD/SDD document's author may use different prefixes to keep separate tables of business rules within the same document. The prefix is meaningful to the author, but the parser does not interpret *what* it means — it only validates the prefix against a per-rule-file allow-list (so a typo'd or unrecognized prefix surfaces as a warning instead of silently vanishing) and preserves it verbatim as part of the BR's identity.
_Avoid_: "BR group" / "BR category" for the prefix — those terms are reserved for the parser's independently-inferred `candidate_categories` (`OracleEBS`, `Java`, `BatchJob`, `SQLView`), which are unrelated to the ID prefix and never vary by prefix.
