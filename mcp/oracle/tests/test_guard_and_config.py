"""SQL guard, schema helpers, configuration and connection helpers."""
from unittest.mock import MagicMock, patch

import oracledb
import pytest

from oracle_mcp import db
from oracle_mcp.guard import guard, resolve_schema, schema_in_clause

# ── SQL guard ─────────────────────────────────────────────────────────────────


def test_select_allowed():
    guard("SELECT * FROM dual")  # should not raise


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET x=1",
    "DELETE FROM t",
    "MERGE INTO t USING s ON (1=1)",
    "DROP TABLE t",
    "CREATE TABLE t (id NUMBER)",
    "ALTER TABLE t ADD col VARCHAR2(10)",
    "TRUNCATE TABLE t",
    "GRANT SELECT ON t TO user2",
    "EXEC my_proc",
    "BEGIN my_proc; END;",
    "COMMIT",
    "ROLLBACK",
    "  \n  DELETE FROM invoices",          # leading whitespace
    "SELECT 1 FROM dual\nDELETE FROM t",   # mutating statement on a later line
])
def test_mutating_blocked(sql):
    with pytest.raises(ValueError, match="Only SELECT"):
        guard(sql)


# ── schema helpers ────────────────────────────────────────────────────────────


def test_resolve_schema_explicit():
    assert resolve_schema("myschema") == "MYSCHEMA"


def test_resolve_schema_default(config):
    config(ORACLE_DEFAULT_SCHEMA="invoicing")
    assert resolve_schema(None) == "INVOICING"


def test_resolve_schema_falls_back_to_user(config):
    config(ORACLE_DEFAULT_SCHEMA="", ORACLE_USER="reader")
    assert resolve_schema(None) == "READER"


def test_schema_in_clause_empty(config):
    config(ALLOWED_SCHEMAS="")
    assert schema_in_clause() == ""


def test_schema_in_clause_populated(config):
    config(ALLOWED_SCHEMAS="invoicing, ref ,")
    assert schema_in_clause("o.owner") == "AND o.owner IN ('INVOICING', 'REF')"


# ── config ────────────────────────────────────────────────────────────────────


def test_dsn_prefers_service(config):
    cfg = config(ORACLE_SERVICE="SVC", ORACLE_SID="SID")
    assert "SERVICE_NAME=SVC" in cfg.dsn()


def test_dsn_falls_back_to_sid(config):
    cfg = config(ORACLE_SERVICE="", ORACLE_SID="XE")
    assert "SID=XE" in cfg.dsn()


def test_validate_reports_all_missing(config):
    cfg = config(ORACLE_USER="", ORACLE_PASSWORD="", ORACLE_SERVICE="", ORACLE_SID="")
    with pytest.raises(OSError) as exc:
        cfg.validate()
    assert "USER, PASSWORD, ORACLE_SERVICE or ORACLE_SID" in str(exc.value)


def test_default_port_matches_meta_yml(config, monkeypatch):
    monkeypatch.delenv("MCP_PORT", raising=False)
    assert config().mcp_port == 8003


# ── db helpers ────────────────────────────────────────────────────────────────


def test_rows_lowercases_columns_and_defaults_to_max_rows(config):
    config(MAX_ROWS="7")
    cur = MagicMock(description=[("ID",), ("NAME",)])
    cur.fetchmany.return_value = [(1, "a")]
    assert db.rows(cur) == [{"id": 1, "name": "a"}]
    cur.fetchmany.assert_called_once_with(7)


def test_init_oracle_client_ignores_already_initialised(config):
    config(ORACLE_CLIENT_LIB_DIR="C:/ic")
    err = oracledb.ProgrammingError("DPY-2017: already initialized")
    with patch.object(oracledb, "init_oracle_client", side_effect=err) as init:
        db.init_oracle_client()
    init.assert_called_once_with(lib_dir="C:/ic")


def test_init_oracle_client_reraises_other_errors(config):
    config(ORACLE_CLIENT_LIB_DIR="")
    with patch.object(oracledb, "init_oracle_client",
                      side_effect=oracledb.ProgrammingError("boom")):
        with pytest.raises(oracledb.ProgrammingError):
            db.init_oracle_client()


def test_conn_releases_connection_on_error():
    pool = MagicMock()
    with patch.object(db, "get_pool", return_value=pool):
        with pytest.raises(RuntimeError):
            with db.conn():
                raise RuntimeError
    pool.release.assert_called_once_with(pool.acquire.return_value)
