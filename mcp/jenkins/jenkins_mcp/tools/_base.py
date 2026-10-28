"""Registration helpers shared by the tool modules."""
from __future__ import annotations

import json
from typing import Callable

from mcp.types import TextContent, Tool, ToolAnnotations

Handler = Callable[[object, dict], list[TextContent]]

REGISTRY: dict[str, tuple[Tool, Handler]] = {}

JOB = {
    "job_name": {
        "type": "string",
        "description": "Full job name; use 'folder/sub/job' for jobs inside folders.",
    }
}
BUILD = {
    "build_number": {"type": "integer", "description": "Build number. Omit for the last build."},
}


def fmt(data) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def text(value: str) -> list[TextContent]:
    return [TextContent(type="text", text=value)]


def err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {message}")]


def tool(
    name: str,
    description: str,
    properties: dict | None = None,
    required: list[str] | None = None,
    *,
    read_only: bool = False,
    destructive: bool = False,
):
    """Register a handler `fn(client, arguments)` as an MCP tool."""

    def register(fn: Handler) -> Handler:
        annotations = ToolAnnotations(readOnlyHint=True) if read_only else (
            ToolAnnotations(destructiveHint=True) if destructive else None
        )
        REGISTRY[name] = (
            Tool(
                name=name,
                description=description,
                annotations=annotations,
                inputSchema={"type": "object", "properties": properties or {}, "required": required or []},
            ),
            fn,
        )
        return fn

    return register
