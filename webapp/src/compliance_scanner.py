"""Note format compliance scanning using the existing parse_header() logic."""

from __future__ import annotations

import sys
from pathlib import Path

# Add pipeline/src/ to sys.path so parse_header can be imported
_pipeline_src = Path(__file__).parent.parent.parent / "pipeline" / "src"
if str(_pipeline_src) not in sys.path:
    sys.path.insert(0, str(_pipeline_src))

from parser import parse_header  # noqa: E402 — path setup above

from .schemas import (
    ComplianceReportResponse,
    ComplianceStats,
    DocumentInfo,
    FormatCompliance,
    NonCompliantDocument,
    NonCompliantResponse,
)
from .tree_builder import TreeBuilder


def _color_indicator(pct: float) -> str:
    if pct >= 80:
        return "green"
    if pct >= 50:
        return "amber"
    return "red"


def _classify(path: Path) -> FormatCompliance:
    """
    Classify a single .md file using parse_header() — single source of truth
    shared with the graph-builder CLI.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return FormatCompliance.UNRECOGNIZED

    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        return FormatCompliance.COMPLIANT

    created_at, status, tag_links, _ = parse_header(lines)
    if created_at or status or tag_links:
        return FormatCompliance.LEGACY

    return FormatCompliance.UNRECOGNIZED


class ComplianceScanner:
    """
    Scans vault folders for format compliance.
    Results are written back into the TreeBuilder's node index so the
    tree API can serve compliance badges without a separate lookup.
    """

    def __init__(self, tree: TreeBuilder) -> None:
        self._tree = tree
        # folder_id → {compliant, legacy, unrecognized}
        self._cache: dict[str, dict[str, int]] = {}

    def scan_folder(self, folder_id: str, recursive: bool = True) -> dict[str, int] | None:
        """
        Scan a folder for compliance. Results are stored in the cache and
        pushed into the tree node. Returns counts dict or None if not found.
        """
        node     = self._tree.get_folder(folder_id)
        abs_path = self._tree.get_folder_path(folder_id)
        vault    = self._tree.vault_root()

        if not node or not abs_path or not vault:
            return None

        counts = {"compliant": 0, "legacy": 0, "unrecognized": 0}
        glob   = abs_path.rglob("*.md") if recursive else abs_path.glob("*.md")

        try:
            for md in glob:
                fc = _classify(md)
                counts[fc.value.lower()] += 1
            self._cache[folder_id] = counts
            self._tree.update_compliance(
                folder_id,
                counts["compliant"],
                counts["legacy"],
                counts["unrecognized"],
            )
        except Exception:
            self._tree.mark_compliance_error(folder_id)
            return None

        return counts

    def scan_all(self) -> None:
        """Scan every folder in the tree (runs in the calling thread)."""
        for fid in self._tree.all_folder_ids():
            if fid not in self._cache:
                self.scan_folder(fid, recursive=False)  # non-recursive; each folder scans its own files

    def get_report(self, scope: str, folder_id: str | None = None) -> ComplianceReportResponse | None:
        vault = self._tree.vault_root()
        if not vault:
            return None

        if scope == "folder" and folder_id:
            node = self._tree.get_folder(folder_id)
            if not node:
                return None
            counts = self._cache.get(folder_id, {"compliant": 0, "legacy": 0, "unrecognized": 0})
            total = sum(counts.values())
            pct   = round(counts["compliant"] / total * 100, 2) if total else 0.0
            return ComplianceReportResponse(
                scope="folder",
                total_documents=total,
                compliance_stats=ComplianceStats(**counts),
                compliance_percentage=pct,
                color_indicator=_color_indicator(pct),
                folder_id=folder_id,
                folder_name=node.relative_path or node.name,
            )

        # Aggregate across requested scope
        folder_ids: list[str]
        if scope == "selection":
            folder_ids = []  # caller should inject selected IDs
            # (main.py passes them via get_selection_report)
        else:
            folder_ids = self._tree.all_folder_ids()

        total = c = l = u = 0
        for fid in folder_ids:
            counts = self._cache.get(fid, {})
            total += sum(counts.values())
            c     += counts.get("compliant", 0)
            l     += counts.get("legacy", 0)
            u     += counts.get("unrecognized", 0)

        pct = round(c / total * 100, 2) if total else 0.0
        return ComplianceReportResponse(
            scope=scope,
            total_documents=total,
            compliance_stats=ComplianceStats(compliant=c, legacy=l, unrecognized=u),
            compliance_percentage=pct,
            color_indicator=_color_indicator(pct),
        )

    def get_selection_report(self, selected_folder_ids: list[str]) -> ComplianceReportResponse:
        total = c = l = u = 0
        for fid in selected_folder_ids:
            counts = self._cache.get(fid, {})
            total += sum(counts.values())
            c     += counts.get("compliant", 0)
            l     += counts.get("legacy", 0)
            u     += counts.get("unrecognized", 0)
        pct = round(c / total * 100, 2) if total else 0.0
        return ComplianceReportResponse(
            scope="selection",
            total_documents=total,
            compliance_stats=ComplianceStats(compliant=c, legacy=l, unrecognized=u),
            compliance_percentage=pct,
            color_indicator=_color_indicator(pct),
        )

    def list_non_compliant(
        self,
        folder_id: str | None = None,
        fmt_filter: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> NonCompliantResponse:
        vault = self._tree.vault_root()
        if not vault:
            return NonCompliantResponse(
                non_compliant_documents=[], total_count=0,
                returned_count=0, limit=limit, offset=offset,
            )

        folder_ids = [folder_id] if folder_id else self._tree.all_folder_ids()
        results: list[NonCompliantDocument] = []

        for fid in folder_ids:
            abs_path = self._tree.get_folder_path(fid)
            node     = self._tree.get_folder(fid)
            if not abs_path or not node:
                continue
            for md in sorted(abs_path.glob("*.md")):
                fc = _classify(md)
                if fc == FormatCompliance.COMPLIANT:
                    continue
                if fmt_filter != "all" and fc.value.lower() != fmt_filter.lower():
                    continue
                rel = str(md.relative_to(vault)).replace("\\", "/")
                results.append(NonCompliantDocument(
                    id=rel,
                    filename=md.name,
                    relative_path=rel,
                    folder_id=fid,
                    size_bytes=md.stat().st_size,
                    modified_at=str(md.stat().st_mtime),
                    format_compliance=fc,
                    reason=(
                        "Contains legacy custom header format"
                        if fc == FormatCompliance.LEGACY
                        else "No recognized header format detected"
                    ),
                ))

        total = len(results)
        page  = results[offset : offset + limit]
        return NonCompliantResponse(
            non_compliant_documents=page,
            total_count=total,
            returned_count=len(page),
            limit=limit,
            offset=offset,
        )

    def enrich_documents(self, docs: list[DocumentInfo], vault: Path) -> list[DocumentInfo]:
        """Fill in format_compliance on a list of DocumentInfo objects."""
        for doc in docs:
            abs_path = vault / doc.relative_path
            doc.format_compliance = _classify(abs_path)
        return docs
