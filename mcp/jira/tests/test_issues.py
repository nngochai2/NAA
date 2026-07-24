import json

import httpx

from jira_mcp.tools.issues import handle_issue_tool


def test_jira_get_issue_returns_formatted_issue_json(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"key": "PROJ-1", "fields": {"summary": "Test issue"}})

    client = make_client(handler)

    result = handle_issue_tool("jira_get_issue", {"issue_key": "PROJ-1"}, client=client, project_key="PROJ")

    assert len(result) == 1
    assert json.loads(result[0].text) == {"key": "PROJ-1", "fields": {"summary": "Test issue"}}


def test_jira_list_issues_returns_formatted_issue_list(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]})

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_list_issues", {"status": "In Progress"}, client=client, project_key="PROJ"
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == [{"key": "PROJ-1"}, {"key": "PROJ-2"}]


def test_jira_get_issue_returns_error_text_on_404_instead_of_raising(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errorMessages": ["Issue does not exist"], "errors": {}})

    client = make_client(handler)

    result = handle_issue_tool("jira_get_issue", {"issue_key": "PROJ-999"}, client=client, project_key="PROJ")

    assert len(result) == 1
    assert result[0].text.startswith("Error:")
    assert "Issue does not exist" in result[0].text


def test_jira_create_issue_defaults_to_task_type_and_returns_created_issue(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "10001", "key": "PROJ-3", "self": "..."})

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_create_issue", {"title": "Fix login bug"}, client=client, project_key="PROJ"
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == {"id": "10001", "key": "PROJ-3", "self": "..."}


def test_jira_update_issue_returns_confirmation_message(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_update_issue", {"issue_key": "PROJ-1", "title": "New title"}, client=client, project_key="PROJ"
    )

    assert len(result) == 1
    body = json.loads(result[0].text)
    assert body["issue_key"] == "PROJ-1"
    assert "updated" in body["message"].lower()


def test_jira_link_issues_creates_link_and_returns_confirmation(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("issueLinkType"):
            return httpx.Response(200, json={"issueLinkTypes": [
                {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            ]})
        return httpx.Response(201)

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_link_issues",
        {"issue_key": "PROJ-1", "target_issue_key": "PROJ-2", "link_type": "blocks"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    body = json.loads(result[0].text)
    assert "PROJ-1" in body["message"]
    assert "PROJ-2" in body["message"]


def test_jira_link_issues_returns_error_text_when_link_type_not_found(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issueLinkTypes": [
            {"id": "10001", "name": "Relates", "inward": "relates to", "outward": "relates to"},
        ]})

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_link_issues",
        {"issue_key": "PROJ-1", "target_issue_key": "PROJ-2", "link_type": "Duplicate"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    assert result[0].text.startswith("Error:")
    assert "Duplicate" in result[0].text


def test_jira_transition_issue_moves_to_target_status_and_returns_confirmation(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/transitions") and request.method == "GET":
            return httpx.Response(200, json={"transitions": [
                {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
            ]})
        return httpx.Response(204)

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_transition_issue",
        {"issue_key": "PROJ-1", "target_status": "In Progress"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    body = json.loads(result[0].text)
    assert "PROJ-1" in body["message"]
    assert "In Progress" in body["message"]


def test_jira_transition_issue_returns_error_text_when_target_status_not_reachable(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transitions": [
            {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
        ]})

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_transition_issue",
        {"issue_key": "PROJ-1", "target_status": "Done"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    assert result[0].text.startswith("Error:")
    assert "Done" in result[0].text


def test_jira_create_issue_with_subtask_parent_sets_native_parent_field(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rest/api/2/issue") and request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "10005", "key": "PROJ-6", "self": "..."})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_create_issue",
        {"title": "Sub-task of PROJ-1", "issue_type": "Sub-task", "parent_key": "PROJ-1"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == {"id": "10005", "key": "PROJ-6", "self": "..."}
    assert captured["body"]["fields"]["parent"] == {"key": "PROJ-1"}


def test_jira_create_issue_with_epic_parent_sets_epic_link_field(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rest/api/2/issue/PROJ-1") and request.method == "GET":
            return httpx.Response(200, json={"key": "PROJ-1", "fields": {"issuetype": {"name": "Epic"}}})
        if path.endswith("/rest/api/2/issue/createmeta"):
            return httpx.Response(200, json={
                "projects": [{
                    "key": "PROJ",
                    "issuetypes": [{
                        "name": "Task",
                        "fields": {
                            "customfield_10008": {"name": "Epic Link"},
                            "summary": {"name": "Summary"},
                        },
                    }],
                }]
            })
        if path.endswith("/rest/api/2/issue") and request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "10006", "key": "PROJ-7", "self": "..."})
        raise AssertionError(f"Unexpected request: {request.method} {path}")

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_create_issue",
        {"title": "Task under Epic", "issue_type": "Task", "parent_key": "PROJ-1"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == {"id": "10006", "key": "PROJ-7", "self": "..."}
    assert captured["body"]["fields"]["customfield_10008"] == "PROJ-1"


def test_jira_create_issue_with_non_epic_non_subtask_parent_falls_back_to_relates_link(make_client):
    link_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rest/api/2/issue/PROJ-1") and request.method == "GET":
            return httpx.Response(200, json={"key": "PROJ-1", "fields": {"issuetype": {"name": "Story"}}})
        if path.endswith("/rest/api/2/issue") and request.method == "POST":
            return httpx.Response(201, json={"id": "10007", "key": "PROJ-8", "self": "..."})
        if path.endswith("/rest/api/2/issueLinkType"):
            return httpx.Response(200, json={"issueLinkTypes": [
                {"id": "10001", "name": "Relates", "inward": "relates to", "outward": "relates to"},
            ]})
        if path.endswith("/rest/api/2/issueLink") and request.method == "POST":
            link_calls.append(json.loads(request.content))
            return httpx.Response(201)
        raise AssertionError(f"Unexpected request: {request.method} {path}")

    client = make_client(handler)

    result = handle_issue_tool(
        "jira_create_issue",
        {"title": "Task under Story", "issue_type": "Task", "parent_key": "PROJ-1"},
        client=client,
        project_key="PROJ",
    )

    assert len(result) == 1
    assert json.loads(result[0].text) == {"id": "10007", "key": "PROJ-8", "self": "..."}
    assert link_calls == [{
        "type": {"id": "10001"},
        "inwardIssue": {"key": "PROJ-8"},
        "outwardIssue": {"key": "PROJ-1"},
    }]
