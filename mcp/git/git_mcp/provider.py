"""Provider factory — returns the configured Git provider (GitLab or GitHub)."""
from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_provider():
    name = os.environ.get("GIT_PROVIDER", "gitlab").lower()
    if name == "github":
        from .providers.github_provider import GitHubProvider
        return GitHubProvider()
    if name == "gitlab":
        from .providers.gitlab_provider import GitLabProvider
        return GitLabProvider()
    raise ValueError(f"Unknown GIT_PROVIDER: {name!r}. Valid values: 'gitlab', 'github'.")
