"""Jira attachment tools — lets the agent see images (and read text files) attached to issues."""
from __future__ import annotations

import base64
import json
import logging

from mcp.types import ImageContent, TextContent, Tool, ToolAnnotations

from ..client import JiraApiError, JiraClient

logger = logging.getLogger(__name__)

# Anthropic's per-image limit is 5 MB; stay under it so the model can always accept the result.
DEFAULT_MAX_IMAGE_BYTES = 5_000_000
DEFAULT_MAX_TEXT_BYTES = 100_000

# Image types the model can read. SVG/TIFF/BMP are deliberately excluded.
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_TEXT_TYPES = {
    "application/json", "application/xml", "application/x-yaml", "application/yaml",
    "application/sql", "application/javascript", "application/x-sh",
}
_TEXT_EXTENSIONS = (".log", ".txt", ".md", ".csv", ".json", ".xml", ".yml", ".yaml", ".sql", ".java", ".py", ".sh")

ATTACHMENT_TOOLS: list[Tool] = [
    Tool(
        name="jira_list_attachments",
        description=(
            "List the attachments of a Jira issue (id, filename, type, size). "
            "Use jira_get_attachment with an id to read one."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Jira issue key, e.g. 'PROJ-123'."},
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="jira_get_attachment",
        description=(
            "Read a Jira attachment by id (from jira_list_attachments or jira_get_issue). "
            "Images (PNG, JPEG, GIF, WebP) are returned as viewable images; text/log/JSON/XML files "
            "are returned as text; other file types are reported by name and size only."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string", "description": "Attachment id, e.g. '10042'."},
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum bytes to download for non-image files.",
                    "default": DEFAULT_MAX_TEXT_BYTES,
                },
            },
            "required": ["attachment_id"],
        },
    ),
]


def _text(data: object) -> list[TextContent | ImageContent]:
    return [TextContent(type="text", text=data if isinstance(data, str) else json.dumps(data, indent=2, default=str))]


def _err(msg: str) -> list[TextContent | ImageContent]:
    return _text(f"Error: {msg}")


def _summarise(att: dict) -> dict:
    return {
        "id": att.get("id"),
        "filename": att.get("filename"),
        "mimeType": att.get("mimeType"),
        "size": att.get("size"),
        "author": (att.get("author") or {}).get("displayName"),
        "created": att.get("created"),
    }


def _is_text(mime: str, filename: str) -> bool:
    return mime.startswith("text/") or mime in _TEXT_TYPES or filename.lower().endswith(_TEXT_EXTENSIONS)


def handle_attachment_tool(name: str, arguments: dict, client: JiraClient) -> list[TextContent | ImageContent]:
    try:
        if name == "jira_list_attachments":
            issue = client.get_issue(arguments["issue_key"])
            attachments = (issue.get("fields") or {}).get("attachment") or []
            return _text([_summarise(a) for a in attachments])

        if name == "jira_get_attachment":
            meta = client.get_attachment_meta(arguments["attachment_id"])
            filename = meta.get("filename", "")
            mime = (meta.get("mimeType") or "").lower()
            size = int(meta.get("size") or 0)
            summary = _summarise(meta)

            if mime in _IMAGE_TYPES:
                if size > DEFAULT_MAX_IMAGE_BYTES:
                    return _err(
                        f"Image '{filename}' is {size} bytes, over the {DEFAULT_MAX_IMAGE_BYTES}-byte limit "
                        "the model can accept."
                    )
                data = client.download_attachment(meta, DEFAULT_MAX_IMAGE_BYTES)
                return [
                    TextContent(type="text", text=json.dumps(summary, indent=2, default=str)),
                    ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mimeType=mime),
                ]

            if _is_text(mime, filename):
                limit = int(arguments.get("max_bytes") or DEFAULT_MAX_TEXT_BYTES)
                data = client.download_attachment(meta, limit, truncate=True)
                text = data.decode("utf-8", errors="replace")
                if size > len(data):
                    text += f"\n\n[truncated at {len(data)} of {size} bytes]"
                return [TextContent(type="text", text=json.dumps(summary, indent=2, default=str)), *_text(text)]

            return _text({
                **summary,
                "note": "Content not returned: only images and text-like files can be read through this tool.",
            })

        return _err(f"Unknown tool: {name}")

    except JiraApiError as exc:
        return _err(str(exc))
    except (ValueError, KeyError) as exc:
        return _err(str(exc))
