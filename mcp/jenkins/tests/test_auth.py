import httpx
import pytest

from jenkins_mcp.auth import MissingCredentialsError, resolve_client_from_headers
from jenkins_mcp.config import JenkinsConfig


@pytest.fixture
def base_config():
    return JenkinsConfig(url="https://ci.example.com/jenkins", ssl_verify=True, timeout=5.0)


@pytest.mark.parametrize("header,expected", [
    ("Basic dTp0", "Basic dTp0"),
    ("basic dTp0", "Basic dTp0"),
    ("Bearer tok", "Bearer tok"),
])
def test_resolve_client_forwards_member_credentials(base_config, header, expected):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={})

    client = resolve_client_from_headers({"authorization": header}, base_config, transport=httpx.MockTransport(handler))
    client.get_json("")

    assert captured["auth"] == expected
    assert captured["url"].startswith("https://ci.example.com/jenkins/api/json")


@pytest.mark.parametrize("headers", [{}, {"authorization": ""}, {"authorization": "Basic"}, {"authorization": "Digest x"}])
def test_resolve_client_rejects_missing_or_unsupported_credentials(base_config, headers):
    with pytest.raises(MissingCredentialsError):
        resolve_client_from_headers(headers, base_config)
