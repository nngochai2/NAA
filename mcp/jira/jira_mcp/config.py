"""Jira MCP configuration — loaded once from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class JiraConfig:
    url: str
    token: str
    project_key: str
    ssl_verify: bool


@lru_cache(maxsize=1)
def get_config() -> JiraConfig:
    load_dotenv()
    return JiraConfig(
        url=os.environ["JIRA_URL"],
        token=os.environ["JIRA_PAT"],
        project_key=os.environ["JIRA_PROJECT_KEY"],
        ssl_verify=os.environ.get("JIRA_SSL_VERIFY", "true").lower() != "false",
    )
