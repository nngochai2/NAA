"""Folder selection management with cascade logic — in-memory state."""

from __future__ import annotations

from datetime import datetime, timezone

from .schemas import (
    SelectionState,
    SelectionSummaryFolder,
    SelectionSummaryResponse,
)
from .tree_builder import TreeBuilder


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SelectionService:
    def __init__(self, tree: TreeBuilder) -> None:
        self._tree        = tree
        self._selected:   set[str] = set()
        self._updated_at: str = _now()

    # ── Cascade helpers ────────────────────────────────────────────────────────

    def _descendants(self, folder_id: str) -> set[str]:
        node = self._tree.get_folder(folder_id)
        if not node:
            return set()
        result: set[str] = set()
        queue = list(node.children)
        while queue:
            child = queue.pop()
            result.add(child.id)
            queue.extend(child.children)
        return result

    def _all_ids(self, folder_id: str) -> set[str]:
        return {folder_id} | self._descendants(folder_id)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_ids(self, folder_ids: list[str]) -> list[str]:
        return [fid for fid in folder_ids if not self._tree.get_folder(fid)]

    # ── Aggregation ───────────────────────────────────────────────────────────

    def _aggregate(self) -> tuple[int, int, int, int, list[SelectionSummaryFolder]]:
        total_docs  = compliant = legacy = unrecognized = 0
        folder_list: list[SelectionSummaryFolder] = []

        for fid in self._selected:
            node = self._tree.get_folder(fid)
            if not node:
                continue
            total_docs += node.document_count
            if node.compliant_docs    is not None:
                compliant    += node.compliant_docs
            if node.legacy_docs       is not None:
                legacy       += node.legacy_docs
            if node.unrecognized_docs is not None:
                unrecognized += node.unrecognized_docs
            folder_list.append(SelectionSummaryFolder(
                id=fid,
                name=node.name,
                relative_path=node.relative_path,
                document_count=node.document_count,
            ))

        return total_docs, compliant, legacy, unrecognized, folder_list

    def _compliance_pct(self, total: int, compliant: int) -> float:
        return round(compliant / total * 100, 2) if total > 0 else 0.0

    # ── Core operations ────────────────────────────────────────────────────────

    def get_state(self, vault_id: str = "") -> SelectionState | None:
        if not self._selected:
            return None
        total, compliant, legacy, unrecognized, folders = self._aggregate()
        return SelectionState(
            vault_id=vault_id,
            selected_folder_ids=sorted(self._selected),
            selected_folders=sorted(folders, key=lambda f: f.relative_path),
            total_selected_docs=total,
            total_selected_compliant=compliant,
            total_selected_legacy=legacy,
            total_selected_unrecognized=unrecognized,
            compliance_percentage=self._compliance_pct(total, compliant),
            created_at=self._updated_at,
        )

    def set_selection(self, folder_ids: list[str]) -> SelectionState:
        self._selected   = set(folder_ids)
        self._updated_at = _now()
        return self.get_state()  # type: ignore[return-value]

    def add_folders(self, folder_ids: list[str], cascade: bool = True) -> set[str]:
        added: set[str] = set()
        for fid in folder_ids:
            ids = self._all_ids(fid) if cascade else {fid}
            new = ids - self._selected
            self._selected |= new
            added |= new
        if added:
            self._updated_at = _now()
        return added

    def remove_folders(self, folder_ids: list[str], cascade: bool = True) -> set[str]:
        removed: set[str] = set()
        for fid in folder_ids:
            ids = self._all_ids(fid) if cascade else {fid}
            gone = ids & self._selected
            self._selected -= gone
            removed |= gone
        if removed:
            self._updated_at = _now()
        return removed

    def toggle(self, folder_id: str) -> bool:
        if folder_id in self._selected:
            self.remove_folders([folder_id], cascade=True)
            return False
        else:
            self.add_folders([folder_id], cascade=True)
            return True

    def select_all(self) -> None:
        root = self._tree.get_root()
        if root:
            self.add_folders([root.id], cascade=True)

    def clear_all(self) -> None:
        self._selected.clear()
        self._updated_at = _now()

    def get_summary(self) -> SelectionSummaryResponse:
        has = bool(self._selected)
        total, compliant, legacy, unrecognized, _ = self._aggregate() if has else (0, 0, 0, 0, [])

        reasons: list[str] = []
        if not has:
            reasons.append("At least one folder must be selected to start processing")

        return SelectionSummaryResponse(
            has_selection=has,
            selected_count=len(self._selected),
            total_docs_in_selection=total,
            compliance={
                "compliant":    compliant,
                "legacy":       legacy,
                "unrecognized": unrecognized,
                "percentage":   self._compliance_pct(total, compliant),
            } if has else None,
            can_start_processing=has,
            reasons_disabled=reasons,
        )

    @property
    def selected_ids(self) -> set[str]:
        return self._selected

    def is_selected(self, folder_id: str) -> bool:
        return folder_id in self._selected

    def is_indeterminate(self, folder_id: str) -> bool:
        node = self._tree.get_folder(folder_id)
        if not node or folder_id in self._selected:
            return False
        desc = self._descendants(folder_id)
        if not desc:
            return False
        selected_desc = desc & self._selected
        return bool(selected_desc) and selected_desc != desc
