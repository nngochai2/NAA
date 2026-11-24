"""The FastMCP instance and the lazily-created Neo4j client shared by all tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import get_config
from .neo4j_client import Neo4jClient

NOTE_TYPES = {"ARCHITECTURE", "TASK", "CONVENTION", "BUSINESS_TERM", "NOTE", "TAG"}

mcp = FastMCP(
    "Knowledge Graph",
    instructions=(
        "You have access to an Obsidian knowledge graph stored in Neo4j. "
        "Notes are classified as ARCHITECTURE, TASK, CONVENTION, BUSINESS_TERM, NOTE, or TAG. "
        "Use search_notes() to find notes by keyword, get_note() for full details, "
        "get_related_notes() to explore relationships, and get_backlinks() to see what "
        "references a given note. Use get_graph_stats() for an overview. "
        "IMPORTANT: When asked about notes related to a specific topic or tag, "
        "always use get_tagged_notes(tag, note_type) first — "
        "it returns all matching notes in one call. Only fall back to get_note() when you need "
        "the full body content of a specific note. "
        "For specification requirements: use get_use_cases() to list UseCases under a flow, "
        "get_documents() to see FDD/SDD under a UseCase, get_requirements() to list all BRs, "
        "and get_requirement_detail() for the full body of a single BR."
    ),
    host=get_config().host,
    port=get_config().port,
)

# Initialised on first tool call; avoids hard failure at import time if
# Neo4j is not yet available when the module loads.
_db: Neo4jClient | None = None


def get_db() -> Neo4jClient:
    global _db
    if _db is None:
        cfg = get_config()
        _db = Neo4jClient(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)
    return _db
