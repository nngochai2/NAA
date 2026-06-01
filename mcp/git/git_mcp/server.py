"""MCP server wired to Starlette SSE transport."""
from __future__ import annotations

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from .tools import ALL_TOOLS, TOOL_HANDLERS

server = Server("git-mcp")


@server.list_tools()
async def list_tools():
    return ALL_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name!r}")]
    return await handler(name, arguments)


def create_starlette_app() -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read, write):
            await server.run(read, write, server.create_initialization_options())
        return Response()

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ])
