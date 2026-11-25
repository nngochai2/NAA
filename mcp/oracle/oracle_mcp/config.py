"""Oracle MCP configuration — all sourced from mcp/oracle/.env, no hard-coded credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import oracledb
from dotenv import load_dotenv

# mcp/oracle/ — the directory holding meta.yml and .env
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class OracleConfig:
    host: str
    port: int
    service: str  # preferred; e.g. "INVOICING"
    sid: str  # fallback; e.g. "XE"
    user: str
    password: str
    client_lib: str  # path to Instant Client; blank = auto-discover
    default_schema: str
    max_rows: int
    # Schemas the MCP server is allowed to expose. Empty = all schemas
    # accessible to ORACLE_USER.
    allowed_schemas: tuple[str, ...]
    mcp_transport: str  # sse (network — same subnet / team) | stdio (local)
    mcp_host: str
    mcp_port: int

    def dsn(self) -> str:
        if self.service:
            return oracledb.makedsn(self.host, self.port, service_name=self.service)
        if self.sid:
            return oracledb.makedsn(self.host, self.port, sid=self.sid)
        raise ValueError("Set ORACLE_SERVICE (preferred) or ORACLE_SID in .env")

    def validate(self) -> None:
        missing = [k for k, v in (("USER", self.user), ("PASSWORD", self.password)) if not v]
        if not self.service and not self.sid:
            missing.append("ORACLE_SERVICE or ORACLE_SID")
        if missing:
            raise OSError(f"Missing required .env variables: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_config() -> OracleConfig:
    load_dotenv(dotenv_path=PACKAGE_ROOT / ".env")
    user = os.getenv("ORACLE_USER", "")
    return OracleConfig(
        host=os.getenv("ORACLE_HOST", "localhost"),
        port=int(os.getenv("ORACLE_PORT", "1521")),
        service=os.getenv("ORACLE_SERVICE", ""),
        sid=os.getenv("ORACLE_SID", ""),
        user=user,
        password=os.getenv("ORACLE_PASSWORD", ""),
        client_lib=os.getenv("ORACLE_CLIENT_LIB_DIR", ""),
        default_schema=os.getenv("ORACLE_DEFAULT_SCHEMA", user).upper(),
        max_rows=int(os.getenv("MAX_ROWS", "200")),
        allowed_schemas=tuple(
            s.strip().upper() for s in os.getenv("ALLOWED_SCHEMAS", "").split(",") if s.strip()
        ),
        mcp_transport=os.getenv("MCP_TRANSPORT", "sse"),
        mcp_host=os.getenv("MCP_HOST", "0.0.0.0"),
        mcp_port=int(os.getenv("MCP_PORT", "8003")),
    )
