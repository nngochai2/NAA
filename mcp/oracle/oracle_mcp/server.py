"""
Oracle 11g MCP Server
=====================
Exposes Oracle database schema, source, dependency, and query tools
to AI assistants via the Model Context Protocol.

Transport : SSE/HTTP (default — team deployment via the webapp)
            stdio (local / VS Code dev; set MCP_TRANSPORT=stdio)
DB Access : Read-only Oracle user (enforced at DB level AND application level)
Oracle    : Requires thick mode — Oracle Instant Client must be present on host

Tool inventory
--------------
  execute_query          Ad-hoc SELECT; row-capped; DML/DDL blocked
  describe_object        Column metadata + comments for any table or view
  get_view_definition    Full DDL via DBMS_METADATA; falls back to ALL_VIEWS.TEXT
  list_objects           Inventory by schema/type/name pattern
  get_dependencies       Upstream + downstream dependency graph (ALL_DEPENDENCIES)
  get_package_source     PL/SQL source from ALL_SOURCE (packages, procs, functions, triggers)
  get_constraints        PK / FK / unique / check constraints with FK target resolution
  search_objects         Object name + column name search; optional PL/SQL source scan
  get_indexes            Index definitions with column list
  get_invalid_objects    INVALID objects in schema — pre/post-deployment check

Importing this module registers every tool on the shared FastMCP instance.
"""

from __future__ import annotations

from .app import mcp
from .tools import metadata, query, source  # noqa: F401  (registers tools)

__all__ = ["mcp"]
