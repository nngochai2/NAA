"""Background graph processing with thread-safe SSE event streaming."""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

# Ensure src/ is importable from ui subpackage
_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from .schemas import JobStatus, JobStatusResponse
from .tree_builder import TreeBuilder

_executor = ThreadPoolExecutor(max_workers=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── ProcessingJob ──────────────────────────────────────────────────────────────

class ProcessingJob:
    def __init__(
        self,
        job_id:          str,
        selected_paths:  list[Path],
        vault_root:      Path,
        dry_run:         bool = False,
        clear_graph:     bool = False,
        neo4j_uri:       str | None = None,
        neo4j_user:      str | None = None,
        neo4j_password:  str | None = None,
    ) -> None:
        self.job_id         = job_id
        self.selected_paths = selected_paths
        self.vault_root     = vault_root
        self.dry_run        = dry_run
        self.clear_graph    = clear_graph
        self.neo4j_uri      = neo4j_uri
        self.neo4j_user     = neo4j_user
        self.neo4j_password = neo4j_password
        self.status         = JobStatus.PENDING
        self.created_at     = _now()
        self.started_at:    str | None = None
        self.completed_at:  str | None = None
        self.error_message: str | None = None

        self.documents_processed = 0
        self.documents_failed    = 0
        self.total_documents     = 0
        self.entities_created    = 0
        self.relationships_created = 0
        self.failed_documents: list[dict] = []

        # Thread-safe event queue; async generator drains it
        self._q:      queue.Queue = queue.Queue()
        self._cancel: threading.Event = threading.Event()

    def emit(self, event: dict) -> None:
        self._q.put(event)

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    async def stream_events(self) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted strings.
        Uses run_in_executor so the blocking queue.get() doesn't block the
        event loop while the processing thread writes events.
        """
        loop = asyncio.get_event_loop()
        terminal = {"processing_completed", "processing_failed", "processing_cancelled"}

        while True:
            try:
                event = await loop.run_in_executor(
                    None, lambda: self._q.get(timeout=5.0)
                )
                event_type = event.get("event_type", "message")
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                if event_type in terminal:
                    break
            except queue.Empty:
                yield ": heartbeat\n\n"

    def to_status_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            documents_processed=self.documents_processed,
            documents_failed=self.documents_failed,
            total_documents=self.total_documents,
            dry_run=self.dry_run,
            error_message=self.error_message,
            total_entities_created=self.entities_created,
            total_relationships_created=self.relationships_created,
            failed_documents=self.failed_documents,
        )


# ── Processing logic (runs in thread) ─────────────────────────────────────────

def _run(job: ProcessingJob) -> None:
    from parser import parse_header, parse_note, resolve_backlinks

    job.status     = JobStatus.IN_PROGRESS
    job.started_at = _now()
    start_time     = time.monotonic()

    try:
        # 1. Enumerate all .md files across selected folders
        all_files: list[Path] = []
        for folder_path in job.selected_paths:
            if not folder_path.is_dir():
                continue
            for md in sorted(folder_path.rglob("*.md")):
                if not any(p.startswith(".") for p in md.relative_to(job.vault_root).parts):
                    all_files.append(md)

        job.total_documents = len(all_files)
        job.emit({
            "event_type":       "processing_started",
            "job_id":           job.job_id,
            "timestamp":        _now(),
            "total_documents":  job.total_documents,
            "dry_run":          job.dry_run,
        })

        notes = []
        current_folder: str | None = None

        # 2. Parse each file and emit per-document events
        for file_path in all_files:
            if job.is_cancelled():
                job.status = JobStatus.CANCELLED
                job.emit({
                    "event_type":          "processing_cancelled",
                    "job_id":              job.job_id,
                    "timestamp":           _now(),
                    "status":              "cancelled",
                    "documents_processed": job.documents_processed,
                    "documents_failed":    job.documents_failed,
                    "message":             "Processing cancelled by user",
                })
                return

            folder_name = str(file_path.parent.relative_to(job.vault_root)).replace("\\", "/")
            if folder_name != current_folder:
                current_folder = folder_name
                job.emit({
                    "event_type":      "folder_started",
                    "timestamp":       _now(),
                    "current_folder":  current_folder,
                })

            try:
                folder_hint = file_path.parent.name
                note = parse_note(file_path, job.vault_root, folder_hint)
                notes.append(note)
                job.documents_processed += 1

                elapsed = time.monotonic() - start_time
                rate    = job.documents_processed / elapsed if elapsed > 0 else 0
                remaining = (
                    (job.total_documents - job.documents_processed) / rate
                    if rate > 0 else 0
                )

                job.emit({
                    "event_type":                    "document_processed",
                    "timestamp":                     _now(),
                    "document":                      file_path.name,
                    "relative_path":                 folder_name + "/" + file_path.name,
                    "documents_processed_so_far":    job.documents_processed,
                    "documents_failed_so_far":       job.documents_failed,
                    "total_documents":               job.total_documents,
                    "processing_rate_docs_per_sec":  round(rate, 2),
                    "estimated_time_remaining_seconds": round(remaining),
                    "entities_created":              job.entities_created,
                    "relationships_created":         job.relationships_created,
                })

            except Exception as exc:
                job.documents_failed += 1
                job.failed_documents.append({
                    "filename":    file_path.name,
                    "error":       str(exc),
                    "error_code":  "PARSE_ERROR",
                })
                job.emit({
                    "event_type":                 "processing_error",
                    "timestamp":                  _now(),
                    "error_code":                 "PARSE_ERROR",
                    "error_message":              str(exc),
                    "document":                   file_path.name,
                    "relative_path":              folder_name + "/" + file_path.name,
                    "documents_processed_so_far": job.documents_processed,
                    "documents_failed_so_far":    job.documents_failed,
                })

        # 3. Write to Neo4j (unless dry run)
        if not job.dry_run and notes:
            resolve_backlinks(notes)

            from config import BATCH_SIZE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
            from graph import GraphBuilder

            uri      = job.neo4j_uri      or NEO4J_URI
            user     = job.neo4j_user     or NEO4J_USER
            password = job.neo4j_password or NEO4J_PASSWORD
            db = GraphBuilder(uri, user, password)
            try:
                if job.clear_graph:
                    job.emit({
                        "event_type": "graph_clearing",
                        "job_id":     job.job_id,
                        "timestamp":  _now(),
                    })
                    db.clear_graph()
                db.create_constraints()
                for i in range(0, len(notes), BATCH_SIZE):
                    db.upsert_notes(notes[i : i + BATCH_SIZE])
                db.upsert_relationships(notes)
                stats = db.get_stats()
                job.entities_created       = stats.get("nodes", 0)
                job.relationships_created  = stats.get("relationships", 0)
            finally:
                db.close()

        elapsed = time.monotonic() - start_time
        job.status       = JobStatus.COMPLETED
        job.completed_at = _now()

        job.emit({
            "event_type":                 "processing_completed",
            "job_id":                     job.job_id,
            "timestamp":                  _now(),
            "status":                     "completed",
            "total_documents_processed":  job.documents_processed,
            "total_documents_failed":     job.documents_failed,
            "total_entities_created":     job.entities_created,
            "total_relationships_created": job.relationships_created,
            "duration_seconds":           round(elapsed),
            "documents_per_second":       round(job.documents_processed / elapsed, 2) if elapsed > 0 else 0,
            "failed_documents":           job.failed_documents,
        })

    except Exception as exc:
        job.status        = JobStatus.FAILED
        job.error_message = str(exc)
        job.emit({
            "event_type":                 "processing_failed",
            "job_id":                     job.job_id,
            "timestamp":                  _now(),
            "status":                     "failed",
            "error_code":                 "CRITICAL_ERROR",
            "error_message":              str(exc),
            "documents_processed_so_far": job.documents_processed,
            "documents_failed_so_far":    job.documents_failed,
        })


# ── ProcessorService ──────────────────────────────────────────────────────────

class ProcessorService:
    def __init__(self, tree: TreeBuilder) -> None:
        self._tree = tree
        self._jobs: dict[str, ProcessingJob] = {}
        self._active_job_id: str | None = None

    def active_job(self) -> ProcessingJob | None:
        if self._active_job_id:
            job = self._jobs.get(self._active_job_id)
            if job and job.status == JobStatus.IN_PROGRESS:
                return job
        return None

    def check_neo4j(
        self,
        neo4j_uri:      str | None = None,
        neo4j_user:     str | None = None,
        neo4j_password: str | None = None,
    ) -> bool:
        try:
            import sys
            _src = Path(__file__).parent.parent
            if str(_src) not in sys.path:
                sys.path.insert(0, str(_src))
            from config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
            from graph import GraphBuilder
            uri      = neo4j_uri      or NEO4J_URI
            user     = neo4j_user     or NEO4J_USER
            password = neo4j_password or NEO4J_PASSWORD
            db = GraphBuilder(uri, user, password)
            ok = db.verify_connection()
            db.close()
            return ok
        except Exception:
            return False

    def start(
        self,
        selected_folder_ids: list[str],
        vault_root: Path,
        dry_run: bool = False,
        clear_graph: bool = False,
        neo4j_uri:      str | None = None,
        neo4j_user:     str | None = None,
        neo4j_password: str | None = None,
    ) -> ProcessingJob:
        selected_paths = []
        for fid in selected_folder_ids:
            p = self._tree.get_folder_path(fid)
            if p:
                selected_paths.append(p)

        job_id = str(uuid.uuid4())
        job    = ProcessingJob(
            job_id=job_id,
            selected_paths=selected_paths,
            vault_root=vault_root,
            dry_run=dry_run,
            clear_graph=clear_graph,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )
        self._jobs[job_id]   = job
        self._active_job_id  = job_id

        _executor.submit(_run, job)
        return job

    def get_job(self, job_id: str) -> ProcessingJob | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.IN_PROGRESS:
            job.cancel()
            return True
        return False

    def recent_jobs(self, limit: int = 10, offset: int = 0) -> list[ProcessingJob]:
        all_jobs = list(reversed(list(self._jobs.values())))
        return all_jobs[offset : offset + limit]
