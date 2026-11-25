"""Table / view metadata tools: columns, view DDL, object inventory, constraints, indexes."""

from __future__ import annotations

import oracledb
from mcp.types import ToolAnnotations

from .. import db
from ..app import mcp, to_json, tool_error
from ..config import get_config
from ..guard import resolve_schema


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def describe_object(object_name: str, schema: str | None = None) -> str:
    """
    Return rich column metadata for a table or view — equivalent to DESC
    in SQL*Plus but includes data types, nullability, defaults, and both
    column-level and table-level comments.

    Parameters
    ----------
    object_name : Table or view name (case-insensitive).
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    """
    owner = resolve_schema(schema)
    name = object_name.upper()

    col_sql = """
        SELECT
            c.column_id                                     AS col_id,
            c.column_name,
            c.data_type
                || CASE
                       WHEN c.data_type IN ('VARCHAR2','NVARCHAR2','CHAR','NCHAR')
                           THEN '(' || c.char_length || ')'
                       WHEN c.data_type = 'NUMBER' AND c.data_precision IS NOT NULL
                           THEN '(' || c.data_precision
                                    || CASE WHEN c.data_scale > 0
                                            THEN ',' || c.data_scale ELSE '' END
                                    || ')'
                       ELSE ''
                   END                                      AS data_type,
            c.nullable,
            c.data_default,
            cc.comments                                     AS column_comment
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cc
               ON cc.owner       = c.owner
              AND cc.table_name  = c.table_name
              AND cc.column_name = c.column_name
        WHERE c.owner      = :owner
          AND c.table_name = :name
        ORDER BY c.column_id
    """
    tab_sql = """
        SELECT comments FROM all_tab_comments
        WHERE owner = :owner AND table_name = :name
    """

    try:
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(col_sql, owner=owner, name=name)
            columns = db.rows(cur)

            cur.execute(tab_sql, owner=owner, name=name)
            row = cur.fetchone()
            table_comment = row[0] if row else None

        if not columns:
            return tool_error(
                f"{owner}.{name} not found or no columns accessible to {get_config().user}."
            )

        return to_json(
            {
                "object": f"{owner}.{name}",
                "comment": table_comment,
                "columns": columns,
            }
        )
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_view_definition(view_name: str, schema: str | None = None) -> str:
    """
    Return the full SQL text of an Oracle view.

    Primary path  : DBMS_METADATA.GET_DDL — returns complete, formatted DDL
                    including the CREATE OR REPLACE header.
    Fallback path : ALL_VIEWS.TEXT — raw SELECT body only; LONG column read
                    via output type handler (32 767 char limit).

    Note: If the MCP read-only user lacks EXECUTE on DBMS_METADATA, grant:
          GRANT EXECUTE ON DBMS_METADATA TO <mcp_user>;
          or rely on the ALL_VIEWS fallback.

    Parameters
    ----------
    view_name : View name (case-insensitive).
    schema    : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    """
    owner = resolve_schema(schema)
    name = view_name.upper()

    try:
        with db.conn() as conn:
            cur = conn.cursor()

            # ── Primary: DBMS_METADATA ────────────────────────────────────────
            try:
                cur.execute(
                    "SELECT DBMS_METADATA.GET_DDL('VIEW', :n, :o) FROM dual",
                    n=name,
                    o=owner,
                )
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0])
            except oracledb.DatabaseError as exc:
                db.logger.warning(
                    "DBMS_METADATA unavailable for %s.%s (%s) — using ALL_VIEWS fallback",
                    owner,
                    name,
                    exc,
                )

            # ── Fallback: ALL_VIEWS.TEXT (LONG column) ────────────────────────
            cur.outputtypehandler = db.long_to_str
            cur.execute(
                "SELECT text FROM all_views WHERE owner = :o AND view_name = :n",
                o=owner,
                n=name,
            )
            row = cur.fetchone()
            if row and row[0]:
                header = "-- Source: ALL_VIEWS.TEXT (DBMS_METADATA unavailable)\n"
                header += f"CREATE OR REPLACE VIEW {owner}.{name} AS\n"
                return header + row[0]

        return tool_error(f"View {owner}.{name} not found or not accessible.")
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_objects(
    schema: str | None = None,
    object_type: str | None = None,
    name_filter: str | None = None,
) -> str:
    """
    List Oracle objects in a schema, optionally filtered by type and/or name.

    Parameters
    ----------
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    object_type : One of TABLE, VIEW, PACKAGE, PACKAGE BODY, PROCEDURE,
                  FUNCTION, TRIGGER, SYNONYM, SEQUENCE, INDEX.
                  Case-insensitive.  Omit for all types.
    name_filter : Partial object name (LIKE match, case-insensitive).
                  Example: 'INV' matches INV_HEADER, INVOICE_LINES, etc.
    """
    owner = resolve_schema(schema)
    conditions = ["owner = :owner"]
    binds: dict = {"owner": owner}

    if object_type:
        conditions.append("object_type = :otype")
        binds["otype"] = object_type.upper()
    if name_filter:
        conditions.append("object_name LIKE :nfilter")
        binds["nfilter"] = f"%{name_filter.upper()}%"

    where = " AND ".join(conditions)
    sql = f"""
        SELECT object_name, object_type, status, last_ddl_time
        FROM   all_objects
        WHERE  {where}
        ORDER  BY object_type, object_name
    """
    try:
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, **binds)
            rows = db.rows(cur)
        return to_json({"schema": owner, "count": len(rows), "objects": rows})
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_constraints(object_name: str, schema: str | None = None) -> str:
    """
    Return all constraints for a table: primary keys, foreign keys,
    unique constraints, and check constraints.

    FK entries include the referenced owner, table, and column list —
    essential for tracing join paths embedded in legacy views.

    Parameters
    ----------
    object_name : Table name (case-insensitive).
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    """
    owner = resolve_schema(schema)
    name = object_name.upper()

    # Oracle 11g has LISTAGG — safe to use.
    sql = """
        SELECT
            c.constraint_name,
            CASE c.constraint_type
                WHEN 'P' THEN 'PRIMARY KEY'
                WHEN 'R' THEN 'FOREIGN KEY'
                WHEN 'U' THEN 'UNIQUE'
                WHEN 'C' THEN 'CHECK'
                ELSE c.constraint_type
            END                                                 AS constraint_type,
            c.status,
            c.validated,
            c.search_condition,
            c.r_owner                                           AS fk_ref_owner,
            rc.table_name                                       AS fk_ref_table,
            c.r_constraint_name                                 AS fk_ref_constraint,
            LISTAGG(cc.column_name, ', ')
                WITHIN GROUP (ORDER BY cc.position)             AS columns
        FROM   all_constraints    c
        JOIN   all_cons_columns   cc
               ON  cc.owner           = c.owner
               AND cc.constraint_name = c.constraint_name
        LEFT JOIN all_constraints rc
               ON  rc.owner           = c.r_owner
               AND rc.constraint_name = c.r_constraint_name
        WHERE  c.owner      = :owner
          AND  c.table_name = :name
        GROUP  BY c.constraint_name, c.constraint_type, c.status, c.validated,
                  c.search_condition, c.r_owner, rc.table_name, c.r_constraint_name
        ORDER  BY c.constraint_type, c.constraint_name
    """
    try:
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, owner=owner, name=name)
            rows = db.rows(cur)
        return to_json({"object": f"{owner}.{name}", "constraints": rows})
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_indexes(object_name: str, schema: str | None = None) -> str:
    """
    Return index definitions for a table, including column list, uniqueness,
    status, and index type (NORMAL, BITMAP, FUNCTION-BASED, etc.).

    Useful for:
    - Understanding query performance characteristics of a view's base tables
    - Checking whether legacy code can rely on a unique index as a surrogate PK

    Parameters
    ----------
    object_name : Table name (case-insensitive).
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    """
    owner = resolve_schema(schema)
    name = object_name.upper()

    sql = """
        SELECT
            i.index_name,
            i.index_type,
            i.uniqueness,
            i.status,
            i.partitioned,
            LISTAGG(ic.column_name || CASE ic.descend WHEN 'DESC' THEN ' DESC' ELSE '' END,
                    ', ')
                WITHIN GROUP (ORDER BY ic.column_position)     AS columns
        FROM   all_indexes     i
        JOIN   all_ind_columns ic
               ON  ic.index_owner = i.owner
               AND ic.index_name  = i.index_name
               AND ic.table_name  = i.table_name
        WHERE  i.table_owner = :owner
          AND  i.table_name  = :name
        GROUP  BY i.index_name, i.index_type, i.uniqueness,
                  i.status, i.partitioned
        ORDER  BY i.uniqueness DESC, i.index_name
    """
    try:
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, owner=owner, name=name)
            rows = db.rows(cur)
        return to_json({"object": f"{owner}.{name}", "indexes": rows})
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")
