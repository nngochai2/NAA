import json

import httpx
import pytest

from jira_mcp.client import JiraApiError


def test_get_issue_sends_bearer_auth_and_returns_parsed_json(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth_header"] = request.headers.get("authorization")
        return httpx.Response(200, json={"key": "PROJ-1", "fields": {"summary": "Test issue"}})

    client = make_client(handler)

    result = client.get_issue("PROJ-1")

    assert result == {"key": "PROJ-1", "fields": {"summary": "Test issue"}}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/PROJ-1"
    assert captured["auth_header"] == "Bearer test-token"


def test_get_issue_raises_jira_api_error_with_message_on_404(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errorMessages": ["Issue does not exist"], "errors": {}})

    client = make_client(handler)

    with pytest.raises(JiraApiError) as exc_info:
        client.get_issue("PROJ-999")

    assert exc_info.value.status_code == 404
    assert "Issue does not exist" in str(exc_info.value)


def test_list_issues_builds_jql_from_filters_and_returns_issues(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["jql"] = request.url.params.get("jql")
        captured["max_results"] = request.url.params.get("maxResults")
        return httpx.Response(200, json={"issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]})

    client = make_client(handler)

    result = client.list_issues(
        project_key="PROJ", status="In Progress", label="backend", assignee="jdoe", per_page=10
    )

    assert result == [{"key": "PROJ-1"}, {"key": "PROJ-2"}]
    assert 'project = "PROJ"' in captured["jql"]
    assert 'status = "In Progress"' in captured["jql"]
    assert 'labels = "backend"' in captured["jql"]
    assert 'assignee = "jdoe"' in captured["jql"]
    assert captured["max_results"] == "10"


def test_list_issues_with_only_project_key_omits_optional_clauses(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["jql"] = request.url.params.get("jql")
        return httpx.Response(200, json={"issues": []})

    client = make_client(handler)

    client.list_issues(project_key="PROJ")

    assert captured["jql"] == 'project = "PROJ"'


def test_create_issue_with_title_only_defaults_to_task_type(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"id": "10001", "key": "PROJ-3", "self": "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/10001"},
        )

    client = make_client(handler)

    result = client.create_issue(project_key="PROJ", title="Fix login bug")

    assert result == {
        "id": "10001", "key": "PROJ-3", "self": "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/10001",
    }
    assert captured["method"] == "POST"
    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue"
    fields = captured["body"]["fields"]
    assert fields["project"] == {"key": "PROJ"}
    assert fields["summary"] == "Fix login bug"
    assert fields["issuetype"] == {"name": "Task"}


def test_create_issue_includes_labels_assignee_and_priority_when_provided(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "10002", "key": "PROJ-4", "self": "..."})

    client = make_client(handler)

    client.create_issue(
        project_key="PROJ",
        title="Add rate limiting",
        issue_type="Bug",
        labels=["backend", "urgent"],
        assignee="jdoe",
        priority="High",
    )

    fields = captured["body"]["fields"]
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["labels"] == ["backend", "urgent"]
    assert fields["assignee"] == {"name": "jdoe"}
    assert fields["priority"] == {"name": "High"}


def test_create_issue_merges_extra_fields_into_payload(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "10003", "key": "PROJ-5", "self": "..."})

    client = make_client(handler)

    client.create_issue(
        project_key="PROJ",
        title="Sub-task of PROJ-1",
        issue_type="Sub-task",
        extra_fields={"parent": {"key": "PROJ-1"}},
    )

    fields = captured["body"]["fields"]
    assert fields["parent"] == {"key": "PROJ-1"}
    assert fields["summary"] == "Sub-task of PROJ-1"


def test_update_issue_with_only_title_sends_only_summary_field(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(204)

    client = make_client(handler)

    client.update_issue("PROJ-1", title="New title")

    assert captured["method"] == "PUT"
    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/PROJ-1"
    assert captured["body"] == {"fields": {"summary": "New title"}}


def test_update_issue_with_all_fields_sends_all_fields(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(204)

    client = make_client(handler)

    client.update_issue(
        "PROJ-1",
        title="New title",
        description="New description",
        labels=["backend"],
        assignee="jdoe",
        priority="High",
    )

    assert captured["body"] == {
        "fields": {
            "summary": "New title",
            "description": "New description",
            "labels": ["backend"],
            "assignee": {"name": "jdoe"},
            "priority": {"name": "High"},
        }
    }


def test_get_link_types_returns_parsed_list(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issueLinkTypes": [
            {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        ]})

    client = make_client(handler)

    result = client.get_link_types()

    assert result == [
        {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
    ]


def test_create_link_sends_correct_request_body(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(201)

    client = make_client(handler)

    client.create_link("PROJ-1", "PROJ-2", "10000")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issueLink"
    assert captured["body"] == {
        "type": {"id": "10000"},
        "inwardIssue": {"key": "PROJ-1"},
        "outwardIssue": {"key": "PROJ-2"},
    }


def test_get_transitions_returns_parsed_list(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transitions": [
            {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
        ]})

    client = make_client(handler)

    result = client.get_transitions("PROJ-1")

    assert result == [
        {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
    ]


def test_do_transition_sends_correct_request_body(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(204)

    client = make_client(handler)

    client.do_transition("PROJ-1", "11")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://insight.fsoft.com.vn/jiradc/rest/api/2/issue/PROJ-1/transitions"
    assert captured["body"] == {"transition": {"id": "11"}}


def test_get_create_meta_returns_fields_dict_for_project_and_issue_type(make_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={
            "projects": [
                {
                    "key": "PROJ",
                    "issuetypes": [
                        {
                            "name": "Task",
                            "fields": {
                                "customfield_10008": {"name": "Epic Link"},
                                "summary": {"name": "Summary"},
                            },
                        }
                    ],
                }
            ]
        })

    client = make_client(handler)

    result = client.get_create_meta("PROJ", "Task")

    assert result == {
        "customfield_10008": {"name": "Epic Link"},
        "summary": {"name": "Summary"},
    }
    assert captured["params"]["projectKeys"] == "PROJ"
    assert captured["params"]["issuetypeNames"] == "Task"
