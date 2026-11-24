"""Application-level read-only enforcement and schema helpers.

The DB user is read-only too; this is the second line of defence.
"""
from __future__ import annotations

import re

from .config import get_config

_MUTATING = re.compile(
    r"""
    ^\s*(
        INSERT | UPDATE | DELETE | MERGE   |   # DML
        DROP   | CREATE | ALTER  | TRUNCATE|   # DDL
        GRANT  | REVOKE                    |   # DCL
        EXEC   | EXECUTE | BEGIN | CALL    |   # PL/SQL execution
        COMMIT | ROLLBACK | SAVEPOINT          # TCL
    )\b
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)


def guard(sql: str) -> None:
    """Raise ValueError if sql contains any mutating statement."""
    if _MUTATING.search(sql):
        raise ValueError(
            "Only SELECT statements are permitted through this MCP server.  "
            "DML, DDL, DCL, and transaction control are blocked."
        )


def schema_in_clause(alias: str = "owner") -> str:
    """
    Returns an AND fragment restricting results to ALLOWED_SCHEMAS,
    or an empty string when the list is unconstrained.
    """
    allowed = get_config().allowed_schemas
    if not allowed:
        return ""
    quoted = ", ".join(f"'{s}'" for s in allowed)
    return f"AND {alias} IN ({quoted})"


def resolve_schema(schema: str | None) -> str:
    cfg = get_config()
    return (schema or cfg.default_schema or cfg.user).upper()
