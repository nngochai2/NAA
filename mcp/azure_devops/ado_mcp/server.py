"""
Azure DevOps Server (on-premises) MCP Server

Transport: SSE/HTTP — run on a shared team VM, one instance for all developers.

Auth: NTLM (Windows domain account) using the shared ADO_USERNAME /
ADO_PASSWORD from .env.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import ImageContent, TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from .client import AdoClient
from .config import get_config
from .tools import TOOLS, handle_tool

logger = logging.getLogger("ado-mcp")

server = Server("ado-mcp")


@lru_cache(maxsize=1)
def get_client() -> AdoClient:
    return AdoClient.from_config(get_config())


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    return await handle_tool(get_client(), name, arguments)


def create_starlette_app() -> Starlette:
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    @asynccontextmanager
    async def lifespan(_app):
        cfg = get_config()
        logger.info(
            "ADO MCP Server running on http://%s:%s/sse  (project: %s)",
            cfg.host,
            cfg.port,
            cfg.project,
        )
        yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
    )
