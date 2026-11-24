"""Staging store for notes awaiting human review, plus note-parsing helpers
used when committing approved notes directly into Neo4j."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .config import get_config

# ── Staging store ─────────────────────────────────────────────────────────────


def load_staging() -> dict:
    path = get_config().staging_file
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"notes": {}}


def save_staging(data: dict) -> None:
    get_config().staging_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def staging_dir() -> Path | None:
    """VAULT_ROOT/_staging, where preview files are written for review in Obsidian."""
    vault_root = get_config().vault_root
    return Path(vault_root) / "_staging" if vault_root else None


# ── Note parsing ──────────────────────────────────────────────────────────────

_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?\|?([^\]]*?)\]\]")
_TAGS_LINE_RE = re.compile(r"^Tags:\s*", re.IGNORECASE)
HEADER_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}")

MAX_BODY_CHARS = 5000


def parse_wikilinks(content: str) -> list[dict]:
    """Extract [[WikiLinks]] from note content."""
    links = []
    for m in _WIKILINK_RE.finditer(content):
        target = m.group(1).strip()
        alias = m.group(2).strip() or target
        start = max(0, m.start() - 80)
        end = min(len(content), m.end() + 80)
        ctx = content[start:end].replace("\n", " ")
        line_start = content.rfind("\n", 0, m.start()) + 1
        on_tags_line = _TAGS_LINE_RE.match(content[line_start:m.start() + 1])
        rel = "TAGGED_WITH" if on_tags_line else "LINKS_TO"
        links.append({"target": target, "alias": alias, "context": ctx, "relationship": rel})
    return links


def extract_body(content: str) -> str:
    """Return everything from the first H1 heading onwards, capped at 5000 chars."""
    for i, line in enumerate(content.splitlines()):
        if line.startswith("# "):
            body = "\n".join(content.splitlines()[i:])
            return body[:MAX_BODY_CHARS]
    return content[:MAX_BODY_CHARS]


def note_props(staged: dict) -> dict:
    """Build the Neo4j property dict from a staged note entry."""
    path = staged["vault_relative_path"].replace("\\", "/")
    parts = Path(path).parts
    subfolder = parts[-2] if len(parts) >= 2 else ""
    body = extract_body(staged["content"])
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
