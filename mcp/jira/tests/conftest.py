import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import pytest

from jira_mcp.client import JiraClient


@pytest.fixture
def make_client():
    """Build a JiraClient wired to a fake Jira via httpx.MockTransport."""

    def _make(handler) -> JiraClient:
        return JiraClient(
            base_url="https://insight.fsoft.com.vn/jiradc",
            token="test-token",
            transport=httpx.MockTransport(handler),
        )

    return _make
