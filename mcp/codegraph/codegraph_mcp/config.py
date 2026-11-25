"""Code Graph MCP configuration — loaded once from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class CodegraphConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str  # blank = no auth (jQAssistant embedded Neo4j)
    host: str
    port: int


@lru_cache(maxsize=1)
def get_config() -> CodegraphConfig:
    load_dotenv()
    return CodegraphConfig(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8001")),
    )
