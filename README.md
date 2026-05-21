# NAA — Knowledge Graph Control Plane

NAA is a self-hosted toolkit for teams maintaining **legacy codebases**. It turns scattered project knowledge — architecture notes, compliance rules, API contracts, incident history — into a queryable Neo4j knowledge graph and exposes it to AI coding assistants via the Model Context Protocol (MCP).

The problem it solves: legacy systems accumulate tribal knowledge that lives nowhere. Developers make changes without understanding regulatory intent or architectural conventions because that context cannot be recovered from code alone. NAA gives AI assistants structured, accurate context about *why* the system works the way it does, not just *what* it does.

---

## What It Does

| Capability | How |
|---|---|
| Parse project documentation into a knowledge graph | Obsidian markdown vault → Neo4j via the pipeline |
| Expose the graph to AI assistants | Knowledge-graph MCP server (SSE, port 8000) |
| Expose code structure to AI assistants | Code-graph MCP server via jQAssistant (port 8001) |
| Expose issue tracker context | GitLab MCP server (port 8002) |
| Expose database schema | Oracle schema MCP server (port 8003) |
| Operate everything from a browser | FastAPI control-plane dashboard (port 5000) |

AI coding assistants (Claude, Copilot, Cursor, etc.) connect to one or more MCP servers and can query the graph while writing or reviewing code.

---

## Monorepo Layout

```
NAA/
├── pipeline/          # Obsidian vault → Neo4j document graph
│   └── src/           # build_knowledge_graph.py, parser.py, graph.py, models.py, config.py
├── webapp/            # FastAPI control-plane dashboard (port 5000)
│   └── src/           # main.py, auth.py, mcp_manager.py, env_writer.py, …
├── mcp/               # Knowledge-graph MCP server (port 8000)
│   ├── src/           # server.py, neo4j_client.py
│   ├── codegraph/     # Code-graph MCP — Phase 3 (port 8001)
│   ├── gitlab/        # GitLab issues + MRs MCP (port 8002)
│   └── oracle/        # Oracle schema introspection MCP (port 8003)
├── docker/            # docker-compose.yml — two Neo4j instances
├── jenkins/           # Jenkinsfile — Neo4j lifecycle pipeline
└── config/            # settings.yml — shared non-secret config
```

The MCP servers are **external sidecar processes**, managed by the webapp but never running inside it.

---

## Port Map

| Service | Port |
|---|---|
| Webapp (control plane) | 5000 |
| Knowledge-graph MCP | 8000 |
| Code-graph MCP | 8001 |
| GitLab MCP | 8002 |
| Oracle MCP | 8003 |
| Docgraph Neo4j — Bolt | 7687 |
| Docgraph Neo4j — Browser | 7474 |
| Codegraph Neo4j — Bolt | 7688 |
| Codegraph Neo4j — Browser | 7475 |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker + Docker Compose
- An Obsidian vault (or any folder of `.md` files with YAML frontmatter)

### 1. Start Neo4j

```powershell
docker compose -f docker/docker-compose.yml up -d
```

This starts two Neo4j instances: `docgraph` (bolt:7687) for the document knowledge graph and `codegraph` (bolt:7688) for the code structure graph.

### 2. Configure the webapp

```powershell
cd webapp
Copy-Item .env.example .env
# Edit .env and set NEO4J_PASSWORD (leave other defaults unless you changed them)
```

### 3. Start the webapp

```powershell
cd webapp
python -m uvicorn src.main:app --host 127.0.0.1 --port 5000 --reload
```

Open **http://127.0.0.1:5000**. On first run you will be prompted to set a password.

### 4. Set credentials through the UI

Go to **06_SETTINGS** and enter the webapp's Neo4j connection details. Then go to **05_MCP_SERVERS**, select each server, and fill in its credentials (tokens, passwords, connection strings) — these are written to each module's `.env` file automatically.

### 5. Build the document graph

```powershell
cd pipeline
python src/build_knowledge_graph.py --vault "C:\path\to\your\vault"
```

Options: `--dry-run` (parse without writing), `--clear` (wipe graph before writing).

### 6. Start MCP servers

From the **05_MCP_SERVERS** tab, click **START ALL** or start individual servers. Copy the SSE endpoint URL shown for each server into your AI assistant's MCP configuration.

---

## Webapp Features

| Tab | What it does |
|---|---|
| 01_VAULT_SETUP | Connect an Obsidian vault, browse its folder tree |
| 02_PROCESS | Select folders, run the pipeline, stream build logs |
| 03_SPEC_DOCS | Parse specification documents into the graph |
| 04_DASHBOARD | View graph stats, compliance summary, recent jobs |
| 05_MCP_SERVERS | Start/stop/restart MCP servers, edit host/port, manage credentials |
| 06_SETTINGS | Set webapp Neo4j credentials, change login password |

---

## MCP Servers

### Knowledge-graph MCP (port 8000)
Exposes the document knowledge graph built from the Obsidian vault. Tools include full-text search, relationship traversal, backlink lookup, tag filtering, gap detection, and a staged-note workflow for adding notes via the AI assistant without direct Neo4j access.

### Code-graph MCP (port 8001) — Phase 3
Exposes a jQAssistant code graph (Java bytecode → Neo4j). Tools: `get_class_dependencies`, `get_transitive_impact`, `find_method_callers`, `get_field_impact`, `get_interface_implementations`, `get_class_layer_path`, `get_class_overview`. Connects to the codegraph Neo4j instance (bolt:7688).

### GitLab MCP (port 8002)
Exposes GitLab issues, merge requests, and project metadata. Useful for giving AI assistants context on in-flight changes and known bugs alongside the knowledge graph.

### Oracle MCP (port 8003)
Introspects Oracle database schema — tables, views, PL/SQL procedures, column definitions. Gives AI assistants accurate schema context without requiring access to the source database from the developer's machine.

---

## Configuration

Each module reads from its own `.env` file (gitignored). Copy `.env.example` → `.env` in each module directory you intend to use.

| Module | Key variables |
|---|---|
| `pipeline/` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |
| `webapp/` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `APP_HOST`, `APP_PORT` |
| `mcp/` | Neo4j vars + `MCP_HOST`, `MCP_PORT`, `VAULT_ROOT` |
| `mcp/codegraph/` | `NEO4J_URI` (bolt:7688) + `MCP_PORT=8001` |
| `mcp/gitlab/` | `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `MCP_PORT=8002` |
| `mcp/oracle/` | `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, `ORACLE_USER`, `ORACLE_PASSWORD`, `MCP_PORT=8003` |

Non-secret config (ports, URIs, folder paths) can alternatively be managed from the webapp UI and is stored in `webapp/mcp_state.json`. Secrets (passwords, tokens) are written only to `.env` files — never to the state file.

---

## Infrastructure

### Neo4j (Docker)
Two separate Neo4j 5 instances managed by Docker Compose. `naa-docgraph` holds the document knowledge graph. `naa-codegraph` holds the jQAssistant code graph. The Jenkins pipeline handles start/stop/wipe-and-seed operations.

### Jenkins
A declarative pipeline (`jenkins/Jenkinsfile`) with `ACTION` (start / stop / restart / wipe-and-seed) and `TARGET` (both / docgraph / codegraph) parameters. Triggered manually from Jenkins UI or from the webapp's Neo4j controls.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Document graph pipeline; knowledge-graph MCP; control-plane webapp with auth and credential management | **Done** |
| 2 | Document graph expansion: curation rules, controlled vocabulary, Tag hub nodes | Planned |
| 3 | Code-graph layer (jQAssistant) cross-linked to document graph; senior developer pilot | Planned |
| 4 | Workflow automation (ticket triage, change-impact pre-checks) | Future |

---

## Hard Constraints

| Constraint | Reason |
|---|---|
| MCP servers are separate processes | Stability and restart isolation — a crashing MCP server must not take the webapp down |
| Neo4j is the content store | Note body lives in Neo4j nodes; the MCP server does not read the filesystem at query time |
| No hardcoded credentials | Use `.env` per module or Jenkins-injected secrets in CI |
| Parameterised Cypher only | No string interpolation of user input in any Neo4j query |
| Self-hosted infrastructure only | Jenkins, Docker, GitLab, Neo4j — no cloud service dependencies |
