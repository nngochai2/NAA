import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock

import pytest

from knowledge_graph_mcp import app
from knowledge_graph_mcp.config import get_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point staging and the vault at a temp dir; never touch a real .env."""
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_ROOT", str(vault))
    monkeypatch.setenv("STAGING_FILE", str(tmp_path / "staged_notes.json"))
    get_config.cache_clear()
    yield vault
    get_config.cache_clear()


@pytest.fixture
def vault(isolated_config):
    return isolated_config


@pytest.fixture
def db(monkeypatch):
    """Replace the lazy Neo4j client with a MagicMock."""
    fake = MagicMock()
    monkeypatch.setattr(app, "_db", fake)
    return fake


VALID_NOTE = """01-01-2026 09:00

Status: #Done

Tags: [[Billing]]

# Invoice Numbering

Invoices are numbered per [[Tenant]] and reference [[Tax Rules|tax]].
"""
