import httpx
import pytest

from jira_mcp.auth import MissingCredentialsError, resolve_client_from_headers
from jira_mcp.config import JiraConfig


@pytest.fixture
def base_config():
    return JiraConfig(url="https://insight.fsoft.com.vn/jiradc", project_key="PROJ", ssl_verify=True)


def test_resolve_client_from_headers_with_valid_bearer_wires_token_and_base_url(base_config):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth_header"] = request.headers.get("authorization")
        return httpx.Response(200, json={"key": "PROJ-1", "fields": {}})

    client = resolve_client_from_headers(
        {"authorization": "Bearer jdoe-token"}, base_config, transport=httpx.MockTransport(handler)
    )
    client.get_issue("PROJ-1")

    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/PROJ-1"
    assert captured["auth_header"] == "Bearer jdoe-token"


def test_resolve_client_from_headers_scheme_is_case_insensitive(base_config):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth_header"] = request.headers.get("authorization")
        return httpx.Response(200, json={"key": "PROJ-1", "fields": {}})

    client = resolve_client_from_headers(
        {"authorization": "bearer jdoe-token"}, base_config, transport=httpx.MockTransport(handler)
    )
    client.get_issue("PROJ-1")

    assert captured["auth_header"] == "Bearer jdoe-token"


def test_resolve_client_from_headers_missing_authorization_raises(base_config):
    with pytest.raises(MissingCredentialsError):
        resolve_client_from_headers({}, base_config)


def test_resolve_client_from_headers_wrong_scheme_raises(base_config):
    with pytest.raises(MissingCredentialsError):
        resolve_client_from_headers({"authorization": "Basic jdoe-token"}, base_config)


def test_resolve_client_from_headers_empty_token_raises(base_config):
    with pytest.raises(MissingCredentialsError):
        resolve_client_from_headers({"authorization": "Bearer "}, base_config)
