"""Jira issue tools."""
from __future__ import annotations

import json
import logging

from mcp.types import TextContent, Tool, ToolAnnotations

from ..client import JiraApiError, JiraClient
from ..hierarchy import (
    find_epic_link_field_id,
    resolve_link_type_id,
    resolve_parent_strategy,
    resolve_transition_id,
)

logger = logging.getLogger(__name__)

ISSUE_TOOLS: list[Tool] = [
    Tool(
        name="jira_get_issue",
        description="Get full details of a single Jira issue by key (e.g. 'PROJ-123').",
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Jira issue key, e.g. 'PROJ-123'."},
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="jira_list_issues",
        description="List issues in the configured project, with optional status/label/assignee filters.",
        annotations=ToolAnnotations(readOnlyHint=True),
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by workflow status name, e.g. 'In Progress'."},
                "label": {"type": "string", "description": "Filter by label."},
                "assignee": {"type": "string", "description": "Filter by assignee username."},
                "per_page": {"type": "integer", "description": "Maximum number of issues to return.", "default": 20},
            },
            "required": [],
        },
    ),
    Tool(
        name="jira_create_issue",
        description="Create a new issue in the configured Jira project.",
        inputSchema={
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Issue summary/title."},
                "description": {"type": "string", "description": "Issue description (plain text / wiki markup)."},
                "issue_type":  {"type": "string", "description": "Jira issue type name.", "default": "Task"},
                "labels":      {"type": "array", "items": {"type": "string"}},
                "assignee":    {"type": "string", "description": "Assignee username."},
                "priority":    {"type": "string", "description": "Priority name, e.g. 'High'."},
                "parent_key":  {"type": "string", "description": "Issue key to link this issue to as its parent."},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="jira_update_issue",
        description="Update an existing Jira issue's title, description, labels, assignee, or priority.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key":   {"type": "string", "description": "Jira issue key, e.g. 'PROJ-123'."},
                "title":       {"type": "string"},
                "description": {"type": "string"},
                "labels":      {"type": "array", "items": {"type": "string"}},
                "assignee":    {"type": "string"},
                "priority":    {"type": "string"},
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="jira_link_issues",
        description="Link two existing Jira issues with a named relationship (e.g. 'Blocks', 'Relates').",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key":        {"type": "string", "description": "Source issue key."},
                "target_issue_key": {"type": "string", "description": "Target issue key."},
                "link_type":        {"type": "string", "description": "Link type name, e.g. 'Blocks' or 'Relates'."},
            },
            "required": ["issue_key", "target_issue_key", "link_type"],
        },
    ),
    Tool(
        name="jira_transition_issue",
        description="Move a Jira issue to a target workflow status by name (e.g. 'In Progress', 'Done').",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key":     {"type": "string", "description": "Jira issue key, e.g. 'PROJ-123'."},
                "target_status": {"type": "string", "description": "Target status name, e.g. 'In Progress'."},
            },
            "required": ["issue_key", "target_status"],
        },
    ),
]


def _fmt(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error: {msg}")]


def _resolve_parent(client: JiraClient, project_key: str, issue_type: str, parent_key: str) -> dict:
    """Fetches whatever Jira metadata is needed, then delegates the actual
    parent-linking decision to hierarchy.resolve_parent_strategy (ADR 0001 + ADR 0003)."""
    if issue_type.lower() == "sub-task":
        parent_issue_type = ""
        epic_link_field_id = None
    else:
        parent_issue = client.get_issue(parent_key)
        parent_issue_type = parent_issue["fields"]["issuetype"]["name"]
        epic_link_field_id = None
        if parent_issue_type.lower() == "epic":
            epic_link_field_id = find_epic_link_field_id(client.get_create_meta(project_key, issue_type))
    return resolve_parent_strategy(parent_key, issue_type, parent_issue_type, epic_link_field_id)


def handle_issue_tool(name: str, arguments: dict, client: JiraClient, project_key: str) -> list[TextContent]:
    try:
        if name == "jira_get_issue":
            return _fmt(client.get_issue(arguments["issue_key"]))

        if name == "jira_list_issues":
            return _fmt(client.list_issues(
                project_key=project_key,
                status=arguments.get("status"),
                label=arguments.get("label"),
                assignee=arguments.get("assignee"),
                per_page=int(arguments.get("per_page", 20)),
            ))

        if name == "jira_create_issue":
            issue_type = arguments.get("issue_type", "Task")
            parent_key = arguments.get("parent_key")
            strategy = _resolve_parent(client, project_key, issue_type, parent_key) if parent_key else None

            created = client.create_issue(
                project_key=project_key,
                title=arguments["title"],
                description=arguments.get("description"),
                issue_type=issue_type,
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee"),
                priority=arguments.get("priority"),
                extra_fields=strategy["extra_fields"] if strategy else None,
            )

            if strategy and strategy["post_create_link"]:
                link_type_id = resolve_link_type_id("Relates", client.get_link_types())
                client.create_link(created["key"], parent_key, link_type_id)

            return _fmt(created)

        if name == "jira_update_issue":
            issue_key = arguments["issue_key"]
            client.update_issue(
                issue_key,
                title=arguments.get("title"),
                description=arguments.get("description"),
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee"),
                priority=arguments.get("priority"),
            )
            return _fmt({"issue_key": issue_key, "message": f"Issue {issue_key} updated."})

        if name == "jira_link_issues":
            issue_key = arguments["issue_key"]
            target_issue_key = arguments["target_issue_key"]
            link_type_id = resolve_link_type_id(arguments["link_type"], client.get_link_types())
            client.create_link(issue_key, target_issue_key, link_type_id)
            return _fmt({"message": f"Linked {issue_key} to {target_issue_key} as '{arguments['link_type']}'."})

        if name == "jira_transition_issue":
            issue_key = arguments["issue_key"]
            target_status = arguments["target_status"]
            transition_id = resolve_transition_id(target_status, client.get_transitions(issue_key))
            client.do_transition(issue_key, transition_id)
            return _fmt({"message": f"Moved {issue_key} to '{target_status}'."})

        return _err(f"Unknown tool: {name}")

    except JiraApiError as exc:
        return _err(str(exc))
    except (ValueError, KeyError) as exc:
        return _err(str(exc))
