import asyncio
import base64
import io
import json

import pytest
from conftest import BASE, wi_path

from ado_mcp import attachments
from ado_mcp.server import list_tools
from ado_mcp.tools import handle_tool

ATTACHMENT_PATH = "/DefaultCollection/_apis/wit/attachments/{}"


def _with_attachments(ado, *files):
    """Register a work item 5 with AttachedFile relations and their download bodies."""
    relations = [{"rel": "System.LinkTypes.Related", "url": f"{BASE}/_apis/wit/workitems/6"}]
    for i, (name, body) in enumerate(files):
        relations.append(
            {
                "rel": "AttachedFile",
                "url": f"{BASE}/_apis/wit/attachments/{i}",
                "attributes": {"name": name, "resourceSize": len(body), "comment": f"c{i}"},
            }
        )
        ado.add("GET", ATTACHMENT_PATH.format(i), content=body)
    ado.add("GET", wi_path("workitems/5"), {"relations": relations})


def _docx_bytes():
    from docx import Document

    doc = Document()
    doc.add_paragraph("Requirement BR01")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Field"
    table.rows[0].cells[1].text = "VAT"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _xlsx_bytes():
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Rates"
    wb.active.append(["code", "rate"])
    wb.active.append(["STD", 20])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── attachments ───────────────────────────────────────────────────────────────


def test_list_attachments_only_returns_attached_files(client, ado):
    _with_attachments(ado, ("spec.docx", b"x"))
    assert attachments.list_attachments(client, 5) == [
        {
            "name": "spec.docx",
            "size_bytes": 1,
            "comment": "c0",
            "url": f"{BASE}/_apis/wit/attachments/0",
        }
    ]
    assert ado.requests[-1].url.params["$expand"] == "relations"


def test_read_docx_case_insensitive_match(client, ado):
    _with_attachments(ado, ("Spec.DOCX", _docx_bytes()))
    result = attachments.read_attachment(client, 5, "spec.docx")
    assert result == {"name": "Spec.DOCX", "content": "Requirement BR01\nField | VAT"}


def test_read_xlsx(client, ado):
    _with_attachments(ado, ("rates.xlsx", _xlsx_bytes()))
    content = attachments.read_attachment(client, 5, "rates.xlsx")["content"]
    assert content == "=== Sheet: Rates ===\ncode | rate\nSTD | 20"


def test_read_pdf_without_text_layer_returns_empty(client, ado):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    _with_attachments(ado, ("scan.pdf", buf.getvalue()))
    assert attachments.read_attachment(client, 5, "scan.pdf") == {"name": "scan.pdf", "content": ""}


def test_read_image_returns_base64(client, ado):
    _with_attachments(ado, ("shot.PNG", b"\x89PNGdata"))
    result = attachments.read_attachment(client, 5, "shot.png")
    assert result["mime_type"] == "image/png"
    assert base64.b64decode(result["image_base64"]) == b"\x89PNGdata"


def test_image_over_limit_is_rejected(client, ado, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_IMAGE_BYTES", 4)
    _with_attachments(ado, ("big.jpg", b"12345"))
    assert "over the 4-byte limit" in attachments.read_attachment(client, 5, "big.jpg")["error"]


@pytest.mark.parametrize(
    "files, filename, expected",
    [
        ((("notes.txt", b"x"),), "notes.txt", "Unsupported file type '.txt'"),
        ((("Makefile", b"x"),), "Makefile", "Unsupported file type '.'"),
        ((), "missing.docx", "No attachment named 'missing.docx' found on work item 5"),
    ],
)
def test_read_attachment_errors_do_not_download(client, ado, files, filename, expected):
    _with_attachments(ado, *files)
    assert expected in attachments.read_attachment(client, 5, filename)["error"]
    assert all("/attachments/" not in r.url.path for r in ado.requests)


# ── tool dispatch ─────────────────────────────────────────────────────────────


def _call(client, name, args):
    return asyncio.run(handle_tool(client, name, args))


def test_list_tools():
    names = [t.name for t in asyncio.run(list_tools())]
    assert names == [
        "get_work_item",
        "search_work_items",
        "get_work_item_comments",
        "get_related_items",
        "list_work_item_attachments",
        "read_work_item_attachment",
    ]


def test_image_attachment_becomes_image_content(client, ado):
    _with_attachments(ado, ("shot.png", b"img"))
    args = {"item_id": "5", "filename": "shot.png"}
    text, image = _call(client, "read_work_item_attachment", args)
    assert text.text == "Image attachment: shot.png"
    assert image.type == "image" and image.mimeType == "image/png"


def test_search_top_is_capped_at_50(client, ado):
    ado.add("POST", wi_path("wiql"), {"workItems": []})
    [content] = _call(client, "search_work_items", {"where_clause": "1=1", "top": 500})
    assert json.loads(content.text) == []
    assert ado.requests[-1].url.params["$top"] == "50"


def test_http_error_is_reported_as_json(client, ado):
    ado.add("GET", wi_path("workitems/1"), status=403, content=b"Forbidden")
    [content] = _call(client, "get_work_item", {"item_id": 1})
    assert json.loads(content.text) == {"error": "ADO API error 403: Forbidden"}


def test_unknown_tool_and_bad_arguments(client):
    [unknown] = _call(client, "nope", {})
    assert json.loads(unknown.text) == {"error": "Unknown tool: nope"}
    [bad] = _call(client, "get_work_item", {})
    assert json.loads(bad.text) == {"error": "'item_id'"}
