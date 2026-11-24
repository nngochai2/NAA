from unittest.mock import MagicMock, patch

from knowledge_graph_mcp.neo4j_client import Neo4jClient


def _client_with_row(row):
    with patch("knowledge_graph_mcp.neo4j_client.GraphDatabase") as gd:
        client = Neo4jClient("bolt://x", "u", "p")
    session = gd.driver.return_value.session.return_value.__enter__.return_value
    session.run.return_value.single.return_value = row
    return client, session


def test_set_br_categories_serialises_list_and_reports_match():
    client, session = _client_with_row(MagicMock())
    assert client.set_br_categories("BR1", "UC1", "FDD", "flow", ["A", "B"]) is True
    kwargs = session.run.call_args.kwargs
    assert kwargs["cats"] == '["A", "B"]'
    assert kwargs["br_id"] == "BR1" and kwargs["flow_name"] == "flow"


def test_set_br_categories_no_match():
    client, _ = _client_with_row(None)
    assert client.set_br_categories("BR1", "UC1", "FDD", "flow", []) is False
