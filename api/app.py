# api/app.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI REST API + Frontend Serving
#
# Endpoints:
#   POST /ingest          — upload and index a document
#   POST /query           — natural language Q&A
#   POST /summarize       — summarize by topic
#   POST /extract         — structured field extraction
#   POST /table-query     — question over tables
#   GET  /status          — index stats + Ollama status
#   GET  /health          — liveness check
#   POST /clear           — clear the entire index
#   GET  /                — serves the frontend UI
#
# Run:  uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

import pipeline
from config import UPLOAD_DIR, API_HOST, API_PORT, FRONTEND_DIR, MAX_FILE_SIZE_MB, __version__


# ── Lifespan — runs on startup and shutdown ──────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the pipeline on startup, clean up on shutdown."""
    logger.info("🚀 Starting Document AI + RAG Pipeline API…")
    info = pipeline.startup()
    logger.info(f"   Index: {info['index']}")
    logger.info(f"   Ollama: {info['ollama']}")
    yield
    logger.info("Shutting down pipeline API.")


# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Document AI + RAG Pipeline",
    description=(
        "Upload documents (PDF, images, Word) and query them in natural language. "
        "Powered by PaddleOCR, FAISS, cross-encoder reranking, and Mistral 7B via Ollama."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Request timing middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0       = time.perf_counter()
    response = await call_next(request)
    elapsed  = time.perf_counter() - t0
    response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
    return response


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question to ask")
    history: List[Dict[str, str]] = Field(default_factory=list, description="Array of past messages")

class SummarizeRequest(BaseModel):
    topic: Optional[str] = Field("the document", description="Topic to summarize")

class ExtractRequest(BaseModel):
    fields: List[str] = Field(..., min_length=1, description="Field names to extract")
    context_query: Optional[str] = Field("", description="Optional context query")

class TableQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Table question to ask")

class UrlIngestRequest(BaseModel):
    url: str = Field(..., description="The URL to scrape and index")

class SourceInfo(BaseModel):
    source: str
    page: int
    excerpt: str

class QAResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]

class IngestResponse(BaseModel):
    file: str
    pages: int
    chunks: int
    index_size: int
    time_seconds: float

class StatusResponse(BaseModel):
    status: str
    total_vectors: int
    dimension: int
    unique_sources: int
    sources: List[str] = []
    ollama: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the frontend UI."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Document AI + RAG Pipeline</h1>"
                "<p>Frontend not found. Visit <a href='/docs'>/docs</a> for the API.</p>"
    )


@app.get("/health")
def health():
    """Health check — returns API version and status."""
    return {"status": "ok", "version": __version__}


@app.get("/status", response_model=StatusResponse)
def status():
    """Return FAISS index stats and Ollama connectivity."""
    return pipeline.status()


@app.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)):
    """
    Upload a document (PDF / image / DOCX) and add it to the vector index.

    Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP, WEBP, DOCX, TXT, MD

    Example (curl):
        curl -X POST http://localhost:8000/ingest -F "file=@invoice.pdf"
    """
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".docx", ".doc", ".txt", ".md"}
    suffix  = Path(file.filename).suffix.lower()

    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
                   f"Allowed: {', '.join(sorted(allowed))}"
        )

    # Read file content to check size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f} MB (max: {MAX_FILE_SIZE_MB} MB)"
        )

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(content)

    logger.info(f"File saved: {save_path} ({size_mb:.1f} MB)")

    try:
        result = pipeline.ingest(save_path)
    except Exception as e:
        logger.exception(f"Ingestion failed for {file.filename}")
        raise HTTPException(status_code=500, detail=str(e))

    return result


@app.post("/query", response_model=QAResponse)
def query(req: QueryRequest):
    """
    Ask a question and get an answer with source citations.

    Example:
        curl -X POST http://localhost:8000/query \\
             -H "Content-Type: application/json" \\
             -d '{"question": "What is the invoice total?"}'
    """
    try:
        return pipeline.query(req.question)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query-stream")
def query_stream(req: QueryRequest):
    """
    Stream a Q&A answer via Server-Sent Events (SSE).
    """
    from fastapi.responses import StreamingResponse
    
    try:
        results = pipeline.get_relevant_chunks(req.question)
        from llm.prompt_chains import stream_answer_question
        return StreamingResponse(
            stream_answer_question(req.question, results, req.history),
            media_type="text/event-stream"
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Query stream failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    """
    Summarize document content about a given topic.

    Example:
        curl -X POST http://localhost:8000/summarize \\
             -H "Content-Type: application/json" \\
             -d '{"topic": "payment terms"}'
    """
    try:
        return pipeline.get_summary(req.topic)
    except Exception as e:
        logger.exception("Summarization failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract")
def extract(req: ExtractRequest):
    """
    Extract specific fields as structured JSON.

    Example:
        curl -X POST http://localhost:8000/extract \\
             -H "Content-Type: application/json" \\
             -d '{"fields": ["invoice_number", "date", "total_amount"]}'
    """
    try:
        return pipeline.extract(req.fields, req.context_query)
    except Exception as e:
        logger.exception("Extraction failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/table-query")
def table_query(req: TableQueryRequest):
    """
    Ask a question specifically over tables in the documents.

    Example:
        curl -X POST http://localhost:8000/table-query \\
             -H "Content-Type: application/json" \\
             -d '{"question": "What is the total in the last row?"}'
    """
    try:
        return pipeline.query_table(req.question)
    except Exception as e:
        logger.exception("Table query failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear")
def clear():
    """Clear the entire FAISS index and start fresh."""
    try:
        return pipeline.clear_index()
    except Exception as e:
        logger.exception("Clear failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/document/{filename}")
def delete_document(filename: str):
    """Delete a specific document from the index."""
    try:
        return pipeline.delete_document(filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Delete failed for {filename}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app:app", host=API_HOST, port=API_PORT, reload=True)
