"""GitHub provider — wraps PyGithub."""
from __future__ import annotations

import os
from functools import lru_cache

from github import Auth, Github


@lru_cache(maxsize=1)
def _get_client() -> Github:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set")
    return Github(auth=Auth.Token(token))


class GitHubProvider:

    def resolve_repo_id(self, arguments: dict) -> str:
        rid = arguments.get("repo_id") or os.environ.get("GITHUB_REPO", "")
        if not rid:
            raise ValueError("repo_id argument or GITHUB_REPO env var is required (format: owner/repo)")
        return rid

    def get_repo(self, repo_id: str):
        return _get_client().get_repo(repo_id)

    # ── Issues ──────────────────────────────────────────────────────────────

    def list_issues(self, repo, *, state="opened", labels=None, assignee=None, search=None, per_page=20) -> list[dict]:
        # Normalise GitLab "opened" to GitHub "open"
        gh_state = "open" if state == "opened" else state
        kwargs: dict = {"state": gh_state}
        if labels:
            kwargs["labels"] = labels if isinstance(labels, list) else [labels]
        if assignee:
            kwargs["assignee"] = assignee
        result = []
        for issue in repo.get_issues(**kwargs):
            if len(result) >= per_page:
                break
            if "/pull/" in issue.html_url:  # GitHub issues API returns PRs too
                continue
            result.append(self._issue_summary(issue))
        return result

    def get_issue(self, repo, issue_number: int) -> dict:
        return self._issue_detail(repo.get_issue(issue_number))

    def create_issue(self, repo, *, title, description=None, labels=None, assignees=None, milestone_id=None, due_date=None) -> dict:
        kwargs: dict = {"title": title}
        if description:
            kwargs["body"] = description
        if labels:
            kwargs["labels"] = labels if isinstance(labels, list) else [labels]
        if assignees:
            kwargs["assignees"] = assignees
        if milestone_id:
            kwargs["milestone"] = repo.get_milestone(int(milestone_id))
        return self._issue_summary(repo.create_issue(**kwargs))

    def update_issue(self, repo, issue_number: int, *, title=None, description=None, labels=None, state_event=None, assignees=None) -> dict:
        issue  = repo.get_issue(issue_number)
        kwargs: dict = {}
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["body"] = description
        if labels is not None:
            kwargs["labels"] = labels
        if assignees is not None:
            kwargs["assignees"] = assignees
        if state_event == "close":
            kwargs["state"] = "closed"
        elif state_event == "reopen":
            kwargs["state"] = "open"
        issue.edit(**kwargs)
        return self._issue_summary(issue)

    def close_issue(self, repo, issue_number: int) -> str:
        repo.get_issue(issue_number).edit(state="closed")
        return f"Issue #{issue_number} closed."

    def delete_issue(self, repo, issue_number: int) -> str:
        return (
            f"GitHub does not support deleting issues via the API. "
            f"Use git_close_issue to close issue #{issue_number} instead."
        )

    def link_issues(self, repo, issue_number: int, target_issue_number: int, link_type: str = "relates_to") -> str:
        repo.get_issue(issue_number).create_comment(
            f"Linked to #{target_issue_number} ({link_type})"
        )
        return f"Added link comment on issue #{issue_number} referencing #{target_issue_number}."

    # ── Pull Requests ────────────────────────────────────────────────────────

    def list_pull_requests(self, repo, *, state="opened", source_branch=None, target_branch=None, author=None, search=None, per_page=20) -> list[dict]:
        gh_state = "open" if state in ("opened", "open") else state
        kwargs: dict = {"state": gh_state}
        if target_branch:
            kwargs["base"] = target_branch
        if source_branch:
            kwargs["head"] = source_branch
        result = []
        for pr in repo.get_pulls(**kwargs):
            if len(result) >= per_page:
                break
            result.append(self._pr_summary(pr))
        return result

    def get_pull_request(self, repo, pr_number: int) -> dict:
        return self._pr_detail(repo.get_pull(pr_number))

    def get_pull_request_changes(self, repo, pr_number: int) -> list[dict]:
        return [
            {
                "old_path": f.previous_filename or f.filename,
                "new_path": f.filename,
                "diff":     f.patch,
            }
            for f in repo.get_pull(pr_number).get_files()
        ]

    def get_pull_request_discussions(self, repo, pr_number: int) -> list[dict]:
        pr     = repo.get_pull(pr_number)
        result = []
        for c in pr.get_issue_comments():
            result.append({"notes": [{"author": c.user.login if c.user else None, "body": c.body, "created_at": str(c.created_at), "resolvable": False, "resolved": False}]})
        for c in pr.get_review_comments():
            result.append({"notes": [{"author": c.user.login if c.user else None, "body": c.body, "created_at": str(c.created_at), "resolvable": True, "resolved": False}]})
        return result

    def create_pull_request_note(self, repo, pr_number: int, body: str) -> dict:
        comment = repo.get_pull(pr_number).create_issue_comment(body)
        return {"id": comment.id, "author": comment.user.login if comment.user else None, "body": comment.body}

    def approve_pull_request(self, repo, pr_number: int) -> str:
        repo.get_pull(pr_number).create_review(event="APPROVE")
        return f"Pull request #{pr_number} approved."

    def merge_pull_request(self, repo, pr_number: int, *, message=None, squash=False, remove_source=False) -> str:
        pr     = repo.get_pull(pr_number)
        kwargs: dict = {"merge_method": "squash" if squash else "merge"}
        if message:
            kwargs["commit_message"] = message
        pr.merge(**kwargs)
        if remove_source:
            try:
                pr.head.repo.get_git_ref(f"heads/{pr.head.ref}").delete()
            except Exception:
                pass
        return f"Pull request #{pr_number} merged."

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _issue_summary(self, issue) -> dict:
        return {
            "number":     issue.number,
            "title":      issue.title,
            "state":      issue.state,
            "author":     issue.user.login if issue.user else None,
            "assignees":  [a.login for a in issue.assignees],
            "labels":     [lb.name for lb in issue.labels],
            "created_at": str(issue.created_at),
            "updated_at": str(issue.updated_at),
            "web_url":    issue.html_url,
        }

    def _issue_detail(self, issue) -> dict:
        d = self._issue_summary(issue)
        d.update({
            "description": issue.body,
            "milestone":   issue.milestone.title if issue.milestone else None,
            "due_date":    None,
            "closed_at":   str(issue.closed_at) if issue.closed_at else None,
            "notes_count": issue.comments,
        })
        return d

    def _pr_summary(self, pr) -> dict:
        return {
            "number":        pr.number,
            "title":         pr.title,
            "state":         pr.state,
            "source_branch": pr.head.ref,
            "target_branch": pr.base.ref,
            "author":        pr.user.login if pr.user else None,
            "assignees":     [a.login for a in pr.assignees],
            "reviewers":     [r.login for r in pr.requested_reviewers],
            "labels":        [lb.name for lb in pr.labels],
            "draft":         pr.draft,
            "created_at":    str(pr.created_at),
            "updated_at":    str(pr.updated_at),
            "web_url":       pr.html_url,
        }

    def _pr_detail(self, pr) -> dict:
        d = self._pr_summary(pr)
        d.update({
            "description":   pr.body,
            "merge_status":  pr.mergeable_state,
            "sha":           pr.head.sha,
            "squash":        False,
            "notes_count":   pr.comments,
            "changes_count": pr.changed_files,
        })
        return d
