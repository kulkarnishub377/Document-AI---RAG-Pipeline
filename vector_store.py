# embedding/vector_store.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Embedding + FAISS Vector Store
#
# Responsibilities:
#   • Load the sentence-transformer embedding model once (lazy, cached)
#   • Embed a list of Chunk objects in batches  (memory-efficient)
#   • Build / update a FAISS flat-L2 index
#   • Persist index + metadata to disk so you don't re-index on every restart
#   • Provide similarity_search(query, top_k) → List[SearchResult]
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import faiss
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from chunking.semantic_chunker import Chunk
from config import (
    EMBED_DIMENSION,
    EMBED_MODEL_NAME,
    FAISS_INDEX_PATH,
    METADATA_PATH,
    RETRIEVAL_TOP_K,
)


# ── Search result container ───────────────────────────────────────────────────

@dataclass
class SearchResult:
    chunk_id:   str
    source:     str
    page_num:   int
    chunk_type: str
    text:       str
    score:      float      # L2 distance (lower = more similar)
    rank:       int        # 1-based position in result list


# ── Module-level singletons (loaded once, reused) ────────────────────────────

_embed_model: Optional[SentenceTransformer] = None
_faiss_index: Optional[faiss.Index]         = None
_metadata:    Dict[int, dict]               = {}   # faiss_id → chunk dict


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info(f"Loading embedding model: {EMBED_MODEL_NAME}  "
                    "(first run downloads ~90 MB)…")
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info("Embedding model ready.")
    return _embed_model


# ── Internal helpers ──────────────────────────────────────────────────────────

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
    """Build a flat inner-product index (equivalent to cosine sim after L2 norm)."""
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)    # IP = inner product
    index.add(embeddings)
    return index


# ── Public API ────────────────────────────────────────────────────────────────

def index_chunks(chunks: List[Chunk], force_rebuild: bool = False) -> None:
    """
    Embed all chunks and save FAISS index + metadata to disk.

    If the index already exists and force_rebuild=False, new chunks are
    appended rather than re-indexing everything from scratch.

    Usage:
        index_chunks(chunks)                    # first build
        index_chunks(new_chunks)                # incremental add
        index_chunks(chunks, force_rebuild=True) # full rebuild
    """
    global _faiss_index, _metadata

    if not chunks:
        logger.warning("index_chunks called with empty chunk list — nothing to do.")
        return

    texts = [c.text for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks…")
    embeddings = _embed_texts(texts)

    # ── Load existing index (incremental mode) ────────────────────────────────
    if not force_rebuild and FAISS_INDEX_PATH.exists() and METADATA_PATH.exists():
        logger.info("Existing index found — appending new vectors.")
        _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        with open(METADATA_PATH, "r") as f:
            _metadata = {int(k): v for k, v in json.load(f).items()}
        start_id = _faiss_index.ntotal
    else:
        logger.info("Building fresh FAISS index.")
        _faiss_index = faiss.IndexFlatIP(EMBED_DIMENSION)
        _metadata    = {}
        start_id     = 0

    _faiss_index.add(embeddings)

    # Store metadata keyed by faiss vector id
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
    with open(METADATA_PATH, "w") as f:
        json.dump(_metadata, f, ensure_ascii=False, indent=2)

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
            "Run index_chunks() first."
        )

    logger.info("Loading FAISS index from disk…")
    _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))

    with open(METADATA_PATH, "r") as f:
        _metadata = {int(k): v for k, v in json.load(f).items()}

    logger.info(f"Index loaded — {_faiss_index.ntotal} vectors.")


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

    q_vec = _embed_texts([query], show_progress=False)
    scores, ids = _faiss_index.search(q_vec, top_k)

    results: List[SearchResult] = []
    for rank, (score, idx) in enumerate(zip(scores[0], ids[0]), start=1):
        if idx == -1:          # FAISS returns -1 for empty slots
            continue
        meta = _metadata.get(int(idx))
        if meta is None:
            continue
        results.append(SearchResult(
            chunk_id   = meta["chunk_id"],
            source     = meta["source"],
            page_num   = meta["page_num"],
            chunk_type = meta["chunk_type"],
            text       = meta["text"],
            score      = float(score),
            rank       = rank,
        ))

    return results


def get_index_stats() -> dict:
    """Return basic stats about the current in-memory index."""
    global _faiss_index, _metadata
    if _faiss_index is None:
        return {"status": "not_loaded"}
    return {
        "status":        "loaded",
        "total_vectors": _faiss_index.ntotal,
        "dimension":     _faiss_index.d,
        "unique_sources": len({v["source"] for v in _metadata.values()}),
    }
