"""Jenkins MCP configuration — loaded once from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


def _csv(value: str | None) -> frozenset[str]:
    return frozenset(part.strip() for part in (value or "").split(",") if part.strip())


@dataclass(frozen=True)
class JenkinsConfig:
    url: str
    ssl_verify: bool
    timeout: float
    allow_tools: frozenset[str] = frozenset()
    block_tools: frozenset[str] = frozenset()

    def is_tool_enabled(self, name: str) -> bool:
        """The allow list, when set, wins over the block list."""
        if self.allow_tools:
            return name in self.allow_tools
        return name not in self.block_tools


@lru_cache(maxsize=1)
def get_config() -> JenkinsConfig:
    load_dotenv()
    return JenkinsConfig(
        url=os.environ["JENKINS_URL"],
        ssl_verify=os.environ.get("JENKINS_SSL_VERIFY", "true").lower() != "false",
        timeout=float(os.environ.get("JENKINS_TIMEOUT", "30")),
        allow_tools=_csv(os.environ.get("JENKINS_ALLOW_TOOLS")),
        block_tools=_csv(os.environ.get("JENKINS_BLOCK_TOOLS")),
    )
