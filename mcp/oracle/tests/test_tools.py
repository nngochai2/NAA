"""Tool behaviour with a mocked Oracle cursor."""
import asyncio
import json

import pytest

from oracle_mcp.config import get_config
from oracle_mcp.server import drop_disabled_tools, mcp
from oracle_mcp.tools import metadata, query, source


def test_all_tools_registered_read_only():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {
        "execute_query", "describe_object", "get_view_definition", "list_objects",
        "get_dependencies", "get_package_source", "get_constraints", "search_objects",
        "get_indexes", "get_invalid_objects",
    }
    assert all(t.annotations.readOnlyHint for t in tools)


def test_drop_disabled_tools_removes_execute_query_when_disabled(config):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("t")
    server.add_tool(query.execute_query)
    server.add_tool(source.get_invalid_objects)

    drop_disabled_tools(server, config(ENABLE_EXECUTE_QUERY="true"))
    assert {t.name for t in asyncio.run(server.list_tools())} == {"execute_query", "get_invalid_objects"}

    drop_disabled_tools(server, config(ENABLE_EXECUTE_QUERY="false"))
    assert {t.name for t in asyncio.run(server.list_tools())} == {"get_invalid_objects"}


# ── execute_query ─────────────────────────────────────────────────────────────

class TestExecuteQuery:
    @pytest.mark.asyncio
    async def test_returns_rows(self, cursor):
        cursor.description = [("ID",), ("NAME",)]
        cursor.fetchmany.return_value = [(1, "Alpha"), (2, "Beta")]

        data = json.loads(await query.execute_query("SELECT id, name FROM t"))

        assert data["row_count"] == 2
        assert data["rows"][0]["name"] == "Alpha"

    @pytest.mark.asyncio
    async def test_blocks_dml(self, cursor):
        data = json.loads(await query.execute_query("DELETE FROM invoices"))
        assert "Only SELECT" in data["error"]
        cursor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuses_when_disabled(self, cursor, config):
        config(ENABLE_EXECUTE_QUERY="false")
        data = json.loads(await query.execute_query("SELECT 1 FROM dual"))
        assert "disabled" in data["error"]
        cursor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_caps_rows(self, cursor):
        """Request more rows than MAX_ROWS — should cap silently."""
        cursor.description = [("X",)]
        cursor.fetchmany.return_value = [(i,) for i in range(50)]

        data = json.loads(await query.execute_query("SELECT x FROM t", max_rows=9999))

        assert data["capped_at"] == get_config().max_rows == 50
        cursor.fetchmany.assert_called_once_with(50)


# ── describe_object ───────────────────────────────────────────────────────────

class TestDescribeObject:
    @pytest.mark.asyncio
    async def test_returns_columns(self, cursor):
        cursor.description = [
            ("COL_ID",), ("COLUMN_NAME",), ("DATA_TYPE",),
            ("NULLABLE",), ("DATA_DEFAULT",), ("COLUMN_COMMENT",),
        ]
        cursor.fetchmany.return_value = [(1, "INVOICE_ID", "NUMBER(10)", "N", None, "PK")]
        cursor.fetchone.return_value = ("Invoice header table",)

        data = json.loads(await metadata.describe_object("invoice_header", schema="invoicing"))

        assert data["object"] == "INVOICING.INVOICE_HEADER"
        assert data["comment"] == "Invoice header table"
        assert len(data["columns"]) == 1
        assert cursor.execute.call_args_list[0].kwargs == {
            "owner": "INVOICING", "name": "INVOICE_HEADER",
        }

    @pytest.mark.asyncio
    async def test_not_found(self, cursor):
        cursor.description = [("COL_ID",)]
        cursor.fetchmany.return_value = []
        cursor.fetchone.return_value = None

        data = json.loads(await metadata.describe_object("NO_SUCH_TABLE"))

        assert "not found" in data["error"]


# ── get_view_definition ───────────────────────────────────────────────────────

class TestGetViewDefinition:
    @pytest.mark.asyncio
    async def test_prefers_dbms_metadata(self, cursor):
        cursor.fetchone.return_value = ("CREATE OR REPLACE VIEW X AS SELECT 1 FROM dual",)
        out = await metadata.get_view_definition("x", schema="s")
        assert out.startswith("CREATE OR REPLACE VIEW X")
        assert cursor.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_all_views(self, cursor):
        import oracledb

        cursor.execute.side_effect = [oracledb.DatabaseError("no grant"), None]
        cursor.fetchone.return_value = ("SELECT 1 FROM dual",)

        out = await metadata.get_view_definition("v_x", schema="s")

        assert out.startswith("-- Source: ALL_VIEWS.TEXT")
        assert "CREATE OR REPLACE VIEW S.V_X AS\nSELECT 1 FROM dual" in out


# ── list_objects ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_objects_binds_filters(cursor):
    cursor.description = [("OBJECT_NAME",)]
    cursor.fetchmany.return_value = [("INV_HEADER",)]

    data = json.loads(await metadata.list_objects("s", object_type="view", name_filter="inv"))

    sql, = cursor.execute.call_args.args
    assert "object_type = :otype" in sql and "object_name LIKE :nfilter" in sql
    assert cursor.execute.call_args.kwargs == {"owner": "S", "otype": "VIEW", "nfilter": "%INV%"}
    assert data["count"] == 1


# ── get_dependencies ──────────────────────────────────────────────────────────

class TestGetDependencies:
    @pytest.mark.asyncio
    async def test_both_directions(self, cursor):
        cursor.description = [("DEP_OWNER",), ("DEP_NAME",), ("DEP_TYPE",), ("DEPENDENCY_TYPE",)]
        cursor.fetchmany.side_effect = [
            [("INVOICING", "BASE_TABLE", "TABLE", "HARD")],
            [("INVOICING", "REPORT_VIEW", "VIEW", "HARD")],
        ]

        data = json.loads(await source.get_dependencies("V_INVOICE", schema="INVOICING"))

        assert data["depends_on"][0]["dep_name"] == "BASE_TABLE"
        assert data["used_by"][0]["dep_name"] == "REPORT_VIEW"

    @pytest.mark.asyncio
    async def test_downstream_only(self, cursor):
        cursor.description = [("DEP_NAME",)]
        cursor.fetchmany.return_value = []

        data = json.loads(await source.get_dependencies("t", direction="DOWNSTREAM"))

        assert "used_by" in data and "depends_on" not in data


# ── get_package_source ────────────────────────────────────────────────────────

class TestGetPackageSource:
    @pytest.mark.asyncio
    async def test_package_spec_only(self, cursor):
        cursor.fetchone.return_value = ("PACKAGE",)
        cursor.fetchall.return_value = [("PACKAGE p IS\n",), ("END;\n",)]

        data = json.loads(await source.get_package_source("p", part="spec"))

        assert data["type"] == "PACKAGE"
        assert data["source"] == {"PACKAGE": "PACKAGE p IS\nEND;\n"}

    @pytest.mark.asyncio
    async def test_missing_object(self, cursor):
        cursor.fetchone.return_value = None
        data = json.loads(await source.get_package_source("nope"))
        assert "No PL/SQL object named" in data["error"]


# ── search_objects ────────────────────────────────────────────────────────────

class TestSearchObjects:
    @pytest.mark.asyncio
    async def test_finds_objects_and_columns(self, cursor):
        cursor.description = [("A",), ("B",), ("C",), ("D",), ("E",)]
        cursor.fetchmany.side_effect = [
            [("INVOICING", "V_VAT_EXEMPT", "VIEW", "VALID", "2024-01-01")],
            [("INVOICING", "INVOICE_LINES", "VAT_EXEMPT_FLAG", "VARCHAR2", "Y")],
        ]

        data = json.loads(await source.search_objects("VAT", schema="INVOICING"))

        assert data["keyword"] == "VAT"
        assert data["total_hits"] == 2
        assert set(data["results"]) == {"objects_by_name", "columns_by_name"}

    @pytest.mark.asyncio
    async def test_include_source_adds_third_query(self, cursor):
        cursor.description = [("A",)]
        cursor.fetchmany.return_value = []

        data = json.loads(await source.search_objects("vat", include_source=True))

        assert "source_references" in data["results"]
        assert cursor.execute.call_count == 3
        assert cursor.execute.call_args.kwargs == {"kw": "%VAT%", "owner": "TEST_USER"}

    @pytest.mark.asyncio
    async def test_schema_is_bound_not_interpolated(self, cursor, config):
        config(ALLOWED_SCHEMAS="")
        cursor.description = [("A",)]
        cursor.fetchmany.return_value = []
        evil = "X' OR '1'='1"

        await source.search_objects("vat", schema=evil)

        for call in cursor.execute.call_args_list:
            sql = call.args[0]
            assert evil.upper() not in sql
            assert "owner = :owner" in sql
            assert call.kwargs["owner"] == evil.upper()


# ── ALLOWED_SCHEMAS enforcement ───────────────────────────────────────────────

SCHEMA_TOOLS = {
    "describe_object":     lambda s: metadata.describe_object("t", schema=s),
    "get_view_definition": lambda s: metadata.get_view_definition("v", schema=s),
    "list_objects":        lambda s: metadata.list_objects(schema=s),
    "get_constraints":     lambda s: metadata.get_constraints("t", schema=s),
    "get_indexes":         lambda s: metadata.get_indexes("t", schema=s),
    "get_dependencies":    lambda s: source.get_dependencies("p", schema=s),
    "get_package_source":  lambda s: source.get_package_source("p", schema=s),
    "search_objects":      lambda s: source.search_objects("vat", schema=s),
    "get_invalid_objects": lambda s: source.get_invalid_objects(schema=s),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", SCHEMA_TOOLS)
async def test_tools_reject_schema_outside_allowlist(tool, cursor, config):
    config(ALLOWED_SCHEMAS="INVOICING")

    data = json.loads(await SCHEMA_TOOLS[tool]("hr"))

    assert data["error"].startswith("Schema HR is not in ALLOWED_SCHEMAS")
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", SCHEMA_TOOLS)
async def test_tools_accept_schema_inside_allowlist(tool, cursor, config):
    config(ALLOWED_SCHEMAS="INVOICING")
    cursor.description = [("A",)]
    cursor.fetchmany.return_value = []
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None

    raw = await SCHEMA_TOOLS[tool]("invoicing")

    assert "ALLOWED_SCHEMAS" not in raw
    cursor.execute.assert_called()


# ── get_invalid_objects ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_invalid_objects(cursor):
    cursor.description = [("OBJECT_NAME",), ("OBJECT_TYPE",)]
    cursor.fetchmany.return_value = [("P_BROKEN", "PROCEDURE")]

    data = json.loads(await source.get_invalid_objects("s"))

    assert data == {"schema": "S", "invalid_count": 1,
                    "objects": [{"object_name": "P_BROKEN", "object_type": "PROCEDURE"}]}


@pytest.mark.asyncio
async def test_database_errors_are_reported_not_raised(cursor):
    import oracledb

    cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")
    data = json.loads(await metadata.get_indexes("t"))
    assert data["error"].startswith("Oracle error: ORA-00942")
