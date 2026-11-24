"""Note authoring tools — "growing" the knowledge graph.

Notes are staged for human review, approved or rejected, and then committed:
written into the vault and upserted directly into Neo4j.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path

from mcp.types import ToolAnnotations

from ..app import get_db, mcp
from ..config import get_config
from ..staging import (
    HEADER_DATE_RE,
    MAX_BODY_CHARS,
    extract_body,
    load_staging,
    note_props,
    parse_wikilinks,
    save_staging,
    staging_dir,
)

STAGEABLE_TYPES = {"ARCHITECTURE", "CONVENTION", "TASK", "BUSINESS_TERM", "NOTE"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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

    results = get_db().find_coverage(concept_list)
    lines = [f"Gap analysis for {len(results)} concept(s):\n"]
    for r in results:
        gap_label = {"full": "FULL GAP", "partial": "PARTIAL", "covered": "covered"}[r["gap_type"]]
        lines.append(f"[{gap_label}] {r['concept']}")
        for note in r["existing"]:
            summary = note["summary"][:80] if note.get("summary") else "no summary"
            lines.append(
                f"    → '{note['title']}' [{note['type']}] "
                f"{note['word_count']} words — {summary}"
            )
        if not r["existing"]:
            lines.append("    → (nothing found in graph)")
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_all_note_titles() -> str:
    """
    Return every note title currently in the graph, one per line.
    Use this when composing new notes so you can add valid [[WikiLinks]] —
    only link to titles that actually exist in this list.
    """
    titles = get_db().get_all_note_titles()
    if not titles:
        return "Graph is empty."
    return f"{len(titles)} note titles:\n\n" + "\n".join(titles)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
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
    nt = note_type.strip().upper()
    if nt not in STAGEABLE_TYPES:
        return f"Invalid note_type '{note_type}'. Valid: {', '.join(sorted(STAGEABLE_TYPES))}"

    clean = vault_relative_path.replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        return "Invalid path: '..' is not allowed."
    if not clean.endswith(".md"):
        return "vault_relative_path must end with .md"

    if not HEADER_DATE_RE.match(content.lstrip()):
        today = date.today().strftime("%d-%m-%Y")
        return (
            f"Content must start with a date header. Example:\n"
            f"  {today} 09:00\n\n  Status: #Done\n\n  Tags: [[YourTag]]\n\n  # {title}"
        )

    body = extract_body(content)
    if len(body) > MAX_BODY_CHARS:
        return (
            f"Body is {len(body)} characters. "
            "The build pipeline truncates at 5000 — split into smaller notes."
        )

    note_id = uuid.uuid4().hex[:8]
    staging = load_staging()
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
    save_staging(staging)

    # Write preview file to VAULT_ROOT/_staging/ for review in Obsidian
    preview_path: str | None = None
    preview_dir = staging_dir()
    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title.strip())
        preview_file = preview_dir / f"{note_id}_{safe_title}.md"
        try:
            preview_file.write_text(content, encoding="utf-8")
            preview_path = f"_staging/{note_id}_{safe_title}.md"
        except OSError:
            pass

    links = parse_wikilinks(content)
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_staged_notes(show_content: bool = False) -> str:
    """
    List all staged notes and their current status (pending / approved / rejected).

    Args:
        show_content: If True, include the first 20 lines of each note's content.
    """
    notes = load_staging().get("notes", {})
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def approve_staged_note(note_id: str) -> str:
    """
    Approve a staged note so it will be written and indexed on the next commit.
    Call commit_approved_notes() when all reviews are done.

    Args:
        note_id: The 8-character ID returned by stage_note().
    """
    staging = load_staging()
    note = staging["notes"].get(note_id.strip())
    if not note:
        return f"No staged note with ID '{note_id}'. Call list_staged_notes() to see all IDs."
    if note["status"] == "approved":
        return f"'{note['title']}' is already approved."
    note["status"] = "approved"
    note["reject_reason"] = ""
    save_staging(staging)
    return (
        f"✅ Approved: [{note_id}] {note['title']}\n"
        "Call commit_approved_notes() when all reviews are done."
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def reject_staged_note(note_id: str, reason: str = "") -> str:
    """
    Reject a staged note. It will be skipped on commit and removed from staging.

    Args:
        note_id: The 8-character ID returned by stage_note().
        reason:  Optional explanation shown in list_staged_notes().
    """
    staging = load_staging()
    note = staging["notes"].get(note_id.strip())
    if not note:
        return f"No staged note with ID '{note_id}'. Call list_staged_notes() to see all IDs."
    note["status"] = "rejected"
    note["reject_reason"] = reason.strip()
    save_staging(staging)
    # Delete preview file from _staging/ if present
    preview_dir = staging_dir()
    if preview_dir and preview_dir.exists():
        for pf in preview_dir.glob(f"{note_id.strip()}_*.md"):
            try:
                pf.unlink()
            except OSError:
                pass
    suffix = f"\n   Reason: {reason}" if reason else ""
    return f"❌ Rejected: [{note_id}] {note['title']}{suffix}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def commit_approved_notes() -> str:
    """
    Commit all approved staged notes:
      1. Write each note as a .md file in the vault.
      2. Upsert the note into Neo4j directly — no rebuild required.
      3. Remove committed and rejected notes from staging.

    Pending (not yet reviewed) notes are left in staging untouched.
    """
    vault_root = get_config().vault_root
    if not vault_root:
        return "VAULT_ROOT is not configured. Add VAULT_ROOT to the MCP server .env file."

    staging = load_staging()
    notes   = staging.get("notes", {})

    # Purge rejected notes regardless of whether anything is being committed
    rejected_ids = [nid for nid, n in list(notes.items()) if n["status"] == "rejected"]
    for nid in rejected_ids:
        del notes[nid]

    approved = [n for n in notes.values() if n["status"] == "approved"]
    if not approved:
        if rejected_ids:
            save_staging(staging)
        pending = sum(1 for n in notes.values() if n["status"] == "pending")
        return (
            "No approved notes to commit."
            + (f" {pending} note(s) still pending review." if pending else "")
        )

    committed, skipped, errors = [], [], []
    db = get_db()
    preview_dir = staging_dir()

    for note in approved:
        try:
            target = Path(vault_root) / note["vault_relative_path"]
            if target.exists():
                skipped.append(f"  [{note['id']}] {note['title']} — file already exists")
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            # Move from _staging/ preview if available, otherwise write fresh
            previews = list(preview_dir.glob(f"{note['id']}_*.md")) if preview_dir.exists() else []
            if previews:
                previews[0].rename(target)
            else:
                target.write_text(note["content"], encoding="utf-8")

            db.upsert_note_direct(note_props(note), parse_wikilinks(note["content"]))

            committed.append(f"  [{note['id']}] {note['title']}  →  {note['vault_relative_path']}")
            del notes[note["id"]]
        except Exception as exc:
            errors.append(f"  [{note['id']}] {note['title']} — ERROR: {exc}")

    save_staging(staging)

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
