"""Oracle client initialisation, connection pool, and result helpers."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

import oracledb

from .config import get_config

logger = logging.getLogger("oracle-mcp")


def init_oracle_client() -> None:
    """
    Oracle 11g pre-dates the thin wire protocol.  python-oracledb thin mode
    only supports 12.1+, so thick mode (Oracle Instant Client) is mandatory.

    Installation options:
      Linux  : rpm -ivh oracle-instantclient-basic-*.rpm
               export LD_LIBRARY_PATH=/usr/lib/oracle/21/client64/lib
      Windows: unzip instantclient_21_x to C:\\oracle\\instantclient
               set PATH=%PATH%;C:\\oracle\\instantclient

    ORACLE_CLIENT_LIB_DIR in .env overrides auto-discovery from PATH /
    LD_LIBRARY_PATH.  Omit to let the driver find the client automatically.
    """
    client_lib = get_config().client_lib
    try:
        if client_lib:
            oracledb.init_oracle_client(lib_dir=client_lib)
            logger.info("Oracle thick mode — client lib: %s", client_lib)
        else:
            oracledb.init_oracle_client()
            logger.info("Oracle thick mode — client lib from system path")
    except oracledb.ProgrammingError as exc:
        # Already initialised in this process — safe to ignore
        if "already" in str(exc).lower():
            logger.debug("Oracle client already initialised: %s", exc)
        else:
            raise


_pool: oracledb.ConnectionPool | None = None


def get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        cfg = get_config()
        _pool = oracledb.create_pool(
            user=cfg.user,
            password=cfg.password,
            dsn=cfg.dsn(),
            min=1,
            max=5,
            increment=1,
            getmode=oracledb.POOL_GETMODE_WAIT,
            timeout=30,
        )
        logger.info("Connection pool created — %s@%s:%s", cfg.user, cfg.host, cfg.port)
    return _pool


@contextmanager
def conn() -> Generator[oracledb.Connection, None, None]:
    """Borrow a connection from the pool; return it on exit."""
    pool = get_pool()
    connection = pool.acquire()
    try:
        yield connection
    finally:
        pool.release(connection)


def long_to_str(cursor, name, default_type, size, precision, scale):
    """Output type handler: convert LONG columns to Python str (up to 32 767 chars).

    Oracle 11g stores ALL_VIEWS.TEXT as LONG.
    """
    if default_type == oracledb.DB_TYPE_LONG:
        return cursor.var(str, 32_767, cursor.arraysize)


def rows(cursor, limit: int | None = None) -> list[dict]:
    cols = [d[0].lower() for d in cursor.description]
    cap = limit or get_config().max_rows
    return [dict(zip(cols, row)) for row in cursor.fetchmany(cap)]
