import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import pytest

from jenkins_mcp.client import JenkinsClient


@pytest.fixture
def make_client():
    """Build a JenkinsClient wired to a fake Jenkins via httpx.MockTransport."""

    def _make(handler) -> JenkinsClient:
        return JenkinsClient(
            base_url="https://ci.example.com/jenkins",
            authorization="Basic dGVzdDp0b2tlbg==",
            transport=httpx.MockTransport(handler),
        )

    return _make
