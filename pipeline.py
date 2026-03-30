# pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator — coordinates all stages of the RAG pipeline.
# v3.1 — Added batch Q&A, export/import, document versioning, async ingest
#         support, scheduled crawl tracking, improved error handling
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config import (
    DATA_DIR,
    DOC_VERSIONING_ENABLED,
    DOC_VERSIONS_PATH,
    KNOWLEDGE_GRAPH_ENABLED,
    RERANKER_TOP_K,
    RETRIEVAL_TOP_K,
    UPLOAD_DIR,
)

# ── Lazy imports of heavy modules ────────────────────────────────────────────
# Defer to avoid loading PaddleOCR / SentenceTransformers at import time

def _load_pages(file_path: str, source_name: str):
    from ingestion.document_loader import load_document
    return load_document(file_path, source_name)

def _chunk(pages):
    from chunking.semantic_chunker import chunk_pages
    return chunk_pages(pages)

def _index(chunks):
    from embedding.vector_store import index_chunks
    return index_chunks(chunks)

def _search(query, top_k=RETRIEVAL_TOP_K, source_filter=None):
    from embedding.vector_store import similarity_search
    return similarity_search(query, top_k, source_filter)

def _rerank(query, chunks, top_k=RERANKER_TOP_K):
    from retrieval.reranker import rerank
    return rerank(query, chunks, top_k)


# ── Document Versioning (v3.1 — F2) ─────────────────────────────────────────

def _load_versions() -> Dict[str, List[Dict[str, Any]]]:
    """Load document version history from disk."""
    if DOC_VERSIONS_PATH.exists():
        try:
            with open(DOC_VERSIONS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_versions(versions: Dict[str, List[Dict[str, Any]]]) -> None:
    """Save document version history to disk."""
    with open(DOC_VERSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(versions, f, ensure_ascii=False, indent=2)

def _record_version(filename: str, chunks: int, pages: int) -> None:
    """Record a new version of a document."""
    if not DOC_VERSIONING_ENABLED:
        return
    versions = _load_versions()
    if filename not in versions:
        versions[filename] = []
    versions[filename].append({
        "version": len(versions[filename]) + 1,
        "chunks": chunks,
        "pages": pages,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep last 20 versions per document
    versions[filename] = versions[filename][-20:]
    _save_versions(versions)

def get_document_versions(filename: str) -> List[Dict[str, Any]]:
    """Get version history for a document."""
    versions = _load_versions()
    return versions.get(filename, [])

def get_all_versions() -> Dict[str, List[Dict[str, Any]]]:
    """Get version history for all documents."""
    return _load_versions()


# ── Core Pipeline Functions ──────────────────────────────────────────────────

def ingest(file_path: str, original_filename: str) -> Dict[str, Any]:
    """
    Full ingestion pipeline: load → chunk → embed → knowledge graph.
    Now supports document versioning and duplicate detection.
    """
    t0 = time.perf_counter()

    # v3.1: Auto-delete previous version if re-uploading same file
    from embedding.vector_store import get_index_stats, delete_source
    stats = get_index_stats()
    if original_filename in stats.get("sources", []):
        logger.info(f"Re-uploading '{original_filename}' — removing old version from index")
        delete_source(original_filename)

    # Stage 1: Load document
    pages = _load_pages(file_path, original_filename)
    logger.info(f"Loaded {len(pages)} pages from '{original_filename}'")

    # Stage 2: Chunk
    chunks = _chunk(pages)
    logger.info(f"Created {len(chunks)} chunks")

    # Stage 3: Embed & Index
    total_vectors = _index(chunks)
    logger.info(f"Indexed → total vectors: {total_vectors}")

    # Stage 4: Knowledge Graph (optional)
    kg_result = {"entities_added": 0}
    if KNOWLEDGE_GRAPH_ENABLED:
        try:
            from features.knowledge_graph import knowledge_graph
            kg_result = knowledge_graph.process_chunks(chunks, original_filename)
        except Exception as e:
            logger.warning(f"Knowledge graph processing failed: {e}")

    # v3.1: Record version
    _record_version(original_filename, len(chunks), len(pages))

    elapsed = round(time.perf_counter() - t0, 2)

    return {
        "file": original_filename,
        "pages": len(pages),
        "chunks": len(chunks),
        "index_size": total_vectors,
        "time_seconds": elapsed,
        "knowledge_graph": kg_result,
    }


def ingest_url(url: str) -> Dict[str, Any]:
    """Ingest a web page by URL."""
    t0 = time.perf_counter()

    from ingestion.document_loader import parse_url
    pages = parse_url(url)

    if not pages:
        raise ValueError(f"No content extracted from URL: {url}")

    source_name = pages[0].source

    chunks = _chunk(pages)
    total_vectors = _index(chunks)

    # Knowledge Graph
    if KNOWLEDGE_GRAPH_ENABLED:
        try:
            from features.knowledge_graph import knowledge_graph
            knowledge_graph.process_chunks(chunks, source_name)
        except Exception as e:
            logger.warning(f"KG processing failed for URL: {e}")

    _record_version(source_name, len(chunks), len(pages))

    elapsed = round(time.perf_counter() - t0, 2)

    return {
        "file": source_name,
        "pages": len(pages),
        "chunks": len(chunks),
        "index_size": total_vectors,
        "time_seconds": elapsed,
    }


def query(
    question: str,
    source_filter: Optional[str] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Full RAG query: search → rerank → generate answer.
    Now tracks query analytics.
    """
    t0 = time.perf_counter()

    # Stage 1: Retrieve
    candidates = _search(question, top_k=RETRIEVAL_TOP_K, source_filter=source_filter)

    if not candidates:
        return {
            "answer": "No relevant documents found. Please upload and index some documents first.",
            "sources": [],
        }

    # Stage 2: Rerank
    reranked = _rerank(question, candidates, top_k=RERANKER_TOP_K)

    # Stage 3: Generate
    from llm.prompt_chains import answer_question
    answer = answer_question(question, reranked, chat_history)

    sources = [
        {
            "source": r.source,
            "page": r.page_num,
            "excerpt": r.text[:300],
            "score": round(r.score, 4),
            "chunk_type": r.chunk_type,
        }
        for r in reranked
    ]

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # v3.1: Track analytics
    try:
        from features.query_analytics import query_analytics
        query_analytics.record_query(
            question=question,
            mode="qa",
            response_time_ms=elapsed_ms,
            sources_used=[s["source"] for s in sources[:3]],
            success=True,
        )
    except Exception:
        pass

    return {
        "answer": answer,
        "sources": sources,
        "response_time_ms": elapsed_ms,
    }


def get_summary(
    topic: str = "the document",
    source_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a summary of indexed content."""
    candidates = _search(topic, top_k=15, source_filter=source_filter)

    if not candidates:
        return {"summary": "No documents found to summarize.", "sources": []}

    from llm.prompt_chains import summarize_text
    summary = summarize_text(candidates, topic)

    return {
        "summary": summary,
        "sources": [
            {"source": r.source, "page": r.page_num, "score": round(r.score, 4)}
            for r in candidates[:5]
        ],
    }


def extract(
    fields: List[str],
    context_query: str = "",
) -> Dict[str, Any]:
    """Extract structured fields from indexed documents."""
    search_query = context_query or "document content overview"
    candidates = _search(search_query, top_k=10)

    if not candidates:
        return {
            "fields": {f: None for f in fields},
            "sources": [],
        }

    from llm.prompt_chains import extract_fields
    raw = extract_fields(candidates, fields)

    # Try to parse as JSON
    try:
        parsed_fields = json.loads(raw)
    except json.JSONDecodeError:
        parsed_fields = {"raw_output": raw}

    return {
        "fields": parsed_fields,
        "extracted_data": parsed_fields,
        "sources": [
            {"source": r.source, "page": r.page_num, "score": round(r.score, 4)}
            for r in candidates[:5]
        ],
    }


def query_table(
    question: str, source_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Query specifically about tabular data."""
    candidates = _search(question, top_k=15, source_filter=source_filter)

    # Prefer table chunks
    table_chunks = [c for c in candidates if c.chunk_type == "table"]
    chunks_to_use = table_chunks[:5] if table_chunks else candidates[:5]

    from llm.prompt_chains import answer_table_question
    answer = answer_table_question(chunks_to_use, question)

    return {
        "answer": answer,
        "sources": [
            {"source": r.source, "page": r.page_num, "chunk_type": r.chunk_type}
            for r in chunks_to_use
        ],
    }


def compare_documents(
    doc_a: str, doc_b: str, question: str = ""
) -> Dict[str, Any]:
    """Compare two indexed documents."""
    from features.comparator import compare_documents as _compare
    from features.comparator import get_document_chunks

    chunks_a = get_document_chunks(doc_a, question)
    chunks_b = get_document_chunks(doc_b, question)

    if not chunks_a and not chunks_b:
        return {
            "analysis": "Neither document has been indexed. Please upload both documents first.",
            "doc_a": doc_a,
            "doc_b": doc_b,
        }

    return _compare(chunks_a, chunks_b, doc_a, doc_b, question)


# ── Batch Q&A (v3.1 — F14) ──────────────────────────────────────────────────

def batch_query(
    questions: List[str],
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Answer multiple questions in batch.
    Returns list of {question, answer, sources} dicts.
    """
    results = []
    for q in questions:
        try:
            result = query(q, source_filter=source_filter)
            results.append({
                "question": q,
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "response_time_ms": result.get("response_time_ms", 0),
            })
        except Exception as e:
            results.append({
                "question": q,
                "answer": f"Error: {str(e)}",
                "sources": [],
                "response_time_ms": 0,
            })
    return results


# ── Semantic Search (v3.1 — F7) ──────────────────────────────────────────────

def semantic_search(
    query_text: str,
    top_k: int = 20,
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Raw semantic search results without LLM generation.
    Returns ranked chunks with scores.
    """
    candidates = _search(query_text, top_k=top_k, source_filter=source_filter)
    return [
        {
            "text": r.text,
            "source": r.source,
            "page": r.page_num,
            "chunk_type": r.chunk_type,
            "score": round(r.score, 6),
            "chunk_id": r.chunk_id,
        }
        for r in candidates
    ]


# ── Export / Import (v3.1 — F5) ──────────────────────────────────────────────

def export_index_zip() -> bytes:
    """
    Export the entire index (FAISS + metadata) as a zip file.
    Returns zip file as bytes.
    """
    from embedding.vector_store import export_index
    from config import FAISS_INDEX_PATH, METADATA_PATH

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add metadata JSON
        data = export_index()
        zf.writestr("metadata.json", json.dumps(data["metadata"], ensure_ascii=False, indent=2))

        # Add FAISS index binary
        if FAISS_INDEX_PATH.exists():
            zf.write(FAISS_INDEX_PATH, "faiss.index")

        # Add version info
        zf.writestr("info.json", json.dumps({
            "total_vectors": data["total_vectors"],
            "dimension": data["dimension"],
            "model": data["model"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

    return buf.getvalue()


def import_index_zip(zip_bytes: bytes) -> Dict[str, Any]:
    """
    Import an index from a zip file.
    Returns info about the imported index.
    """
    from embedding.vector_store import import_index_data

    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        # Read metadata
        metadata_json = zf.read("metadata.json").decode("utf-8")
        metadata = json.loads(metadata_json)

        total = import_index_data(metadata)

    return {
        "imported_vectors": total,
        "status": "success",
    }


# ── Status & Document Management ─────────────────────────────────────────────

def status() -> Dict[str, Any]:
    """Get pipeline status."""
    from embedding.vector_store import get_index_stats
    from llm.prompt_chains import check_ollama_connection

    stats = get_index_stats()
    return {
        **stats,
        "status": "loaded" if stats["total_vectors"] > 0 else "empty",
        "ollama": "connected" if check_ollama_connection() else "not reachable",
    }


def get_analytics() -> Dict[str, Any]:
    """Get comprehensive analytics data."""
    from embedding.vector_store import get_index_stats, get_storage_stats
    from utils.cache import query_cache
    from llm.prompt_chains import check_ollama_connection

    stats = get_index_stats()
    storage = get_storage_stats()
    cache_stats = query_cache.stats()

    return {
        **stats,
        "status": "loaded" if stats["total_vectors"] > 0 else "empty",
        "ollama": "connected" if check_ollama_connection() else "not reachable",
        "storage": storage,
        "cache": cache_stats,
    }


def clear_index() -> Dict[str, str]:
    """Clear the entire FAISS index."""
    from embedding.vector_store import clear_index as _clear
    _clear()
    return {"status": "index cleared successfully"}


def delete_document(filename: str) -> Dict[str, str]:
    """Delete a document from the index."""
    from embedding.vector_store import delete_source, get_index_stats

    stats = get_index_stats()
    if filename not in stats.get("sources", []):
        from utils.exceptions import DocumentNotFoundError
        raise DocumentNotFoundError(filename)

    delete_source(filename)

    # Also delete the uploaded file
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()

    return {"status": f"Deleted '{filename}' from index"}


def list_documents() -> List[Dict[str, Any]]:
    """List all indexed documents."""
    from embedding.vector_store import list_documents as _list_docs
    return _list_docs()


# ── Scheduled Crawl Tracking (v3.1 — F9) ────────────────────────────────────

_crawl_urls: List[str] = []

def add_crawl_url(url: str) -> None:
    """Add a URL to the scheduled crawl list."""
    if url not in _crawl_urls:
        _crawl_urls.append(url)

def remove_crawl_url(url: str) -> None:
    """Remove a URL from the scheduled crawl list."""
    if url in _crawl_urls:
        _crawl_urls.remove(url)

def get_crawl_urls() -> List[str]:
    """Get the scheduled crawl URL list."""
    return list(_crawl_urls)

def run_scheduled_crawl() -> Dict[str, Any]:
    """Re-crawl all scheduled URLs."""
    results = []
    for url in _crawl_urls:
        try:
            result = ingest_url(url)
            results.append({"url": url, "status": "success", **result})
        except Exception as e:
            results.append({"url": url, "status": "failed", "error": str(e)})
    return {"crawled": len(results), "results": results}
