"""GitLab provider — wraps python-gitlab."""
from __future__ import annotations

import os
from functools import lru_cache

import gitlab
import gitlab.exceptions


@lru_cache(maxsize=1)
def _get_client() -> gitlab.Gitlab:
    url   = os.environ.get("GITLAB_URL", "https://gitlab.com")
    token = os.environ.get("GITLAB_TOKEN")
    ssl   = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("false", "0", "no")
    if not token:
        raise RuntimeError("GITLAB_TOKEN is not set")
    return gitlab.Gitlab(url, private_token=token, ssl_verify=ssl)


class GitLabProvider:

    def resolve_repo_id(self, arguments: dict) -> str:
        rid = arguments.get("repo_id") or os.environ.get("GITLAB_PROJECT_ID", "")
        if not rid:
            raise ValueError("repo_id argument or GITLAB_PROJECT_ID env var is required")
        return rid

    def get_repo(self, repo_id: str):
        return _get_client().projects.get(repo_id)

    # ── Issues ──────────────────────────────────────────────────────────────

    def list_issues(self, repo, *, state="opened", labels=None, assignee=None, search=None, per_page=20) -> list[dict]:
        kwargs: dict = {"state": state, "per_page": per_page}
        if labels:
            kwargs["labels"] = labels
        if assignee:
            kwargs["assignee_username"] = assignee
        if search:
            kwargs["search"] = search
        return [self._issue_summary(i) for i in repo.issues.list(**kwargs)]

    def get_issue(self, repo, issue_number: int) -> dict:
        return self._issue_detail(repo.issues.get(issue_number))

    def create_issue(self, repo, *, title, description=None, labels=None, assignees=None, milestone_id=None, due_date=None) -> dict:
        data: dict = {"title": title}
        if description:
            data["description"] = description
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignee_ids"] = self._resolve_user_ids(assignees)
        if milestone_id:
            data["milestone_id"] = milestone_id
        if due_date:
            data["due_date"] = due_date
        return self._issue_summary(repo.issues.create(data))

    def update_issue(self, repo, issue_number: int, *, title=None, description=None, labels=None, state_event=None, assignees=None) -> dict:
        issue = repo.issues.get(issue_number)
        if title is not None:
            issue.title = title
        if description is not None:
            issue.description = description
        if labels is not None:
            issue.labels = labels
        if state_event:
            issue.state_event = state_event
        if assignees is not None:
            issue.assignee_ids = self._resolve_user_ids(assignees)
        issue.save()
        return self._issue_summary(issue)

    def close_issue(self, repo, issue_number: int) -> str:
        issue = repo.issues.get(issue_number)
        issue.state_event = "close"
        issue.save()
        return f"Issue #{issue_number} closed."

    def delete_issue(self, repo, issue_number: int) -> str:
        repo.issues.get(issue_number).delete()
        return f"Issue #{issue_number} deleted."

    def link_issues(self, repo, issue_number: int, target_issue_number: int, link_type: str = "relates_to") -> str:
        issue = repo.issues.get(issue_number)
        issue.links.create({
            "target_project_id": repo.id,
            "target_issue_iid":  target_issue_number,
            "link_type":         link_type,
        })
        return f"Issue #{issue_number} linked to #{target_issue_number} ({link_type})."

    # ── Pull requests (Merge Requests) ───────────────────────────────────────

    def list_pull_requests(self, repo, *, state="opened", source_branch=None, target_branch=None, author=None, search=None, per_page=20) -> list[dict]:
        kwargs: dict = {"state": state, "per_page": per_page}
        if source_branch:
            kwargs["source_branch"] = source_branch
        if target_branch:
            kwargs["target_branch"] = target_branch
        if author:
            kwargs["author_username"] = author
        if search:
            kwargs["search"] = search
        return [self._pr_summary(mr) for mr in repo.mergerequests.list(**kwargs)]

    def get_pull_request(self, repo, pr_number: int) -> dict:
        return self._pr_detail(repo.mergerequests.get(pr_number))

    def get_pull_request_changes(self, repo, pr_number: int) -> list[dict]:
        mr = repo.mergerequests.get(pr_number)
        return [
            {"old_path": c.get("old_path"), "new_path": c.get("new_path"), "diff": c.get("diff")}
            for c in mr.changes().get("changes", [])
        ]

    def get_pull_request_discussions(self, repo, pr_number: int) -> list[dict]:
        mr = repo.mergerequests.get(pr_number)
        result = []
        for d in mr.discussions.list():
            notes = [
                {
                    "author":     note.get("author", {}).get("username"),
                    "body":       note.get("body"),
                    "created_at": note.get("created_at"),
                    "resolvable": note.get("resolvable"),
                    "resolved":   note.get("resolved"),
                }
                for note in d.attributes.get("notes", [])
            ]
            result.append({"id": d.id, "notes": notes})
        return result

    def create_pull_request_note(self, repo, pr_number: int, body: str) -> dict:
        mr   = repo.mergerequests.get(pr_number)
        note = mr.notes.create({"body": body})
        return {"id": note.id, "author": note.author.get("username"), "body": note.body}

    def approve_pull_request(self, repo, pr_number: int) -> str:
        repo.mergerequests.get(pr_number).approve()
        return f"Merge request !{pr_number} approved."

    def merge_pull_request(self, repo, pr_number: int, *, message=None, squash=False, remove_source=False) -> str:
        mr     = repo.mergerequests.get(pr_number)
        kwargs: dict = {}
        if message:
            kwargs["merge_commit_message"] = message
        if squash:
            kwargs["squash"] = True
        if remove_source:
            kwargs["should_remove_source_branch"] = True
        mr.merge(**kwargs)
        return f"Merge request !{pr_number} merged."

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _resolve_user_ids(self, usernames: list[str]) -> list[int]:
        gl  = _get_client()
        ids = []
        for username in usernames:
            users = gl.users.list(username=username)
            if users:
                ids.append(users[0].id)
        return ids

    def _issue_summary(self, issue) -> dict:
        return {
            "number":     issue.iid,
            "title":      issue.title,
            "state":      issue.state,
            "author":     issue.author.get("username") if issue.author else None,
            "assignees":  [a.get("username") for a in (issue.assignees or [])],
            "labels":     issue.labels,
            "created_at": issue.created_at,
            "updated_at": issue.updated_at,
            "web_url":    issue.web_url,
        }

    def _issue_detail(self, issue) -> dict:
        d = self._issue_summary(issue)
        d.update({
            "description": issue.description,
            "milestone":   issue.milestone.get("title") if issue.milestone else None,
            "due_date":    getattr(issue, "due_date", None),
            "closed_at":   getattr(issue, "closed_at", None),
            "notes_count": issue.user_notes_count,
        })
        return d

    def _pr_summary(self, mr) -> dict:
        return {
            "number":        mr.iid,
            "title":         mr.title,
            "state":         mr.state,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "author":        mr.author.get("username") if mr.author else None,
            "assignees":     [a.get("username") for a in (mr.assignees or [])],
            "reviewers":     [r.get("username") for r in (getattr(mr, "reviewers", []) or [])],
            "labels":        mr.labels,
            "draft":         mr.draft,
            "created_at":    mr.created_at,
            "updated_at":    mr.updated_at,
            "web_url":       mr.web_url,
        }

    def _pr_detail(self, mr) -> dict:
        d = self._pr_summary(mr)
        d.update({
            "description":   mr.description,
            "merge_status":  mr.merge_status,
            "sha":           mr.sha,
            "squash":        mr.squash,
            "notes_count":   mr.user_notes_count,
            "changes_count": getattr(mr, "changes_count", None),
        })
        return d
