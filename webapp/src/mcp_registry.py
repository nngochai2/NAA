"""
MCP server discovery via meta.yml sidecar files.

To register a new MCP server with the webapp, create a meta.yml in its
directory under mcp/. No Python code changes required.

Expected meta.yml schema:
    id: <server-key>          # unique slug, e.g. "git"
    label: "Human Name MCP"
    cmd: ["python", ...]      # "python"/"python3" is replaced with sys.executable
    host: "127.0.0.1"
    port: 8002
    env_file: .env            # path relative to the meta.yml directory
    credentials:
      - key: MY_TOKEN
        label: "API Token"
        secret: true
        placeholder: "tok-..."
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp"


def _resolve_cmd(cmd: list[str]) -> list[str]:
    if cmd and cmd[0] in ("python", "python3"):
        return [sys.executable, *cmd[1:]]
    return list(cmd)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.warning("Could not load %s: %s", path, exc)
        return None


def _meta_paths() -> list[Path]:
    """Return all candidate meta.yml paths, root first then subdirectories."""
    root = _MCP_ROOT / "meta.yml"
    subs = sorted(_MCP_ROOT.glob("*/meta.yml"))
    return [p for p in [root, *subs] if p.exists()]


def discover_servers() -> dict[str, dict[str, Any]]:
    """Return a SERVERS-compatible dict built from meta.yml files."""
    servers: dict[str, dict[str, Any]] = {}
    for meta_path in _meta_paths():
        data = _load(meta_path)
        if not data:
            continue
        server_id = data.get("id")
        if not server_id:
            logger.warning("%s missing 'id' field — skipped", meta_path)
            continue
        host = str(data.get("host", "127.0.0.1"))
        port = int(data.get("port", 8000))
        sse_host = "localhost" if host == "0.0.0.0" else host
        servers[server_id] = {
            "label":   data.get("label", server_id),
            "cmd":     _resolve_cmd(data.get("cmd", [])),
            "cwd":     meta_path.parent,
            "port":    port,
            "host":    host,
            "sse_url": f"http://{sse_host}:{port}/sse",
        }
    return servers


def discover_credentials() -> tuple[dict[str, Path], dict[str, list[dict[str, Any]]]]:
    """Return (MODULE_ENV_PATHS, MODULE_CRED_FIELDS) built from meta.yml files."""
    env_paths:   dict[str, Path]                  = {}
    cred_fields: dict[str, list[dict[str, Any]]]  = {}
    for meta_path in _meta_paths():
        data = _load(meta_path)
        if not data:
            continue
        server_id = data.get("id")
        if not server_id:
            continue
        env_file = data.get("env_file", ".env")
        env_paths[server_id]   = meta_path.parent / env_file
        cred_fields[server_id] = data.get("credentials", [])
    return env_paths, cred_fields
