"""Work item attachments: listing, and text/image extraction for supported formats."""
from __future__ import annotations

import base64
import io
from typing import Any

from .client import AdoClient

IMAGE_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


# ── Document readers (imported lazily — heavy optional deps) ──────────────────


def read_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells)
            if row_text.strip(" |"):
                parts.append(row_text)
    return "\n".join(parts)


def read_xlsx(data: bytes) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in wb.worksheets:
        parts.append(f"=== Sheet: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            row_str = " | ".join(str(v) if v is not None else "" for v in row)
            if row_str.strip(" |"):
                parts.append(row_str)
    wb.close()
    return "\n".join(parts)


def read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"=== Page {i} ===")
            parts.append(text)
    return "\n".join(parts)


READERS = {"docx": read_docx, "xlsx": read_xlsx, "pdf": read_pdf}


# ── Attachment API ────────────────────────────────────────────────────────────


def _attachment_relations(client: AdoClient, item_id: int) -> list[dict[str, Any]]:
    """Return raw AttachedFile relations for a work item."""
    data = client.get(client.wi_url(f"workitems/{item_id}"), params={"$expand": "relations"})
    return [r for r in data.get("relations", []) if r.get("rel") == "AttachedFile"]


def list_attachments(client: AdoClient, item_id: int) -> list[dict[str, Any]]:
    results = []
    for rel in _attachment_relations(client, item_id):
        attrs = rel.get("attributes", {})
        results.append({
            "name": attrs.get("name", ""),
            "size_bytes": attrs.get("resourceSize"),
            "comment": attrs.get("comment", ""),
            "url": rel.get("url", ""),
        })
    return results


def read_attachment(client: AdoClient, item_id: int, filename: str) -> dict[str, Any]:
    """
    Download the first attachment whose name matches *filename* (case-insensitive)
    and return its extracted text content.  Supports .docx, .xlsx and .pdf.
    Images (png, jpg, jpeg, gif, webp) are returned as base64 under
    ``image_base64`` with their ``mime_type`` for the caller to emit as image content.
    """
    match = next(
        (r for r in _attachment_relations(client, item_id)
         if r.get("attributes", {}).get("name", "").lower() == filename.lower()),
        None,
    )
    if match is None:
        return {"error": f"No attachment named '{filename}' found on work item {item_id}."}

    name: str = match["attributes"]["name"]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in READERS and ext not in IMAGE_MIME_TYPES:
        return {
            "error": (
                f"Unsupported file type '.{ext}'. Supported: .docx, .xlsx, .pdf, "
                f"{', '.join('.' + e for e in IMAGE_MIME_TYPES)}."
            )
        }

    content = client.download(match["url"])
    if ext in IMAGE_MIME_TYPES:
        if len(content) > MAX_IMAGE_BYTES:
            return {
                "error": (
                    f"Image '{name}' is {len(content)} bytes, over the "
                    f"{MAX_IMAGE_BYTES}-byte limit."
                )
            }
        return {
            "name": name,
            "mime_type": IMAGE_MIME_TYPES[ext],
            "image_base64": base64.b64encode(content).decode("ascii"),
        }
    return {"name": name, "content": READERS[ext](content)}
