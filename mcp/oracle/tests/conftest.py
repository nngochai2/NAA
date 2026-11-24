"""All Oracle connectivity is mocked — no live database or Instant Client required."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Minimal env before the package builds its config (load_dotenv never overrides these).
os.environ.setdefault("ORACLE_USER", "test_user")
os.environ.setdefault("ORACLE_PASSWORD", "test_pass")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_HOST", "localhost")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("MAX_ROWS", "50")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oracle_mcp.config import get_config  # noqa: E402


@pytest.fixture
def config(monkeypatch):
    """Override env vars for one test: config(ORACLE_DEFAULT_SCHEMA="X")."""

    def _set(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_config.cache_clear()
        return get_config()

    yield _set
    get_config.cache_clear()


@pytest.fixture
def cursor():
    """A mock cursor wired into a patched db.conn() context manager."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    with patch("oracle_mcp.db.conn") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = mock_conn
        mock_ctx.return_value.__exit__.return_value = False
        yield mock_cursor
