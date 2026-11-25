"""PL/SQL source, dependency, search and validity tools."""

from __future__ import annotations

import oracledb
from mcp.types import ToolAnnotations

from .. import db
from ..app import mcp, to_json, tool_error
from ..guard import SchemaNotAllowed, resolve_schema


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_dependencies(
    object_name: str,
    schema: str | None = None,
    direction: str = "both",
) -> str:
    """
    Return the dependency graph for an Oracle object via ALL_DEPENDENCIES.

    Parameters
    ----------
    object_name : Object name (case-insensitive).
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    direction   : 'upstream'   — what this object depends on
                  'downstream' — what depends on this object
                  'both'       — full picture (default)

    Primary use: impact analysis before changing a view, package, or table.
    "If I modify V_INVOICE_LINES, what breaks?"  →  direction='downstream'
    "What tables does P_CALC_VAT read?"          →  direction='upstream'
    """
    try:
        owner = resolve_schema(schema)
    except SchemaNotAllowed as exc:
        return tool_error(str(exc))
    name = object_name.upper()
    direction = direction.lower()
    result: dict = {"object": f"{owner}.{name}", "direction": direction}

    try:
        with db.conn() as conn:
            cur = conn.cursor()

            if direction in ("upstream", "both"):
                cur.execute(
                    """
                    SELECT referenced_owner  AS dep_owner,
                           referenced_name   AS dep_name,
                           referenced_type   AS dep_type,
                           dependency_type
                    FROM   all_dependencies
                    WHERE  owner = :o AND name = :n
                    ORDER  BY referenced_type, referenced_name
                """,
                    o=owner,
                    n=name,
                )
                result["depends_on"] = db.rows(cur)

            if direction in ("downstream", "both"):
                cur.execute(
                    """
                    SELECT owner        AS dep_owner,
                           name         AS dep_name,
                           type         AS dep_type,
                           dependency_type
                    FROM   all_dependencies
                    WHERE  referenced_owner = :o AND referenced_name = :n
                    ORDER  BY type, name
                """,
                    o=owner,
                    n=name,
                )
                result["used_by"] = db.rows(cur)

        return to_json(result)
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_package_source(
    object_name: str,
    schema: str | None = None,
    part: str = "both",
) -> str:
    """
    Return PL/SQL source from ALL_SOURCE for packages, procedures,
    functions, or triggers.

    Parameters
    ----------
    object_name : Package / procedure / function / trigger name (case-insensitive).
    schema      : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    part        : For packages only:
                    'spec' — package specification (interface)
                    'body' — package body (implementation)
                    'both' — both (default)
                  Ignored for procedures, functions, and triggers.

    Note: Large package bodies can exceed LLM context windows.  Use 'spec'
    first to understand the interface, then 'body' only if the implementation
    detail is required.
    """
    try:
        owner = resolve_schema(schema)
    except SchemaNotAllowed as exc:
        return tool_error(str(exc))
    name = object_name.upper()
    part = part.lower()

    try:
        with db.conn() as conn:
            cur = conn.cursor()

            # Auto-detect object type
            cur.execute(
                """
                SELECT object_type FROM all_objects
                WHERE  owner = :o AND object_name = :n
                  AND  object_type IN (
                         'PACKAGE','PACKAGE BODY','PROCEDURE',
                         'FUNCTION','TRIGGER','TYPE','TYPE BODY'
                       )
                  AND  ROWNUM = 1
            """,
                o=owner,
                n=name,
            )
            row = cur.fetchone()

        if not row:
            return tool_error(
                f"No PL/SQL object named {owner}.{name} found "
                f"(looked for PACKAGE, PROCEDURE, FUNCTION, TRIGGER, TYPE)."
            )

        obj_type = row[0]

        # Determine which source type(s) to fetch
        if obj_type == "PACKAGE":
            fetch_types = []
            if part in ("spec", "both"):
                fetch_types.append("PACKAGE")
            if part in ("body", "both"):
                fetch_types.append("PACKAGE BODY")
        else:
            fetch_types = [obj_type]

        sections: dict[str, str] = {}
        with db.conn() as conn:
            cur = conn.cursor()
            for stype in fetch_types:
                cur.execute(
                    """
                    SELECT text FROM all_source
                    WHERE  owner = :o AND name = :n AND type = :t
                    ORDER  BY line
                """,
                    o=owner,
                    n=name,
                    t=stype,
                )
                lines = [r[0] for r in cur.fetchall()]
                sections[stype] = "".join(lines) if lines else "(source not accessible)"

        return to_json(
            {
                "object": f"{owner}.{name}",
                "type": obj_type,
                "part": part,
                "source": sections,
            }
        )
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_objects(
    keyword: str,
    schema: str | None = None,
    include_source: bool = False,
) -> str:
    """
    Search Oracle metadata for a keyword across:
      1. Object names    (ALL_OBJECTS.OBJECT_NAME)
      2. Column names    (ALL_TAB_COLUMNS.COLUMN_NAME)
      3. PL/SQL source   (ALL_SOURCE.TEXT) — only when include_source=True

    Use for:
    - Finding all objects related to a business term (e.g. 'VAT', 'EXEMPTION')
    - Locating where a column name pattern appears across schemas
    - Finding PL/SQL that references a specific constant or procedure

    Parameters
    ----------
    keyword        : Search term (case-insensitive, LIKE match).
    schema         : Schema to search.  Defaults to ORACLE_DEFAULT_SCHEMA.
                     Rejected if ALLOWED_SCHEMAS is set and does not include it.
    include_source : Also search ALL_SOURCE.TEXT.  Can be slow on large codebases.
                     Default: False.
    """
    try:
        owner = resolve_schema(schema)
    except SchemaNotAllowed as exc:
        return tool_error(str(exc))
    binds = {"kw": f"%{keyword.upper()}%", "owner": owner}
    results: dict = {}

    try:
        with db.conn() as conn:
            cur = conn.cursor()

            # Object names
            cur.execute(
                """
                SELECT owner, object_name, object_type, status, last_ddl_time
                FROM   all_objects
                WHERE  object_name LIKE :kw AND owner = :owner
                ORDER  BY object_type, object_name
            """,
                **binds,
            )
            results["objects_by_name"] = db.rows(cur)

            # Column names
            cur.execute(
                """
                SELECT owner, table_name, column_name, data_type, nullable
                FROM   all_tab_columns
                WHERE  column_name LIKE :kw AND owner = :owner
                ORDER  BY owner, table_name, column_name
            """,
                **binds,
            )
            results["columns_by_name"] = db.rows(cur)

            # PL/SQL source (optional; potentially slow)
            if include_source:
                cur.execute(
                    """
                    SELECT DISTINCT owner, name, type
                    FROM   all_source
                    WHERE  UPPER(text) LIKE :kw AND owner = :owner
                    ORDER  BY type, name
                """,
                    **binds,
                )
                results["source_references"] = db.rows(cur)

        total = sum(len(v) for v in results.values())
        return to_json(
            {"keyword": keyword, "schema": owner, "total_hits": total, "results": results}
        )
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_invalid_objects(schema: str | None = None) -> str:
    """
    Return all INVALID objects in a schema.

    Run this:
    - After any deployment to verify nothing broke
    - Before a change to baseline which objects are already invalid
      (so post-change invalids can be correctly attributed)
    - As part of an automated post-deployment Jenkins stage

    Parameters
    ----------
    schema : Owner schema.  Defaults to ORACLE_DEFAULT_SCHEMA from .env.
    """
    try:
        owner = resolve_schema(schema)
    except SchemaNotAllowed as exc:
        return tool_error(str(exc))
    try:
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT object_name, object_type, last_ddl_time
                FROM   all_objects
                WHERE  owner  = :o
                  AND  status = 'INVALID'
                ORDER  BY object_type, object_name
            """,
                o=owner,
            )
            rows = db.rows(cur)
        return to_json({"schema": owner, "invalid_count": len(rows), "objects": rows})
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")
