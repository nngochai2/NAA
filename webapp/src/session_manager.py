"""Per-session state management for multi-user server deployment."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Lazy imports to avoid circular deps at module load time
def _make_session() -> "SessionState":
    from .compliance_scanner import ComplianceScanner
    from .processor import ProcessorService
    from .selection_service import SelectionService
    from .tree_builder import TreeBuilder
    from .vault_manager import VaultManager

    tree    = TreeBuilder()
    vault   = VaultManager()
    sel     = SelectionService(tree)
    scanner = ComplianceScanner(tree)
    proc    = ProcessorService(tree)
    return SessionState(vault=vault, tree=tree, sel=sel, scanner=scanner, proc=proc)


@dataclass
class SessionState:
    vault:          object   # VaultManager
    tree:           object   # TreeBuilder
    sel:            object   # SelectionService
    scanner:        object   # ComplianceScanner
    proc:           object   # ProcessorService
    neo4j_uri:      str | None = None
    neo4j_user:     str | None = None
    neo4j_password: str | None = None
    last_active:    float = field(default_factory=time.time)


class SessionManager:
    _SESSION_TTL = 7200  # 2 hours idle

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get_or_create(self, session_id: str | None) -> tuple[str, SessionState]:
        """Return (session_id, state). Creates a new session if id is unknown."""
        if session_id and session_id in self._sessions:
            state = self._sessions[session_id]
            state.last_active = time.time()
            return session_id, state

        new_id    = str(uuid.uuid4())
        new_state = _make_session()
        self._sessions[new_id] = new_state
        return new_id, new_state

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self._SESSION_TTL
        expired = [sid for sid, s in self._sessions.items() if s.last_active < cutoff]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    async def run_cleanup_loop(self) -> None:
        """Background coroutine — drop idle sessions every 10 minutes."""
        while True:
            await asyncio.sleep(600)
            self.cleanup_expired()


# Module-level singleton used by main.py
session_manager = SessionManager()
