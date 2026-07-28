"""Jira REST API v2 client (Data Center / Server, not Cloud)."""
from __future__ import annotations

import httpx


class JiraApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Jira API error {status_code}: {message}")


def _add_name_field(fields: dict, key: str, value: str | None) -> None:
    if value is not None:
        fields[key] = {"name": value}


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    messages = body.get("errorMessages") or []
    if messages:
        return "; ".join(messages)
    errors = body.get("errors") or {}
    if errors:
        return "; ".join(f"{k}: {v}" for k, v in errors.items())
    return resp.text


class JiraClient:
    def __init__(self, base_url: str, token: str, ssl_verify: bool = True, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            verify=ssl_verify,
            transport=transport,
        )

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise JiraApiError(resp.status_code, _extract_error_message(resp))

    def get_issue(self, issue_key: str) -> dict:
        resp = self._http.get(f"/rest/api/2/issue/{issue_key}")
        self._raise_for_status(resp)
        return resp.json()

    def list_issues(
        self,
        project_key: str,
        status: str | None = None,
        label: str | None = None,
        assignee: str | None = None,
        per_page: int = 20,
    ) -> list[dict]:
        clauses = [f'project = "{project_key}"']
        if status:
            clauses.append(f'status = "{status}"')
        if label:
            clauses.append(f'labels = "{label}"')
        if assignee:
            clauses.append(f'assignee = "{assignee}"')
        jql = " AND ".join(clauses)

        resp = self._http.get("/rest/api/2/search", params={"jql": jql, "maxResults": per_page})
        self._raise_for_status(resp)
        return resp.json().get("issues", [])

    def create_issue(
        self,
        project_key: str,
        title: str,
        description: str | None = None,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        components: list[str] | None = None,
        due_date: str | None = None,
        extra_fields: dict | None = None,
    ) -> dict:
        fields: dict = {
            "project": {"key": project_key},
            "summary": title,
            "issuetype": {"name": issue_type},
        }
        if description is not None:
            fields["description"] = description
        if labels:
            fields["labels"] = labels
        _add_name_field(fields, "assignee", assignee)
        _add_name_field(fields, "priority", priority)
        if components:
            fields["components"] = [{"name": name} for name in components]
        if due_date is not None:
            fields["duedate"] = due_date
        if extra_fields:
            fields.update(extra_fields)

        resp = self._http.post("/rest/api/2/issue", json={"fields": fields})
        self._raise_for_status(resp)
        return resp.json()

    def update_issue(
        self,
        issue_key: str,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        assignee: str | None = None,
        priority: str | None = None,
    ) -> None:
        fields: dict = {}
        if title is not None:
            fields["summary"] = title
        if description is not None:
            fields["description"] = description
        if labels is not None:
            fields["labels"] = labels
        _add_name_field(fields, "assignee", assignee)
        _add_name_field(fields, "priority", priority)

        resp = self._http.put(f"/rest/api/2/issue/{issue_key}", json={"fields": fields})
        self._raise_for_status(resp)

    def get_link_types(self) -> list[dict]:
        resp = self._http.get("/rest/api/2/issueLinkType")
        self._raise_for_status(resp)
        return resp.json().get("issueLinkTypes", [])

    def create_link(self, issue_key: str, target_issue_key: str, link_type_id: str) -> None:
        resp = self._http.post("/rest/api/2/issueLink", json={
            "type": {"id": link_type_id},
            "inwardIssue": {"key": issue_key},
            "outwardIssue": {"key": target_issue_key},
        })
        self._raise_for_status(resp)

    def get_transitions(self, issue_key: str) -> list[dict]:
        resp = self._http.get(f"/rest/api/2/issue/{issue_key}/transitions")
        self._raise_for_status(resp)
        return resp.json().get("transitions", [])

    def do_transition(self, issue_key: str, transition_id: str) -> None:
        resp = self._http.post(
            f"/rest/api/2/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )
        self._raise_for_status(resp)

    def get_create_meta(self, project_key: str, issue_type: str) -> dict:
        resp = self._http.get("/rest/api/2/issue/createmeta", params={
            "projectKeys": project_key,
            "issuetypeNames": issue_type,
            "expand": "projects.issuetypes.fields",
        })
        self._raise_for_status(resp)

        for project in resp.json().get("projects", []):
            for issuetype in project.get("issuetypes", []):
                if issuetype.get("name") == issue_type:
                    return issuetype.get("fields", {})
        return {}
