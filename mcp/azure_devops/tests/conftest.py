import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import pytest

from ado_mcp.client import AdoClient

BASE = "http://ado.local/DefaultCollection"


class FakeAdo:
    """Route table for httpx.MockTransport: {(method, path): response}."""

    def __init__(self):
        self.routes: dict[tuple[str, str], httpx.Response] = {}
        self.requests: list[httpx.Request] = []

    def add(self, method, path, json_body=None, status=200, content=None):
        if content is None:
            content = json.dumps(json_body or {}).encode()
        self.routes[(method, path)] = httpx.Response(status, content=content)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, text=f"no route for {key}")
        return self.routes[key]


@pytest.fixture
def ado():
    return FakeAdo()


@pytest.fixture
def client(ado):
    return AdoClient(BASE, "Proj", "DOMAIN\\user", "pw", "5.0", transport=httpx.MockTransport(ado))


def wi_path(suffix: str) -> str:
    return f"/DefaultCollection/Proj/_apis/wit/{suffix}"
