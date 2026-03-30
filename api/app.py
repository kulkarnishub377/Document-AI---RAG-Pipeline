# api/app.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI REST + WebSocket Server
# v3.1 — Lifespan context manager, asyncio.to_thread for all sync ops,
#         configurable CORS, new endpoints (search, batch, export/import,
#         versions, crawl, query analytics), improved security
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

import pipeline
from config import (
    ALLOWED_EXTENSIONS,
    ANNOTATED_PDF_DIR,
    API_PORT,
    CORS_ORIGINS,
    CRAWL_ENABLED,
    CRAWL_INTERVAL_MINS,
    FRONTEND_DIR,
    MAX_FILE_SIZE_MB,
    UPLOAD_DIR,
    WS_ENABLED,
    __version__,
)
from llm.prompt_chains import check_ollama_connection
from utils.cache import query_cache
from utils.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    PipelineError,
    UnsupportedFileTypeError,
)
from utils.rate_limiter import rate_limiter
from utils.sessions import session_manager


# ── Pydantic Request/Response Models ─────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    source_filter: Optional[str] = None

class SummarizeRequest(BaseModel):
    topic: str = "the document"
    source_filter: Optional[str] = None

class ExtractRequest(BaseModel):
    fields: List[str] = Field(..., min_length=1)
    context_query: str = ""

class CompareRequest(BaseModel):
    doc_a: str
    doc_b: str
    question: str = ""

class TableQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    source_filter: Optional[str] = None

class UrlIngestRequest(BaseModel):
    url: str = Field(..., min_length=5)

class SessionCreate(BaseModel):
    title: str = "Untitled"

class BatchQueryRequest(BaseModel):
    questions: List[str] = Field(..., min_length=1, max_length=50)
    source_filter: Optional[str] = None

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(20, ge=1, le=100)
    source_filter: Optional[str] = None

class CrawlUrlRequest(BaseModel):
    url: str = Field(..., min_length=5)


# ── Scheduled Crawl Background Thread (v3.1 — F9) ───────────────────────────

_crawl_timer: Optional[threading.Timer] = None

def _start_crawl_scheduler():
    """Start the background crawl scheduler."""
    global _crawl_timer

    def crawl_loop():
        global _crawl_timer
        try:
            urls = pipeline.get_crawl_urls()
            if urls:
                logger.info(f"Running scheduled crawl for {len(urls)} URLs")
                pipeline.run_scheduled_crawl()
        except Exception as e:
            logger.error(f"Scheduled crawl failed: {e}")
        finally:
            _crawl_timer = threading.Timer(CRAWL_INTERVAL_MINS * 60, crawl_loop)
            _crawl_timer.daemon = True
            _crawl_timer.start()

    if CRAWL_ENABLED:
        _crawl_timer = threading.Timer(CRAWL_INTERVAL_MINS * 60, crawl_loop)
        _crawl_timer.daemon = True
        _crawl_timer.start()
        logger.info(f"Scheduled crawl enabled: every {CRAWL_INTERVAL_MINS} minutes")


# ── Background Task Tracker (v3.1 — F3) ─────────────────────────────────────

_tasks: Dict[str, Dict[str, Any]] = {}

def _track_task(task_id: str, status: str = "running", result: Any = None) -> None:
    _tasks[task_id] = {
        "task_id": task_id,
        "status": status,
        "result": result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Lifespan (v3.1 — replaces deprecated @app.on_event) ─────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(f"Document AI Pipeline v{__version__} starting...")

    # Load index on startup
    try:
        from embedding.vector_store import load_index
        loaded = load_index()
        if loaded:
            stats = pipeline.status()
            logger.info(
                f"Index loaded: {stats['total_vectors']} vectors, "
                f"{stats['unique_sources']} sources"
            )
        else:
            logger.info("No existing index found — ready for first ingestion")
    except Exception as e:
        logger.warning(f"Index load skipped: {e}")

    # Start crawl scheduler
    _start_crawl_scheduler()

    yield

    # Shutdown
    global _crawl_timer
    if _crawl_timer:
        _crawl_timer.cancel()
    logger.info("Pipeline shutting down...")


# ── App Instance ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Document AI + RAG Pipeline",
    version=__version__,
    description="Local-first RAG pipeline with multi-format document ingestion, "
                "hybrid search, and AI-powered Q&A.",
    lifespan=lifespan,
)

# CORS — v3.1: Configurable origins from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.exception_handler(PipelineError)
async def pipeline_error_handler(request: Request, exc: PipelineError):
    status_map = {
        "DocumentNotFoundError": 404,
        "UnsupportedFileTypeError": 400,
        "FileTooLargeError": 413,
        "RateLimitExceededError": 429,
        "IndexNotFoundError": 404,
        "OllamaNotReachableError": 503,
        "IngestionError": 500,
    }
    code = status_map.get(type(exc).__name__, 500)
    return JSONResponse(status_code=code, content={"detail": exc.message})

@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    return JSONResponse(status_code=422, content={"errors": str(exc)})


# ── Utility Functions ────────────────────────────────────────────────────────

# Windows reserved filenames
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

def _safe_filename(name: str) -> str:
    """
    Sanitize a filename for safe storage.
    v3.1: Added Windows reserved name checks and hidden file protection.
    """
    name = Path(name).name  # Strip any directory traversal
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)  # Remove unsafe chars
    name = name.strip('. ')  # Remove leading/trailing dots and spaces

    # Block Windows reserved names
    stem = Path(name).stem.upper()
    if stem in _WINDOWS_RESERVED:
        name = f"_{name}"

    # Block hidden files (starting with .)
    if name.startswith('.'):
        name = f"_{name}"

    return name or "unnamed_file"

def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Health & Status Endpoints ────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__}

@app.get("/status")
async def get_status():
    return await asyncio.to_thread(pipeline.status)

@app.get("/analytics")
async def get_analytics():
    return await asyncio.to_thread(pipeline.get_analytics)


# ── Document Management ─────────────────────────────────────────────────────

@app.get("/documents")
async def list_documents():
    return await asyncio.to_thread(pipeline.list_documents)

@app.delete("/document/{filename}")
async def delete_document(filename: str):
    try:
        return await asyncio.to_thread(pipeline.delete_document, filename)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

@app.post("/clear")
async def clear_index():
    return await asyncio.to_thread(pipeline.clear_index)


# ── Document Ingestion ───────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_file(request: Request, file: UploadFile = File(...)):
    # Rate limit check
    client_ip = _get_client_ip(request)
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Validate filename
    safe_name = _safe_filename(file.filename or "unnamed")
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Path traversal check
    if ".." in (file.filename or ""):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Read and check size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f} MB (max: {MAX_FILE_SIZE_MB} MB)"
        )

    # Save to disk
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(content)

    # Run ingestion in thread pool
    try:
        result = await asyncio.to_thread(pipeline.ingest, str(file_path), safe_name)
        return result
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/ingest/url")
async def ingest_url(body: UrlIngestRequest):
    try:
        return await asyncio.to_thread(pipeline.ingest_url, body.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/async")
async def ingest_file_async(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
):
    """
    v3.1 (F3): Async ingestion — returns immediately with a task ID.
    Check progress via GET /tasks/{task_id}
    """
    import uuid
    task_id = str(uuid.uuid4())[:12]

    safe_name = _safe_filename(file.filename or "unnamed")
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'")

    content = await file.read()
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(content)

    def run_ingest():
        _track_task(task_id, "running")
        try:
            result = pipeline.ingest(str(file_path), safe_name)
            _track_task(task_id, "completed", result)
        except Exception as e:
            _track_task(task_id, "failed", {"error": str(e)})

    background_tasks.add_task(run_ingest)
    _track_task(task_id, "queued")

    return {"task_id": task_id, "status": "queued", "filename": safe_name}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of an async task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ── Query Endpoints ──────────────────────────────────────────────────────────

@app.post("/query")
async def query_endpoint(body: QueryRequest, request: Request):
    client_ip = _get_client_ip(request)
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not check_ollama_connection():
        # Allow demo mode to still work
        pass

    # Check cache
    cached = query_cache.get(body.question, "qa", body.source_filter or "")
    if cached:
        try:
            from features.query_analytics import query_analytics
            query_analytics.record_query(body.question, "qa", 0, cached=True)
        except Exception:
            pass
        return cached

    # Get chat history if session provided
    history = None
    if body.session_id:
        try:
            history = session_manager.get_chat_history(body.session_id)
        except Exception:
            pass

    result = await asyncio.to_thread(
        pipeline.query, body.question, body.source_filter, history
    )

    # Store in session
    if body.session_id:
        try:
            session_manager.add_message(body.session_id, "user", body.question)
            session_manager.add_message(
                body.session_id, "assistant",
                result.get("answer", ""),
                sources=result.get("sources"),
            )
        except Exception as e:
            logger.warning(f"Session save failed: {e}")

    # Cache
    query_cache.put(result, body.question, "qa", body.source_filter or "")

    return result


@app.post("/query-stream")
async def query_stream(body: QueryRequest):
    """SSE streaming endpoint for real-time query responses."""
    from llm.prompt_chains import stream_answer_question

    candidates = await asyncio.to_thread(
        pipeline._search, body.question, source_filter=body.source_filter
    )

    if not candidates:
        async def empty_stream():
            yield f"data: {json.dumps({'delta': 'No relevant documents found.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    reranked = await asyncio.to_thread(pipeline._rerank, body.question, candidates)

    sources = [
        {"source": r.source, "page": r.page_num, "excerpt": r.text[:300],
         "score": round(r.score, 4), "chunk_type": r.chunk_type}
        for r in reranked
    ]

    history = None
    if body.session_id:
        try:
            history = session_manager.get_chat_history(body.session_id)
        except Exception:
            pass

    async def event_generator():
        yield f"data: {json.dumps({'sources': sources})}\n\n"

        full_answer = ""
        async for token in stream_answer_question(body.question, reranked, history):
            full_answer += token
            yield f"data: {json.dumps({'delta': token})}\n\n"

        yield "data: [DONE]\n\n"

        # Save to session
        if body.session_id:
            try:
                session_manager.add_message(body.session_id, "user", body.question)
                session_manager.add_message(
                    body.session_id, "assistant", full_answer, sources=sources
                )
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Semantic Search (v3.1 — F7) ──────────────────────────────────────────────

@app.post("/search")
async def semantic_search(body: SearchRequest):
    """Raw semantic search without LLM generation."""
    results = await asyncio.to_thread(
        pipeline.semantic_search, body.query, body.top_k, body.source_filter
    )
    return {"results": results, "total": len(results), "query": body.query}


# ── Batch Q&A (v3.1 — F14) ───────────────────────────────────────────────────

@app.post("/query/batch")
async def batch_query(body: BatchQueryRequest):
    """Answer multiple questions in batch."""
    results = await asyncio.to_thread(
        pipeline.batch_query, body.questions, body.source_filter
    )
    return {"results": results, "total": len(results)}


# ── Intelligence Endpoints ───────────────────────────────────────────────────

@app.post("/summarize")
async def summarize(body: SummarizeRequest):
    return await asyncio.to_thread(pipeline.get_summary, body.topic, body.source_filter)

@app.post("/extract")
async def extract_fields(body: ExtractRequest):
    if not body.fields:
        raise HTTPException(status_code=422, detail="Fields list cannot be empty")
    return await asyncio.to_thread(pipeline.extract, body.fields, body.context_query)

@app.post("/table-query")
async def table_query(body: TableQueryRequest):
    return await asyncio.to_thread(pipeline.query_table, body.question, body.source_filter)

@app.post("/compare")
async def compare_documents(body: CompareRequest):
    result = await asyncio.to_thread(
        pipeline.compare_documents, body.doc_a, body.doc_b, body.question
    )
    # Compatibility alias for frontend
    result["comparison"] = result.get("analysis", "")
    return result


# ── Export / Import (v3.1 — F5) ──────────────────────────────────────────────

@app.get("/export")
async def export_index():
    """Download the index as a zip file."""
    zip_bytes = await asyncio.to_thread(pipeline.export_index_zip)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="docuai_index.zip"'},
    )

@app.post("/import")
async def import_index(file: UploadFile = File(...)):
    """Import an index from a zip file."""
    content = await file.read()
    try:
        result = await asyncio.to_thread(pipeline.import_index_zip, content)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


# ── Document Versioning (v3.1 — F2) ──────────────────────────────────────────

@app.get("/versions")
async def get_all_versions():
    """Get version history for all documents."""
    return await asyncio.to_thread(pipeline.get_all_versions)

@app.get("/versions/{filename}")
async def get_document_versions(filename: str):
    """Get version history for a specific document."""
    versions = await asyncio.to_thread(pipeline.get_document_versions, filename)
    return {"filename": filename, "versions": versions}


# ── Scheduled Crawl (v3.1 — F9) ──────────────────────────────────────────────

@app.get("/crawl/urls")
async def list_crawl_urls():
    return {"urls": pipeline.get_crawl_urls(), "enabled": CRAWL_ENABLED}

@app.post("/crawl/add")
async def add_crawl_url(body: CrawlUrlRequest):
    pipeline.add_crawl_url(body.url)
    return {"status": "added", "url": body.url, "total": len(pipeline.get_crawl_urls())}

@app.post("/crawl/remove")
async def remove_crawl_url(body: CrawlUrlRequest):
    pipeline.remove_crawl_url(body.url)
    return {"status": "removed", "url": body.url}

@app.post("/crawl/run")
async def run_crawl_now():
    """Manually trigger a scheduled crawl."""
    result = await asyncio.to_thread(pipeline.run_scheduled_crawl)
    return result


# ── Query Analytics (v3.1 — F10) ─────────────────────────────────────────────

@app.get("/query-analytics")
async def get_query_analytics():
    from features.query_analytics import query_analytics
    return query_analytics.get_stats()

@app.post("/query-analytics/clear")
async def clear_query_analytics():
    from features.query_analytics import query_analytics
    count = query_analytics.clear()
    return {"cleared": count}


# ── Session Endpoints ────────────────────────────────────────────────────────

@app.get("/sessions")
async def list_sessions():
    return session_manager.list_sessions()

@app.post("/sessions")
async def create_session(body: SessionCreate):
    return session_manager.create_session(body.title)

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, limit: int = Query(100, ge=1, le=500)):
    return session_manager.get_messages(session_id, limit)

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


# ── Cache Endpoints ──────────────────────────────────────────────────────────

@app.get("/cache/stats")
async def cache_stats():
    return query_cache.stats()

@app.post("/cache/clear")
async def clear_cache():
    count = query_cache.invalidate()
    return {"entries_removed": count}


# ── Knowledge Graph Endpoints ────────────────────────────────────────────────

@app.get("/knowledge-graph")
async def get_knowledge_graph():
    from features.knowledge_graph import knowledge_graph
    return knowledge_graph.get_graph_data()

@app.get("/knowledge-graph/search")
async def search_kg(q: str = "", entity_type: str = "", limit: int = 50):
    from features.knowledge_graph import knowledge_graph
    return knowledge_graph.search_entities(q, entity_type, limit)

@app.post("/knowledge-graph/reset")
async def reset_kg():
    from features.knowledge_graph import knowledge_graph
    knowledge_graph.reset()
    return {"status": "knowledge graph cleared"}


# ── Evaluation Endpoints ─────────────────────────────────────────────────────

@app.post("/evaluate")
async def evaluate_query(body: QueryRequest):
    """Run RAGAS evaluation on a query."""
    result = await asyncio.to_thread(
        pipeline.query, body.question, body.source_filter
    )

    from features.evaluation import evaluator
    contexts = [s["excerpt"] for s in result.get("sources", [])]
    eval_result = await asyncio.to_thread(
        evaluator.evaluate,
        body.question,
        result.get("answer", ""),
        contexts,
    )

    from dataclasses import asdict
    return {**result, "evaluation": asdict(eval_result)}

@app.get("/evaluate/dashboard")
async def evaluation_dashboard():
    from features.evaluation import evaluator
    return evaluator.get_dashboard_stats()

@app.get("/evaluate/history")
async def evaluation_history(limit: int = Query(50, ge=1, le=200)):
    from features.evaluation import evaluator
    return evaluator.get_history(limit)

@app.post("/evaluate/clear")
async def clear_evaluations():
    from features.evaluation import evaluator
    count = evaluator.clear_history()
    return {"cleared": count}


# ── PDF Annotation ───────────────────────────────────────────────────────────

@app.post("/annotate")
async def annotate_pdf(body: QueryRequest):
    """Generate annotated PDF with highlighted source passages."""
    result = await asyncio.to_thread(
        pipeline.query, body.question, body.source_filter
    )
    sources = result.get("sources", [])
    if not sources:
        return {"annotated_files": {}, "answer": result.get("answer", "")}

    from features.pdf_annotator import annotate_from_sources
    annotated = await asyncio.to_thread(annotate_from_sources, sources)

    return {
        "annotated_files": annotated,
        "answer": result.get("answer", ""),
        "sources": sources,
    }

@app.get("/annotated")
async def list_annotated():
    from features.pdf_annotator import list_annotated as _list
    return _list()

@app.get("/annotated/{filename}")
async def download_annotated(filename: str):
    path = ANNOTATED_PDF_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Annotated PDF not found")
    return FileResponse(str(path), filename=filename)


# ── File Download ────────────────────────────────────────────────────────────

@app.get("/download/{filename}")
async def download_file(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), filename=filename)


# ── WebSocket Collaboration ──────────────────────────────────────────────────

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str = "default"):
    if not WS_ENABLED:
        await websocket.close(code=1008, reason="WebSocket disabled")
        return

    from features.collaboration import collab_manager

    username = websocket.query_params.get("username", "Anonymous")
    ws_id = await collab_manager.connect(websocket, room_id, username)

    try:
        while True:
            data = await websocket.receive_json()

            # v3.1 (S6): Validate and limit WebSocket input
            msg_type = str(data.get("type", ""))[:50]
            question = str(data.get("question", ""))[:2000]

            if msg_type == "query" and question:
                # Broadcast the question
                await collab_manager.broadcast(room_id, {
                    "type": "user_query",
                    "user": username,
                    "question": question,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Run query in thread pool (v3.1: fix event loop blocking)
                try:
                    result = await asyncio.to_thread(pipeline.query, question)
                    await collab_manager.broadcast(room_id, {
                        "type": "query_result",
                        "user": username,
                        "question": question,
                        "answer": result.get("answer", ""),
                        "sources": result.get("sources", []),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    await collab_manager.send_to(ws_id, {
                        "type": "error",
                        "message": str(e),
                    })

    except WebSocketDisconnect:
        collab_manager.disconnect(ws_id)
        await collab_manager.broadcast(room_id, {
            "type": "user_left",
            "user": username,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
