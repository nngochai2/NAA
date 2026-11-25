"""Knowledge Graph MCP server — SSE transport.

Exposes the Neo4j knowledge graph so that AI agents (GitHub Copilot,
Claude Desktop, etc.) can query notes, relationships, specification
requirements and graph statistics, and stage new notes for review.

Importing this module registers every tool on the shared FastMCP instance.
"""

from __future__ import annotations

from .app import mcp
from .tools import authoring, notes, requirements  # noqa: F401  (registers tools)

__all__ = ["mcp"]
