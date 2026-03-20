# pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
#
# This is the single entry point that wires all 5 stages together.
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
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

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
from config import RETRIEVAL_TOP_K, RERANKER_TOP_K


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

    Steps:  load → OCR if needed → chunk → embed → index → save to disk

    Args:
        file_path:     path to PDF / image / DOCX / TXT
        force_rebuild: if True, rebuild the entire FAISS index from scratch

    Returns:
        {
          "file":       str,
          "pages":      int,
          "chunks":     int,
          "index_size": int,
          "time_seconds": float,
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
    elapsed = round(time.perf_counter() - t0, 2)

    logger.info(f"═══ INGESTION DONE: {path.name}  "
                f"| chunks={len(chunks)}  "
                f"| total_index_size={stats['total_vectors']}  "
                f"| time={elapsed}s ═══")

    return {
        "file":         path.name,
        "pages":        len(pages),
        "chunks":       len(chunks),
        "index_size":   stats["total_vectors"],
        "time_seconds": elapsed,
    }


def ingest_folder(folder: str | Path) -> List[Dict[str, Any]]:
    """
    Ingest all supported documents in a folder.

    Usage:
        results = ingest_folder("data/uploads/")
    """
    folder  = Path(folder)
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".docx", ".txt", ".md"}
    files   = sorted(f for f in folder.iterdir() if f.suffix.lower() in allowed)

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

def get_relevant_chunks(query: str) -> list:
    """Shared retrieval step: FAISS search → rerank → return top chunks."""
    candidates = similarity_search(query, top_k=RETRIEVAL_TOP_K)
    if not candidates:
        return []
    return rerank(query, candidates, top_k=RERANKER_TOP_K)


def query(question: str) -> Dict[str, Any]:
    """
    Answer a natural language question over all indexed documents.

    Usage:
        result = query("What is the total amount on the invoice?")
        print(result["answer"])
        print(result["sources"])
    """
    logger.info(f"QUERY: '{question}'")
    results = get_relevant_chunks(question)
    return answer_question(question, results)


def get_summary(topic: str = "the document") -> Dict[str, Any]:
    """
    Retrieve relevant chunks and summarize them.

    Usage:
        result = get_summary("payment terms")
        print(result["summary"])
    """
    logger.info(f"SUMMARY request: '{topic}'")
    results = get_relevant_chunks(topic)
    return summarize(results)


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
    return {"status": "index cleared successfully"}

def delete_document(source: str) -> Dict[str, Any]:
    """Delete a single document from the index by its filename."""
    count = delete_source(source)
    if count == 0:
        raise FileNotFoundError(f"Source '{source}' not found in index.")
    return {"status": "success", "deleted_chunks": count, "source": source}


# ─────────────────────────────────────────────────────────────────────────────
# CLI — run this file directly for a quick smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("\nDocument AI + RAG Pipeline")
        print("=" * 40)
        print("\nUsage:")
        print("  python pipeline.py <path-to-document>     Ingest and start Q&A")
        print("  python pipeline.py --status               Show index stats")
        print("  python pipeline.py --clear                Clear the entire index")
        sys.exit(0)

    arg = sys.argv[1]

    if arg == "--status":
        import json
        print(json.dumps(status(), indent=2))
        sys.exit(0)

    if arg == "--clear":
        print(clear_index())
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
