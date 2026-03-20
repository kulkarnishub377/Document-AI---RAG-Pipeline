# embedding/vector_store.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Embedding + FAISS Vector Store
#
# Responsibilities:
#   • Load the sentence-transformer embedding model once (lazy, cached)
#   • Embed a list of Chunk objects in batches  (memory-efficient)
#   • Build / update a FAISS flat inner-product index
#   • Persist index + metadata to disk
#   • Provide similarity_search(query, top_k) → List[SearchResult]
#   • Provide reset_index() to clear and rebuild from scratch
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import time
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import faiss
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from config import (
    EMBED_DIMENSION,
    EMBED_MODEL_NAME,
    FAISS_INDEX_PATH,
    METADATA_PATH,
    RETRIEVAL_TOP_K,
)


# ── Search result container ──────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single chunk returned from similarity search or reranking."""
    chunk_id:   str
    source:     str
    page_num:   int
    chunk_type: str
    text:       str
    score:      float      # cosine similarity (higher = more similar)
    rank:       int        # 1-based position in result list


# ── Module-level singletons (loaded once, reused) ────────────────────────────

_embed_model: Optional[SentenceTransformer] = None
_faiss_index: Optional[faiss.Index]         = None
_metadata:    Dict[int, dict]               = {}
_lock = threading.Lock()


def _get_embed_model() -> SentenceTransformer:
    """Load the embedding model lazily (downloads ~90 MB on first run)."""
    global _embed_model
    if _embed_model is None:
        logger.info(f"Loading embedding model: {EMBED_MODEL_NAME}  "
                    "(first run downloads ~90 MB)…")
        t0 = time.perf_counter()
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info(f"Embedding model ready in {time.perf_counter() - t0:.2f}s.")
    return _embed_model


# ── Internal helpers ─────────────────────────────────────────────────────────

def _embed_texts(texts: List[str],
                 batch_size: int = 64,
                 show_progress: bool = True) -> np.ndarray:
    """
    Embed a list of strings in batches.
    Returns float32 numpy array of shape (N, EMBED_DIMENSION).
    """
    model      = _get_embed_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,  # cosine similarity via dot-product
        convert_to_numpy=True,
    )
    return embeddings.astype("float32")


def _build_faiss_index(embeddings: np.ndarray) -> faiss.Index:
    """Build a flat inner-product index (cosine sim after L2 norm)."""
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index


# ── Public API ───────────────────────────────────────────────────────────────

def index_chunks(chunks, force_rebuild: bool = False) -> None:
    """
    Embed all chunks and save FAISS index + metadata to disk.

    If the index already exists and force_rebuild=False, new chunks are
    appended. Otherwise, the index is rebuilt from scratch.

    Usage:
        index_chunks(chunks)                    # first build
        index_chunks(new_chunks)                # incremental add
        index_chunks(chunks, force_rebuild=True) # full rebuild
    """
    global _faiss_index, _metadata

    if not chunks:
        logger.warning("index_chunks called with empty chunk list — skipping.")
        return

    texts = [c.text for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks…")
    t0 = time.perf_counter()
    embeddings = _embed_texts(texts)
    embed_time = time.perf_counter() - t0
    logger.info(f"Embedding done in {embed_time:.2f}s  "
                f"({len(texts) / max(embed_time, 0.001):.0f} chunks/sec)")

    with _lock:
        # Load existing index (incremental mode)
        if not force_rebuild and FAISS_INDEX_PATH.exists() and METADATA_PATH.exists():
            logger.info("Existing index found — appending new vectors.")
            _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                _metadata = {int(k): v for k, v in json.load(f).items()}
            start_id = _faiss_index.ntotal
        else:
            logger.info("Building fresh FAISS index.")
            _faiss_index = faiss.IndexFlatIP(EMBED_DIMENSION)
            _metadata    = {}
            start_id     = 0

        _faiss_index.add(embeddings)

        # Store metadata keyed by FAISS vector id
        for i, chunk in enumerate(chunks):
            _metadata[start_id + i] = {
                "chunk_id":   chunk.chunk_id,
                "source":     chunk.source,
                "page_num":   chunk.page_num,
                "chunk_idx":  chunk.chunk_idx,
                "chunk_type": chunk.chunk_type,
                "text":       chunk.text,
            }

        # Persist to disk
        faiss.write_index(_faiss_index, str(FAISS_INDEX_PATH))
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(_metadata, f, ensure_ascii=False, indent=2)

        global _bm25_index
        _bm25_index = None

    logger.info(
        f"Index saved — total vectors: {_faiss_index.ntotal}  |  "
        f"index: {FAISS_INDEX_PATH}  |  metadata: {METADATA_PATH}"
    )


def load_index() -> None:
    """Load a previously saved FAISS index from disk into memory."""
    global _faiss_index, _metadata

    if not FAISS_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"No FAISS index found at {FAISS_INDEX_PATH}. "
            "Run index_chunks() first by ingesting a document."
        )

    logger.info("Loading FAISS index from disk…")
    t0 = time.perf_counter()

    with _lock:
        _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata = {int(k): v for k, v in json.load(f).items()}

        global _bm25_index
        _bm25_index = None

    logger.info(f"Index loaded — {_faiss_index.ntotal} vectors "
                f"in {time.perf_counter() - t0:.2f}s.")


def _build_bm25() -> None:
    """Build the BM25 index from _metadata."""
    global _bm25_index, _bm25_corpus_ids
    import string
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank_bm25 not installed. Hybrid search BM25 disabled.")
        _bm25_index = False
        return

    _bm25_corpus_ids = []
    tokenized_corpus = []
    table = str.maketrans('', '', string.punctuation)
    
    for k in sorted(_metadata.keys()):
        text = str(_metadata[k].get("text", "")).lower().translate(table)
        tokenized_corpus.append(text.split())
        _bm25_corpus_ids.append(k)
        
    if tokenized_corpus:
        _bm25_index = BM25Okapi(tokenized_corpus)
        logger.info(f"Built BM25 index over {len(tokenized_corpus)} chunks.")
    else:
        _bm25_index = False


def get_bm25_scores(query: str, top_k: int) -> dict:
    """Return top_k document IDs and their BM25 scores."""
    global _bm25_index
    if _bm25_index is None:
        _build_bm25()
    if not _bm25_index:
        return {}
        
    import string
    import numpy as np
    
    table = str.maketrans('', '', string.punctuation)
    tokenized_query = query.lower().translate(table).split()
    
    scores = _bm25_index.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = {}
    for idx in top_indices:
        if scores[idx] > 0:
            doc_id = _bm25_corpus_ids[idx]
            results[doc_id] = float(scores[idx])
    return results


def similarity_search(query: str,
                       top_k: int = RETRIEVAL_TOP_K) -> List[SearchResult]:
    """
    Embed the query and return the top-k most similar chunks.

    Usage:
        results = similarity_search("What is the invoice total?", top_k=20)
        for r in results:
            print(r.rank, r.score, r.text[:80])
    """
    global _faiss_index, _metadata

    if _faiss_index is None:
        load_index()

    t0 = time.perf_counter()
    
    # 1. Semantic Search (FAISS)
    q_vec = _embed_texts([query], show_progress=False)
    scores, ids = _faiss_index.search(q_vec, top_k)
    
    candidate_scores = {}
    for score, idx in zip(scores[0], ids[0]):
        if idx != -1:
            candidate_scores[int(idx)] = float(score)

    # 2. Keyword Search (BM25)
    try:
        bm25_scores = get_bm25_scores(query, top_k)
        for doc_id, bm25_score in bm25_scores.items():
            # If doc_id already in candidate_scores, we leave its FAISS score there,
            # otherwise we add it with a base score (0.0) so reranker evaluates it.
            if doc_id not in candidate_scores:
                candidate_scores[doc_id] = 0.0
    except Exception as e:
        logger.warning(f"BM25 search failed: {e}")

    search_time = time.perf_counter() - t0

    results: List[SearchResult] = []
    # Convert all candidate IDs back to SearchResult objects
    for meta_id, score in candidate_scores.items():
        meta = _metadata.get(meta_id)
        if meta is None:
            continue
        results.append(SearchResult(
            chunk_id   = meta["chunk_id"],
            source     = meta["source"],
            page_num   = meta["page_num"],
            chunk_type = meta["chunk_type"],
            text       = meta["text"],
            score      = score,
            rank       = 0, # Will be set by reranker
        ))

    # Sort candidates initially by FAISS score (fallback if reranker is disabled)
    results.sort(key=lambda x: x.score, reverse=True)
    for index, res in enumerate(results, start=1):
        res.rank = index

    logger.debug(f"Hybrid search: FAISS + BM25 yielded {len(results)} distinct candidates in {search_time:.3f}s")
    return results


def reset_index() -> None:
    """Delete the FAISS index and metadata from disk and memory."""
    global _faiss_index, _metadata, _bm25_index

    with _lock:
        _faiss_index = None
        _metadata    = {}
        _bm25_index  = None

        if FAISS_INDEX_PATH.exists():
            FAISS_INDEX_PATH.unlink()
            logger.info(f"Deleted {FAISS_INDEX_PATH}")
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()
            logger.info(f"Deleted {METADATA_PATH}")

    logger.info("Index reset — all vectors cleared.")


def delete_source(source_name: str) -> int:
    """
    Remove all chunks belonging to a specific source document.
    Returns the number of chunks deleted.
    """
    global _faiss_index, _metadata

    with _lock:
        if _faiss_index is None:
            if FAISS_INDEX_PATH.exists():
                load_index()
            else:
                return 0

        # Find which indices belong to the source
        ids_to_remove = [k for k, v in _metadata.items() if v["source"] == source_name]
        if not ids_to_remove:
            return 0

        # Remove from FAISS index (this physically shifts the remaining vectors down)
        sel = faiss.IDSelectorBatch(ids_to_remove)
        _faiss_index.remove_ids(sel)

        # Because FAISS IndexFlatIP shifted the remaining vectors downwards to fill the gaps,
        # we MUST rebuild our metadata dictionary sequentially to match the new vector IDs!
        keep_items = [v for k, v in sorted(_metadata.items()) if k not in ids_to_remove]
        _metadata.clear()
        for i, v in enumerate(keep_items):
            _metadata[i] = v

        # Persist updated index and metadata
        faiss.write_index(_faiss_index, str(FAISS_INDEX_PATH))
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(_metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Deleted {len(ids_to_remove)} chunks for source: {source_name}")
        return len(ids_to_remove)


def get_index_stats() -> dict:
    """Return basic stats about the current in-memory index."""
    global _faiss_index, _metadata

    if _faiss_index is None:
        if FAISS_INDEX_PATH.exists():
            try:
                load_index()
            except Exception:
                return {"status": "not_loaded", "total_vectors": 0, "dimension": 0, "unique_sources": 0}
        else:
            return {"status": "empty", "total_vectors": 0, "dimension": 0, "unique_sources": 0}

    return {
        "status":         "loaded",
        "total_vectors":  _faiss_index.ntotal,
        "dimension":      _faiss_index.d,
        "unique_sources": len({v["source"] for v in _metadata.values()}),
        "sources":        list({v["source"] for v in _metadata.values()}),
    }
