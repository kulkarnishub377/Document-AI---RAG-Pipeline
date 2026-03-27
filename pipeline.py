# pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator — v3.0
#
# This is the single entry point that wires all stages together.
#
#   Stage 1 → load_document()       ingestion/document_loader.py
#   Stage 2 → chunk_pages()         chunking/semantic_chunker.py
#   Stage 3 → index_chunks()        embedding/vector_store.py
#   Stage 4 → similarity_search()
#             + rerank()            retrieval/reranker.py
#   Stage 5 → answer_question()
#             summarize()
#             extract_fields()
#             table_qa()            llm/prompt_chains.py
#
# v3.0 additions:
#   - Query caching (LRU with TTL)
#   - Knowledge graph extraction
#   - Document comparison
#   - Source-filtered queries
#   - Integrated chat history for sync Q&A
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from chunking.semantic_chunker import chunk_pages
from embedding.vector_store import (
    get_index_stats,
    index_chunks,
    load_index,
    reset_index,
    delete_source,
    similarity_search,
)
from ingestion.document_loader import load_document
from llm.prompt_chains import (
    answer_question,
    check_ollama_connection,
    extract_fields,
    summarize,
    table_qa,
)
from retrieval.reranker import rerank
from config import (
    RETRIEVAL_TOP_K, RERANKER_TOP_K, UPLOAD_DIR, ALLOWED_EXTENSIONS,
    KNOWLEDGE_GRAPH_ENABLED,
)
from utils.cache import query_cache
from utils.exceptions import DocumentNotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP  (call once at API boot)
# ─────────────────────────────────────────────────────────────────────────────

def startup() -> Dict[str, Any]:
    """
    Initialize the pipeline — load index from disk if it exists,
    and verify Ollama is reachable.

    Returns a status dict with what was initialized.
    """
    info: Dict[str, Any] = {"index": "empty", "ollama": "unknown"}

    # Try to load existing FAISS index
    try:
        stats = get_index_stats()
        if stats.get("total_vectors", 0) > 0:
            info["index"] = f"loaded ({stats['total_vectors']} vectors)"
        else:
            info["index"] = "empty (no documents ingested yet)"
    except Exception as e:
        info["index"] = f"error: {e}"

    # Check Ollama connectivity
    if check_ollama_connection():
        info["ollama"] = "connected"
        logger.info("Ollama is reachable — LLM ready.")
    else:
        info["ollama"] = "not reachable"
        logger.warning(
            "Ollama is not reachable at the configured URL. "
            "Query endpoints will fail until Ollama is started. "
            "Run: ollama serve"
        )

    logger.info(f"Pipeline startup complete: {info}")
    return info


# ─────────────────────────────────────────────────────────────────────────────
# INGEST  (run once per new document)
# ─────────────────────────────────────────────────────────────────────────────

def ingest(file_path: str | Path, force_rebuild: bool = False) -> Dict[str, Any]:
    """
    Full ingestion pipeline for a single document.

    Steps:  load → OCR if needed → chunk → embed → index → knowledge graph → save

    Args:
        file_path:     path to PDF / image / DOCX / Excel / PPTX / TXT
        force_rebuild: if True, rebuild the entire FAISS index from scratch

    Returns:
        {
          "file":       str,
          "pages":      int,
          "chunks":     int,
          "index_size": int,
          "time_seconds": float,
          "knowledge_graph": dict,  # v3.0
        }
    """
    path = Path(file_path)
    logger.info(f"═══ INGESTION START: {path.name} ═══")
    t0 = time.perf_counter()

    # Stage 1 — Load
    pages = load_document(path)
    logger.info(f"Loaded {len(pages)} pages from {path.name}")

    # Stage 2 — Chunk
    chunks = chunk_pages(pages)
    logger.info(f"Created {len(chunks)} chunks")

    if not chunks:
        return {
            "file": path.name, "pages": len(pages),
            "chunks": 0, "index_size": get_index_stats().get("total_vectors", 0),
            "time_seconds": round(time.perf_counter() - t0, 2),
        }

    # Stage 3 — Embed + Index
    index_chunks(chunks, force_rebuild=force_rebuild)
    stats = get_index_stats()

    # v3.0 — Knowledge Graph Extraction
    kg_result = {}
    if KNOWLEDGE_GRAPH_ENABLED:
        try:
            from features.knowledge_graph import knowledge_graph
            kg_result = knowledge_graph.process_chunks(chunks, path.name)
        except Exception as e:
            logger.warning(f"Knowledge graph extraction failed: {e}")

    # Invalidate cache after ingestion
    query_cache.invalidate()

    elapsed = round(time.perf_counter() - t0, 2)

    logger.info(f"═══ INGESTION DONE: {path.name}  "
                f"| chunks={len(chunks)}  "
                f"| total_index_size={stats['total_vectors']}  "
                f"| time={elapsed}s ═══")

    return {
        "file":            path.name,
        "pages":           len(pages),
        "chunks":          len(chunks),
        "index_size":      stats["total_vectors"],
        "time_seconds":    elapsed,
        "knowledge_graph": kg_result,
    }


def ingest_url(url: str) -> Dict[str, Any]:
    """Fetch and ingest a web URL directly into the index."""
    from ingestion.document_loader import parse_url
    logger.info(f"═══ INGESTION START URL: {url} ═══")
    t0 = time.perf_counter()
    
    pages = parse_url(url)
    source_name = pages[0].source
    logger.info(f"Loaded web page: {source_name}")
    
    chunks = chunk_pages(pages)
    if not chunks:
        return {"file": source_name, "pages": 1, "chunks": 0, "index_size": get_index_stats().get("total_vectors", 0), "time_seconds": 0}

    index_chunks(chunks)
    stats = get_index_stats()
    elapsed = round(time.perf_counter() - t0, 2)

    # Knowledge Graph
    if KNOWLEDGE_GRAPH_ENABLED:
        try:
            from features.knowledge_graph import knowledge_graph
            knowledge_graph.process_chunks(chunks, source_name)
        except Exception:
            pass

    query_cache.invalidate()
    
    return {
        "file": source_name,
        "pages": 1,
        "chunks": len(chunks),
        "index_size": stats["total_vectors"],
        "time_seconds": elapsed,
    }


def ingest_folder(folder: str | Path) -> List[Dict[str, Any]]:
    """
    Ingest all supported documents in a folder.

    Usage:
        results = ingest_folder("data/uploads/")
    """
    folder  = Path(folder)
    files   = sorted(f for f in folder.iterdir() if f.suffix.lower() in ALLOWED_EXTENSIONS)

    if not files:
        logger.warning(f"No supported files found in {folder}")
        return []

    results = []
    for i, f in enumerate(files, 1):
        logger.info(f"Processing file {i}/{len(files)}: {f.name}")
        try:
            results.append(ingest(f))
        except Exception as e:
            logger.error(f"Failed to ingest {f.name}: {e}")
            results.append({"file": f.name, "error": str(e)})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# QUERY  (run for every user question)
# ─────────────────────────────────────────────────────────────────────────────

def get_relevant_chunks(
    query: str,
    source_filter: Optional[str] = None,
) -> list:
    """Shared retrieval step: FAISS search → rerank → return top chunks."""
    candidates = similarity_search(query, top_k=RETRIEVAL_TOP_K)
    if not candidates:
        return []

    # v3.0 — Source filter: restrict to a specific document
    if source_filter:
        candidates = [c for c in candidates if c.source == source_filter]
        if not candidates:
            return []

    return rerank(query, candidates, top_k=RERANKER_TOP_K)


def query(
    question: str,
    source_filter: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Answer a natural language question over all indexed documents.
    v3.0: supports source filtering and chat history for sync mode.

    Usage:
        result = query("What is the total amount on the invoice?")
        print(result["answer"])
        print(result["sources"])
    """
    logger.info(f"QUERY: '{question}'" + (f" [source={source_filter}]" if source_filter else ""))

    history_key = ""
    if history:
        try:
            history_key = json.dumps(history[-5:], sort_keys=True, ensure_ascii=False)
        except Exception:
            history_key = str(history[-5:])

    cache_context = f"source={source_filter or ''}|history={history_key}"

    # Check cache first
    cached = query_cache.get(question, mode="qa", context_key=cache_context)
    if cached:
        logger.info("Query cache HIT — returning cached result")
        return cached

    results = get_relevant_chunks(question, source_filter=source_filter)
    answer = answer_question(question, results, history=history)

    # Store in cache
    query_cache.put(question, answer, mode="qa", context_key=cache_context)

    return answer


def get_summary(topic: str = "the document") -> Dict[str, Any]:
    """
    Retrieve relevant chunks and summarize them.

    Usage:
        result = get_summary("payment terms")
        print(result["summary"])
    """
    logger.info(f"SUMMARY request: '{topic}'")

    cached = query_cache.get(topic, mode="summary")
    if cached:
        return cached

    results = get_relevant_chunks(topic)
    result = summarize(results)
    query_cache.put(topic, result, mode="summary")
    return result


def extract(fields: List[str], context_query: str = "") -> Dict[str, Any]:
    """
    Extract specific fields from documents as structured JSON.

    Args:
        fields:        list of field names to extract
        context_query: optional query to narrow the search

    Usage:
        result = extract(["invoice_number", "vendor_name", "due_date", "total"])
        print(result["fields"])
    """
    search_query = context_query or " ".join(fields)
    logger.info(f"EXTRACT fields: {fields}")
    results = get_relevant_chunks(search_query)
    return extract_fields(results, fields)


def query_table(question: str) -> Dict[str, Any]:
    """
    Ask a question specifically targeting tables in the documents.

    Usage:
        result = query_table("What is the subtotal in row 3?")
        print(result["answer"])
    """
    logger.info(f"TABLE QUERY: '{question}'")
    results = get_relevant_chunks(question)
    return table_qa(question, results)


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT COMPARISON (v3.0)
# ─────────────────────────────────────────────────────────────────────────────

def compare_documents(
    doc_a: str,
    doc_b: str,
    question: str = "",
) -> Dict[str, Any]:
    """
    Compare two indexed documents.

    Args:
        doc_a: filename of first document
        doc_b: filename of second document
        question: optional specific comparison question
    """
    from features.comparator import compare_documents as _compare, get_document_chunks

    chunks_a = get_document_chunks(doc_a, question)
    chunks_b = get_document_chunks(doc_b, question)

    if not chunks_a and not chunks_b:
        return {"error": f"Neither '{doc_a}' nor '{doc_b}' found in index."}
    if not chunks_a:
        return {"error": f"Document '{doc_a}' not found in index."}
    if not chunks_b:
        return {"error": f"Document '{doc_b}' not found in index."}

    return _compare(chunks_a, chunks_b, doc_a, doc_b, question)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS & MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def status() -> Dict[str, Any]:
    """Return current pipeline status and index statistics."""
    stats = get_index_stats()
    stats["ollama"] = "connected" if check_ollama_connection() else "not reachable"
    return stats


def clear_index() -> Dict[str, str]:
    """Delete the entire FAISS index and start fresh."""
    reset_index()
    query_cache.invalidate()
    return {"status": "index cleared successfully"}

def delete_document(source: str) -> Dict[str, Any]:
    """Delete a single document from the index by its filename."""
    count = delete_source(source)
    if count == 0:
        raise DocumentNotFoundError(source)
    
    # Also delete the uploaded file if it exists
    upload_path = UPLOAD_DIR / source
    if upload_path.exists():
        upload_path.unlink()
        logger.info(f"Deleted uploaded file: {upload_path}")

    query_cache.invalidate()
    
    return {"status": "success", "deleted_chunks": count, "source": source}


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def get_analytics() -> Dict[str, Any]:
    """Return comprehensive analytics about the pipeline."""
    stats = get_index_stats()
    
    # Calculate storage usage
    from config import FAISS_INDEX_PATH, METADATA_PATH, DATA_DIR
    storage = {
        "index_size_mb": 0,
        "metadata_size_mb": 0,
        "uploads_size_mb": 0,
    }
    
    if FAISS_INDEX_PATH.exists():
        storage["index_size_mb"] = round(FAISS_INDEX_PATH.stat().st_size / (1024 * 1024), 2)
    if METADATA_PATH.exists():
        storage["metadata_size_mb"] = round(METADATA_PATH.stat().st_size / (1024 * 1024), 2)
    
    uploads_dir = DATA_DIR / "uploads"
    if uploads_dir.exists():
        total_upload_bytes = sum(f.stat().st_size for f in uploads_dir.iterdir() if f.is_file())
        storage["uploads_size_mb"] = round(total_upload_bytes / (1024 * 1024), 2)
    
    storage["total_size_mb"] = round(
        storage["index_size_mb"] + storage["metadata_size_mb"] + storage["uploads_size_mb"],
        2
    )
    
    # Per-source breakdown
    source_breakdown = []
    if stats.get("sources"):
        import json
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            source_counts: Dict[str, int] = {}
            for v in metadata.values():
                src = v.get("source", "unknown")
                source_counts[src] = source_counts.get(src, 0) + 1
            
            for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
                source_breakdown.append({"source": source, "chunks": count})
        except Exception:
            pass

    # v3.0 — cache stats
    cache_stats = query_cache.stats()
    
    return {
        **stats,
        "storage": storage,
        "source_breakdown": source_breakdown,
        "cache": cache_stats,
        "ollama": "connected" if check_ollama_connection() else "not reachable",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI — run this file directly for a quick smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("\nDocument AI + RAG Pipeline v3.0")
        print("=" * 40)
        print("\nUsage:")
        print("  python pipeline.py <path-to-document>     Ingest and start Q&A")
        print("  python pipeline.py --status               Show index stats")
        print("  python pipeline.py --clear                Clear the entire index")
        print("  python pipeline.py --analytics            Show analytics")
        sys.exit(0)

    arg = sys.argv[1]

    if arg == "--status":
        import json
        print(json.dumps(status(), indent=2))
        sys.exit(0)

    if arg == "--clear":
        print(clear_index())
        sys.exit(0)

    if arg == "--analytics":
        import json
        print(json.dumps(get_analytics(), indent=2))
        sys.exit(0)

    # Normal mode: ingest + interactive Q&A
    print("\n─── Ingesting document ───")
    result = ingest(arg)
    print(f"\n✓ Ingested: {result['file']}")
    print(f"  Pages:      {result['pages']}")
    print(f"  Chunks:     {result['chunks']}")
    print(f"  Index size: {result['index_size']} vectors")
    print(f"  Time:       {result['time_seconds']}s")

    print("\n─── Q&A mode (type 'exit' to quit) ───\n")
    while True:
        try:
            q = input("Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit", "q"}:
            break
        if not q:
            continue

        ans = query(q)
        print(f"\n📝 Answer:\n{ans['answer']}\n")
        print("📎 Sources:")
        for s in ans["sources"]:
            print(f"  • {s['source']}, page {s['page']}  — {s['excerpt'][:80]}…")
        print()
