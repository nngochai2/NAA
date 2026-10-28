"""Tool registry — importing the submodules registers their tools."""
from __future__ import annotations

import httpx
from mcp.types import TextContent, Tool

from ..client import JenkinsApiError, JenkinsClient
from . import artifacts, builds, jobs, system  # noqa: F401  (import side effect: registration)
from ._base import REGISTRY, err

ALL_TOOLS: list[Tool] = [tool for tool, _ in REGISTRY.values()]


def handle_tool(name: str, arguments: dict, client: JenkinsClient) -> list[TextContent]:
    entry = REGISTRY.get(name)
    if entry is None:
        return err(f"Unknown tool: {name}")
    try:
        return entry[1](client, arguments)
    except JenkinsApiError as exc:
        return err(str(exc))
    except httpx.HTTPError as exc:
        return err(f"Could not reach Jenkins: {exc}")
    except KeyError as exc:
        return err(f"Missing required argument: {exc.args[0]}")
    except ValueError as exc:
        return err(str(exc))
