from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class ComplianceStatus(str, Enum):
    PENDING = "PENDING"
    SCANNED = "SCANNED"
    ERROR   = "ERROR"

class FormatCompliance(str, Enum):
    COMPLIANT    = "COMPLIANT"
    LEGACY       = "LEGACY"
    UNRECOGNIZED = "UNRECOGNIZED"

class JobStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


# ── Vault ──────────────────────────────────────────────────────────────────────

class VaultInfo(BaseModel):
    path:          str
    display_name:  str
    connected_at:  str
    last_accessed: str

class ConnectVaultRequest(BaseModel):
    vault_path:   str
    display_name: str | None = None

class ConnectVaultResponse(BaseModel):
    status:         str
    vault:          VaultInfo
    folder_count:   int
    document_count: int

class VaultValidateResponse(BaseModel):
    is_valid:   bool
    path:       str
    accessible: bool
    reason:     str | None = None


# ── Tree ───────────────────────────────────────────────────────────────────────

class FolderNode(BaseModel):
    id:                str
    name:              str
    relative_path:     str
    level:             int
    parent_id:         str | None
    document_count:    int
    subfolder_count:   int
    total_size_bytes:  int
    compliance_status: ComplianceStatus = ComplianceStatus.PENDING
    compliant_docs:    int | None = None
    legacy_docs:       int | None = None
    unrecognized_docs: int | None = None
    children:          list[FolderNode] = Field(default_factory=list)

FolderNode.model_rebuild()

class DocumentInfo(BaseModel):
    id:                str
    filename:          str
    relative_path:     str
    folder_id:         str
    size_bytes:        int
    modified_at:       str
    format_compliance: FormatCompliance

class TreeResponse(BaseModel):
    tree:              FolderNode
    scan_completed_at: str | None = None

class FolderDetailResponse(BaseModel):
    folder:          FolderNode
    documents:       list[DocumentInfo]
    documents_count: int


# ── Selection ──────────────────────────────────────────────────────────────────

class SelectionSummaryFolder(BaseModel):
    id:             str
    name:           str
    relative_path:  str
    document_count: int

class SelectionState(BaseModel):
    vault_id:                   str
    selected_folder_ids:        list[str]
    selected_folders:           list[SelectionSummaryFolder]
    total_selected_docs:        int
    total_selected_compliant:   int
    total_selected_legacy:      int
    total_selected_unrecognized: int
    compliance_percentage:      float
    created_at:                 str

class SetSelectionRequest(BaseModel):
    folder_ids: list[str]

class AddRemoveFoldersRequest(BaseModel):
    folder_ids: list[str]
    cascade:    bool = True

class SelectionSummaryResponse(BaseModel):
    has_selection:        bool
    selected_count:       int
    total_docs_in_selection: int
    compliance:           dict[str, Any] | None
    can_start_processing: bool
    reasons_disabled:     list[str]


# ── Processing ─────────────────────────────────────────────────────────────────

class Neo4jCredentials(BaseModel):
    neo4j_uri:      str
    neo4j_user:     str
    neo4j_password: str

class StartProcessingRequest(BaseModel):
    selected_folder_ids: list[str] | None = None
    dry_run:             bool = False
    clear_graph:         bool = False
    neo4j_uri:           str | None = None
    neo4j_user:          str | None = None
    neo4j_password:      str | None = None

class StartProcessingResponse(BaseModel):
    status:                  str
    job_id:                  str
    message:                 str
    stream_url:              str
    total_documents_estimate: int
    dry_run:                 bool

class JobStatusResponse(BaseModel):
    job_id:              str
    status:              JobStatus
    created_at:          str
    started_at:          str | None
    completed_at:        str | None
    documents_processed: int
    documents_failed:    int
    total_documents:     int
    dry_run:             bool
    error_message:       str | None = None
    total_entities_created:      int | None = None
    total_relationships_created: int | None = None
    failed_documents:            list[dict] = Field(default_factory=list)


# ── Compliance ────────────────────────────────────────────────────────────────

class ComplianceStats(BaseModel):
    compliant:    int
    legacy:       int
    unrecognized: int

class ComplianceReportResponse(BaseModel):
    scope:                 str
    total_documents:       int
    compliance_stats:      ComplianceStats
    compliance_percentage: float
    color_indicator:       str
    folder_id:             str | None = None
    folder_name:           str | None = None

class NonCompliantDocument(BaseModel):
    id:                str
    filename:          str
    relative_path:     str
    folder_id:         str
    size_bytes:        int
    modified_at:       str
    format_compliance: FormatCompliance
    reason:            str

class NonCompliantResponse(BaseModel):
    non_compliant_documents: list[NonCompliantDocument]
    total_count:             int
    returned_count:          int
    limit:                   int
    offset:                  int


# ── Spec Doc Parsing ──────────────────────────────────────────────────────────

class DocRuleInfo(BaseModel):
    path:       str
    name:       str
    node_label: str

class DocParseRequest(BaseModel):
    docx_path:      str
    rule_file:      str
    source_label:   str        = ""
    dry_run:        bool       = True
    parent_node_id: str | None = None
    flow_name:      str        = ""
    uc_id:          str        = ""
    doc_type:       str        = ""

class ParsedItemDetail(BaseModel):
    req_id:               str
    title:                str
    body:                 str
    source_file:          str
    candidate_categories: list[str]
    named_extractions:    dict[str, list[str]]

class DocParseResponse(BaseModel):
    status:           str
    rule_name:        str
    node_label:       str
    item_count:       int
    context_length:   int
    dry_run:          bool
    ingested:         bool
    hierarchy_built:  bool = False   # True when Flow→UC→Doc→BR chain was created
    items:            list[ParsedItemDetail]
    warnings:         list[str] = []


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error:   str
    message: str
    details: dict[str, Any] | None = None
