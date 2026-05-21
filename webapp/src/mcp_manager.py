"""
MCP server process manager.

Manages start / stop / restart of the four MCP servers as subprocesses.
Persists the desired-running set and per-server config overrides so the
webapp can restore state across restarts.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT  = Path(__file__).parent.parent.parent
_STATE_FILE = Path(__file__).parent.parent / "mcp_state.json"

# Server definitions — cmd paths are relative to cwd
SERVERS: dict[str, dict[str, Any]] = {
    "knowledge-graph": {
        "label":   "Knowledge Graph MCP",
        "cmd":     [sys.executable, "src/server.py"],
        "cwd":     _REPO_ROOT / "mcp",
        "port":    8000,
        "host":    "127.0.0.1",
        "sse_url": "http://127.0.0.1:8000/sse",
    },
    "codegraph": {
        "label":   "Code Graph MCP",
        "cmd":     [sys.executable, "-m", "codegraph_mcp"],
        "cwd":     _REPO_ROOT / "mcp" / "codegraph",
        "port":    8001,
        "host":    "127.0.0.1",
        "sse_url": "http://127.0.0.1:8001/sse",
    },
    "gitlab": {
        "label":   "GitLab MCP",
        "cmd":     [sys.executable, "-m", "gitlab_mcp"],
        "cwd":     _REPO_ROOT / "mcp" / "gitlab",
        "port":    8002,
        "host":    "0.0.0.0",
        "sse_url": "http://localhost:8002/sse",
    },
    "oracle": {
        "label":   "Oracle MCP",
        "cmd":     [sys.executable, "oracle_11g/src/oracle_mcp_server.py"],
        "cwd":     _REPO_ROOT / "mcp" / "oracle",
        "port":    8003,
        "host":    "0.0.0.0",
        "sse_url": "http://localhost:8003/sse",
    },
}


def _port_open(host: str, port: int) -> bool:
    target = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect((target, port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


class McpManager:
    def __init__(self) -> None:
        self._procs:      dict[str, subprocess.Popen | None] = {k: None for k in SERVERS}
        self._started_at: dict[str, datetime | None]         = {k: None for k in SERVERS}

    # ── State file ────────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"desired": [], "config": {}}

    def _save_state(self, state: dict) -> None:
        try:
            _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not save MCP state: %s", exc)

    def _desired(self) -> set[str]:
        return set(self._load_state().get("desired", []))

    def _set_desired(self, desired: set[str]) -> None:
        state = self._load_state()
        state["desired"] = sorted(desired)
        self._save_state(state)

    def get_config(self, name: str) -> dict[str, str]:
        """Return the stored config overrides for a server, falling back to defaults."""
        cfg      = SERVERS[name]
        overrides = self._load_state().get("config", {}).get(name, {})
        return {
            "host": overrides.get("MCP_HOST", cfg["host"]),
            "port": str(overrides.get("MCP_PORT", cfg["port"])),
        }

    def set_config(self, name: str, host: str, port: int) -> None:
        state = self._load_state()
        state.setdefault("config", {})[name] = {
            "MCP_HOST": host,
            "MCP_PORT": str(port),
        }
        self._save_state(state)

    # ── Liveness ──────────────────────────────────────────────────────────────

    def _is_running(self, name: str) -> bool:
        proc = self._procs.get(name)
        if proc is not None and proc.poll() is None:
            return True
        cfg = SERVERS[name]
        conf = self.get_config(name)
        return _port_open(conf["host"], int(conf["port"]))

    # ── Process control ───────────────────────────────────────────────────────

    def start(self, name: str) -> None:
        if name not in SERVERS:
            raise KeyError(f"Unknown server: {name!r}")
        if self._is_running(name):
            return

        cfg   = SERVERS[name]
        conf  = self.get_config(name)
        env   = os.environ.copy()
        env["MCP_HOST"] = conf["host"]
        env["MCP_PORT"] = conf["port"]

        try:
            proc = subprocess.Popen(
                cfg["cmd"],
                cwd=str(cfg["cwd"]),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("Failed to start %s: %s", name, exc)
            raise

        self._procs[name]      = proc
        self._started_at[name] = datetime.now(timezone.utc)
        logger.info("Started %s pid=%s", name, proc.pid)

        desired = self._desired()
        desired.add(name)
        self._set_desired(desired)

    def stop(self, name: str) -> None:
        if name not in SERVERS:
            raise KeyError(f"Unknown server: {name!r}")
        proc = self._procs.get(name)
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._procs[name]      = None
            self._started_at[name] = None

        desired = self._desired()
        desired.discard(name)
        self._set_desired(desired)
        logger.info("Stopped %s", name)

    def restart(self, name: str) -> None:
        self.stop(name)
        self.start(name)

    def start_all(self) -> None:
        for name in SERVERS:
            try:
                self.start(name)
            except Exception as exc:
                logger.warning("Could not start %s: %s", name, exc)

    def stop_all(self) -> None:
        for name in SERVERS:
            try:
                self.stop(name)
            except Exception as exc:
                logger.warning("Could not stop %s: %s", name, exc)

    def restore_desired(self) -> None:
        """Start servers that were running when the webapp last shut down."""
        for name in self._desired():
            if name in SERVERS and not self._is_running(name):
                try:
                    self.start(name)
                except Exception as exc:
                    logger.warning("Could not restore %s: %s", name, exc)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self, name: str) -> dict:
        if name not in SERVERS:
            raise KeyError(f"Unknown server: {name!r}")
        cfg     = SERVERS[name]
        conf    = self.get_config(name)
        running = self._is_running(name)
        started = self._started_at.get(name)
        proc    = self._procs.get(name)
        uptime  = None
        if running and started:
            uptime = int((datetime.now(timezone.utc) - started).total_seconds())
        sse_url = f"http://{conf['host']}:{conf['port']}/sse"
        return {
            "name":    name,
            "label":   cfg["label"],
            "host":    conf["host"],
            "port":    int(conf["port"]),
            "sse_url": sse_url,
            "running": running,
            "pid":     proc.pid if proc and proc.poll() is None else None,
            "uptime":  uptime,
        }

    def all_statuses(self) -> list[dict]:
        return [self.status(name) for name in SERVERS]


mcp_manager = McpManager()
