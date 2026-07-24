"""
Rule-file-driven parser for .docx specification documents.

Reads a YAML rule file (from parsing-rules/) and uses it to extract
structured items from a .docx file without any hardcoded document assumptions.

Produces ParsedItem instances whose attributes match what
GraphBuilder.upsert_requirements() accesses (node_id, node_label, req_id,
title, body, source_file, candidate_categories, named_extractions, metadata).
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph


# ── Item model ────────────────────────────────────────────────────────────────

@dataclass
class ParsedItem:
    """
    One extracted requirement.  Attribute names match GenericRequirement in
    pipeline/src/models.py so both can be passed to upsert_requirements().
    """
    node_id_key:          str
    node_label:           str
    req_id:               str
    title:                str
    body:                 str
    source_file:          str                  = ""
    candidate_categories: list[str]            = field(default_factory=list)
    named_extractions:    dict[str, list[str]] = field(default_factory=dict)
    metadata:             dict                 = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return hashlib.sha1(self.node_id_key.encode()).hexdigest()[:16]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_flags(flags_str: str | None) -> int:
    if not flags_str:
        return 0
    flags = 0
    for token in flags_str.upper().split("|"):
        token = token.strip()
        if token == "IGNORECASE":
            flags |= re.IGNORECASE
        elif token == "MULTILINE":
            flags |= re.MULTILINE
        elif token == "DOTALL":
            flags |= re.DOTALL
    return flags


def _dedup_merged_cells(row_cells) -> list[str]:
    """
    Merged table cells appear as duplicate adjacent text in python-docx.
    Keep only the first occurrence of each consecutive duplicate.
    """
    result: list[str] = []
    for cell in row_cells:
        text = cell.text.strip()
        if not result or text != result[-1]:
            result.append(text)
    return result


def _table_has_id_row(table: Table, id_re: re.Pattern) -> bool:
    for row in table.rows:
        if row.cells and id_re.match(row.cells[0].text.strip()):
            return True
    return False


# ── Parser ────────────────────────────────────────────────────────────────────

class DocxRuleParser:
    """
    Parse a .docx file according to a YAML rule file.

    Example::

        parser = DocxRuleParser("parsing-rules/br_requirements.yml")
        items, context = parser.parse("specs/UC36_FDD.docx", source_label="UC36")
    """

    def __init__(self, rule_path: str | Path) -> None:
        rule_path = Path(rule_path)
        with rule_path.open(encoding="utf-8") as fh:
            rule: dict[str, Any] = yaml.safe_load(fh)

        self.rule_name  = rule.get("name", rule_path.stem)
        self.node_label = rule.get("node_label", "Requirement")

        # ID matching
        id_flags    = _parse_flags(rule.get("id_flags"))
        self._id_re  = re.compile(rule["id_pattern"], id_flags)
        self._id_fmt = rule.get("id_format", "{}")

        # Title extraction
        self._title_from = rule.get("title_from", "first_line")

        # Category signals — compiled once, evaluated per item
        self._cat_signals: list[tuple[re.Pattern, str]] = [
            (re.compile(sig["pattern"], _parse_flags(sig.get("flags"))), sig["name"])
            for sig in rule.get("category_signals", [])
        ]

        # Named extractions — compiled once, applied per item
        self._extractions: list[dict[str, Any]] = [
            {**ext, "_re": re.compile(ext["pattern"], _parse_flags(ext.get("flags")))}
            for ext in rule.get("named_extractions", [])
        ]

        # Context collection config
        ctx = rule.get("context", {})
        self._ctx_paragraphs     = ctx.get("include_paragraphs", True)
        self._ctx_non_br_tables  = ctx.get("include_non_br_tables", True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def parse(
        self,
        docx_path: str | Path,
        source_label: str = "",
    ) -> tuple[list[ParsedItem], str]:
        """
        Parse *docx_path* and return ``(items, context)``.

        Parameters
        ----------
        docx_path:
            Path to the .docx file.
        source_label:
            Caller-supplied identifier (e.g. a use-case ID or filename slug)
            stored in each item's metadata and used to build a stable node key.
        """
        path = Path(docx_path)
        doc  = DocxDocument(path)

        context = self._collect_context(doc)
        items   = self._extract_items(doc, path.name, source_label)

        return items, context

    # ── Context collection (Pass 1) ────────────────────────────────────────────

    def _collect_context(self, doc) -> str:
        parts: list[str] = []

        for child in doc.element.body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p" and self._ctx_paragraphs:
                text = Paragraph(child, doc).text.strip()
                if text:
                    parts.append(text)

            elif tag == "tbl" and self._ctx_non_br_tables:
                table = Table(child, doc)
                if _table_has_id_row(table, self._id_re):
                    continue
                rows_text = []
                for row in table.rows:
                    cells = _dedup_merged_cells(row.cells)
                    line  = "  ".join(c for c in cells if c)
                    if line:
                        rows_text.append(line)
                if rows_text:
                    parts.append("\n".join(rows_text))

        return "\n\n".join(parts)

    # ── Item extraction (Pass 2) ───────────────────────────────────────────────

    def _extract_items(
        self,
        doc,
        source_file: str,
        source_label: str,
    ) -> list[ParsedItem]:
        items: list[ParsedItem] = []

        for child in doc.element.body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "tbl":
                continue

            table = Table(child, doc)
            if not _table_has_id_row(table, self._id_re):
                continue

            for row in table.rows:
                cells     = _dedup_merged_cells(row.cells)
                non_empty = [c for c in cells if c]
                if len(non_empty) < 2:
                    continue

                m = self._id_re.match(non_empty[0])
                if not m:
                    continue

                req_id = self._format_id(m)
                body   = non_empty[1].strip()
                title  = self._extract_title(body, fallback=non_empty[0])

                items.append(ParsedItem(
                    node_id_key          = f"{self.node_label}::{source_label}::{source_file}::{req_id}",
                    node_label           = self.node_label,
                    req_id               = req_id,
                    title                = title,
                    body                 = body,
                    source_file          = source_file,
                    candidate_categories = self._infer_categories(body),
                    named_extractions    = self._run_extractions(body),
                    metadata             = {"source_label": source_label},
                ))

        return items

    # ── Per-item helpers ───────────────────────────────────────────────────────

    def _format_id(self, match: re.Match) -> str:
        try:
            return self._id_fmt.format(int(match.group(1)))
        except (IndexError, ValueError):
            return self._id_fmt.format(match.group(0))

    def _extract_title(self, body: str, fallback: str) -> str:
        if self._title_from == "first_line":
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            return lines[0] if lines else fallback
        return fallback

    def _infer_categories(self, body: str) -> list[str]:
        return [name for pattern, name in self._cat_signals if pattern.search(body)]

    def _run_extractions(self, body: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for ext in self._extractions:
            pattern: re.Pattern = ext["_re"]
            group               = ext.get("group", 0)
            transform           = ext.get("transform", "")

            matches = [m.group(group) for m in pattern.finditer(body)]

            if transform == "uppercase":
                matches = [v.upper() for v in matches]
            elif transform == "lowercase":
                matches = [v.lower() for v in matches]

            if ext.get("filter") == "no_spaces":
                matches = [v for v in matches if " " not in v]

            # sort implies deduplicate; deduplicate alone preserves insertion order
            if ext.get("sort", False):
                matches = sorted(set(matches))
            elif ext.get("deduplicate", False):
                matches = list(dict.fromkeys(matches))

            result[ext["name"]] = matches

        return result
