import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from codegraph_mcp import graph_client


class FakeGraph:
    """Stands in for graph_client.run_query: maps a Cypher string to canned rows."""

    def __init__(self):
        self.results: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, dict]] = []

    def on(self, cypher: str, rows: list[dict]):
        self.results[cypher] = rows
        return self

    def __call__(self, cypher: str, params: dict | None = None) -> list[dict]:
        self.calls.append((cypher, params or {}))
        return self.results.get(cypher, [])


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(graph_client, "run_query", fake)
    return fake


def type_row(name, pkg="com.acme"):
    return {"name": name, "fqn": f"{pkg}.{name}"}
