"""Builds and caches the vault folder hierarchy."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ComplianceStatus, DocumentInfo, FolderDetailResponse, FolderNode, FormatCompliance

# Folders to skip when scanning the vault
_SKIP_FOLDERS = {".obsidian", ".git", "_staging", ".trash"}


def _folder_id(relative_path: str) -> str:
    """Stable, URL-safe ID derived from the folder's relative path."""
    if not relative_path:
        return "root"
    return hashlib.sha1(relative_path.encode()).hexdigest()[:12]


def _doc_id(relative_path: str) -> str:
    return hashlib.sha1(relative_path.encode()).hexdigest()[:12]


def _is_hidden(parts: tuple[str, ...]) -> bool:
    return any(p.startswith(".") for p in parts)


class TreeBuilder:
    """
    Builds a FolderNode tree from the filesystem and maintains a flat
    index (folder_id → FolderNode and folder_id → abs_path) for fast
    lookup by the selection and compliance services.
    """

    def __init__(self) -> None:
        # folder_id → FolderNode (the live tree nodes, mutated by compliance)
        self._index:      dict[str, FolderNode] = {}
        # folder_id → absolute Path on disk
        self._paths:      dict[str, Path]       = {}
        # root FolderNode (None until build() is called)
        self._root:       FolderNode | None     = None
        self._vault_root: Path | None           = None
        self._built_at:   str | None            = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def build(self, vault_root: Path) -> FolderNode:
        """Scan vault_root and rebuild the in-memory tree. Returns root node."""
        self._index.clear()
        self._paths.clear()
        self._vault_root = vault_root

        root = self._scan_dir(vault_root, vault_root, parent_id=None, level=0)
        self._root     = root
        self._built_at = datetime.now(timezone.utc).isoformat()
        return root

    def get_root(self) -> FolderNode | None:
        return self._root

    def get_folder(self, folder_id: str) -> FolderNode | None:
        return self._index.get(folder_id)

    def get_folder_path(self, folder_id: str) -> Path | None:
        return self._paths.get(folder_id)

    def all_folder_ids(self) -> list[str]:
        return list(self._index.keys())

    def get_folder_documents(self, folder_id: str) -> list[DocumentInfo]:
        node = self._index.get(folder_id)
        abs_path = self._paths.get(folder_id)
        if not node or not abs_path or not self._vault_root:
            return []
        docs = []
        for f in sorted(abs_path.iterdir()):
            if f.is_file() and f.suffix == ".md":
                rel = str(f.relative_to(self._vault_root)).replace("\\", "/")
                docs.append(DocumentInfo(
                    id=_doc_id(rel),
                    filename=f.name,
                    relative_path=rel,
                    folder_id=folder_id,
                    size_bytes=f.stat().st_size,
                    modified_at=datetime.fromtimestamp(
                        f.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    format_compliance=FormatCompliance.UNRECOGNIZED,  # filled by compliance scanner
                ))
        return docs

    def get_folder_detail(self, folder_id: str) -> FolderDetailResponse | None:
        node = self._index.get(folder_id)
        if not node:
            return None
        docs = self.get_folder_documents(folder_id)
        return FolderDetailResponse(
            folder=node,
            documents=docs,
            documents_count=node.document_count,
        )

    def update_compliance(
        self,
        folder_id: str,
        compliant: int,
        legacy: int,
        unrecognized: int,
    ) -> None:
        """Called by ComplianceScanner to push results into the tree."""
        node = self._index.get(folder_id)
        if not node:
            return
        node.compliance_status  = ComplianceStatus.SCANNED
        node.compliant_docs     = compliant
        node.legacy_docs        = legacy
        node.unrecognized_docs  = unrecognized
        self._propagate_compliance(folder_id)

    def mark_compliance_error(self, folder_id: str) -> None:
        node = self._index.get(folder_id)
        if node:
            node.compliance_status = ComplianceStatus.ERROR

    def built_at(self) -> str | None:
        return self._built_at

    def vault_root(self) -> Path | None:
        return self._vault_root

    # ── Internal ────────────────────────────────────────────────────────────────

    def _scan_dir(
        self,
        directory: Path,
        vault_root: Path,
        parent_id: str | None,
        level: int,
    ) -> FolderNode:
        rel = str(directory.relative_to(vault_root)).replace("\\", "/")
        if rel == ".":
            rel = ""
        fid  = _folder_id(rel)
        name = directory.name if rel else vault_root.name

        doc_count   = 0
        total_bytes = 0
        children:   list[FolderNode] = []

        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            entries = []

        for entry in entries:
            entry_rel_parts = entry.relative_to(vault_root).parts
            if _is_hidden(entry_rel_parts) or entry.name in _SKIP_FOLDERS:
                continue
            if entry.is_dir():
                child = self._scan_dir(entry, vault_root, parent_id=fid, level=level + 1)
                children.append(child)
                total_bytes += child.total_size_bytes
            elif entry.is_file() and entry.suffix == ".md":
                try:
                    sz = entry.stat().st_size
                    doc_count   += 1
                    total_bytes += sz
                except OSError:
                    pass

        node = FolderNode(
            id=fid,
            name=name,
            relative_path=rel,
            level=level,
            parent_id=parent_id,
            document_count=doc_count,
            subfolder_count=len(children),
            total_size_bytes=total_bytes,
            compliance_status=ComplianceStatus.PENDING,
            children=children,
        )

        self._index[fid] = node
        self._paths[fid]  = directory
        return node

    def _propagate_compliance(self, folder_id: str) -> None:
        """Bubble-up aggregated compliance counts to all ancestor nodes."""
        node = self._index.get(folder_id)
        if not node or not self._vault_root:
            return

        # Recompute ancestors by walking the path
        path = self._paths.get(folder_id)
        if not path:
            return

        current = path.parent
        while current != self._vault_root.parent:
            rel = str(current.relative_to(self._vault_root)).replace("\\", "/")
            if rel == ".":
                rel = ""
            pid = _folder_id(rel)
            parent_node = self._index.get(pid)
            if not parent_node:
                break
            # Aggregate compliance across all direct children that have been scanned
            total_c = total_l = total_u = 0
            all_scanned = True
            for child in parent_node.children:
                if child.compliance_status != ComplianceStatus.SCANNED:
                    all_scanned = False
                    continue
                total_c += child.compliant_docs    or 0
                total_l += child.legacy_docs       or 0
                total_u += child.unrecognized_docs or 0
            # Also include docs directly in this folder
            if parent_node.compliance_status == ComplianceStatus.SCANNED:
                pass  # already set; don't double-count
            if all_scanned:
                parent_node.compliance_status  = ComplianceStatus.SCANNED
                parent_node.compliant_docs     = total_c
                parent_node.legacy_docs        = total_l
                parent_node.unrecognized_docs  = total_u
            current = current.parent
            if current == self._vault_root.parent:
                break
