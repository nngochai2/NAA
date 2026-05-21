"""Read and write individual keys in .env files without clobbering other content."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_KEY_RE    = re.compile(r'^([A-Z_][A-Z0-9_]*)(\s*=)(.*)')
_REPO_ROOT = Path(__file__).parent.parent.parent

# Absolute path to each module's .env file
MODULE_ENV_PATHS: dict[str, Path] = {
    "webapp":          _REPO_ROOT / "webapp" / ".env",
    "knowledge-graph": _REPO_ROOT / "mcp"    / ".env",
    "codegraph":       _REPO_ROOT / "mcp"    / "codegraph" / ".env",
    "gitlab":          _REPO_ROOT / "mcp"    / "gitlab"    / ".env",
    "oracle":          _REPO_ROOT / "mcp"    / "oracle"    / ".env",
}

# Declared credential fields per module — key, display label, secret flag, placeholder
MODULE_CRED_FIELDS: dict[str, list[dict[str, Any]]] = {
    "webapp": [
        {"key": "NEO4J_URI",      "label": "Neo4j URI",      "secret": False, "placeholder": "bolt://localhost:7687"},
        {"key": "NEO4J_USER",     "label": "Neo4j User",     "secret": False, "placeholder": "neo4j"},
        {"key": "NEO4J_PASSWORD", "label": "Neo4j Password", "secret": True,  "placeholder": ""},
    ],
    "knowledge-graph": [
        {"key": "NEO4J_URI",      "label": "Neo4j URI",      "secret": False, "placeholder": "bolt://localhost:7687"},
        {"key": "NEO4J_USER",     "label": "Neo4j User",     "secret": False, "placeholder": "neo4j"},
        {"key": "NEO4J_PASSWORD", "label": "Neo4j Password", "secret": True,  "placeholder": ""},
        {"key": "VAULT_ROOT",     "label": "Vault Root",     "secret": False, "placeholder": "C:/path/to/vault"},
    ],
    "codegraph": [
        {"key": "NEO4J_URI",      "label": "Neo4j URI",      "secret": False, "placeholder": "bolt://localhost:7688"},
        {"key": "NEO4J_USER",     "label": "Neo4j User",     "secret": False, "placeholder": "neo4j"},
        {"key": "NEO4J_PASSWORD", "label": "Neo4j Password", "secret": True,  "placeholder": ""},
    ],
    "gitlab": [
        {"key": "GITLAB_URL",        "label": "GitLab URL",  "secret": False, "placeholder": "https://gitlab.example.com"},
        {"key": "GITLAB_TOKEN",      "label": "Token",       "secret": True,  "placeholder": "glpat-..."},
        {"key": "GITLAB_PROJECT_ID", "label": "Project ID",  "secret": False, "placeholder": "42"},
        {"key": "GITLAB_SSL_VERIFY", "label": "SSL Verify",  "secret": False, "placeholder": "true"},
    ],
    "oracle": [
        {"key": "ORACLE_HOST",     "label": "Host",     "secret": False, "placeholder": "localhost"},
        {"key": "ORACLE_PORT",     "label": "Port",     "secret": False, "placeholder": "1521"},
        {"key": "ORACLE_SERVICE",  "label": "Service",  "secret": False, "placeholder": "ORCL"},
        {"key": "ORACLE_USER",     "label": "User",     "secret": False, "placeholder": "system"},
        {"key": "ORACLE_PASSWORD", "label": "Password", "secret": True,  "placeholder": ""},
    ],
}


def write_env(path: Path, updates: dict[str, str]) -> None:
    """Update/add keys in a .env file, preserving comments and unrelated keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines   = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    result  = []
    for line in lines:
        m = _KEY_RE.match(line)
        if m and m.group(1) in pending:
            result.append(f"{m.group(1)}={pending.pop(m.group(1))}")
        else:
            result.append(line)
    for key, val in pending.items():
        result.append(f"{key}={val}")
    path.write_text("\n".join(result) + "\n", encoding="utf-8")


def key_presence(path: Path, keys: list[str]) -> dict[str, bool]:
    """Return which keys are present and non-empty in the .env file."""
    present = {k: False for k in keys}
    if not path.exists():
        return present
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _KEY_RE.match(line)
        if m and m.group(1) in present:
            val = m.group(3).strip().strip('"').strip("'")
            present[m.group(1)] = bool(val)
    return present


def get_cred_status(module: str) -> list[dict]:
    """Return field definitions + whether each key is currently set, for a module."""
    fields   = MODULE_CRED_FIELDS.get(module, [])
    path     = MODULE_ENV_PATHS.get(module)
    keys     = [f["key"] for f in fields]
    presence = key_presence(path, keys) if path else {k: False for k in keys}
    return [{**f, "is_set": presence[f["key"]]} for f in fields]
