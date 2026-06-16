# NAA — Knowledge Graph Control Plane

NAA is a self-hosted toolkit for teams maintaining **legacy codebases**. It turns scattered project knowledge — architecture notes, compliance rules, API contracts, incident history — into a queryable Neo4j knowledge graph and exposes it to AI coding assistants via the **Model Context Protocol (MCP)**.

**The problem it solves:** legacy systems accumulate tribal knowledge that lives nowhere. Developers make changes without understanding regulatory intent or architectural conventions because that context cannot be recovered from code alone. NAA gives AI assistants structured, accurate context about *why* the system works the way it does — not just *what* it does.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [What You Need](#what-you-need)
3. [Repository Layout](#repository-layout)
4. [Setup — Step by Step](#setup--step-by-step)
5. [Using the Control Plane (UI)](#using-the-control-plane-ui)
6. [Connecting an AI Assistant](#connecting-an-ai-assistant)
7. [MCP Server Reference](#mcp-server-reference)
8. [Adding a New MCP Server](#adding-a-new-mcp-server)
9. [Configuration Reference](#configuration-reference)
10. [Infrastructure](#infrastructure)
11. [Roadmap](#roadmap)
12. [Hard Constraints](#hard-constraints)

---

## How It Works

```
Your project docs              AI assistant (Claude, Cursor, …)
  (Markdown vault)                        │
       │                                  │ MCP (SSE)
       ▼                                  ▼
   pipeline/          webapp:5000     mcp/:8000   mcp/git/:8002
  build graph  ───►   Control UI  ──► Knowledge   Git issues
                       (browser)      graph MCP   & PRs MCP
                           │
                           ├──► mcp/codegraph/:8001    (code structure)
                           ├──► mcp/oracle/:8003       (DB schema)
                           └──► mcp/azure_devops/:8004 (ADO work items)
                                         │
                                    Neo4j graphs
```

**MCP (Model Context Protocol)** is an open standard that lets AI assistants call tools on external servers. When an AI assistant has NAA's MCP servers configured, it can search your knowledge graph, look up open issues, query your database schema, and understand code structure — all while you chat with it.

---

## What You Need

| Requirement | Version / Notes |
|---|---|
| Python | 3.11 or newer |
| Docker + Docker Compose | For the two Neo4j instances |
| An Obsidian vault **or** any folder of `.md` files | Files must use YAML frontmatter (`---` blocks) |
| A GitLab or GitHub account | Only if you want the Git MCP |
| An Oracle database | Only if you want the Oracle MCP |
| An Azure DevOps Server (on-prem) instance | Only if you want the Azure DevOps MCP |

You do **not** need a cloud account. Everything runs locally.

---

## Repository Layout

```
NAA/
├── pipeline/              # Step 1 — parse docs, write to Neo4j
│   ├── src/
│   │   ├── build_knowledge_graph.py   # entry point
│   │   ├── parser.py                  # scans vault, extracts links & frontmatter
│   │   ├── graph.py                   # writes to Neo4j
│   │   ├── models.py                  # Note dataclass
│   │   └── config.py                  # folder/keyword config
│   ├── .env.example
│   └── requirements.txt
│
├── webapp/                # Step 2 — browser control panel
│   ├── src/
│   │   ├── main.py                    # FastAPI app, all API routes
│   │   ├── mcp_manager.py             # start/stop MCP servers as subprocesses
│   │   ├── mcp_registry.py            # discovers MCP servers from meta.yml files
│   │   ├── env_writer.py              # reads/writes .env files safely
│   │   └── static/                    # HTML/CSS/JS UI
│   ├── .env.example
│   └── requirements.txt
│
├── mcp/                   # MCP servers — each is an independent process
│   ├── meta.yml           # ← describes this server to the webapp
│   ├── src/               # Knowledge-graph MCP (port 8000)
│   │
│   ├── codegraph/         # Code-graph MCP (port 8001)
│   │   └── meta.yml
│   │
│   ├── git/               # Git MCP — GitLab or GitHub (port 8002)
│   │   └── meta.yml
│   │
│   ├── oracle/            # Oracle schema MCP (port 8003)
│   │   └── meta.yml
│   │
│   └── azure_devops/      # Azure DevOps MCP (port 8004)
│       └── meta.yml
│
├── docker/
│   └── docker-compose.yml # Two Neo4j instances
├── jenkins/
│   └── Jenkinsfile        # CI pipeline for Neo4j lifecycle
└── config/
    └── settings.yml       # Shared non-secret config (ports, URIs)
```

### Key concept: meta.yml

Every MCP server has a `meta.yml` sidecar file. The webapp reads these at startup to discover what servers exist, how to start them, and what credentials to show in the UI. You never need to edit Python to add or reconfigure a server — just edit (or create) a `meta.yml`.

---

## Setup — Step by Step

### Step 1 — Clone and start Neo4j

```powershell
git clone <repo-url>
cd NAA
docker compose -f docker/docker-compose.yml up -d
```

This starts two Neo4j 5 instances:

| Instance | Bolt port | Browser port | Purpose |
|---|---|---|---|
| `naa-docgraph` | 7687 | 7474 | Document knowledge graph |
| `naa-codegraph` | 7688 | 7475 | Code structure graph (Phase 3) |

Verify they are running: open **http://localhost:7474** in your browser. You should see the Neo4j login page. Default credentials are `neo4j / neo4j` — you will be asked to change them on first login.

> **Note the password you set** — you will need it in Step 3.

---

### Step 2 — Set up the webapp

```powershell
cd webapp
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # Mac / Linux

pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `webapp/.env` and set `NEO4J_PASSWORD` to the password you chose in Step 1. Leave everything else at the defaults unless you changed Neo4j's ports.

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
```

---

### Step 3 — Start the webapp

```powershell
# still inside webapp/ with the venv active
python -m uvicorn src.main:app --host 127.0.0.1 --port 5000 --reload
```

Open **http://127.0.0.1:5000**. On first visit you will be prompted to set a login password for the dashboard.

---

### Step 4 — Build the document graph

Set up the pipeline's own environment, then run it against your vault:

```powershell
cd ..\pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit pipeline/.env with the same Neo4j credentials

python src/build_knowledge_graph.py --vault "C:\path\to\your\vault"
```

Useful flags:

| Flag | Effect |
|---|---|
| *(none)* | Parse and write to Neo4j |
| `--dry-run` | Parse only, no Neo4j writes — good for testing |
| `--clear` | Wipe the graph first, then re-seed |

The pipeline classifies notes by subfolder name and extracts relationships from wikilinks (`[[Note Title]]`). YAML frontmatter fields (`tags`, `type`, etc.) are stored as node properties.

---

### Step 5 — Configure MCP server credentials

In the webapp UI, go to **05_MCP_SERVERS**. For each server you want to use:

1. Click on the server card.
2. Open the **Credentials** tab.
3. Fill in the required fields (tokens, passwords, connection strings).
4. Click **Save** — credentials are written directly to the server's `.env` file.

You can also copy the `.env.example` files manually:

```powershell
# Knowledge-graph MCP
Copy-Item mcp\.env.example mcp\.env

# Git MCP
Copy-Item mcp\git\.env.example mcp\git\.env
# Edit mcp\git\.env: set GIT_PROVIDER, then the matching token

# Oracle MCP
Copy-Item mcp\oracle\.env.example mcp\oracle\.env
# Edit mcp\oracle\.env: set ORACLE_HOST, ORACLE_USER, ORACLE_PASSWORD, etc.

# Azure DevOps MCP
Copy-Item mcp\azure_devops\.env.example mcp\azure_devops\.env
# Edit mcp\azure_devops\.env: set ADO_BASE_URL, ADO_PROJECT, ADO_USERNAME, ADO_PASSWORD
```

---

### Step 6 — Start MCP servers

In **05_MCP_SERVERS**, click **START ALL** to launch all servers, or click individual servers to start them one at a time.

Each server runs as a subprocess managed by the webapp. If the webapp restarts, it will automatically restart any servers that were running before.

---

## Using the Control Plane (UI)

| Tab | What it does |
|---|---|
| **01_VAULT_SETUP** | Point the webapp at your markdown vault and browse its folder tree |
| **02_PROCESS** | Select folders to include, run the pipeline, watch the live build log |
| **03_SPEC_DOCS** | Parse specification documents (`.docx`) into the graph using YAML rules |
| **04_DASHBOARD** | Graph statistics, compliance summary, recent pipeline jobs |
| **05_MCP_SERVERS** | Start / stop / restart servers, edit host and port, manage credentials |
| **06_SETTINGS** | Change the webapp's Neo4j connection and the dashboard login password |

The top-right corner shows **VAULT CONNECTED** / **NO VAULT** to indicate whether a vault is currently linked.

---

## Connecting an AI Assistant

Once an MCP server is running, copy its SSE URL from the **05_MCP_SERVERS** tab. The URL follows the pattern `http://<host>:<port>/sse`.

### Claude Desktop / Claude Code

Add this to your Claude MCP configuration (usually `~/.claude/mcp.json` or via the Claude app settings):

```json
{
  "mcpServers": {
    "naa-knowledge-graph": {
      "url": "http://127.0.0.1:8000/sse",
      "transport": "sse"
    },
    "naa-git": {
      "url": "http://localhost:8002/sse",
      "transport": "sse"
    }
  }
}
```

### Cursor

Go to **Settings → MCP**, click **Add MCP Server**, and paste the SSE URL.

### Other assistants

Any MCP-compatible client that supports SSE transport will work. Paste the SSE URL wherever the client asks for a server endpoint.

---

## MCP Server Reference

### Knowledge-graph MCP — port 8000

Exposes the document graph built from your vault.

| Tool | What it does |
|---|---|
| `search_notes` | Full-text search across all notes |
| `get_note` | Retrieve a single note by title or ID |
| `get_related_notes` | Notes linked to or from a given note |
| `get_backlinks` | Notes that reference a given note |
| `get_tagged_notes` | Notes with a specific tag |
| `get_notes_by_type` | Notes of a given type (e.g. `DECISION`, `INCIDENT`) |
| `get_graph_stats` | Total node and relationship counts |
| `find_knowledge_gaps` | Notes with few connections — likely under-documented areas |
| `get_all_note_titles` | Full list of note titles |
| `stage_note` | Draft a new note via the AI (requires approval before commit) |
| `approve_staged_note` | Approve a staged note for writing |
| `reject_staged_note` | Discard a staged note |
| `commit_approved_notes` | Write all approved staged notes to Neo4j |

**Required credentials (`mcp/.env`):** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `VAULT_ROOT`

---

### Code-graph MCP — port 8001 *(Phase 3)*

Exposes a jQAssistant code graph (Java bytecode → Neo4j). Connects to the codegraph Neo4j instance on bolt:7688.

| Tool | What it does |
|---|---|
| `get_class_dependencies` | Direct imports and usages of a class |
| `get_transitive_impact` | All classes affected if a given class changes |
| `find_method_callers` | Every call site of a method |
| `get_field_impact` | Classes that read or write a field |
| `get_interface_implementations` | All classes implementing an interface |
| `get_class_layer_path` | Architectural layer path for a class |
| `get_class_overview` | Summary of a class — fields, methods, annotations |

**Required credentials (`mcp/codegraph/.env`):** `NEO4J_URI` (bolt:7688), `NEO4J_USER`, `NEO4J_PASSWORD`

---

### Git MCP — port 8002

Exposes issues and pull requests / merge requests from GitLab **or** GitHub. Set `GIT_PROVIDER` in `mcp/git/.env` to choose.

**Issues:**

| Tool | What it does |
|---|---|
| `git_list_issues` | List issues, with optional state / label / assignee filter |
| `git_get_issue` | Full detail of one issue |
| `git_create_issue` | Open a new issue |
| `git_update_issue` | Edit title, description, labels, state, or assignees |
| `git_close_issue` | Close an issue |
| `git_delete_issue` | Permanently delete an issue (GitLab only; requires Owner/Admin) |
| `git_link_issues` | Link two issues as *relates_to*, *blocks*, or *is_blocked_by* |

**Pull requests / Merge requests:**

| Tool | What it does |
|---|---|
| `git_list_pull_requests` | List PRs/MRs with optional filters |
| `git_get_pull_request` | Full detail of one PR/MR |
| `git_get_pull_request_changes` | File diff for a PR/MR |
| `git_get_pull_request_discussions` | All review comments and discussions |
| `git_create_pull_request_note` | Add a comment |
| `git_approve_pull_request` | Approve a PR/MR |
| `git_merge_pull_request` | Merge an approved PR/MR |

**GitLab credentials (`mcp/git/.env`):**

```dotenv
GIT_PROVIDER=gitlab
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=glpat-...
GITLAB_PROJECT_ID=42
GITLAB_SSL_VERIFY=true
```

**GitHub credentials (`mcp/git/.env`):**

```dotenv
GIT_PROVIDER=github
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo
```

---

### Oracle MCP — port 8003

Introspects an Oracle database schema — tables, views, columns, PL/SQL procedures, indexes, and foreign keys. Gives AI assistants accurate schema context without direct database access from the developer's machine.

**Required credentials (`mcp/oracle/.env`):** `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE` (or `ORACLE_SID`), `ORACLE_USER`, `ORACLE_PASSWORD`

Optional: `ORACLE_CLIENT_LIB_DIR` (path to Oracle Instant Client), `ALLOWED_SCHEMAS` (comma-separated list to restrict introspection scope).

---

### Azure DevOps MCP — port 8004

Exposes work items from an on-premises Azure DevOps Server collection over Basic or NTLM auth.

| Tool | What it does |
|---|---|
| `get_work_item` | Full details for a work item — title, type, state, description, acceptance criteria, tags, priority, assignee, dates, relations |
| `search_work_items` | Run a WIQL `WHERE` clause fragment, return up to `top` matches (default 20, max 50) |
| `get_work_item_comments` | Discussion thread / history entries for a work item |
| `get_related_items` | Linked items (parent, child, related, duplicate, etc.) with resolved title and state |
| `list_work_item_attachments` | List file attachments (name, size, comment) |
| `read_work_item_attachment` | Download and extract text from a `.docx` or `.xlsx` attachment |

**Required credentials (`mcp/azure_devops/.env`):** `ADO_BASE_URL`, `ADO_PROJECT`, `ADO_USERNAME`, `ADO_PASSWORD`

Optional: `ADO_API_VERSION` (`5.0` for ADO Server 2019, `4.1` for older installs), `NO_PROXY`.

---

## Adding a New MCP Server

Create a directory under `mcp/` for your server, then add a `meta.yml`:

```yaml
# mcp/my-server/meta.yml

id: my-server              # unique slug — used as the server key everywhere
label: "My Custom MCP"     # display name in the UI
cmd: ["python", "-m", "my_mcp_package"]   # "python" is resolved to the active interpreter
host: "127.0.0.1"
port: 8004
env_file: .env             # path relative to this directory

credentials:
  - key: MY_API_URL
    label: "API URL"
    secret: false
    placeholder: "https://api.example.com"
  - key: MY_API_KEY
    label: "API Key"
    secret: true
    placeholder: "sk-..."
```

That is the entire change required. On next startup:

- The webapp automatically discovers the server from `meta.yml`.
- A card appears in **05_MCP_SERVERS** with start/stop controls.
- A credentials panel is rendered with your declared fields.
- The correct `.env` file is read and written by the credential manager.

No Python files need to be edited.

---

## Configuration Reference

### `.env` files

Each module has its own `.env` (gitignored). Copy `.env.example` → `.env` in each module you use.

| Module | `.env` location | Key variables |
|---|---|---|
| Webapp | `webapp/.env` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |
| Knowledge-graph MCP | `mcp/.env` | Neo4j vars + `VAULT_ROOT`, `MCP_HOST`, `MCP_PORT` |
| Code-graph MCP | `mcp/codegraph/.env` | `NEO4J_URI` (bolt:7688), `NEO4J_USER`, `NEO4J_PASSWORD` |
| Git MCP | `mcp/git/.env` | `GIT_PROVIDER`, tokens — see Git MCP section above |
| Oracle MCP | `mcp/oracle/.env` | Oracle connection vars — see Oracle MCP section above |
| Azure DevOps MCP | `mcp/azure_devops/.env` | `ADO_BASE_URL`, `ADO_PROJECT`, `ADO_USERNAME`, `ADO_PASSWORD` — see Azure DevOps MCP section above |
| Pipeline | `pipeline/.env` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |

Secrets (passwords, tokens) go in `.env` only — never in `config/settings.yml` or `mcp_state.json`.

### `config/settings.yml`

Shared non-secret config. Environment variables always take precedence over values in this file.

```yaml
neo4j:
  docgraph:
    uri: bolt://localhost:7687
  codegraph:
    uri: bolt://localhost:7688

mcp_servers:
  knowledge-graph:
    host: "127.0.0.1"
    port: 8000
  git:
    host: "0.0.0.0"
    port: 8002
  # … etc.
```

### Port map

| Service | Port |
|---|---|
| Webapp | 5000 |
| Knowledge-graph MCP | 8000 |
| Code-graph MCP | 8001 |
| Git MCP | 8002 |
| Oracle MCP | 8003 |
| Azure DevOps MCP | 8004 |
| Docgraph Neo4j — Bolt | 7687 |
| Docgraph Neo4j — Browser | 7474 |
| Codegraph Neo4j — Bolt | 7688 |
| Codegraph Neo4j — Browser | 7475 |

---

## Infrastructure

### Neo4j (Docker)

Two independent Neo4j 5 instances run via Docker Compose. `naa-docgraph` holds the document knowledge graph. `naa-codegraph` holds the jQAssistant code structure graph.

```powershell
# Start both
docker compose -f docker/docker-compose.yml up -d

# Check status
docker compose -f docker/docker-compose.yml ps

# Stop both
docker compose -f docker/docker-compose.yml down
```

### Jenkins

A declarative pipeline in `jenkins/Jenkinsfile` manages the Neo4j lifecycle in CI. Parameters:

- `ACTION`: `start`, `stop`, `restart`, or `wipe-and-seed`
- `TARGET`: `both`, `docgraph`, or `codegraph`

Jenkins injects secrets via environment variables — credentials are never stored in the Jenkinsfile.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Document graph pipeline; knowledge-graph MCP; control-plane webapp with auth and credential management | **Done** |
| 2 | Document graph expansion: curation rules, controlled vocabulary, Tag hub nodes | Planned |
| 3 | Code-graph layer (jQAssistant) cross-linked to document graph; developer pilot | Planned |
| 4 | Workflow automation — ticket triage, change-impact pre-checks | Future |

---

## Hard Constraints

| Constraint | Reason |
|---|---|
| MCP servers run as separate processes | A crashing MCP server must not take down the webapp |
| Neo4j is the content store | Note body lives in Neo4j nodes; the MCP server does not read the filesystem at query time |
| YAML frontmatter only | Obsidian notes must use standard YAML `---` blocks; legacy custom headers are not supported |
| No hardcoded credentials | Secrets go in `.env` per module, or are injected by Jenkins in CI |
| Parameterised Cypher only | No string interpolation of user input in any Neo4j query — injection prevention |
| Self-hosted only | Jenkins, Docker, GitLab/GitHub, Neo4j — no cloud service dependencies |
