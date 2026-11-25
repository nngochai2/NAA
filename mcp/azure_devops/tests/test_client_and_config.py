import httpx
import pytest
from conftest import BASE, wi_path

from ado_mcp.config import get_config


@pytest.fixture
def env(monkeypatch):
    for key in (
        "ADO_BASE_URL",
        "ADO_PROJECT",
        "ADO_USERNAME",
        "ADO_PASSWORD",
        "ADO_API_VERSION",
        "MCP_HOST",
        "MCP_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(__import__("tempfile").gettempdir())  # no stray .env
    get_config.cache_clear()
    yield monkeypatch
    get_config.cache_clear()


def test_config_reports_missing_vars(env):
    env.setenv("ADO_BASE_URL", "http://x")
    with pytest.raises(OSError, match="ADO_PROJECT, ADO_USERNAME, ADO_PASSWORD"):
        get_config()


def test_config_defaults_and_blank_values(env):
    for key, value in {
        "ADO_BASE_URL": "http://x/Coll/",
        "ADO_PROJECT": "P",
        "ADO_USERNAME": "u",
        "ADO_PASSWORD": "p",
        "ADO_API_VERSION": "",
        "MCP_PORT": "",
    }.items():
        env.setenv(key, value)
    cfg = get_config()
    assert cfg.base_url == "http://x/Coll"
    assert cfg.api_version == "5.0"  # blank in .env falls back to the default
    assert cfg.port == 8004  # matches meta.yml
    assert cfg.host == "0.0.0.0"


def test_get_adds_api_version_and_json_headers(client, ado):
    ado.add("GET", wi_path("workitems/1"), {"id": 1})
    assert client.get(client.wi_url("workitems/1"), params={"$expand": "all"}) == {"id": 1}
    req = ado.requests[-1]
    assert str(req.url).startswith(f"{BASE}/Proj/_apis/wit/workitems/1?")
    assert req.url.params["api-version"] == "5.0"
    assert req.url.params["$expand"] == "all"
    assert req.headers["accept"] == "application/json"


def test_post_sends_json_body(client, ado):
    ado.add("POST", wi_path("wiql"), {"workItems": []})
    client.post(client.wi_url("wiql"), body={"query": "q"}, params={"$top": 5})
    req = ado.requests[-1]
    assert req.content == b'{"query":"q"}'
    assert req.url.params["$top"] == "5"


def test_download_returns_bytes_without_json_headers(client, ado):
    ado.add("GET", "/DefaultCollection/_apis/wit/attachments/abc", content=b"\x89PNG")
    assert client.download(f"{BASE}/_apis/wit/attachments/abc") == b"\x89PNG"
    assert "content-type" not in ado.requests[-1].headers


def test_http_errors_raise(client, ado):
    ado.add("GET", wi_path("workitems/9"), status=500)
    with pytest.raises(httpx.HTTPStatusError):
        client.get(client.wi_url("workitems/9"))
