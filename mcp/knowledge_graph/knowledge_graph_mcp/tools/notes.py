"""Read-only tools for querying Obsidian notes in the graph."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ..app import NOTE_TYPES, get_db, mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_notes(query: str, limit: int = 10) -> str:
    """
    Search the knowledge graph by keyword. Matches against:
    - Note titles and subfolders (Obsidian notes)
    - Requirement BR IDs, titles, UC IDs, and tags (ingested documents)

    Args:
        query: Keyword to search for (case-insensitive). Can be a UC ID (e.g. "UC39"),
               BR ID (e.g. "BR03"), tag name, or any title keyword.
        limit: Max results to return (capped at 50).
    """
    results = get_db().search_notes(query.strip(), min(limit, 50))
    if not results:
        return f"No notes or requirements found matching '{query}'."
    lines = [f"Found {len(results)} result(s) matching '{query}':\n"]
    for r in results:
        if r.get("result_type") == "br":
            br = r.get("br_id", "")
            uc = r.get("uc_id", "")
            flow_name = r.get("flow_name", "")
            doc = r.get("status", "")
            lines.append(
                f"- **[{br}] {r['title']}**  [BR]  "
                f"uc={uc}  doc_type={doc}  flow={flow_name}"
                f"\n  → Call get_requirement_detail(br_id='{br}', uc_id='{uc}', "
                f"doc_type='{doc}', flow_name='{flow_name}') for full body."
            )
        else:
            lines.append(
                f"- **{r['title']}**  [{r['type']}]  {r['subfolder']}  "
                f"— {r['backlinks']} backlink(s)"
            )
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_note(title: str) -> str:
    """
    Get full details for a note: type, status, created date, word count,
    all outgoing wikilinks with relationship types, and backlink count.
    Use the exact title (case-sensitive). If unsure, call search_notes() first.

    Args:
        title: Exact note title.
    """
    note = get_db().get_note(title.strip())
    if not note:
        return f"Note '{title}' not found. Call search_notes() to find the correct title."
    lines = [
        f"# {note['title']}",
        f"Type: {note['type']} | Subfolder: {note['subfolder']} | Status: {note['status'] or '—'}",
        f"Created: {note['created_at'] or '—'} | "
        f"Words: {note['word_count']} | Backlinks: {note['backlinks']}",
        f"Path: {note['path']}",
    ]
    links = [lnk for lnk in (note.get("links") or []) if lnk.get("target")]
    if links:
        lines.append(f"\nOutgoing links ({len(links)}):")
        for lnk in links:
            lines.append(f"  [{lnk.get('rel', 'LINKS_TO')}] → {lnk['target']}")
    if note.get("summary"):
        lines.append(f"\n## Summary\n{note['summary']}")
    if note.get("body"):
        lines.append(f"\n---\n{note['body']}")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_related_notes(title: str, hops: int = 1) -> str:
    """
    Traverse the graph from a note and return nearby notes.
    hops=1 is direct neighbours; hops=2 extends one more step (max 3).

    Args:
        title: Starting note title (exact).
        hops:  Graph traversal depth (1–3, default 1).
    """
    results = get_db().get_related_notes(title.strip(), hops)
    if not results:
        return f"No related notes found for '{title}' within {hops} hop(s)."
    lines = [f"Related notes for '{title}' ({hops} hop(s), {len(results)} found):\n"]
    for r in results:
        lines.append(
            f"- **{r['title']}**  [{r['type']}]  via {r['relationship']}  ({r['subfolder']})"
        )
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_backlinks(title: str) -> str:
    """
    Get all notes that link TO the given note (incoming edges).
    Shows the relationship type and the surrounding context text.

    Args:
        title: Exact note title to look up backlinks for.
    """
    results = get_db().get_backlinks(title.strip())
    if not results:
        return f"No notes link to '{title}'."
    lines = [f"Notes linking to '{title}' ({len(results)}):\n"]
    for r in results:
        ctx = f'\n    context: "{r["context"][:100]}"' if r.get("context") else ""
        lines.append(f"- **{r['source']}**  [{r['source_type']}]  via {r['relationship']}{ctx}")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_tagged_notes(tag: str, note_type: str | None = None, limit: int = 50) -> str:
    """
    Get all notes linked to a specific tag or topic, optionally filtered by type.
    This is the most efficient way to answer questions like:
      - "What tasks have been done for eInvoice?" → get_tagged_notes("eInvoice", "TASK")
      - "What architecture notes exist for MuleSoft?" → get_tagged_notes("MuleSoft", "ARCHITECTURE")
      - "Show all notes related to eInvoice" → get_tagged_notes("eInvoice")
    Returns title, type, status, and Ollama-generated summary for each match.

    Args:
        tag:       Title of the tag or topic note to look up (exact, case-sensitive).
        note_type: Optional type filter — ARCHITECTURE, TASK, CONVENTION, BUSINESS_TERM, NOTE, TAG.
        limit:     Max results to return (default 50).
    """
    nt = note_type.strip().upper() if note_type else None
    if nt and nt not in NOTE_TYPES:
        return f"Invalid type '{note_type}'. Valid types: {', '.join(sorted(NOTE_TYPES))}"
    results = get_db().get_tagged_notes(tag.strip(), nt, limit)
    label = f" of type {nt}" if nt else ""
    if not results:
        return f"No notes{label} found linked to '{tag}'."
    lines = [f"Notes{label} linked to '{tag}' ({len(results)} found):\n"]
    for r in results:
        summary = f"\n    {r['summary']}" if r.get("summary") else ""
        lines.append(f"- **{r['title']}**  [{r['type']}]  status: {r['status'] or '—'}{summary}")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_notes_by_type(note_type: str, limit: int = 20) -> str:
    """
    List notes of a specific type, ordered by popularity (backlink count).
    Valid types: ARCHITECTURE, TASK, CONVENTION, BUSINESS_TERM, NOTE, TAG.

    Args:
        note_type: One of the valid type strings above (case-insensitive).
        limit:     Max results (capped at 100).
    """
    nt = note_type.strip().upper()
    if nt not in NOTE_TYPES:
        return f"Invalid type '{note_type}'. Valid types: {', '.join(sorted(NOTE_TYPES))}"
    results = get_db().get_notes_by_type(nt, min(limit, 100))
    if not results:
        return f"No notes of type '{nt}' in the graph."
    lines = [f"Notes of type {nt} ({len(results)}):\n"]
    for r in results:
        lines.append(
            f"- **{r['title']}**  ({r['subfolder']})  "
            f"status: {r['status'] or '—'}  |  {r['backlinks']} backlink(s)"
        )
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_graph_stats() -> str:
    """
    Return an overview of the knowledge graph:
    total notes, total relationships, and a breakdown of notes by type.
    Useful as a first call to understand the graph's contents.
    """
    db = get_db()
    stats = db.get_stats()
    counts = db.get_type_counts()
    lines = [
        f"Total notes:         {stats.get('total_notes', '?')}",
        f"Total relationships: {stats.get('total_relationships', '?')}",
        "\nBreakdown by type:",
    ]
    for row in counts:
        lines.append(f"  {row['type']:<20} {row['count']}")
    return "\n".join(lines)
