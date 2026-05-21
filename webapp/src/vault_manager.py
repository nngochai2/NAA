"""Vault connection and validation — in-memory state, no disk persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .schemas import VaultInfo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Vault validation ───────────────────────────────────────────────────────────

class VaultValidationError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code    = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def validate_vault_path(path: str) -> Path:
    """
    Check that path exists, is readable, and contains .obsidian/.
    Returns the resolved Path on success, raises VaultValidationError otherwise.
    """
    p = Path(path)

    if not p.exists():
        raise VaultValidationError(
            "path_not_found",
            "Vault directory does not exist.",
            {"path": str(p)},
        )

    if not p.is_dir():
        raise VaultValidationError(
            "invalid_vault_path",
            "The path is not a directory.",
            {"path": str(p)},
        )

    if not os.access(p, os.R_OK):
        raise VaultValidationError(
            "permission_denied",
            "Cannot read vault directory. Please check folder permissions.",
            {"path": str(p), "reason": "read_permission_required"},
        )

    if not (p / ".obsidian").exists():
        raise VaultValidationError(
            "invalid_vault_path",
            "Directory does not contain .obsidian/ subdirectory. "
            "Please select a valid Obsidian vault.",
            {"path_checked": str(p), "reason": "missing_obsidian_marker"},
        )

    return p.resolve()


# ── VaultManager ───────────────────────────────────────────────────────────────

class VaultManager:
    """Per-session vault state stored entirely in memory."""

    def __init__(self) -> None:
        self._info: VaultInfo | None = None

    def connect(self, vault_path: str, display_name: str | None = None) -> VaultInfo:
        resolved = validate_vault_path(vault_path)
        now  = _now()
        name = display_name or resolved.name
        self._info = VaultInfo(
            path=str(resolved),
            display_name=name,
            connected_at=now,
            last_accessed=now,
        )
        return self._info

    def get_current(self) -> VaultInfo | None:
        if self._info:
            self._info = self._info.model_copy(update={"last_accessed": _now()})
        return self._info

    def validate_current(self) -> tuple[bool, str | None]:
        if not self._info:
            return False, "no_vault_configured"
        try:
            validate_vault_path(self._info.path)
            return True, None
        except VaultValidationError as e:
            return False, e.code

    def disconnect(self) -> None:
        self._info = None

    def get_vault_path(self) -> Path | None:
        return Path(self._info.path) if self._info else None

    def count_contents(self, vault_root: Path) -> tuple[int, int]:
        """Return (folder_count, document_count) — skips hidden dirs."""
        folders = docs = 0
        for item in vault_root.rglob("*"):
            if any(p.startswith(".") for p in item.relative_to(vault_root).parts):
                continue
            if item.is_dir():
                folders += 1
            elif item.suffix == ".md":
                docs += 1
        return folders, docs
