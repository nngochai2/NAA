import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, field
 
 
@dataclass
class WikiLink:
    target:          str
    alias:           str
    context:         str
    relationship:    str  = "LINKS_TO"
    is_tag_link:     bool = False  # True when from the Tags: section
    is_llm_extracted: bool = False  # True when added by LLM enrichment
 
 
@dataclass
class Note:
    path:         Path
    title:        str
    note_type:    str
    subfolder:    str            = ""
    status:       str            = ""
    created_at:   str            = ""
    links:        list[WikiLink] = field(default_factory=list)
    backlinks:    list[str]      = field(default_factory=list)
    content_hash: str            = ""
    word_count:   int            = 0
    body:         str            = ""
    summary:      str            = ""
 
    @property
    def node_id(self) -> str:
        return hashlib.sha1(str(self.path).encode()).hexdigest()[:16]
 
 
# ── eInvoice SQL / docx models ───────────────────────────────────────────────
 
@dataclass
class SqlView:
    """One SQL CREATE OR REPLACE VIEW script."""
    qualified_name: str          # e.g. RASDBT.VW_GOV_INV_EXTENSIONS
    schema:         str          # e.g. RASDBT
    view_name:      str          # e.g. VW_GOV_INV_EXTENSIONS
    body:           str          # full SQL script text
    tag:            str = ""     # e.g. eInvoice
 
    @property
    def node_id(self) -> str:
        return hashlib.sha1(self.qualified_name.encode()).hexdigest()[:16]
 
    @property
    def content_hash(self) -> str:
        return hashlib.sha1(self.body.encode()).hexdigest()
 
 
@dataclass
class SqlSegment:
    """One UNION ALL branch inside a view (e.g. Polish, Italian)."""
    view_qualified_name: str     # parent view
    segment_name:        str     # e.g. "Polish", "Italian", "Main"
    dispatch_codes:      list[str] = field(default_factory=list)
    body:                str    = ""   # SQL text of this segment only
    tag:                 str    = ""
 
    @property
    def node_id(self) -> str:
        key = f"{self.view_qualified_name}::{self.segment_name}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 
@dataclass
class FieldMapping:
    """One output column in a SQL view."""
    view_qualified_name: str     # parent view
    segment_name:        str     # which UNION ALL branch
    alias:               str     # column alias (output name)
    expression:          str     # raw SQL expression
    br_refs:             list[str] = field(default_factory=list)  # e.g. ["BR04"]
    tfs_refs:            list[str] = field(default_factory=list)  # e.g. ["TFS_2608"]
    inline_comment:      str    = ""   # nearest -- comment above the column
    tag:                 str    = ""
 
    @property
    def node_id(self) -> str:
        key = f"{self.view_qualified_name}::{self.segment_name}::{self.alias}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 
# ── Project hierarchy models ──────────────────────────────────────────────────
 
@dataclass
class Flow:
    """Top-level project flow (e.g. eInvoice, OracleEBS)."""
    name: str
 
    @property
    def node_id(self) -> str:
        return hashlib.sha1(f"FLOW::{self.name}".encode()).hexdigest()[:16]
 
 
@dataclass
class UseCase:
    """A use case within a flow (e.g. UC36)."""
    uc_id:      str   # e.g. "UC36"
    project_id: str   # e.g. "PRJ00445"
    flow_name:  str   # e.g. "eInvoice"
 
    @property
    def node_id(self) -> str:
        key = f"UC::{self.flow_name}::{self.uc_id}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 
@dataclass
class Document:
    """One spec document (FDD or SDD) within a use case."""
    uc_id:       str
    doc_type:    str        # "FDD" | "SDD"
    flow_name:   str
    source_file: str = ""
    context:     str = ""  # full non-BR document text (intro, scope, background)
 
    @property
    def node_id(self) -> str:
        key = f"DOC::{self.flow_name}::{self.uc_id}::{self.doc_type}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 
@dataclass
class BR:
    """One business requirement sourced from a specific document (FDD or SDD)."""
    br_id:                str
    uc_id:                str
    doc_type:             str         # "FDD" | "SDD"
    flow_name:            str         # primary flow tag, e.g. "eInvoice"
    title:                str
    body:                 str
    candidate_categories: list[str]   = field(default_factory=list)  # auto-inferred
    confirmed_categories: list[str]   = field(default_factory=list)  # human-reviewed
    affected_fields:      list[str]   = field(default_factory=list)
    affected_views:       list[str]   = field(default_factory=list)
    source_file:          str         = ""
    project_id:           str         = ""
 
    @property
    def node_id(self) -> str:
        key = f"BR::{self.flow_name}::{self.uc_id}::{self.doc_type}::{self.br_id}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
    @property
    def doc_node_id(self) -> str:
        key = f"DOC::{self.flow_name}::{self.uc_id}::{self.doc_type}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 
# Backward compat alias — do not create new Requirement instances directly
Requirement = BR


# ── Generic parsed requirement (rule-file driven) ─────────────────────────────

@dataclass
class GenericRequirement:
    """
    A parsed item produced by DocxRuleParser from any user-defined rule file.

    `node_id_key` should be a stable unique string (e.g. "label::source::req_id")
    so that re-ingestion upserts rather than duplicates.
    """
    node_id_key:          str
    node_label:           str               # Neo4j label from the rule file
    req_id:               str               # e.g. "BR04", "REQ-01"
    title:                str
    body:                 str
    source_file:          str               = ""
    candidate_categories: list[str]         = field(default_factory=list)
    named_extractions:    dict[str, list[str]] = field(default_factory=dict)
    metadata:             dict              = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return hashlib.sha1(self.node_id_key.encode()).hexdigest()[:16]
 
 
# ── Oracle Package / Procedure models ────────────────────────────────────────
 
@dataclass
class OraclePackage:
    """One Oracle PL/SQL package (spec + body combined)."""
    qualified_name: str   # e.g. RASDBT.EINV_UTIL_PKG
    schema:         str   # e.g. RASDBT
    package_name:   str   # e.g. EINV_UTIL_PKG
    spec_body:      str   # CREATE PACKAGE … END; text
    tag:            str = ""
 
    @property
    def node_id(self) -> str:
        return hashlib.sha1(self.qualified_name.encode()).hexdigest()[:16]
 
    @property
    def content_hash(self) -> str:
        return hashlib.sha1(self.spec_body.encode()).hexdigest()
 
 
@dataclass
class PackageFunction:
    """One function inside an Oracle package."""
    package_qualified_name: str   # parent package
    function_name:          str   # e.g. GET_INV_TYPE_CODE
    parameters:             str   # raw parameter list string
    return_type:            str   # e.g. CHAR, NVARCHAR2
    body:                   str   # full function implementation
    br_refs:  list[str] = field(default_factory=list)
    tfs_refs: list[str] = field(default_factory=list)
    tag:      str       = ""
 
    @property
    def node_id(self) -> str:
        key = f"PKG::{self.package_qualified_name}::{self.function_name}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]
 
 