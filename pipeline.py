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

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from chunking.semantic_chunker import chunk_pages
from embedding.vector_store import (
    get_index_stats,
    index_chunks,
    load_index,
    similarity_search,
)
from ingestion.document_loader import load_document
from llm.prompt_chains import (
    answer_question,
    extract_fields,
    summarize,
    table_qa,
)
from retrieval.reranker import rerank
from config import RETRIEVAL_TOP_K, RERANKER_TOP_K


# ─────────────────────────────────────────────────────────────────────────────
# INGEST  (run once per new document)
# ─────────────────────────────────────────────────────────────────────────────

def ingest(file_path: str | Path, force_rebuild: bool = False) -> Dict[str, Any]:
    """
    Full ingestion pipeline for a single document.

    Steps:  load → OCR if needed → chunk → embed → index → save to disk

    Args:
        file_path:     path to PDF / image / DOCX
        force_rebuild: if True, rebuild the entire FAISS index from scratch

    Returns:
        {
          "file":       str,
          "pages":      int,
          "chunks":     int,
          "index_size": int,   ← total vectors now in the index
        }

    Usage:
        result = ingest("my_invoice.pdf")
        print(result)
    """
    path = Path(file_path)
    logger.info(f"═══ INGESTION START: {path.name} ═══")

    # Stage 1 — Load
    pages = load_document(path)
    logger.info(f"Loaded {len(pages)} pages from {path.name}")

    # Stage 2 — Chunk
    chunks = chunk_pages(pages)
    logger.info(f"Created {len(chunks)} chunks")

    if not chunks:
        return {
            "file": path.name, "pages": len(pages),
            "chunks": 0, "index_size": get_index_stats().get("total_vectors", 0)
        }

    # Stage 3 — Embed + Index
    index_chunks(chunks, force_rebuild=force_rebuild)
    stats = get_index_stats()

    logger.info(f"═══ INGESTION DONE: {path.name}  "
                f"| chunks={len(chunks)}  "
                f"| total_index_size={stats['total_vectors']} ═══")

    return {
        "file":       path.name,
        "pages":      len(pages),
        "chunks":     len(chunks),
        "index_size": stats["total_vectors"],
    }


def ingest_folder(folder: str | Path) -> List[Dict[str, Any]]:
    """
    Ingest all supported documents in a folder.

    Usage:
        results = ingest_folder("data/uploads/")
    """
    folder  = Path(folder)
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".docx"}
    files   = [f for f in folder.iterdir() if f.suffix.lower() in allowed]

    if not files:
        logger.warning(f"No supported files found in {folder}")
        return []

    results = []
    for i, f in enumerate(files, 1):
        logger.info(f"Processing file {i}/{len(files)}: {f.name}")
        results.append(ingest(f))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# QUERY  (run for every user question)
# ─────────────────────────────────────────────────────────────────────────────

def _retrieve(query: str) -> list:
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
    results = _retrieve(question)
    return answer_question(question, results)


def get_summary(topic: str = "the document") -> Dict[str, Any]:
    """
    Retrieve relevant chunks and summarize them.

    Usage:
        result = get_summary("payment terms")
        print(result["summary"])
    """
    logger.info(f"SUMMARY request: '{topic}'")
    results = _retrieve(topic)
    return summarize(results)


def extract(fields: List[str], context_query: str = "") -> Dict[str, Any]:
    """
    Extract specific fields from documents as structured JSON.

    Args:
        fields:        list of field names to extract
        context_query: optional query to narrow down which chunks to search
                       (defaults to searching by the field names themselves)

    Usage:
        result = extract(["invoice_number", "vendor_name", "due_date", "total"])
        print(result["fields"])
        # → {"invoice_number": "INV-2024-001", "vendor_name": "Acme Corp", ...}
    """
    search_query = context_query or " ".join(fields)
    logger.info(f"EXTRACT fields: {fields}")
    results = _retrieve(search_query)
    return extract_fields(results, fields)


def query_table(question: str) -> Dict[str, Any]:
    """
    Ask a question specifically targeting tables in the documents.

    Usage:
        result = query_table("What is the subtotal in row 3?")
        print(result["answer"])
    """
    logger.info(f"TABLE QUERY: '{question}'")
    results = _retrieve(question)
    return table_qa(question, results)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────────────────────

def status() -> Dict[str, Any]:
    """Return current pipeline status and index statistics."""
    return get_index_stats()


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST  —  run this file directly to smoke-test the pipeline
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <path-to-pdf-or-image>")
        sys.exit(1)

    doc_path = sys.argv[1]

    # Step 1: Ingest
    print("\n─── Ingesting document ───")
    result = ingest(doc_path)
    print(result)

    # Step 2: Interactive Q&A loop
    print("\n─── Q&A mode (type 'exit' to quit) ───")
    while True:
        q = input("\nYour question: ").strip()
        if q.lower() in {"exit", "quit", "q"}:
            break
        if not q:
            continue

        ans = query(q)
        print(f"\nAnswer:\n{ans['answer']}")
        print("\nSources:")
        for s in ans["sources"]:
            print(f"  • {s['source']}, page {s['page']}  — {s['excerpt'][:80]}…")
