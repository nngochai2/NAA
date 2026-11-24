"""Entry point: python -m oracle_mcp"""
import asyncio
import logging
import os

import oracledb

from . import db
from .config import get_config
from .server import mcp


async def _run() -> None:
    cfg = get_config()
    cfg.validate()
    db.init_oracle_client()

    # Warm pool at startup — fails fast if credentials or TNS are wrong
    try:
        db.get_pool()
    except oracledb.DatabaseError as exc:
        db.logger.error("Cannot connect to Oracle: %s", exc)
        raise SystemExit(1) from exc

    transport = cfg.mcp_transport.lower()
    db.logger.info("Oracle MCP server ready (transport: %s)", transport)
    if transport == "sse":
        db.logger.info("Listening on %s:%s", cfg.mcp_host, cfg.mcp_port)
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
