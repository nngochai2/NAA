"""MCP server wired to Starlette SSE transport."""
from __future__ import annotations

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from .client import get_client
from .config import get_config
from .tools.issues import ISSUE_TOOLS, handle_issue_tool

server = Server("jira-mcp")


@server.list_tools()
async def list_tools():
    return ISSUE_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    return handle_issue_tool(name, arguments, client=get_client(), project_key=get_config().project_key)


def create_starlette_app() -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read, write):
            await server.run(read, write, server.create_initialization_options())

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])
