# api/app.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI REST Server — v3.0
#
# 30+ endpoints covering ingestion, querying, sessions, knowledge graph,
# document comparison, collaboration, PDF annotation, and analytics.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from loguru import logger

import pipeline
from config import (
    __version__, FRONTEND_DIR, UPLOAD_DIR, MAX_FILE_SIZE_MB,
    ALLOWED_EXTENSIONS, API_VERSION, WS_ENABLED,
    KNOWLEDGE_GRAPH_ENABLED,
)
from llm.prompt_chains import (
    check_ollama_connection,
    stream_answer_question,
)
from utils.cache import query_cache
from utils.rate_limiter import rate_limiter
from utils.sessions import session_manager
from utils.exceptions import (
    PipelineError,
    DocumentNotFoundError,
    UnsupportedFileTypeError,
    FileTooLargeError,
    OllamaNotReachableError,
    RateLimitExceededError,
)

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Document AI + RAG Pipeline",
    description=(
        "Upload any document (PDF, Image, Excel, PowerPoint, Word, CSV, text, or web URL) "
        "and ask questions in plain English. Fully local, private, and powered by Mistral via Ollama."
    ),
    version=__version__,
    docs_url=f"/api/{API_VERSION}/docs",
    redoc_url=f"/api/{API_VERSION}/redoc",
    openapi_url=f"/api/{API_VERSION}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000, description="Your question in natural language")
    source_filter: Optional[str] = Field(None, description="Filter to a specific source document")
    session_id: Optional[str] = Field(None, description="Session ID for persistent chat history")
    history: Optional[List[Dict[str, str]]] = Field(None, description="Chat history for context")


class UrlIngestRequest(BaseModel):
    url: str = Field(..., min_length=10, description="Web URL to ingest")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class SummarizeRequest(BaseModel):
    topic: str = Field(default="the document", max_length=500)


class ExtractRequest(BaseModel):
    fields: List[str] = Field(..., min_length=1, description="Field names to extract")
    context_query: str = Field(default="", max_length=1000)


class TableQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class CompareRequest(BaseModel):
    doc_a: str = Field(..., description="Filename of first document")
    doc_b: str = Field(..., description="Filename of second document")
    question: str = Field(default="", description="Specific comparison question")


class SessionCreateRequest(BaseModel):
    title: str = Field(default="Untitled", max_length=200)


class SessionMessageRequest(BaseModel):
    role: str = Field(default="user")
    content: str = Field(..., min_length=1, max_length=10000)
    mode: str = Field(default="qa")


class SourceResult(BaseModel):
    source: str
    page: int
    excerpt: str
    score: float
    chunk_type: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceResult]


# ─────────────────────────────────────────────────────────────────────────────
# Middleware: Rate Limiting
# ─────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all non-static endpoints."""
    path = request.url.path
    # Skip static files and health checks
    if path.startswith("/frontend") or path == "/health" or path == "/":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Please try again later.",
                "remaining": 0,
                "limit": rate_limiter.max_requests,
                "window_secs": rate_limiter.window_secs,
            },
        )

    response = await call_next(request)
    # Add rate limit headers
    response.headers["X-RateLimit-Remaining"] = str(rate_limiter.remaining(client_ip))
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(PipelineError)
async def pipeline_error_handler(request: Request, exc: PipelineError):
    """Handle all custom pipeline exceptions."""
    status_map = {
        DocumentNotFoundError: 404,
        UnsupportedFileTypeError: 400,
        FileTooLargeError: 413,
        OllamaNotReachableError: 503,
        RateLimitExceededError: 429,
    }
    status_code = status_map.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": exc.message})


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return clean validation error messages."""
    errors = []
    for err in exc.errors():
        field = " → ".join(str(loc) for loc in err["loc"])
        errors.append({"field": field, "message": err["msg"]})
    return JSONResponse(status_code=422, content={"errors": errors})


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    logger.info(f"Document AI + RAG Pipeline v{__version__} starting up...")
    info = pipeline.startup()
    logger.info(f"Startup complete: {info}")


# ─────────────────────────────────────────────────────────────────────────────
# Static Files + Frontend
# ─────────────────────────────────────────────────────────────────────────────

app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the premium web UI."""
    return FileResponse(FRONTEND_DIR / "index.html")


# ─────────────────────────────────────────────────────────────────────────────
# Health & Status
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Core"], summary="Health check")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/status", tags=["Core"], summary="Index statistics + Ollama status")
async def status():
    return pipeline.status()


@app.get("/analytics", tags=["Core"], summary="Detailed storage & document analytics")
async def analytics():
    return pipeline.get_analytics()


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/ingest", tags=["Ingestion"], summary="Upload a single document")
async def ingest(file: UploadFile = File(...)):
    """Ingest a document: PDF, Image, DOCX, Excel, PPTX, CSV, TXT, or Markdown."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(suffix, ALLOWED_EXTENSIONS)

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(size_mb, MAX_FILE_SIZE_MB)

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(content)

    try:
        result = pipeline.ingest(save_path)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))

    return result


@app.post("/ingest/url", tags=["Ingestion"], summary="Ingest a web URL")
async def ingest_url(req: UrlIngestRequest):
    """Fetch a web page, extract text, and index it."""
    try:
        result = pipeline.ingest_url(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/ingest/batch", tags=["Ingestion"], summary="Upload multiple documents at once")
async def ingest_batch(files: List[UploadFile] = File(...)):
    """Batch upload and ingest multiple documents."""
    results = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            results.append({"file": file.filename, "error": f"Unsupported type: {suffix}"})
            continue

        content = await file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            results.append({"file": file.filename, "error": f"Too large: {size_mb:.1f} MB"})
            continue

        save_path = UPLOAD_DIR / file.filename
        with open(save_path, "wb") as f:
            f.write(content)

        try:
            result = pipeline.ingest(save_path)
            results.append(result)
        except Exception as e:
            save_path.unlink(missing_ok=True)
            results.append({"file": file.filename, "error": str(e)})

    return {"results": results, "total": len(results)}


# ─────────────────────────────────────────────────────────────────────────────
# Query & AI
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/query", tags=["Query"], summary="Ask a question (sync)", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    """Ask a question about your documents. Returns answer with source citations."""
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")

    # Get history from session if provided
    history = req.history
    if req.session_id and not history:
        history = session_manager.get_chat_history(req.session_id)

    result = pipeline.query(
        req.question,
        source_filter=req.source_filter,
        history=history,
    )

    # Save to session if provided
    if req.session_id:
        session_manager.add_message(req.session_id, "user", req.question, mode="qa")
        session_manager.add_message(
            req.session_id, "assistant", result["answer"],
            sources=result.get("sources", []), mode="qa",
        )

    return result


@app.post("/query-stream", tags=["Query"], summary="Ask a question (streaming SSE)")
async def query_stream(req: QueryRequest):
    """
    Streaming Server-Sent Events endpoint for real-time answer generation.
    Returns chunks of the answer as they are generated by the LLM.
    """
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")

    # Get relevant chunks
    results = pipeline.get_relevant_chunks(req.question, source_filter=req.source_filter)

    history = req.history
    if req.session_id and not history:
        history = session_manager.get_chat_history(req.session_id)

    return StreamingResponse(
        stream_answer_question(req.question, results, history=history),
        media_type="text/event-stream",
    )


@app.post("/summarize", tags=["Query"], summary="Summarize documents by topic")
async def summarize_endpoint(req: SummarizeRequest):
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")
    return pipeline.get_summary(req.topic)


@app.post("/extract", tags=["Query"], summary="Extract structured fields as JSON")
async def extract_endpoint(req: ExtractRequest):
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")
    return pipeline.extract(req.fields, req.context_query)


@app.post("/table-query", tags=["Query"], summary="Ask about tables in documents")
async def table_query_endpoint(req: TableQueryRequest):
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")
    return pipeline.query_table(req.question)


# ─────────────────────────────────────────────────────────────────────────────
# Document Comparison (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/compare", tags=["Comparison"], summary="Compare two documents")
async def compare_documents(req: CompareRequest):
    """Compare two documents and get analysis of similarities, differences, and unique content."""
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")
    return pipeline.compare_documents(req.doc_a, req.doc_b, req.question)


# ─────────────────────────────────────────────────────────────────────────────
# Sessions (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sessions", tags=["Sessions"], summary="Create a new chat session")
async def create_session(req: SessionCreateRequest):
    return session_manager.create_session(req.title)


@app.get("/sessions", tags=["Sessions"], summary="List recent chat sessions")
async def list_sessions(limit: int = 50):
    return session_manager.list_sessions(limit)


@app.get("/sessions/{session_id}", tags=["Sessions"], summary="Get session details")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@app.get("/sessions/{session_id}/messages", tags=["Sessions"], summary="Get messages in a session")
async def get_messages(session_id: str, limit: int = 100):
    return session_manager.get_messages(session_id, limit)


@app.post("/sessions/{session_id}/messages", tags=["Sessions"], summary="Add a message to a session")
async def add_message(session_id: str, req: SessionMessageRequest):
    return session_manager.add_message(session_id, req.role, req.content, mode=req.mode)


@app.delete("/sessions/{session_id}", tags=["Sessions"], summary="Delete a session")
async def delete_session(session_id: str):
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"status": "deleted"}


@app.get("/sessions-stats", tags=["Sessions"], summary="Get session statistics")
async def session_stats():
    return session_manager.get_stats()


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Graph (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/knowledge-graph", tags=["Knowledge Graph"], summary="Get full knowledge graph data")
async def get_knowledge_graph():
    if not KNOWLEDGE_GRAPH_ENABLED:
        raise HTTPException(status_code=404, detail="Knowledge graph is disabled")
    from features.knowledge_graph import knowledge_graph
    return knowledge_graph.get_graph_data()


@app.get("/knowledge-graph/entities", tags=["Knowledge Graph"], summary="Search entities")
async def search_entities(query: str = "", entity_type: str = "", limit: int = 50):
    if not KNOWLEDGE_GRAPH_ENABLED:
        raise HTTPException(status_code=404, detail="Knowledge graph is disabled")
    from features.knowledge_graph import knowledge_graph
    return knowledge_graph.search_entities(query, entity_type, limit)


@app.get("/knowledge-graph/entity/{name}", tags=["Knowledge Graph"], summary="Get entity details")
async def get_entity(name: str):
    if not KNOWLEDGE_GRAPH_ENABLED:
        raise HTTPException(status_code=404, detail="Knowledge graph is disabled")
    from features.knowledge_graph import knowledge_graph
    entity = knowledge_graph.get_entity(name)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return entity


# ─────────────────────────────────────────────────────────────────────────────
# PDF Annotation (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/annotate", tags=["PDF Annotation"], summary="Create annotated PDF with highlighted sources")
async def annotate_pdf(req: QueryRequest):
    """Answer a question and create an annotated PDF highlighting the source passages."""
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")

    result = pipeline.query(req.question)
    sources = result.get("sources", [])

    from features.pdf_annotator import annotate_from_sources
    annotated = annotate_from_sources(sources)

    return {
        "answer": result["answer"],
        "sources": sources,
        "annotated_pdfs": annotated,
    }


@app.get("/annotated", tags=["PDF Annotation"], summary="List all annotated PDFs")
async def list_annotated():
    from features.pdf_annotator import list_annotated
    return list_annotated()


@app.get("/annotated/{filename}", tags=["PDF Annotation"], summary="Download an annotated PDF")
async def download_annotated(filename: str):
    from config import ANNOTATED_PDF_DIR
    file_path = ANNOTATED_PDF_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Annotated PDF '{filename}' not found")
    return FileResponse(str(file_path), media_type="application/pdf", filename=filename)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Collaboration (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

if WS_ENABLED:
    from features.collaboration import collab_manager

    @app.websocket("/ws/{room_id}")
    async def websocket_endpoint(websocket: WebSocket, room_id: str, username: str = "Anonymous"):
        """Real-time collaboration via WebSocket."""
        ws_id = await collab_manager.connect(websocket, room_id, username)
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "query":
                    # Broadcast query to room
                    await collab_manager.broadcast(room_id, {
                        "type": "user_query",
                        "user": username,
                        "question": data.get("question", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                    # Process query
                    if check_ollama_connection():
                        result = pipeline.query(data.get("question", ""))
                        await collab_manager.broadcast(room_id, {
                            "type": "answer",
                            "user": "AI",
                            "answer": result.get("answer", ""),
                            "sources": result.get("sources", []),
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                elif msg_type == "message":
                    await collab_manager.broadcast(room_id, {
                        "type": "chat_message",
                        "user": username,
                        "content": data.get("content", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    }, exclude=ws_id)

                elif msg_type == "get_users":
                    users = collab_manager.get_room_users(room_id)
                    await collab_manager.send_to(ws_id, {
                        "type": "users_list",
                        "users": users,
                    })

        except WebSocketDisconnect:
            collab_manager.disconnect(ws_id)
            await collab_manager.broadcast(room_id, {
                "type": "user_left",
                "user": username,
                "timestamp": datetime.utcnow().isoformat(),
            })


# ─────────────────────────────────────────────────────────────────────────────
# Cache Management (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/cache/stats", tags=["Cache"], summary="Get cache statistics")
async def cache_stats():
    return query_cache.stats()


@app.post("/cache/clear", tags=["Cache"], summary="Clear the query cache")
async def cache_clear():
    count = query_cache.invalidate()
    return {"status": "cache cleared", "entries_removed": count}


# ─────────────────────────────────────────────────────────────────────────────
# Document Management
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/clear", tags=["Management"], summary="Clear the entire index")
async def clear():
    return pipeline.clear_index()


@app.delete("/document/{filename}", tags=["Management"], summary="Delete a specific document")
async def delete_document(filename: str):
    try:
        return pipeline.delete_document(filename)
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found in index")


@app.get("/documents", tags=["Management"], summary="List all uploaded documents")
async def list_documents():
    """List all documents in the uploads directory."""
    if not UPLOAD_DIR.exists():
        return []
    
    docs = []
    for f in sorted(UPLOAD_DIR.iterdir()):
        if f.is_file():
            docs.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "suffix": f.suffix.lower(),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# RAGAS Evaluation Dashboard (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

class EvalRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    contexts: List[str] = Field(..., min_length=1)
    run_all: bool = Field(default=True, description="Run all 4 metrics (slower)")


@app.post("/evaluate", tags=["Evaluation"], summary="Run RAGAS evaluation on a Q&A pair")
async def evaluate_qa(req: EvalRequest):
    """
    Evaluate the quality of a Q&A interaction using RAGAS metrics:
    faithfulness, answer relevancy, context precision, context recall.
    """
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")

    from features.evaluation import evaluator
    result = evaluator.evaluate(
        question=req.question,
        answer=req.answer,
        contexts=req.contexts,
        run_all=req.run_all,
    )
    return asdict(result)


@app.post("/evaluate/auto", tags=["Evaluation"], summary="Query + auto-evaluate in one call")
async def evaluate_auto(req: QueryRequest):
    """Ask a question and automatically evaluate the answer quality."""
    if not check_ollama_connection():
        raise OllamaNotReachableError("configured URL")

    # Run query
    result = pipeline.query(req.question, source_filter=req.source_filter)
    contexts = [s.get("excerpt", "") for s in result.get("sources", [])]

    # Run evaluation
    from features.evaluation import evaluator
    eval_result = evaluator.evaluate(
        question=req.question,
        answer=result["answer"],
        contexts=contexts,
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "evaluation": asdict(eval_result),
    }


@app.get("/evaluate/dashboard", tags=["Evaluation"], summary="RAGAS dashboard statistics")
async def eval_dashboard():
    """Get aggregate RAGAS evaluation statistics and trend data."""
    from features.evaluation import evaluator
    return evaluator.get_dashboard_stats()


@app.get("/evaluate/history", tags=["Evaluation"], summary="Evaluation history")
async def eval_history(limit: int = 50):
    """Get recent evaluation results."""
    from features.evaluation import evaluator
    return evaluator.get_history(limit)


@app.post("/evaluate/clear", tags=["Evaluation"], summary="Clear evaluation history")
async def eval_clear():
    from features.evaluation import evaluator
    count = evaluator.clear_history()
    return {"status": "cleared", "entries_removed": count}

