"""The FastMCP instance shared by all tool modules, plus JSON result helpers."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import get_config

mcp = FastMCP("oracle-mcp", host=get_config().mcp_host, port=get_config().mcp_port)


def to_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def tool_error(msg: str) -> str:
    return to_json({"error": msg})
