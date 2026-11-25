"""MCP tool definitions and dispatch."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import anyio
import httpx
from mcp.types import ImageContent, TextContent, Tool, ToolAnnotations

from . import attachments, work_items
from .client import AdoClient

logger = logging.getLogger("ado-mcp")

_ITEM_ID = {
    "type": "integer",
    "description": "The numeric work item ID.",
}

TOOLS: list[Tool] = [
    Tool(
        name="get_work_item",
        description=(
            "Fetch full details for an Azure DevOps work item by ID. "
            "Returns title, type, state, description, acceptance criteria, "
            "tags, priority, assignee, dates, and all relations."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "The numeric work item ID (ticket number).",
                }
            },
            "required": ["item_id"],
        },
    ),
    Tool(
        name="search_work_items",
        description=(
            "Search work items using a WIQL WHERE clause. "
            "Example clauses: \"[System.State] = 'Active'\", "
            "\"[System.WorkItemType] = 'Bug' AND [System.IterationPath] UNDER 'Sprint 5'\". "
            "Returns up to `top` results (default 20)."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "where_clause": {
                    "type": "string",
                    "description": "WIQL WHERE fragment (do not include the WHERE keyword).",
                },
                "top": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20, max 50).",
                    "default": 20,
                },
            },
            "required": ["where_clause"],
        },
    ),
    Tool(
        name="get_work_item_comments",
        description=(
            "Fetch the discussion thread (comments) for a work item. "
            "Useful for recovering the reasoning behind decisions made during a ticket."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {"item_id": _ITEM_ID},
            "required": ["item_id"],
        },
    ),
    Tool(
        name="get_related_items",
        description=(
            "Fetch all items linked to a work item (parent, child, related, duplicate, etc.). "
            "Resolves work-item links to include title and state."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {"item_id": _ITEM_ID},
            "required": ["item_id"],
        },
    ),
    Tool(
        name="list_work_item_attachments",
        description=(
            "List all file attachments on a work item. "
            "Returns the filename, size, and optional comment for each attachment. "
            "Use this before read_work_item_attachment to discover what files are available."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {"item_id": _ITEM_ID},
            "required": ["item_id"],
        },
    ),
    Tool(
        name="read_work_item_attachment",
        description=(
            "Download and read a .docx, .xlsx, .pdf or image (.png, .jpg, .jpeg, .gif, .webp) "
            "attachment from a work item. Use list_work_item_attachments first to get the "
            "exact filename. "
            "Returns the full text of the document (paragraphs and tables for .docx; "
            "all sheets/cells for .xlsx; per-page text for .pdf — scanned PDFs without "
            "a text layer return no text). Images (max 5 MB) are returned as image content."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "item_id": _ITEM_ID,
                "filename": {
                    "type": "string",
                    "description": "Exact filename of the attachment (e.g. 'requirements.docx').",
                },
            },
            "required": ["item_id", "filename"],
        },
    ),
]


def _dispatch(client: AdoClient, name: str, args: dict) -> Callable[[], Any] | None:
    """Return a zero-arg callable performing the (blocking) tool call."""
    if name == "get_work_item":
        return lambda: work_items.fetch_work_item(client, int(args["item_id"]))
    if name == "search_work_items":
        top = min(int(args.get("top", 20)), 50)
        return lambda: work_items.search_work_items(client, args["where_clause"], top)
    if name == "get_work_item_comments":
        return lambda: work_items.fetch_comments(client, int(args["item_id"]))
    if name == "get_related_items":
        return lambda: work_items.fetch_related_items(client, int(args["item_id"]))
    if name == "list_work_item_attachments":
        return lambda: attachments.list_attachments(client, int(args["item_id"]))
    if name == "read_work_item_attachment":
        item_id, filename = int(args["item_id"]), args["filename"]
        return lambda: attachments.read_attachment(client, item_id, filename)
    return None


async def handle_tool(
    client: AdoClient, name: str, arguments: dict
) -> list[TextContent | ImageContent]:
    try:
        call = _dispatch(client, name, arguments)
        result = (
            await anyio.to_thread.run_sync(call) if call else {"error": f"Unknown tool: {name}"}
        )

        if isinstance(result, dict) and "image_base64" in result:
            return [
                TextContent(type="text", text=f"Image attachment: {result['name']}"),
                ImageContent(
                    type="image",
                    data=result["image_base64"],
                    mimeType=result["mime_type"],
                ),
            ]

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except httpx.HTTPStatusError as e:
        msg = f"ADO API error {e.response.status_code}: {e.response.text}"
        logger.error(msg)
        return [TextContent(type="text", text=json.dumps({"error": msg}))]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
