"""Ad-hoc read-only query tool."""

from __future__ import annotations

import oracledb
from mcp.types import ToolAnnotations

from .. import db
from ..app import mcp, to_json, tool_error
from ..config import get_config
from ..guard import guard


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def execute_query(sql: str, max_rows: int = get_config().max_rows) -> str:
    """
    Execute an ad-hoc read-only SELECT against Oracle.

    Results are capped at max_rows (default from MAX_ROWS env var; hard ceiling
    also applies).  DML, DDL, and transaction control are blocked.

    Use for:
    - Spot-checking view output before relying on it in code
    - Verifying that a WHERE clause matches expected rows
    - Investigating data quality issues
    """
    try:
        guard(sql)
        cap = min(max_rows, get_config().max_rows)
        with db.conn() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            rows = db.rows(cur, cap)
        return to_json({"row_count": len(rows), "capped_at": cap, "rows": rows})
    except ValueError as exc:
        return tool_error(str(exc))
    except oracledb.DatabaseError as exc:
        return tool_error(f"Oracle error: {exc}")
