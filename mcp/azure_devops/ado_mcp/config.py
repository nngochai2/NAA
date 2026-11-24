"""Azure DevOps MCP configuration — loaded once from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

REQUIRED_VARS = ("ADO_BASE_URL", "ADO_PROJECT", "ADO_USERNAME", "ADO_PASSWORD")


@dataclass(frozen=True)
class AdoConfig:
    base_url: str
    project: str
    username: str
    password: str
    api_version: str
    host: str
    port: int


@lru_cache(maxsize=1)
def get_config() -> AdoConfig:
    load_dotenv()
    missing = [k for k in REQUIRED_VARS if not os.getenv(k)]
    if missing:
        raise OSError(f"Missing required env vars: {', '.join(missing)}")
    return AdoConfig(
        base_url=os.environ["ADO_BASE_URL"].rstrip("/"),
        project=os.environ["ADO_PROJECT"],
        username=os.environ["ADO_USERNAME"],
        password=os.environ["ADO_PASSWORD"],
        api_version=os.getenv("ADO_API_VERSION") or "5.0",
        host=os.getenv("MCP_HOST") or "0.0.0.0",
        port=int(os.getenv("MCP_PORT") or "8004"),
    )
