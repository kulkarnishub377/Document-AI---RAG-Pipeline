# api/app.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI REST API
#
# Endpoints:
#   POST /ingest          — upload and index a document
#   POST /query           — natural language Q&A
#   POST /summarize       — summarize by topic
#   POST /extract         — structured field extraction
#   POST /table-query     — question over tables
#   GET  /status          — index stats
#   GET  /health          — liveness check
#
# Run:  uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

import pipeline
from config import UPLOAD_DIR, API_HOST, API_PORT


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Document AI + RAG Pipeline",
    description="Upload documents and query them in natural language.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock this down in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

class SummarizeRequest(BaseModel):
    topic: Optional[str] = "the document"

class ExtractRequest(BaseModel):
    fields: List[str]
    context_query: Optional[str] = ""

class TableQueryRequest(BaseModel):
    question: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    """Return FAISS index stats."""
    return pipeline.status()


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a document (PDF / image / DOCX) and add it to the vector index.

    Example (curl):
        curl -X POST http://localhost:8000/ingest \
             -F "file=@invoice.pdf"
    """
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".docx"}
    suffix  = Path(file.filename).suffix.lower()

    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
                   f"Allowed: {', '.join(allowed)}"
        )

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"File saved: {save_path}")

    try:
        result = pipeline.ingest(save_path)
    except Exception as e:
        logger.exception(f"Ingestion failed for {file.filename}")
        raise HTTPException(status_code=500, detail=str(e))

    return result


@app.post("/query")
def query(req: QueryRequest) -> Dict[str, Any]:
    """
    Ask a question and get an answer with source citations.

    Example (curl):
        curl -X POST http://localhost:8000/query \
             -H "Content-Type: application/json" \
             -d '{"question": "What is the invoice total?"}'
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    try:
        return pipeline.query(req.question)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize")
def summarize(req: SummarizeRequest) -> Dict[str, Any]:
    """
    Summarize document content about a given topic.

    Example:
        curl -X POST http://localhost:8000/summarize \
             -H "Content-Type: application/json" \
             -d '{"topic": "payment terms"}'
    """
    try:
        return pipeline.get_summary(req.topic)
    except Exception as e:
        logger.exception("Summarization failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract")
def extract(req: ExtractRequest) -> Dict[str, Any]:
    """
    Extract specific fields as structured JSON.

    Example:
        curl -X POST http://localhost:8000/extract \
             -H "Content-Type: application/json" \
             -d '{"fields": ["invoice_number", "date", "total_amount", "vendor"]}'
    """
    if not req.fields:
        raise HTTPException(status_code=400, detail="fields list cannot be empty")

    try:
        return pipeline.extract(req.fields, req.context_query)
    except Exception as e:
        logger.exception("Extraction failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/table-query")
def table_query(req: TableQueryRequest) -> Dict[str, Any]:
    """
    Ask a question specifically over tables in the documents.

    Example:
        curl -X POST http://localhost:8000/table-query \
             -H "Content-Type: application/json" \
             -d '{"question": "What is the total in the last row?"}'
    """
    try:
        return pipeline.query_table(req.question)
    except Exception as e:
        logger.exception("Table query failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app:app", host=API_HOST, port=API_PORT, reload=True)
