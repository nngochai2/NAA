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


class SchemaNotAllowed(ValueError):
    """The requested schema is outside ALLOWED_SCHEMAS."""


def resolve_schema(schema: str | None) -> str:
    """
    Upper-cased owner to query: the given schema, else ORACLE_DEFAULT_SCHEMA,
    else ORACLE_USER.  Raises SchemaNotAllowed when ALLOWED_SCHEMAS is set and
    the schema is not in it.

    The allowlist only scopes the metadata tools.  It is not a security
    boundary: execute_query runs arbitrary SQL, so the DB user's grants are
    what really limit access (see sql/db_setup.sql).
    """
    cfg = get_config()
    owner = (schema or cfg.default_schema or cfg.user).upper()
    if cfg.allowed_schemas and owner not in cfg.allowed_schemas:
        raise SchemaNotAllowed(
            f"Schema {owner} is not in ALLOWED_SCHEMAS ({', '.join(cfg.allowed_schemas)})."
        )
    return owner
