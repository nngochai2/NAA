import base64
import json

import httpx

from jira_mcp.tools.attachments import handle_attachment_tool

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _meta(**over):
    base = {
        "id": "10042",
        "filename": "screen shot.png",
        "mimeType": "image/png",
        "size": len(PNG),
        "author": {"displayName": "Jane"},
        "created": "2026-11-01T10:00:00.000+0000",
    }
    return {**base, **over}


def _jira(meta, body=b"", seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((str(request.url), request.headers.get("authorization")))
        if request.url.path.startswith("/jiradc/rest/api/2/attachment/"):
            return httpx.Response(200, json=meta)
        if request.url.path.startswith("/jiradc/secure/attachment/"):
            return httpx.Response(200, content=body)
        return httpx.Response(404, json={"errorMessages": ["nope"]})

    return handler


def test_list_attachments_returns_compact_summaries(make_client):
    def handler(request):
        return httpx.Response(
            200, json={"key": "PROJ-1", "fields": {"attachment": [_meta(content="http://x")]}}
        )

    result = handle_attachment_tool(
        "jira_list_attachments", {"issue_key": "PROJ-1"}, client=make_client(handler)
    )

    items = json.loads(result[0].text)
    assert items == [
        {
            "id": "10042",
            "filename": "screen shot.png",
            "mimeType": "image/png",
            "size": len(PNG),
            "author": "Jane",
            "created": "2026-11-01T10:00:00.000+0000",
        }
    ]


def test_list_attachments_empty_when_issue_has_none(make_client):
    handler = lambda r: httpx.Response(200, json={"key": "PROJ-1", "fields": {}})  # noqa: E731

    result = handle_attachment_tool(
        "jira_list_attachments", {"issue_key": "PROJ-1"}, client=make_client(handler)
    )

    assert json.loads(result[0].text) == []


def test_get_attachment_returns_image_content_for_png(make_client):
    seen = []
    client = make_client(_jira(_meta(), PNG, seen))

    result = handle_attachment_tool(
        "jira_get_attachment", {"attachment_id": "10042"}, client=client
    )

    assert result[1].type == "image"
    assert result[1].mimeType == "image/png"
    assert base64.b64decode(result[1].data) == PNG
    download_url, auth = seen[-1]
    assert (
        download_url
        == "https://insight.fsoft.com.vn/jiradc/secure/attachment/10042/screen%20shot.png"
    )
    assert auth == "Bearer test-token"


def test_get_attachment_rejects_oversized_image_without_downloading(make_client):
    seen = []
    client = make_client(_jira(_meta(size=6_000_000), PNG, seen))

    result = handle_attachment_tool(
        "jira_get_attachment", {"attachment_id": "10042"}, client=client
    )

    assert result[0].text.startswith("Error:")
    assert all("/secure/attachment/" not in url for url, _ in seen)


def test_get_attachment_aborts_when_download_exceeds_limit_despite_small_declared_size(make_client):
    client = make_client(_jira(_meta(size=10), b"\x00" * 6_000_000))

    result = handle_attachment_tool(
        "jira_get_attachment", {"attachment_id": "10042"}, client=client
    )

    assert result[0].text.startswith("Error:")
    assert "limit" in result[0].text


def test_get_attachment_returns_text_for_log_files(make_client):
    body = b"line1\nline2\n"
    client = make_client(
        _jira(_meta(filename="app.log", mimeType="application/octet-stream", size=len(body)), body)
    )

    result = handle_attachment_tool("jira_get_attachment", {"attachment_id": "1"}, client=client)

    assert result[-1].text == "line1\nline2\n"


def test_get_attachment_truncates_large_text(make_client):
    body = b"a" * 500
    client = make_client(_jira(_meta(filename="big.txt", mimeType="text/plain", size=500), body))

    result = handle_attachment_tool(
        "jira_get_attachment", {"attachment_id": "1", "max_bytes": 100}, client=client
    )

    assert result[-1].text.startswith("a" * 100)
    assert "truncated at 100 of 500 bytes" in result[-1].text


def test_get_attachment_reports_metadata_only_for_unsupported_types(make_client):
    seen = []
    client = make_client(
        _jira(_meta(filename="spec.pdf", mimeType="application/pdf"), b"%PDF", seen)
    )

    result = handle_attachment_tool("jira_get_attachment", {"attachment_id": "1"}, client=client)

    assert len(result) == 1
    assert json.loads(result[0].text)["filename"] == "spec.pdf"
    assert "note" in json.loads(result[0].text)
    assert all("/secure/attachment/" not in url for url, _ in seen)


def test_get_attachment_returns_error_text_on_404(make_client):
    client = make_client(
        lambda r: httpx.Response(404, json={"errorMessages": ["Attachment not found"]})
    )

    result = handle_attachment_tool("jira_get_attachment", {"attachment_id": "9"}, client=client)

    assert result[0].text.startswith("Error:")
    assert "Attachment not found" in result[0].text
