"""
MCP Server — SSE transport
 
Exposes the Neo4j knowledge graph as an MCP server so that
AI agents (GitHub Copilot, Claude Desktop, etc.) can query notes,
relationships, and graph statistics.
 
Transport: SSE  (default: http://127.0.0.1:8000/sse)
 
Start:
    python server.py
 
Configure:
    Copy .env.example → .env and set NEO4J_* and MCP_HOST/MCP_PORT.
"""
 
import os
import re
import json
import hashlib
import uuid
from datetime import date, datetime
from pathlib import Path
 
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
 
from neo4j_client import Neo4jClient
 
load_dotenv()
 
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
HOST           = os.getenv("MCP_HOST",    "127.0.0.1")
PORT           = int(os.getenv("MCP_PORT", "8000"))
VAULT_ROOT     = os.getenv("VAULT_ROOT",  "")
 
# Staging file persists notes awaiting human review across server restarts.
STAGING_FILE   = Path(__file__).parent.parent / "staged_notes.json"
 
# ── Staging helpers ───────────────────────────────────────────────────────────
 
def _load_staging() -> dict:
    if STAGING_FILE.exists():
        try:
            return json.loads(STAGING_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"notes": {}}
 
 
def _save_staging(data: dict) -> None:
    STAGING_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
 
 
# ── Note parsing helpers (used for direct Neo4j upsert) ──────────────────────
 
_WIKILINK_RE    = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?\|?([^\]]*?)\]\]")
_TAGS_LINE_RE   = re.compile(r"^Tags:\s*", re.IGNORECASE)
_HEADER_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}")
 
 
def _parse_wikilinks(content: str) -> list[dict]:
    """Extract [[WikiLinks]] from note content."""
    links = []
    for m in _WIKILINK_RE.finditer(content):
        target = m.group(1).strip()
        alias  = m.group(2).strip() or target
        start  = max(0, m.start() - 80)
        end    = min(len(content), m.end() + 80)
        ctx    = content[start:end].replace("\n", " ")
        line_start = content.rfind("\n", 0, m.start()) + 1
        rel = "TAGGED_WITH" if _TAGS_LINE_RE.match(content[line_start:m.start() + 1]) else "LINKS_TO"
        links.append({"target": target, "alias": alias, "context": ctx, "relationship": rel})
    return links
 
 
def _extract_body(content: str) -> str:
    """Return everything from the first H1 heading onwards, capped at 5000 chars."""
    for i, line in enumerate(content.splitlines()):
        if line.startswith("# "):
            body = "\n".join(content.splitlines()[i:])
            return body[:5000]
    return content[:5000]
 
 
def _note_props(staged: dict) -> dict:
    """Build the Neo4j property dict from a staged note entry."""
    path = staged["vault_relative_path"].replace("\\", "/")
    parts = Path(path).parts
    subfolder = parts[-2] if len(parts) >= 2 else ""
    body = _extract_body(staged["content"])
    return {
        "node_id":      hashlib.sha1(path.encode()).hexdigest()[:16],
        "title":        staged["title"],
        "type":         staged["note_type"],
        "subfolder":    subfolder,
        "status":       "Done",
        "created_at":   datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "path":         path,
        "word_count":   len(body.split()),
        "content_hash": hashlib.md5(staged["content"].encode()).hexdigest(),
        "body":         body,
        "summary":      "",
    }
 
 
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
    host=HOST,
    port=PORT,
)
 
# =====================================================================================================
# Lazy singleton
# =====================================================================================================
# Initialised on first tool call; avoids hard failure at import time if
# Neo4j is not yet available when the module loads.
 
_db: Neo4jClient | None = None
 
 
def _get_db() -> Neo4jClient:
    global _db
    if _db is None:
        _db = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return _db
 
 
# =====================================================================================================
# Tools
# =====================================================================================================
 
@mcp.tool()
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
    results = _get_db().search_notes(query.strip(), min(limit, 50))
    if not results:
        return f"No notes or requirements found matching '{query}'."
    lines = [f"Found {len(results)} result(s) matching '{query}':\n"]
    for r in results:
        if r.get("result_type") == "br":
            br        = r.get("br_id", "")
            uc        = r.get("uc_id", "")
            flow_name = r.get("flow_name", "")
            doc       = r.get("status", "")
            lines.append(
                f"- **[{br}] {r['title']}**  [BR]  "
                f"uc={uc}  doc_type={doc}  flow={flow_name}"
                f"\n  \u2192 Call get_requirement_detail(br_id='{br}', uc_id='{uc}', doc_type='{doc}', flow_name='{flow_name}') for full body."
            )
        else:
            lines.append(
                f"- **{r['title']}**  [{r['type']}]  {r['subfolder']}  "
                f"— {r['backlinks']} backlink(s)"
            )
    return "\n".join(lines)
 
 
@mcp.tool()
def get_note(title: str) -> str:
    """
    Get full details for a note: type, status, created date, word count,
    all outgoing wikilinks with relationship types, and backlink count.
    Use the exact title (case-sensitive). If unsure, call search_notes() first.
 
    Args:
        title: Exact note title.
    """
    note = _get_db().get_note(title.strip())
    if not note:
        return (
            f"Note '{title}' not found. "
            "Call search_notes() to find the correct title."
        )
    lines = [
        f"# {note['title']}",
        f"Type: {note['type']} | Subfolder: {note['subfolder']} | "
        f"Status: {note['status'] or '—'}",
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
 
 
@mcp.tool()
def get_related_notes(title: str, hops: int = 1) -> str:
    """
    Traverse the graph from a note and return nearby notes.
    hops=1 is direct neighbours; hops=2 extends one more step (max 3).
 
    Args:
        title: Starting note title (exact).
        hops:  Graph traversal depth (1–3, default 1).
    """
    results = _get_db().get_related_notes(title.strip(), hops)
    if not results:
        return f"No related notes found for '{title}' within {hops} hop(s)."
    lines = [f"Related notes for '{title}' ({hops} hop(s), {len(results)} found):\n"]
    for r in results:
        lines.append(
            f"- **{r['title']}**  [{r['type']}]  via {r['relationship']}  "
            f"({r['subfolder']})"
        )
    return "\n".join(lines)
 
 
@mcp.tool()
def get_backlinks(title: str) -> str:
    """
    Get all notes that link TO the given note (incoming edges).
    Shows the relationship type and the surrounding context text.
 
    Args:
        title: Exact note title to look up backlinks for.
    """
    results = _get_db().get_backlinks(title.strip())
    if not results:
        return f"No notes link to '{title}'."
    lines = [f"Notes linking to '{title}' ({len(results)}):\n"]
    for r in results:
        ctx = f'\n    context: "{r["context"][:100]}"' if r.get("context") else ""
        lines.append(
            f"- **{r['source']}**  [{r['source_type']}]  "
            f"via {r['relationship']}{ctx}"
        )
    return "\n".join(lines)
 
 
@mcp.tool()
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
    _VALID = {"ARCHITECTURE", "TASK", "CONVENTION", "BUSINESS_TERM", "NOTE", "TAG"}
    nt = note_type.strip().upper() if note_type else None
    if nt and nt not in _VALID:
        return f"Invalid type '{note_type}'. Valid types: {', '.join(sorted(_VALID))}"
    results = _get_db().get_tagged_notes(tag.strip(), nt, limit)
    if not results:
        label = f" of type {nt}" if nt else ""
        return f"No notes{label} found linked to '{tag}'."
    label = f" of type {nt}" if nt else ""
    lines = [f"Notes{label} linked to '{tag}' ({len(results)} found):\n"]
    for r in results:
        summary = f"\n    {r['summary']}" if r.get("summary") else ""
        lines.append(
            f"- **{r['title']}**  [{r['type']}]  status: {r['status'] or '—'}{summary}"
        )
    return "\n".join(lines)
 
 
@mcp.tool()
def get_notes_by_type(note_type: str, limit: int = 20) -> str:
    """
    List notes of a specific type, ordered by popularity (backlink count).
    Valid types: ARCHITECTURE, TASK, CONVENTION, BUSINESS_TERM, NOTE, TAG.
 
    Args:
        note_type: One of the valid type strings above (case-insensitive).
        limit:     Max results (capped at 100).
    """
    _VALID = {"ARCHITECTURE", "TASK", "CONVENTION", "BUSINESS_TERM", "NOTE", "TAG"}
    nt = note_type.strip().upper()
    if nt not in _VALID:
        return f"Invalid type '{note_type}'. Valid types: {', '.join(sorted(_VALID))}"
    results = _get_db().get_notes_by_type(nt, min(limit, 100))
    if not results:
        return f"No notes of type '{nt}' in the graph."
    lines = [f"Notes of type {nt} ({len(results)}):\n"]
    for r in results:
        lines.append(
            f"- **{r['title']}**  ({r['subfolder']})  "
            f"status: {r['status'] or '—'}  |  {r['backlinks']} backlink(s)"
        )
    return "\n".join(lines)
 
 
@mcp.tool()
def get_graph_stats() -> str:
    """
    Return an overview of the knowledge graph:
    total notes, total relationships, and a breakdown of notes by type.
    Useful as a first call to understand the graph's contents.
    """
    stats  = _get_db().get_stats()
    counts = _get_db().get_type_counts()
    lines = [
        f"Total notes:         {stats.get('total_notes', '?')}",
        f"Total relationships: {stats.get('total_relationships', '?')}",
        "\nBreakdown by type:",
    ]
    for row in counts:
        lines.append(f"  {row['type']:<20} {row['count']}")
    return "\n".join(lines)
 
 
# =====================================================================================================
# Note authoring tools — "Growing" the knowledge graph
# =====================================================================================================
 
@mcp.tool()
def find_knowledge_gaps(concepts: str) -> str:
    """
    Given a comma-separated list of concepts extracted from a source document,
    check each one against the existing graph and classify coverage as:
      - full    : no existing note covers this concept at all
      - partial : a note exists but is shallow (few words, no real body)
      - covered : a substantial note already exists
 
    Use this BEFORE planning new notes — only write notes that fill full or partial gaps.
 
    Args:
        concepts: Comma-separated concept names.
                  Example: "EU Naming Conventions, Finder vs Searcher, 3-Tier Architecture"
    """
    concept_list = [c.strip() for c in concepts.split(",") if c.strip()]
    if not concept_list:
        return "No concepts provided."
    if len(concept_list) > 30:
        return "Too many concepts (max 30). Split into smaller batches."
 
    results = _get_db().find_coverage(concept_list)
    lines = [f"Gap analysis for {len(results)} concept(s):\n"]
    for r in results:
        gap_label = {"full": "FULL GAP", "partial": "PARTIAL", "covered": "covered"}[r["gap_type"]]
        lines.append(f"[{gap_label}] {r['concept']}")
        for note in r["existing"]:
            lines.append(
                f"    → '{note['title']}' [{note['type']}] "
                f"{note['word_count']} words — {note['summary'][:80] if note.get('summary') else 'no summary'}"
            )
        if not r["existing"]:
            lines.append("    → (nothing found in graph)")
    return "\n".join(lines)
 
 
@mcp.tool()
def get_all_note_titles() -> str:
    """
    Return every note title currently in the graph, one per line.
    Use this when composing new notes so you can add valid [[WikiLinks]] —
    only link to titles that actually exist in this list.
    """
    titles = _get_db().get_all_note_titles()
    if not titles:
        return "Graph is empty."
    return f"{len(titles)} note titles:\n\n" + "\n".join(titles)
 
 
@mcp.tool()
def stage_note(
    title: str,
    vault_relative_path: str,
    note_type: str,
    content: str,
) -> str:
    """
    Stage a new note for human review. The note is NOT written to disk or indexed
    until a human calls approve_staged_note() then commit_approved_notes().
 
    Note content MUST start with the standard Obsidian header:
        DD-MM-YYYY HH:MM
        (blank line)
        Status: #Done
        (blank line)
        Tags: [[YourTag]]
        (blank line)
        # <title>
 
    Args:
        title:               Exact note title (must match the # heading in content).
        vault_relative_path: Path relative to vault root, e.g.
                             "6 - Main Notes/Project/Knowledge/Architecture/My Note.md"
        note_type:           ARCHITECTURE | CONVENTION | TASK | BUSINESS_TERM | NOTE
        content:             Full file content including header. Body must be <5000 chars.
    """
    _VALID_TYPES = {"ARCHITECTURE", "CONVENTION", "TASK", "BUSINESS_TERM", "NOTE"}
    nt = note_type.strip().upper()
    if nt not in _VALID_TYPES:
        return f"Invalid note_type '{note_type}'. Valid: {', '.join(sorted(_VALID_TYPES))}"
 
    clean = vault_relative_path.replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        return "Invalid path: '..' is not allowed."
    if not clean.endswith(".md"):
        return "vault_relative_path must end with .md"
 
    if not _HEADER_DATE_RE.match(content.lstrip()):
        today = date.today().strftime("%d-%m-%Y")
        return (
            f"Content must start with a date header. Example:\n"
            f"  {today} 09:00\n\n  Status: #Done\n\n  Tags: [[YourTag]]\n\n  # {title}"
        )
 
    body = _extract_body(content)
    if len(body) > 5000:
        return (
            f"Body is {len(body)} characters. "
            "The build pipeline truncates at 5000 — split into smaller notes."
        )
 
    note_id = uuid.uuid4().hex[:8]
    staging = _load_staging()
    staging["notes"][note_id] = {
        "id":                  note_id,
        "title":               title.strip(),
        "vault_relative_path": clean,
        "note_type":           nt,
        "content":             content,
        "status":              "pending",
        "reject_reason":       "",
        "staged_at":           datetime.now().isoformat(timespec="seconds"),
    }
    _save_staging(staging)
 
    # Write preview file to VAULT_ROOT/_staging/ for review in Obsidian
    preview_path: str | None = None
    if VAULT_ROOT:
        staging_dir = Path(VAULT_ROOT) / "_staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title.strip())
        preview_file = staging_dir / f"{note_id}_{safe_title}.md"
        try:
            preview_file.write_text(content, encoding="utf-8")
            preview_path = f"_staging/{note_id}_{safe_title}.md"
        except OSError:
            pass
 
    links = _parse_wikilinks(content)
    preview_lines = [
        f"Staged note ID: {note_id}",
        f"Title:    {title}",
        f"Type:     {nt}",
        f"Path:     {clean}",
        f"Body:     {len(body)} chars, {len(body.split())} words",
        f"Links:    {len(links)} wikilink(s) found",
    ]
    for lnk in links[:8]:
        preview_lines.append(f"  [{lnk['relationship']}] → {lnk['target']}")
    if len(links) > 8:
        preview_lines.append(f"  … and {len(links) - 8} more")
    if preview_path:
        preview_lines.append(f"Preview: {preview_path}  (open in Obsidian to review)")
    preview_lines.append(
        f"\nStatus: PENDING — call approve_staged_note('{note_id}') or "
        f"reject_staged_note('{note_id}', reason) to decide."
    )
    return "\n".join(preview_lines)
 
 
@mcp.tool()
def list_staged_notes(show_content: bool = False) -> str:
    """
    List all staged notes and their current status (pending / approved / rejected).
 
    Args:
        show_content: If True, include the first 20 lines of each note's content.
    """
    staging = _load_staging()
    notes = staging.get("notes", {})
    if not notes:
        return "No staged notes. Use stage_note() to add a note for review."
 
    lines = [f"{len(notes)} staged note(s):\n"]
    for note in notes.values():
        icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(note["status"], "?")
        lines.append(
            f"{icon} [{note['id']}] {note['title']}  "
            f"[{note['note_type']}]  →  {note['vault_relative_path']}"
        )
        if note["status"] == "rejected" and note.get("reject_reason"):
            lines.append(f"    Reason: {note['reject_reason']}")
        if show_content:
            lines.append("    Content preview:")
            for ln in note["content"].splitlines()[:20]:
                lines.append(f"      {ln}")
            if note["content"].count("\n") > 20:
                lines.append("      [… truncated]")
    return "\n".join(lines)
 
 
@mcp.tool()
def approve_staged_note(note_id: str) -> str:
    """
    Approve a staged note so it will be written and indexed on the next commit.
    Call commit_approved_notes() when all reviews are done.
 
    Args:
        note_id: The 8-character ID returned by stage_note().
    """
    staging = _load_staging()
    note = staging["notes"].get(note_id.strip())
    if not note:
        return f"No staged note with ID '{note_id}'. Call list_staged_notes() to see all IDs."
    if note["status"] == "approved":
        return f"'{note['title']}' is already approved."
    note["status"] = "approved"
    note["reject_reason"] = ""
    _save_staging(staging)
    return (
        f"✅ Approved: [{note_id}] {note['title']}\n"
        "Call commit_approved_notes() when all reviews are done."
    )
 
 
@mcp.tool()
def reject_staged_note(note_id: str, reason: str = "") -> str:
    """
    Reject a staged note. It will be skipped on commit and removed from staging.
 
    Args:
        note_id: The 8-character ID returned by stage_note().
        reason:  Optional explanation shown in list_staged_notes().
    """
    staging = _load_staging()
    note = staging["notes"].get(note_id.strip())
    if not note:
        return f"No staged note with ID '{note_id}'. Call list_staged_notes() to see all IDs."
    note["status"] = "rejected"
    note["reject_reason"] = reason.strip()
    _save_staging(staging)
    # Delete preview file from _staging/ if present
    if VAULT_ROOT:
        staging_dir = Path(VAULT_ROOT) / "_staging"
        if staging_dir.exists():
            for pf in staging_dir.glob(f"{note_id.strip()}_*.md"):
                try:
                    pf.unlink()
                except OSError:
                    pass
    return f"❌ Rejected: [{note_id}] {note['title']}" + (f"\n   Reason: {reason}" if reason else "")
 
 
@mcp.tool()
def commit_approved_notes() -> str:
    """
    Commit all approved staged notes:
      1. Write each note as a .md file in the vault.
      2. Upsert the note into Neo4j directly — no rebuild required.
      3. Remove committed and rejected notes from staging.
 
    Pending (not yet reviewed) notes are left in staging untouched.
    """
    if not VAULT_ROOT:
        return "VAULT_ROOT is not configured. Add VAULT_ROOT to the MCP server .env file."
 
    staging  = _load_staging()
    notes    = staging.get("notes", {})
 
    # Purge rejected notes regardless of whether anything is being committed
    rejected_ids = [nid for nid, n in list(notes.items()) if n["status"] == "rejected"]
    for nid in rejected_ids:
        del notes[nid]
 
    approved = [n for n in notes.values() if n["status"] == "approved"]
    if not approved:
        if rejected_ids:
            _save_staging(staging)
        pending = sum(1 for n in notes.values() if n["status"] == "pending")
        return (
            "No approved notes to commit."
            + (f" {pending} note(s) still pending review." if pending else "")
        )
 
    committed, skipped, errors = [], [], []
    db = _get_db()
 
    for note in approved:
        try:
            target = Path(VAULT_ROOT) / note["vault_relative_path"]
            if target.exists():
                skipped.append(f"  [{note['id']}] {note['title']} — file already exists")
                continue
 
            target.parent.mkdir(parents=True, exist_ok=True)
            # Move from _staging/ preview if available, otherwise write fresh
            _sd = Path(VAULT_ROOT) / "_staging"
            _pf = list(_sd.glob(f"{note['id']}_*.md")) if _sd.exists() else []
            if _pf:
                _pf[0].rename(target)
            else:
                target.write_text(note["content"], encoding="utf-8")
 
            props     = _note_props(note)
            wikilinks = _parse_wikilinks(note["content"])
            db.upsert_note_direct(props, wikilinks)
 
            committed.append(f"  [{note['id']}] {note['title']}  →  {note['vault_relative_path']}")
            del notes[note["id"]]
        except Exception as exc:
            errors.append(f"  [{note['id']}] {note['title']} — ERROR: {exc}")
 
    _save_staging(staging)
 
    lines = []
    if committed:
        lines.append(f"✅ Committed ({len(committed)}):")
        lines.extend(committed)
    if skipped:
        lines.append(f"\n⚠️  Skipped — already existed ({len(skipped)}):")
        lines.extend(skipped)
    if errors:
        lines.append(f"\n❌ Errors ({len(errors)}):")
        lines.extend(errors)
    pending_remaining = sum(1 for n in notes.values() if n["status"] == "pending")
    if pending_remaining:
        lines.append(f"\n⏳ {pending_remaining} note(s) still pending review.")
    return "\n".join(lines)
 
# =====================================================================================================
# Specification requirements tools — Flow → UseCase → Document → BR
# =====================================================================================================

@mcp.tool()
def get_use_cases(flow_name: str = "") -> str:
    """
    List all UseCases under a flow.

    Args:
        flow_name: The flow to query.
    """
    ucs = _get_db().get_use_cases(flow_name.strip())
    if not ucs:
        return f"No UseCases found for flow '{flow_name}'."
    lines = [f"UseCases for flow '{flow_name}' ({len(ucs)}):\n"]
    for uc in ucs:
        lines.append(f"  {uc['uc_id']}  (project: {uc.get('project_id', '?')})")
    return "\n".join(lines)


@mcp.tool()
def get_documents(uc_id: str, flow_name: str = "") -> str:
    """
    List all Documents (FDD, SDD, UC …) under a UseCase.

    Args:
        uc_id:     The UseCase ID, e.g. "UC36".
        flow_name: The flow name.
    """
    docs = _get_db().get_documents(uc_id.strip().upper(), flow_name.strip())
    if not docs:
        return f"No Documents found for {uc_id} in flow '{flow_name}'."
    lines = [f"Documents for {uc_id} / flow '{flow_name}':\n"]
    for d in docs:
        lines.append(f"  [{d['doc_type']}]  {d.get('source_file', '?')}")
    return "\n".join(lines)


@mcp.tool()
def get_requirements(flow_name: str = "") -> str:
    """
    List all BRs (business requirements) extracted from specification documents.
    Shows BR ID, UC, doc_type, title, and categories.

    Args:
        flow_name: Flow to filter by. Leave empty to return BRs across all flows.
    """
    brs = _get_db().get_requirements(flow_name.strip() if flow_name else None)
    if not brs:
        return f"No BRs found for flow '{flow_name}'."
    lines = [f"BRs ({len(brs)}) for flow '{flow_name}':\n"]
    for b in brs:
        cats = b.get("confirmed_categories") or b.get("candidate_categories") or "[]"
        lines.append(f"[{b['br_id']}] {b.get('uc_id','')}/{b.get('doc_type','')}  {b['title'][:75]}")
        if cats and cats != "[]":
            lines.append(f"    categories: {cats}")
    return "\n".join(lines)


@mcp.tool()
def get_requirement_detail(
    br_id:     str,
    uc_id:     str,
    doc_type:  str,
    flow_name: str = "",
) -> str:
    """
    Get the full body of a single BR node, including the parent Document context
    (intro/scope/background), affected fields, categories, and source file.

    Args:
        br_id:     The BR identifier, e.g. "BR03".
        uc_id:     The UseCase ID, e.g. "UC36".
        doc_type:  Document type: "FDD", "SDD", or "UC".
        flow_name: Flow the BR belongs to.
    """
    r = _get_db().get_requirement_detail(
        br_id.strip().upper(),
        uc_id.strip().upper(),
        doc_type.strip().upper(),
        flow_name.strip(),
    )
    if not r:
        return f"No BR found for {br_id} / {uc_id} / {doc_type} in flow '{flow_name}'."
    lines = [
        f"**[{r['br_id']}] {r['title']}**",
        f"UC: {r.get('uc_id','')}  |  doc_type: {r.get('doc_type','')}  |  "
        f"flow: {r.get('flow_name','')}  |  source: {r.get('source_file','')}",
    ]
    confirmed = r.get("confirmed_categories") or ""
    candidate = r.get("candidate_categories") or ""
    if confirmed and confirmed != "[]":
        lines.append(f"**Categories (confirmed):** {confirmed}")
    elif candidate and candidate != "[]":
        lines.append(f"**Categories (candidate):** {candidate}")
    if r.get("document_context"):
        lines += ["", "### Document Context (intro / scope / background)", r["document_context"]]
    if r.get("body"):
        lines += ["", "### Requirement Body", r["body"]]
    fields = r.get("affected_fields", "[]")
    if fields and fields != "[]":
        lines += ["", f"**Affected fields:** {fields}"]
    return "\n".join(lines)


@mcp.tool()
def assign_br_category(
    br_id:      str,
    uc_id:      str,
    doc_type:   str,
    flow_name:  str,
    categories: str,
) -> str:
    """
    Confirm the implementation category/categories for a BR node.
    Updates confirmed_categories, overwriting any previous value.

    Args:
        br_id:      The BR identifier, e.g. "BR04".
        uc_id:      The UseCase ID, e.g. "UC36".
        doc_type:   Document type: "FDD", "SDD", or "UC".
        flow_name:  The flow name.
        categories: Comma-separated category labels to assign.
    """
    cats = [c.strip() for c in categories.split(",") if c.strip()]
    with _get_db()._driver.session() as s:
        row = s.run(
            """
            MATCH (b:BR {br_id: $br_id, uc_id: $uc_id, doc_type: $doc_type, flow_name: $flow_name})
            SET b.confirmed_categories = $cats
            RETURN b.id AS id
            """,
            br_id=br_id.strip().upper(),
            uc_id=uc_id.strip().upper(),
            doc_type=doc_type.strip().upper(),
            flow_name=flow_name.strip(),
            cats=json.dumps(cats),
        ).single()
    if not row:
        return f"No BR found for {br_id} / {uc_id} / {doc_type} in flow '{flow_name}'."
    return f"✅ Set confirmed_categories = {cats} on {br_id} ({uc_id}/{doc_type}/{flow_name})."


# =====================================================================================================
# Entry point
# =====================================================================================================
 
if __name__ == "__main__":
    print(f"MCP server starting — SSE on http://{HOST}:{PORT}/sse")
    print(f"Neo4j: {NEO4J_URI}")
    mcp.run(transport="sse")
 
 