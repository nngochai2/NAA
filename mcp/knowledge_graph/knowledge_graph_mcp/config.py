"""Knowledge Graph MCP configuration — loaded once from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# mcp/knowledge_graph/ — the directory holding meta.yml and .env
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class KnowledgeGraphConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    host: str
    port: int
    vault_root: str
    staging_file: Path


@lru_cache(maxsize=1)
def get_config() -> KnowledgeGraphConfig:
    load_dotenv()
    return KnowledgeGraphConfig(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
        vault_root=os.getenv("VAULT_ROOT", ""),
        # Staging file persists notes awaiting human review across server restarts.
        staging_file=Path(os.getenv("STAGING_FILE") or PACKAGE_ROOT / "staged_notes.json"),
    )
