"""Generic Git pull-request / merge-request tools."""
from __future__ import annotations

import json
import logging

from mcp.types import TextContent, Tool

from ..provider import get_provider

logger = logging.getLogger(__name__)

PR_TOOLS: list[Tool] = [
    Tool(
        name="git_list_pull_requests",
        description="List pull requests (GitHub) / merge requests (GitLab).",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_id": {"type": "string"},
                "state": {
                    "type": "string",
                    "enum": ["opened", "open", "closed", "merged", "all"],
                    "default": "opened",
                },
                "source_branch": {"type": "string"},
                "target_branch": {"type": "string"},
                "author": {"type": "string", "description": "Filter by author username."},
                "search": {"type": "string", "description": "Search string (GitLab only)."},
                "per_page": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    ),
    Tool(
        name="git_get_pull_request",
        description="Get full details of a pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR/MR number."},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number"],
        },
    ),
    Tool(
        name="git_get_pull_request_changes",
        description="Get the file diff for a pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number"],
        },
    ),
    Tool(
        name="git_get_pull_request_discussions",
        description="Get all comments and review discussions on a pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number"],
        },
    ),
    Tool(
        name="git_create_pull_request_note",
        description="Add a comment to a pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "body": {"type": "string", "description": "Comment body (Markdown supported)."},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number", "body"],
        },
    ),
    Tool(
        name="git_approve_pull_request",
        description="Approve a pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number"],
        },
    ),
    Tool(
        name="git_merge_pull_request",
        description="Merge an approved pull request / merge request.",
        inputSchema={
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer"},
                "message": {"type": "string", "description": "Custom merge commit message."},
                "squash": {"type": "boolean", "default": False},
                "remove_source_branch": {"type": "boolean", "default": False},
                "repo_id": {"type": "string"},
            },
            "required": ["pr_number"],
        },
    ),
]


def _fmt(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {msg}")]


async def handle_pr_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        provider = get_provider()
        repo_id  = provider.resolve_repo_id(arguments)
        repo     = provider.get_repo(repo_id)

        if name == "git_list_pull_requests":
            return _fmt(provider.list_pull_requests(
                repo,
                state=arguments.get("state", "opened"),
                source_branch=arguments.get("source_branch"),
                target_branch=arguments.get("target_branch"),
                author=arguments.get("author"),
                search=arguments.get("search"),
                per_page=int(arguments.get("per_page", 20)),
            ))

        if name == "git_get_pull_request":
            return _fmt(provider.get_pull_request(repo, int(arguments["pr_number"])))

        if name == "git_get_pull_request_changes":
            return _fmt(provider.get_pull_request_changes(repo, int(arguments["pr_number"])))

        if name == "git_get_pull_request_discussions":
            return _fmt(provider.get_pull_request_discussions(repo, int(arguments["pr_number"])))

        if name == "git_create_pull_request_note":
            return _fmt(provider.create_pull_request_note(repo, int(arguments["pr_number"]), arguments["body"]))

        if name == "git_approve_pull_request":
            return _fmt({"message": provider.approve_pull_request(repo, int(arguments["pr_number"]))})

        if name == "git_merge_pull_request":
            return _fmt({"message": provider.merge_pull_request(
                repo,
                int(arguments["pr_number"]),
                message=arguments.get("message"),
                squash=bool(arguments.get("squash", False)),
                remove_source=bool(arguments.get("remove_source_branch", False)),
            )})

        return _err(f"Unknown tool: {name}")

    except (ValueError, KeyError) as exc:
        return _err(str(exc))
    except Exception as exc:
        logger.exception("PR tool %s failed", name)
        return _err(str(exc))
