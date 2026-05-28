"""Generic Git issue tools — works with GitLab and GitHub."""
from __future__ import annotations

import json
import logging

from mcp.types import TextContent, Tool

from ..provider import get_provider

logger = logging.getLogger(__name__)

ISSUE_TOOLS: list[Tool] = [
    Tool(
        name="git_list_issues",
        description="List issues from the configured repository. Works with GitLab and GitHub.",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Repository ID or path (e.g. 'owner/repo' for GitHub, project ID or 'group/project' for GitLab). Defaults to GITLAB_PROJECT_ID / GITHUB_REPO env var.",
                },
                "state": {
                    "type": "string",
                    "enum": ["opened", "open", "closed", "all"],
                    "description": "Filter by state. 'opened'/'open' for open issues.",
                    "default": "opened",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by label names.",
                },
                "assignee": {
                    "type": "string",
                    "description": "Filter by assignee username.",
                },
                "search": {
                    "type": "string",
                    "description": "Search string (GitLab only).",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Maximum number of issues to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="git_get_issue",
        description="Get full details of a single issue by number.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Issue number (IID for GitLab, number for GitHub).",
                },
                "repo_id": {"type": "string"},
            },
            "required": ["issue_number"],
        },
    ),
    Tool(
        name="git_create_issue",
        description="Create a new issue in the repository.",
        inputSchema={
            "type": "object",
            "properties": {
                "title":       {"type": "string"},
                "description": {"type": "string", "description": "Issue body / description (Markdown supported)."},
                "labels":      {"type": "array", "items": {"type": "string"}},
                "assignees":   {"type": "array", "items": {"type": "string"}, "description": "Usernames to assign."},
                "milestone_id": {"type": "integer"},
                "due_date":    {"type": "string", "description": "YYYY-MM-DD format (GitLab only)."},
                "repo_id":     {"type": "string"},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="git_update_issue",
        description="Update an existing issue (title, description, labels, state, assignees).",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "title":        {"type": "string"},
                "description":  {"type": "string"},
                "labels":       {"type": "array", "items": {"type": "string"}},
                "state_event":  {"type": "string", "enum": ["close", "reopen"]},
                "assignees":    {"type": "array", "items": {"type": "string"}},
                "repo_id":      {"type": "string"},
            },
            "required": ["issue_number"],
        },
    ),
    Tool(
        name="git_close_issue",
        description="Close an open issue.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "repo_id":      {"type": "string"},
            },
            "required": ["issue_number"],
        },
    ),
    Tool(
        name="git_delete_issue",
        description="Delete an issue permanently. GitLab requires Owner/Admin role. GitHub does not support deletion via API.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number": {"type": "integer"},
                "repo_id":      {"type": "string"},
            },
            "required": ["issue_number"],
        },
    ),
    Tool(
        name="git_link_issues",
        description="Link two issues. GitLab: creates a native issue link. GitHub: adds a reference comment.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_number":        {"type": "integer", "description": "Source issue number."},
                "target_issue_number": {"type": "integer", "description": "Target issue number."},
                "link_type": {
                    "type": "string",
                    "enum": ["relates_to", "blocks", "is_blocked_by"],
                    "default": "relates_to",
                },
                "repo_id": {"type": "string"},
            },
            "required": ["issue_number", "target_issue_number"],
        },
    ),
]


def _fmt(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {msg}")]


async def handle_issue_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        provider = get_provider()
        repo_id  = provider.resolve_repo_id(arguments)
        repo     = provider.get_repo(repo_id)

        if name == "git_list_issues":
            return _fmt(provider.list_issues(
                repo,
                state=arguments.get("state", "opened"),
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee"),
                search=arguments.get("search"),
                per_page=int(arguments.get("per_page", 20)),
            ))

        if name == "git_get_issue":
            return _fmt(provider.get_issue(repo, int(arguments["issue_number"])))

        if name == "git_create_issue":
            return _fmt(provider.create_issue(
                repo,
                title=arguments["title"],
                description=arguments.get("description"),
                labels=arguments.get("labels"),
                assignees=arguments.get("assignees"),
                milestone_id=arguments.get("milestone_id"),
                due_date=arguments.get("due_date"),
            ))

        if name == "git_update_issue":
            return _fmt(provider.update_issue(
                repo,
                int(arguments["issue_number"]),
                title=arguments.get("title"),
                description=arguments.get("description"),
                labels=arguments.get("labels"),
                state_event=arguments.get("state_event"),
                assignees=arguments.get("assignees"),
            ))

        if name == "git_close_issue":
            return _fmt({"message": provider.close_issue(repo, int(arguments["issue_number"]))})

        if name == "git_delete_issue":
            return _fmt({"message": provider.delete_issue(repo, int(arguments["issue_number"]))})

        if name == "git_link_issues":
            return _fmt({"message": provider.link_issues(
                repo,
                int(arguments["issue_number"]),
                int(arguments["target_issue_number"]),
                link_type=arguments.get("link_type", "relates_to"),
            )})

        return _err(f"Unknown tool: {name}")

    except (ValueError, KeyError) as exc:
        return _err(str(exc))
    except Exception as exc:
        logger.exception("Issue tool %s failed", name)
        return _err(str(exc))
