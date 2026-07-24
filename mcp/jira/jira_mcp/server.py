"""MCP server wired to Starlette SSE transport."""
from __future__ import annotations

from contextvars import ContextVar

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from .auth import MissingCredentialsError, resolve_client_from_headers
from .client import JiraClient
from .config import get_config
from .tools.issues import ISSUE_TOOLS, handle_issue_tool

server = Server("jira-mcp")

_current_client: ContextVar[JiraClient] = ContextVar("_current_client")


@server.list_tools()
async def list_tools():
    return ISSUE_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    return handle_issue_tool(name, arguments, client=_current_client.get(), project_key=get_config().project_key)


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
