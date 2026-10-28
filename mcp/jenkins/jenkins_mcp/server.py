"""MCP server wired to Starlette SSE transport."""
from __future__ import annotations

from contextvars import ContextVar

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from .auth import MissingCredentialsError, resolve_client_from_headers
from .client import JenkinsClient
from .config import get_config
from .tools import ALL_TOOLS, handle_tool

server = Server("jenkins-mcp")

_current_client: ContextVar[JenkinsClient] = ContextVar("_current_client")


@server.list_tools()
async def list_tools():
    config = get_config()
    return [t for t in ALL_TOOLS if config.is_tool_enabled(t.name)]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if not get_config().is_tool_enabled(name):
        return [TextContent(type="text", text=f"Error: Tool '{name}' is disabled on this server.")]
    return handle_tool(name, arguments, client=_current_client.get())


def create_starlette_app() -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        try:
            client = resolve_client_from_headers(request.headers, get_config())
        except MissingCredentialsError as exc:
            return Response(str(exc), status_code=401)

        token = _current_client.set(client)
        try:
            async with sse.connect_sse(request.scope, request.receive, request._send) as (read, write):
                await server.run(read, write, server.create_initialization_options())
        finally:
            _current_client.reset(token)

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])
