"""FastAPI application — Vault UI with authentication and credential management."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .compliance_scanner import ComplianceScanner
from .env_writer import MODULE_CRED_FIELDS, MODULE_ENV_PATHS, get_cred_status, write_env
from .mcp_manager import SERVERS as MCP_SERVERS
from .mcp_manager import mcp_manager
from .processor import ProcessorService
from .schemas import (
    AddRemoveFoldersRequest,
    ConnectVaultRequest,
    ConnectVaultResponse,
    DocParseRequest,
    DocParseResponse,
    ErrorResponse,
    FolderDetailResponse,
    JobStatusResponse,
    Neo4jCredentials,
    NonCompliantResponse,
    ParsedItemDetail,
    SelectionSummaryResponse,
    SetSelectionRequest,
    StartProcessingRequest,
    StartProcessingResponse,
    TreeResponse,
    VaultInfo,
    VaultValidateResponse,
)
from .selection_service import SelectionService
from .session_manager import SessionState, session_manager
from .tree_builder import TreeBuilder
from .vault_manager import VaultManager, VaultValidationError

_static_dir = Path(__file__).parent / "static"
_rules_dir  = Path(__file__).parent.parent.parent / "parsing-rules"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    mcp_manager.restore_desired()
    task = asyncio.create_task(session_manager.run_cleanup_loop())
    yield
    task.cancel()
    mcp_manager.stop_all()


app = FastAPI(title="NAA Control Plane", version="2.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# All routes on this router require a valid session cookie
protected = APIRouter(dependencies=[Depends(auth.require_auth)])


# ── Session dependency ────────────────────────────────────────────────────────

async def get_session(request: Request, response: Response) -> SessionState:
    session_id = request.cookies.get("kg_session_id")
    sid, state = session_manager.get_or_create(session_id)
    if sid != session_id:
        response.set_cookie(
            "kg_session_id", sid,
            httponly=True, samesite="lax", max_age=7200,
        )
    return state


def _require_vault(session: SessionState) -> Path:
    info = session.vault.get_current()
    if not info:
        raise HTTPException(
            status_code=404,
            detail={"error": "no_vault_connected", "message": "No vault is currently connected.", "vault": None},
        )
    return Path(info.path)


# ── Public routes (no auth required) ─────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root(request: Request) -> Response:
    if not auth.is_setup_done():
        return RedirectResponse("/setup", status_code=302)
    if not auth.is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(_static_dir / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login", include_in_schema=False)
async def login_page(request: Request) -> Response:
    if auth.is_authenticated(request):
        return RedirectResponse("/", status_code=302)
    return FileResponse(_static_dir / "login.html", headers={"Cache-Control": "no-store"})


@app.post("/login", include_in_schema=False)
async def do_login(password: str = Form(...)) -> Response:
    if not auth.is_setup_done():
        return RedirectResponse("/setup", status_code=303)
    if not auth.check_password(password):
        return RedirectResponse("/login?error=1", status_code=303)
    redirect = RedirectResponse("/", status_code=303)
    auth.set_session(redirect)
    return redirect


@app.post("/logout", include_in_schema=False)
async def logout() -> Response:
    redirect = RedirectResponse("/login", status_code=303)
    auth.clear_session(redirect)
    return redirect


@app.get("/setup", include_in_schema=False)
async def setup_page(request: Request) -> Response:
    if auth.is_setup_done():
        return RedirectResponse("/", status_code=302)
    return FileResponse(_static_dir / "setup.html", headers={"Cache-Control": "no-store"})


@app.post("/setup", include_in_schema=False)
async def do_setup(password: str = Form(...), confirm: str = Form(...)) -> Response:
    if auth.is_setup_done():
        return RedirectResponse("/", status_code=303)
    if len(password) < 8:
        return RedirectResponse("/setup?error=short", status_code=303)
    if password != confirm:
        return RedirectResponse("/setup?error=mismatch", status_code=303)
    auth.setup_password(password)
    redirect = RedirectResponse("/", status_code=303)
    auth.set_session(redirect)
    return redirect


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/static/js/app.js", include_in_schema=False)
async def serve_app_js() -> FileResponse:
    return FileResponse(_static_dir / "js" / "app.js", headers={"Cache-Control": "no-store"})


# ── Auth endpoints (protected) ────────────────────────────────────────────────

@protected.post("/api/auth/change-password")
async def change_password(body: dict) -> dict:
    current = body.get("current_password", "")
    new_pw  = body.get("new_password", "")
    if not auth.check_password(current):
        raise HTTPException(status_code=400, detail={"error": "wrong_password", "message": "Current password is incorrect."})
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail={"error": "weak_password", "message": "Password must be at least 8 characters."})
    auth.setup_password(new_pw)
    return {"status": "changed"}


# ── Vault endpoints ───────────────────────────────────────────────────────────

@protected.post("/api/vault/connect", response_model=ConnectVaultResponse)
async def connect_vault(
    req: ConnectVaultRequest,
    session: SessionState = Depends(get_session),
) -> ConnectVaultResponse:
    try:
        info = session.vault.connect(req.vault_path, req.display_name)
    except VaultValidationError as exc:
        raise HTTPException(
            status_code=400 if exc.code == "invalid_vault_path" else
                        403 if exc.code == "permission_denied" else 404,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    vault_root = Path(info.path)
    session.tree.build(vault_root)
    folders, docs = session.vault.count_contents(vault_root)
    return ConnectVaultResponse(
        status="connected",
        vault=info,
        folder_count=folders,
        document_count=docs,
    )


@protected.get("/api/vault/current")
async def get_current_vault(session: SessionState = Depends(get_session)) -> dict:
    info = session.vault.get_current()
    if not info:
        raise HTTPException(
            status_code=404,
            detail={"error": "no_vault_connected", "message": "No vault is currently connected.", "vault": None},
        )
    return {"vault": info.model_dump()}


@protected.get("/api/vault/validate", response_model=VaultValidateResponse)
async def validate_vault(session: SessionState = Depends(get_session)) -> VaultValidateResponse:
    info = session.vault.get_current()
    if not info:
        raise HTTPException(status_code=404, detail={"error": "no_vault_connected", "message": "No vault is currently connected."})
    is_valid, reason = session.vault.validate_current()
    return VaultValidateResponse(is_valid=is_valid, path=info.path, accessible=is_valid, reason=reason)


@protected.post("/api/vault/disconnect")
async def disconnect_vault(session: SessionState = Depends(get_session)) -> dict:
    session.vault.disconnect()
    session.tree.__init__()   # type: ignore[misc]
    session.sel.clear_all()
    return {"status": "disconnected", "message": "Vault connection cleared."}


@protected.get("/api/vault/stats")
async def vault_stats(session: SessionState = Depends(get_session)) -> dict:
    info = session.vault.get_current()
    if not info:
        raise HTTPException(status_code=404, detail={"error": "no_vault_connected"})
    vault_root = Path(info.path)
    folders, docs = session.vault.count_contents(vault_root)
    return {
        "vault_path":      info.path,
        "total_folders":   folders,
        "total_documents": docs,
        "last_scanned":    session.tree.built_at(),
    }


# ── Tree endpoints ─────────────────────────────────────────────────────────────

@protected.get("/api/tree/structure", response_model=TreeResponse)
async def get_tree(
    include_compliance: bool = Query(default=False),
    session: SessionState = Depends(get_session),
) -> TreeResponse:
    _require_vault(session)
    root = session.tree.get_root()
    if not root:
        raise HTTPException(status_code=404, detail={"error": "no_vault_connected"})
    return TreeResponse(tree=root, scan_completed_at=session.tree.built_at())


@protected.get("/api/tree/folder/{folder_id}", response_model=FolderDetailResponse)
async def get_folder(
    folder_id: str,
    session: SessionState = Depends(get_session),
) -> FolderDetailResponse:
    _require_vault(session)
    detail = session.tree.get_folder_detail(folder_id)
    if not detail:
        raise HTTPException(status_code=404, detail={"error": "folder_not_found"})
    vault = session.tree.vault_root()
    if vault:
        detail.documents = session.scanner.enrich_documents(detail.documents, vault)
    return detail


@protected.post("/api/tree/refresh")
async def refresh_tree(session: SessionState = Depends(get_session)) -> dict:
    vault_root = _require_vault(session)
    session.tree.build(vault_root)
    folders, docs = session.vault.count_contents(vault_root)
    return {
        "status":            "refreshed",
        "message":           "Vault structure re-scanned.",
        "scan_completed_at": session.tree.built_at(),
        "folder_count":      folders,
        "document_count":    docs,
    }


@protected.post("/api/tree/scan-compliance")
async def scan_compliance(
    async_mode: bool = Query(default=False, alias="async"),
    session: SessionState = Depends(get_session),
) -> dict:
    _require_vault(session)
    session.scanner.scan_all()
    root = session.tree.get_root()
    compliant = legacy = unrecognized = 0
    if root:
        compliant    = root.compliant_docs    or 0
        legacy       = root.legacy_docs       or 0
        unrecognized = root.unrecognized_docs or 0
    return {
        "status":            "completed",
        "scan_completed_at": session.tree.built_at(),
        "compliance_stats":  {"compliant": compliant, "legacy": legacy, "unrecognized": unrecognized},
    }


# ── Selection endpoints ────────────────────────────────────────────────────────

@protected.get("/api/selection/current")
async def get_selection(session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    info  = session.vault.get_current()
    state = session.sel.get_state(vault_id=info.path if info else "")
    if not state:
        return {"selection": None, "message": "No folders currently selected."}
    return {"selection": state.model_dump()}


@protected.post("/api/selection/set")
async def set_selection(req: SetSelectionRequest, session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    if not req.folder_ids:
        raise HTTPException(status_code=400, detail={"error": "empty_selection", "message": "Selection must include at least one folder."})
    invalid = session.sel.validate_ids(req.folder_ids)
    if invalid:
        raise HTTPException(status_code=400, detail={"error": "invalid_folder_ids", "invalid_ids": invalid})
    state = session.sel.set_selection(req.folder_ids)
    return {
        "status":                "selection_updated",
        "selected_folder_ids":   state.selected_folder_ids,
        "total_selected_docs":   state.total_selected_docs,
        "compliance_percentage": state.compliance_percentage,
    }


@protected.post("/api/selection/add")
async def add_folders(req: AddRemoveFoldersRequest, session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    invalid = session.sel.validate_ids(req.folder_ids)
    if invalid:
        raise HTTPException(status_code=400, detail={"error": "invalid_folder_ids", "invalid_ids": invalid})
    added = session.sel.add_folders(req.folder_ids, cascade=req.cascade)
    info  = session.vault.get_current()
    state = session.sel.get_state(vault_id=info.path if info else "")
    return {
        "status":                 "folders_added",
        "added_ids":              list(added),
        "total_selected_folders": len(session.sel.selected_ids),
        "total_selected_docs":    state.total_selected_docs if state else 0,
    }


@protected.post("/api/selection/remove")
async def remove_folders(req: AddRemoveFoldersRequest, session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    removed = session.sel.remove_folders(req.folder_ids, cascade=req.cascade)
    info    = session.vault.get_current()
    state   = session.sel.get_state(vault_id=info.path if info else "")
    return {
        "status":                 "folders_removed",
        "removed_ids":            list(removed),
        "total_selected_folders": len(session.sel.selected_ids),
        "total_selected_docs":    state.total_selected_docs if state else 0,
    }


@protected.post("/api/selection/toggle/{folder_id}")
async def toggle_folder(folder_id: str, session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    if not session.tree.get_folder(folder_id):
        raise HTTPException(status_code=404, detail={"error": "folder_not_found"})
    is_selected = session.sel.toggle(folder_id)
    info  = session.vault.get_current()
    state = session.sel.get_state(vault_id=info.path if info else "")
    return {
        "status":                 "folder_added" if is_selected else "folder_removed",
        "folder_id":              folder_id,
        "is_selected":            is_selected,
        "total_selected_folders": len(session.sel.selected_ids),
        "total_selected_docs":    state.total_selected_docs if state else 0,
    }


@protected.post("/api/selection/select-all")
async def select_all(session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    session.sel.select_all()
    info  = session.vault.get_current()
    state = session.sel.get_state(vault_id=info.path if info else "")
    return {
        "status":                 "all_selected",
        "total_selected_folders": len(session.sel.selected_ids),
        "total_selected_docs":    state.total_selected_docs if state else 0,
        "compliance_percentage":  state.compliance_percentage if state else 0,
    }


@protected.post("/api/selection/clear-all")
async def clear_all(session: SessionState = Depends(get_session)) -> dict:
    _require_vault(session)
    session.sel.clear_all()
    return {"status": "all_cleared", "message": "All folders deselected.", "total_selected_folders": 0, "total_selected_docs": 0}


@protected.get("/api/selection/summary", response_model=SelectionSummaryResponse)
async def selection_summary(session: SessionState = Depends(get_session)) -> SelectionSummaryResponse:
    _require_vault(session)
    return session.sel.get_summary()


# ── Neo4j endpoints ────────────────────────────────────────────────────────────

@protected.post("/api/neo4j/test")
async def test_neo4j(creds: Neo4jCredentials, session: SessionState = Depends(get_session)) -> dict:
    try:
        from graph import GraphBuilder
        db = GraphBuilder(creds.neo4j_uri, creds.neo4j_user, creds.neo4j_password)
        ok = db.verify_connection()
        db.close()
        if not ok:
            raise RuntimeError("Connection verification returned false.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": "connection_failed", "message": str(exc)})
    session.neo4j_uri      = creds.neo4j_uri
    session.neo4j_user     = creds.neo4j_user
    session.neo4j_password = creds.neo4j_password
    return {"ok": True}


# ── Processing endpoints ───────────────────────────────────────────────────────

@protected.post("/api/processing/start", response_model=StartProcessingResponse)
async def start_processing(req: StartProcessingRequest, session: SessionState = Depends(get_session)) -> StartProcessingResponse:
    vault_root = _require_vault(session)
    if session.proc.active_job():
        active = session.proc.active_job()
        raise HTTPException(status_code=409, detail={
            "error": "processing_in_progress",
            "message": "Another graph processing job is already running.",
            "active_job_id": active.job_id if active else None,
        })
    folder_ids = req.selected_folder_ids or list(session.sel.selected_ids)
    if not folder_ids:
        raise HTTPException(status_code=400, detail={"error": "no_selection", "message": "No folders selected."})

    neo4j_uri      = req.neo4j_uri      or session.neo4j_uri      or os.getenv("NEO4J_URI", "")
    neo4j_user     = req.neo4j_user     or session.neo4j_user     or os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = req.neo4j_password or session.neo4j_password or os.getenv("NEO4J_PASSWORD", "")

    if not req.dry_run:
        if not (neo4j_uri and neo4j_password):
            raise HTTPException(status_code=400, detail={"error": "neo4j_credentials_missing", "message": "Neo4j credentials are required."})
        if not session.proc.check_neo4j(neo4j_uri, neo4j_user, neo4j_password):
            raise HTTPException(status_code=503, detail={"error": "neo4j_unavailable", "message": "Neo4j database is not available."})

    total_estimate = sum(
        (session.tree.get_folder(fid).document_count if session.tree.get_folder(fid) else 0)
        for fid in folder_ids
    )
    job = session.proc.start(
        folder_ids, vault_root,
        dry_run=req.dry_run, clear_graph=req.clear_graph,
        neo4j_uri=neo4j_uri, neo4j_user=neo4j_user, neo4j_password=neo4j_password,
    )
    return StartProcessingResponse(
        status="accepted",
        job_id=job.job_id,
        message="Graph processing started in background.",
        stream_url=f"/api/processing/stream?job_id={job.job_id}",
        total_documents_estimate=total_estimate,
        dry_run=req.dry_run,
    )


@protected.get("/api/processing/stream")
async def stream_processing(job_id: str, session: SessionState = Depends(get_session)) -> StreamingResponse:
    job = session.proc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return StreamingResponse(
        job.stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@protected.post("/api/processing/cancel/{job_id}")
async def cancel_processing(job_id: str, session: SessionState = Depends(get_session)) -> dict:
    job = session.proc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    cancelled = session.proc.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail={
            "error": "job_not_running",
            "message": f"Job is not currently running (status: {job.status}).",
            "job_status": job.status,
        })
    return {"status": "cancel_requested", "job_id": job_id, "message": "Processing cancellation requested.", "documents_processed": job.documents_processed}


@protected.get("/api/processing/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, session: SessionState = Depends(get_session)) -> JobStatusResponse:
    job = session.proc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return job.to_status_response()


@protected.get("/api/processing/jobs")
async def list_jobs(limit: int = 10, offset: int = 0, session: SessionState = Depends(get_session)) -> dict:
    jobs = session.proc.recent_jobs(limit=limit, offset=offset)
    return {"jobs": [j.to_status_response().model_dump() for j in jobs], "returned_count": len(jobs)}


# ── Compliance endpoints ───────────────────────────────────────────────────────

@protected.get("/api/compliance/report")
async def compliance_report(
    scope: str = Query(default="all"),
    folder_id: str | None = Query(default=None),
    session: SessionState = Depends(get_session),
) -> dict:
    _require_vault(session)
    if scope == "selection":
        report = session.scanner.get_selection_report(list(session.sel.selected_ids))
    elif scope == "folder" and folder_id:
        report = session.scanner.get_report("folder", folder_id)
        if not report:
            raise HTTPException(status_code=404, detail={"error": "folder_not_found"})
    else:
        report = session.scanner.get_report("all", None)
        if not report:
            raise HTTPException(status_code=404, detail={"error": "no_compliance_data"})
    return report.model_dump()


@protected.get("/api/compliance/non-compliant", response_model=NonCompliantResponse)
async def list_non_compliant(
    folder_id: str | None = Query(default=None),
    fmt:       str        = Query(default="all", alias="format"),
    limit:     int        = Query(default=100),
    offset:    int        = Query(default=0),
    session: SessionState = Depends(get_session),
) -> NonCompliantResponse:
    _require_vault(session)
    return session.scanner.list_non_compliant(folder_id, fmt, limit, offset)


@protected.post("/api/compliance/scan/{folder_id}")
async def scan_folder_compliance(
    folder_id: str,
    recursive: bool = Query(default=True),
    session: SessionState = Depends(get_session),
) -> dict:
    _require_vault(session)
    counts = session.scanner.scan_folder(folder_id, recursive)
    if counts is None:
        raise HTTPException(status_code=404, detail={"error": "folder_not_found"})
    return {
        "status":            "scanned",
        "folder_id":         folder_id,
        "documents_scanned": sum(counts.values()),
        "compliance":        counts,
        "scan_completed_at": session.tree.built_at(),
    }


# ── Spec-doc parsing endpoints ────────────────────────────────────────────────

@protected.get("/api/docs/rules")
async def list_doc_rules() -> dict:
    if not _rules_dir.exists():
        return {"rules": []}
    import yaml
    rules = []
    for f in sorted(_rules_dir.glob("*.yaml")) + sorted(_rules_dir.glob("*.yml")):
        try:
            with open(f, encoding="utf-8") as fh:
                rule = yaml.safe_load(fh)
            rules.append({"path": str(f), "name": rule.get("name", f.stem), "node_label": rule.get("node_label", "")})
        except Exception:
            rules.append({"path": str(f), "name": f.stem, "node_label": ""})
    return {"rules": rules}


@protected.post("/api/docs/parse", response_model=DocParseResponse)
async def parse_doc(req: DocParseRequest, session: SessionState = Depends(get_session)) -> DocParseResponse:
    from docx_generic_parser import DocxRuleParser

    rule_path = Path(req.rule_file)
    if not rule_path.is_absolute():
        rule_path = _rules_dir / rule_path.name
    if not rule_path.exists():
        raise HTTPException(status_code=404, detail={"error": "rule_not_found", "message": f"Rule file not found: {req.rule_file}"})

    docx_path = Path(req.docx_path)
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail={"error": "docx_not_found", "message": f"Document not found: {req.docx_path}"})

    try:
        parser = DocxRuleParser(rule_path)
        items, context = parser.parse(docx_path, source_label=req.source_label)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"error": "parse_error", "message": str(exc)})

    ingested = False
    if not req.dry_run and items:
        neo4j_uri      = session.neo4j_uri      or os.getenv("NEO4J_URI", "")
        neo4j_user     = session.neo4j_user     or os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = session.neo4j_password or os.getenv("NEO4J_PASSWORD", "")
        try:
            from graph import GraphBuilder
            db = GraphBuilder(neo4j_uri, neo4j_user, neo4j_password)
            try:
                db.upsert_requirements(items, parent_node_id=req.parent_node_id)
                ingested = True
            finally:
                db.close()
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"error": "neo4j_error", "message": f"Neo4j write failed: {exc}"})

    return DocParseResponse(
        status="parsed",
        rule_name=parser.rule_name,
        node_label=parser.node_label,
        item_count=len(items),
        context_length=len(context),
        dry_run=req.dry_run,
        ingested=ingested,
        items=[
            ParsedItemDetail(
                req_id=item.req_id, title=item.title, body=item.body,
                source_file=item.source_file, candidate_categories=item.candidate_categories,
                named_extractions=item.named_extractions,
            )
            for item in items
        ],
    )


# ── MCP server management endpoints ──────────────────────────────────────────

@protected.get("/api/mcp/servers")
async def list_mcp_servers() -> dict:
    return {"servers": mcp_manager.all_statuses()}


@protected.get("/api/mcp/{name}/status")
async def get_mcp_status(name: str) -> dict:
    try:
        return mcp_manager.status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})


@protected.post("/api/mcp/{name}/start")
async def start_mcp(name: str) -> dict:
    try:
        mcp_manager.start(name)
        return mcp_manager.status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "start_failed", "message": str(exc)})


@protected.post("/api/mcp/{name}/stop")
async def stop_mcp(name: str) -> dict:
    try:
        mcp_manager.stop(name)
        return mcp_manager.status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})


@protected.post("/api/mcp/{name}/restart")
async def restart_mcp(name: str) -> dict:
    try:
        mcp_manager.restart(name)
        return mcp_manager.status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "restart_failed", "message": str(exc)})


@protected.post("/api/mcp/start-all")
async def start_all_mcp() -> dict:
    mcp_manager.start_all()
    return {"servers": mcp_manager.all_statuses()}


@protected.post("/api/mcp/stop-all")
async def stop_all_mcp() -> dict:
    mcp_manager.stop_all()
    return {"servers": mcp_manager.all_statuses()}


@protected.get("/api/mcp/{name}/config")
async def get_mcp_config(name: str) -> dict:
    try:
        return mcp_manager.get_config(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})


@protected.post("/api/mcp/{name}/config")
async def set_mcp_config(name: str, body: dict) -> dict:
    try:
        host = str(body.get("host", "127.0.0.1"))
        port = int(body.get("port", 8000))
        mcp_manager.set_config(name, host, port)
        mcp_manager.restart(name)
        return mcp_manager.status(name)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "unknown_server", "name": name})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_config", "message": str(exc)})


# ── Credentials endpoints ─────────────────────────────────────────────────────

@protected.get("/api/credentials/{module}")
async def get_credentials(module: str) -> dict:
    if module not in MODULE_CRED_FIELDS:
        raise HTTPException(status_code=404, detail={"error": "unknown_module", "module": module})
    return {"module": module, "fields": get_cred_status(module)}


@protected.post("/api/credentials/{module}")
async def save_credentials(module: str, body: dict) -> dict:
    if module not in MODULE_CRED_FIELDS:
        raise HTTPException(status_code=404, detail={"error": "unknown_module", "module": module})

    raw = body.get("credentials", {})
    updates = {k: str(v) for k, v in raw.items() if v and isinstance(v, str) and k in {f["key"] for f in MODULE_CRED_FIELDS[module]}}

    if updates:
        path = MODULE_ENV_PATHS[module]
        try:
            write_env(path, updates)
        except OSError as exc:
            raise HTTPException(status_code=500, detail={"error": "write_failed", "message": str(exc)})

    # Restart MCP server if it was running so it picks up the new .env
    if module in MCP_SERVERS and mcp_manager.status(module)["running"]:
        try:
            mcp_manager.restart(module)
        except Exception:
            pass

    return {"status": "saved", "module": module, "fields": get_cred_status(module)}


# ── Wire up the protected router ──────────────────────────────────────────────

app.include_router(protected)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, reload=False)
