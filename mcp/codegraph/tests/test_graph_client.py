from unittest.mock import MagicMock, patch

import pytest

from codegraph_mcp import graph_client
from codegraph_mcp.config import get_config


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(graph_client, "_driver", None)
    get_config.cache_clear()
    yield monkeypatch
    get_config.cache_clear()


@pytest.mark.parametrize("password, expected_auth", [("", None), ("pw", ("neo4j", "pw"))])
def test_driver_auth_is_optional(fresh, password, expected_auth):
    fresh.setenv("NEO4J_URI", "bolt://cg:7688")
    fresh.setenv("NEO4J_USER", "neo4j")
    fresh.setenv("NEO4J_PASSWORD", password)
    with patch.object(graph_client, "GraphDatabase") as gd:
        driver = graph_client.get_driver()
        assert graph_client.get_driver() is driver  # cached
    gd.driver.assert_called_once_with("bolt://cg:7688", auth=expected_auth)
    driver.verify_connectivity.assert_called_once()


def test_connection_failure_is_not_cached():
    with patch.object(graph_client, "GraphDatabase") as gd:
        gd.driver.return_value.verify_connectivity.side_effect = OSError("refused")
        with pytest.raises(OSError):
            graph_client.get_driver()
        with pytest.raises(OSError):  # retried, not served from cache
            graph_client.get_driver()
    assert graph_client._driver is None
    assert gd.driver.return_value.close.call_count == 2


def test_run_query_returns_record_data(fresh):
    record = MagicMock()
    record.data.return_value = {"fqn": "a.B"}
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value.run.return_value = [record]
    fresh.setattr(graph_client, "_driver", driver)

    assert graph_client.run_query("MATCH (n) RETURN n") == [{"fqn": "a.B"}]
    driver.session.return_value.__enter__.return_value.run.assert_called_once_with(
        "MATCH (n) RETURN n", {}
    )


def test_close_resets_driver(fresh):
    driver = MagicMock()
    fresh.setattr(graph_client, "_driver", driver)
    graph_client.close()
    driver.close.assert_called_once()
    assert graph_client._driver is None
