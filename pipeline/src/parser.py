import re
import hashlib
from collections.abc import Callable
from pathlib import Path
 
from models import Note, WikiLink
from config import (
    MAIN_FOLDER,
    TAGS_FOLDER,
    INCLUDE_FOLDERS,
    SUBFOLDER_TYPE_MAP,
    TYPE_SIGNALS,
    REL_KEYWORDS,
)
 
_DATE_LINE_RE    = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")   # YYYY-MM-DD
_DATE_LINE_RE_EU = re.compile(r"^(\d{2})-(\d{2})-(\d{4})\s+(\d{2}:\d{2})") # DD-MM-YYYY
_STATUS_RE       = re.compile(r"^Status:\s*#(\w+)", re.IGNORECASE)
_TAGS_START_RE   = re.compile(r"^Tags:\s*(.*)", re.IGNORECASE)
# (?<!!) excludes Obsidian image embeds: ![[image.png]]
# Group 1 is greedy ([^\]|#]+) so the full target name is always captured
_WIKILINK_RE     = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?\|?([^\]]*?)\]\]")
 
 
def infer_relationship(context: str) -> str:
    context = context.lower()
    for keyword, rel_type in REL_KEYWORDS.items():
        if keyword in context:
            return rel_type
    return "LINKS_TO"
 
 
def extract_wikilinks_from_text(text: str, is_tag_section: bool = False) -> list[WikiLink]:
    links = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        alias  = m.group(2).strip() or target
        start  = max(0, m.start() - 60)
        end    = min(len(text), m.end() + 60)
        ctx    = text[start:end].replace("\n", " ")
        rel    = "TAGGED_WITH" if is_tag_section else infer_relationship(ctx)
        links.append(WikiLink(target=target, alias=alias, context=ctx,
                              relationship=rel, is_tag_link=is_tag_section))
    return links
 
 
def parse_header(lines: list[str]) -> tuple[str, str, list[WikiLink], int]:
    """
    Parse custom Obsidian header (non-YAML).
 
    Returns:
    - created_at
    - status
    - tag_links
    - body_start_line_index (the first line that belongs to the body, not the header).
    """
    created_at    = ""
    status        = ""
    tag_links: list[WikiLink] = []
    in_tags_block = False
    last_i        = -1  # index of the last recognised header line; -1 = none found
    for i, line in enumerate(lines[:25]):
        stripped = line.strip()
        if not created_at:
            m = _DATE_LINE_RE.match(stripped)
            if m:
                created_at = f"{m.group(1)}T{m.group(2)}"
                last_i = i
                continue
            m = _DATE_LINE_RE_EU.match(stripped)
            if m:
                # Normalise DD-MM-YYYY → YYYY-MM-DD
                created_at = f"{m.group(3)}-{m.group(2)}-{m.group(1)}T{m.group(4)}"
                last_i = i
                continue
        if not status:
            m = _STATUS_RE.match(stripped)
            if m:
                status        = m.group(1)
                in_tags_block = False
                last_i = i
                continue
        # Check for "Tags:" line which marks the start of the tags section
        m = _TAGS_START_RE.match(line)
        if m:
            in_tags_block = True
            last_i = i
            # Extract any inline tags on the same line as "Tags:"
            inline = m.group(1).strip()
            if inline:
                tag_links.extend(extract_wikilinks_from_text(inline, is_tag_section=True))
            continue
        # Continue parsing tags block: either wiki links or indented lines
        if in_tags_block:
            # Tags continue if line starts with [[ or is indented (and non-empty)
            if stripped.startswith("[[") or (line.startswith((" ", "\t")) and stripped):
                tag_links.extend(extract_wikilinks_from_text(stripped, is_tag_section=True))
            last_i = i
            continue
        else:
            # End of tags block when we hit a non-indented, non-link line
            in_tags_block = False
    # last_i + 1 is the first body line (0 when no header fields were found)
    return created_at, status, tag_links, last_i + 1
 
 
def classify_note(
    title: str,
    subfolder: str,
    body: str,
    llm_classifier: Callable[[str, str], str] | None = None,
) -> str:
    # 1 — subfolder name is the strongest signal
    note_type = SUBFOLDER_TYPE_MAP.get(subfolder.lower(), "")
    if note_type:
        return note_type
    # 2 — keyword scoring over title + first 400 chars of body
    combined = (title + " " + body[:400]).lower()
    scores: dict[str, int] = {t: 0 for t in TYPE_SIGNALS}
    for ntype, keywords in TYPE_SIGNALS.items():
        for kw in keywords:
            if kw in combined:
                scores[ntype] += 1
    best = max(scores, key=scores.__getitem__)
    if scores[best] > 0:
        return best
    # 3 — LLM fallback (only when caller supplies a classifier)
    if llm_classifier is not None:
        return llm_classifier(title, body)
    return "NOTE"
 
 
def parse_note(
    path: Path,
    vault_root: Path,
    folder_hint: str,
    llm_classifier: Callable[[str, str], str] | None = None,
) -> Note:
    # Read file content with fallback for encoding errors
    raw    = path.read_text(encoding="utf-8", errors="replace")
    lines  = raw.splitlines()
   
    # Parse custom header to extract metadata (created_at, status, tags)
    # header_end marks where the body content begins
    created_at, status, tag_links, header_end = parse_header(lines)
   
    # Extract body content (everything after header)
    body       = "\n".join(lines[header_end:])
   
    # Parse wiki links from body; note that tag links are already captured in header
    body_links = extract_wikilinks_from_text(body, is_tag_section=False)
   
    # Use filename as note title (without extension)
    title      = path.stem
   
    # Determine note type using subfolder hint, content signal matching, or LLM fallback
    note_type  = classify_note(title, folder_hint, body, llm_classifier)
   
    # Combine tag links from header with wiki links from body
    # Order matters: header tags typically have higher priority
    return Note(
        path         = path.relative_to(vault_root),
        title        = title,
        note_type    = note_type,
        subfolder    = folder_hint,
        status       = status,
        created_at   = created_at,
        links        = tag_links + body_links,
        content_hash = hashlib.md5(raw.encode()).hexdigest(),
        word_count   = len(body.split()),
        body         = body[:5000],  # Truncate to 5000 chars to avoid storing large content
    )
 
 
def parse_tag_note(path: Path, vault_root: Path) -> Note:
    """Tags folder notes are pure hub nodes — title only."""
    return Note(
        path         = path.relative_to(vault_root),
        title        = path.stem,
        note_type    = "TAG",
        content_hash = hashlib.md5(path.stem.encode()).hexdigest(),
    )
 
 
def get_folder_hint(path: Path, vault_root: Path) -> str:
    """
    Return the direct parent folder name of *path* relative to MAIN_FOLDER.
    Using the immediate parent (rather than the top-level folder) gives the
    most specific signal for SUBFOLDER_TYPE_MAP classification.
 
    Examples (MAIN_FOLDER = '6 - Main Notes'):
      RAS/Tasks/note.md          -> 'Tasks'
      RAS/Knowledge/EInvoice/n.md-> 'EInvoice'
      Java/note.md               -> 'Java'
      6 - Main Notes/orphan.md   -> ''
    """
    try:
        rel = path.relative_to(vault_root / MAIN_FOLDER)
        # rel.parts[-1] is the filename; rel.parts[-2] is its direct parent folder
        return rel.parts[-2] if len(rel.parts) > 1 else ""
    except ValueError:
        return ""
 
 
def resolve_backlinks(notes: list[Note]) -> None:
    title_map = {n.title.lower(): n for n in notes}
    for note in notes:
        for link in note.links:
            resolved = title_map.get(link.target.lower())
            if resolved and resolved is not note:  # skip self-links
                link.target = resolved.title
                if note.title not in resolved.backlinks:
                    resolved.backlinks.append(note.title)
 
 
def scan_vault(
    vault_root: Path,
    llm_classifier: Callable[[str, str], str] | None = None,
) -> tuple[list[Note], list[str], int]:
    """
    Walk *vault_root* and parse every .md file whose path starts with one of
    the prefixes in INCLUDE_FOLDERS (or lives under TAGS_FOLDER).
 
    Returns (notes, errors, skipped_count).  No Rich output — callers add UI.
    Pass llm_classifier to enable LLM fallback for unrecognised notes.
    """
    notes:   list[Note] = []
    errors:  list[str]  = []
    skipped: int        = 0
    _include_parts = [tuple(folder.split("/")) for folder in INCLUDE_FOLDERS]
    for f in vault_root.rglob("*.md"):
        rel_parts  = f.relative_to(vault_root).parts
        top_folder = rel_parts[0] if rel_parts else ""
        included = top_folder == TAGS_FOLDER or any(
            rel_parts[:len(fp)] == fp for fp in _include_parts
        )
        if any(p.startswith(".") for p in rel_parts) or not included:
            skipped += 1
            continue
        try:
            if top_folder == TAGS_FOLDER:
                notes.append(parse_tag_note(f, vault_root))
            else:
                hint = get_folder_hint(f, vault_root)
                notes.append(parse_note(f, vault_root, hint, llm_classifier))
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    return notes, errors, skipped
 
 