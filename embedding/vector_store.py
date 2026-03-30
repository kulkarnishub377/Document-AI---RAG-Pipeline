# embedding/vector_store.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Embedding + FAISS Vector Index
#
# Responsibilities:
#   • Load / persist a FAISS index and metadata store
#   • Embed chunks with SentenceTransformers and add to index
#   • Hybrid search: FAISS (semantic) + BM25 (keyword) with RRF fusion
#   • Thread-safe operations with proper locking
#   • Source deletion without full index rebuild (IndexIDMap)
#   • GPU acceleration when available
#   • Auto-IVF upgrade for large datasets
# v3.1 — Fixed race condition, RRF score fusion, IndexIDMap, type hints,
#         corrupted metadata handling, thread-safe reads
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import faiss
import numpy as np
from loguru import logger

from config import (
    EMBED_DIMENSION,
    EMBED_MODEL_NAME,
    ENABLE_GPU,
    FAISS_INDEX_PATH,
    IVF_THRESHOLD,
    METADATA_PATH,
    RETRIEVAL_TOP_K,
)

from chunking.semantic_chunker import Chunk

# ── Search result data class ────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single search result with score and metadata."""
    text:       str
    source:     str
    page_num:   int
    chunk_type: str
    score:      float
    chunk_id:   str = ""


# ── Module-level singletons (lazy-loaded) ────────────────────────────────────

_lock = threading.RLock()          # Re-entrant lock for all index operations
_embed_model = None                # SentenceTransformer instance
_faiss_index: Optional[faiss.Index] = None
_metadata: List[Dict[str, Any]] = []
_id_counter: int = 0
_bm25_model = None
_bm25_corpus: List[List[str]] = []


def _get_embed_model():
    """Lazy-load the SentenceTransformer model (singleton)."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        device = "cpu"
        if ENABLE_GPU in ("true", "auto"):
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    logger.info("GPU detected — using CUDA for embeddings")
            except ImportError:
                pass
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME, device=device)
        logger.info(f"Embedding model loaded: {EMBED_MODEL_NAME} on {device}")
    return _embed_model


def _build_faiss_index(dimension: int = EMBED_DIMENSION, n_vectors: int = 0) -> faiss.Index:
    """
    Build a FAISS index wrapped in IndexIDMap for efficient deletion.
    Auto-switches to IVF for large datasets.
    """
    if n_vectors > IVF_THRESHOLD:
        nlist = min(int(np.sqrt(n_vectors)), 256)
        quantizer = faiss.IndexFlatIP(dimension)
        base_index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)
        logger.info(f"Using IVF index with {nlist} clusters for {n_vectors} vectors")
    else:
        base_index = faiss.IndexFlatIP(dimension)

    index = faiss.IndexIDMap(base_index)

    if ENABLE_GPU in ("true", "auto"):
        try:
            res = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(res, 0, index)
            logger.info("FAISS index moved to GPU")
        except Exception:
            pass

    return index


def _rebuild_bm25() -> None:
    """Rebuild BM25 index from current metadata."""
    global _bm25_model, _bm25_corpus
    try:
        from rank_bm25 import BM25Okapi
        _bm25_corpus = [m.get("text", "").lower().split() for m in _metadata]
        if _bm25_corpus:
            _bm25_model = BM25Okapi(_bm25_corpus)
        else:
            _bm25_model = None
    except ImportError:
        _bm25_model = None


# ── Index Persistence ────────────────────────────────────────────────────────

def save_index() -> None:
    """Persist FAISS index and metadata to disk."""
    with _lock:
        if _faiss_index is not None:
            cpu_index = faiss.index_gpu_to_cpu(_faiss_index) if hasattr(_faiss_index, 'getDevice') else _faiss_index
            faiss.write_index(cpu_index, str(FAISS_INDEX_PATH))

        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(_metadata, f, ensure_ascii=False)

        logger.info(
            f"Index saved: {len(_metadata)} vectors → {FAISS_INDEX_PATH.name}"
        )


def load_index() -> bool:
    """Load FAISS index and metadata from disk. Returns True if loaded."""
    global _faiss_index, _metadata, _id_counter

    with _lock:
        if not FAISS_INDEX_PATH.exists():
            return False

        try:
            _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        except Exception as e:
            logger.error(f"Failed to load FAISS index: {e}")
            return False

        if METADATA_PATH.exists():
            try:
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    _metadata = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Metadata corrupted, resetting: {e}")
                _metadata = []
        else:
            _metadata = []

        _id_counter = len(_metadata)
        _rebuild_bm25()

        logger.info(
            f"Index loaded: {len(_metadata)} vectors, dim={EMBED_DIMENSION}"
        )
        return True


def _ensure_index_loaded() -> None:
    """Load index from disk if not already loaded."""
    global _faiss_index
    if _faiss_index is None:
        if not load_index():
            _faiss_index = _build_faiss_index()


# ── Chunk Indexing ───────────────────────────────────────────────────────────

def index_chunks(chunks: List[Chunk]) -> int:
    """
    Embed and add chunks to the FAISS index.
    Returns the total number of vectors in the index after addition.
    """
    global _faiss_index, _metadata, _id_counter

    if not chunks:
        return len(_metadata)

    with _lock:
        _ensure_index_loaded()

        texts = [c.text for c in chunks]
        model = _get_embed_model()
        embeddings = model.encode(
            texts, show_progress_bar=False, normalize_embeddings=True, batch_size=64,
        )
        embeddings = np.array(embeddings, dtype=np.float32)

        # Assign sequential IDs for IndexIDMap
        start_id = _id_counter
        ids = np.arange(start_id, start_id + len(chunks), dtype=np.int64)

        # Check if IVF index needs training
        if hasattr(_faiss_index, 'is_trained') and not _faiss_index.is_trained:
            _faiss_index.train(embeddings)

        _faiss_index.add_with_ids(embeddings, ids)

        for i, chunk in enumerate(chunks):
            _metadata.append({
                "id": int(start_id + i),
                "chunk_id":   chunk.chunk_id,
                "source":     chunk.source,
                "page_num":   chunk.page_num,
                "chunk_idx":  chunk.chunk_idx,
                "text":       chunk.text,
                "chunk_type": chunk.chunk_type,
            })

        _id_counter = start_id + len(chunks)
        save_index()
        _rebuild_bm25()

        logger.info(
            f"Indexed {len(chunks)} chunks → total: {len(_metadata)} vectors"
        )
        return len(_metadata)


def delete_source(source_name: str) -> int:
    """
    Remove all vectors from a given source.
    v3.1: Uses IndexIDMap.remove_ids() instead of rebuilding entire index.
    Returns the number of remaining vectors.
    """
    global _faiss_index, _metadata

    with _lock:
        _ensure_index_loaded()

        ids_to_remove = [m["id"] for m in _metadata if m["source"] == source_name]
        if not ids_to_remove:
            logger.warning(f"No vectors found for source: {source_name}")
            return len(_metadata)

        # Remove from FAISS
        id_array = np.array(ids_to_remove, dtype=np.int64)
        try:
            _faiss_index.remove_ids(id_array)
        except Exception as e:
            logger.warning(f"IndexIDMap.remove_ids failed ({e}), rebuilding index")
            # Fallback: rebuild from scratch
            remaining = [m for m in _metadata if m["source"] != source_name]
            _metadata = remaining
            _rebuild_index_from_metadata()
            save_index()
            _rebuild_bm25()
            return len(_metadata)

        # Remove from metadata
        _metadata = [m for m in _metadata if m["source"] != source_name]

        save_index()
        _rebuild_bm25()

        logger.info(
            f"Deleted {len(ids_to_remove)} vectors for '{source_name}' — "
            f"remaining: {len(_metadata)}"
        )
        return len(_metadata)


def _rebuild_index_from_metadata() -> None:
    """Rebuild entire FAISS index from metadata (fallback for delete)."""
    global _faiss_index, _id_counter

    _faiss_index = _build_faiss_index(n_vectors=len(_metadata))

    if not _metadata:
        _id_counter = 0
        return

    model = _get_embed_model()
    texts = [m["text"] for m in _metadata]
    embeddings = model.encode(
        texts, show_progress_bar=True, normalize_embeddings=True, batch_size=64,
    )
    embeddings = np.array(embeddings, dtype=np.float32)

    # Re-assign sequential IDs
    ids = np.arange(0, len(_metadata), dtype=np.int64)
    for i, m in enumerate(_metadata):
        m["id"] = i

    if hasattr(_faiss_index, 'is_trained') and not _faiss_index.is_trained:
        _faiss_index.train(embeddings)

    _faiss_index.add_with_ids(embeddings, ids)
    _id_counter = len(_metadata)

    logger.info(f"Index rebuilt from metadata: {len(_metadata)} vectors")


# ── Hybrid Search ────────────────────────────────────────────────────────────

def similarity_search(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    source_filter: Optional[str] = None,
) -> List[SearchResult]:
    """
    Hybrid search combining dense (FAISS) and sparse (BM25) retrieval
    using Reciprocal Rank Fusion for proper score blending.
    v3.1: Thread-safe reads, RRF fusion instead of 0-score BM25.
    """
    # v3.1 fix: acquire lock during read to prevent race conditions
    with _lock:
        _ensure_index_loaded()

        if not _metadata or _faiss_index is None:
            return []

        model = _get_embed_model()
        q_embedding = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )
        q_embedding = np.array(q_embedding, dtype=np.float32)

        # Expand search if we'll filter later
        search_k = min(top_k * 3, len(_metadata))

        scores, indices = _faiss_index.search(q_embedding, search_k)
        scores = scores[0]
        indices = indices[0]

        # Build candidate map: chunk_id → { metadata_idx, faiss_rank }
        candidate_ranks: Dict[int, Dict[str, Any]] = {}
        faiss_rank = 1
        for score, idx in zip(scores, indices):
            if idx < 0 or idx >= len(_metadata):
                continue
            meta = _metadata[idx]
            if source_filter and meta["source"] != source_filter:
                continue
            candidate_ranks[idx] = {
                "meta": meta,
                "faiss_rank": faiss_rank,
                "faiss_score": float(score),
                "bm25_rank": None,
            }
            faiss_rank += 1

        # BM25 sparse search
        bm25_k = 60  # constant for RRF
        if _bm25_model is not None and _bm25_corpus:
            tokenized_query = query.lower().split()
            bm25_scores = _bm25_model.get_scores(tokenized_query)
            bm25_ranked = np.argsort(bm25_scores)[::-1][:search_k]

            bm25_rank = 1
            for bm25_idx in bm25_ranked:
                bm25_idx = int(bm25_idx)
                if bm25_idx >= len(_metadata):
                    continue
                meta = _metadata[bm25_idx]
                if source_filter and meta["source"] != source_filter:
                    continue

                if bm25_idx in candidate_ranks:
                    candidate_ranks[bm25_idx]["bm25_rank"] = bm25_rank
                else:
                    candidate_ranks[bm25_idx] = {
                        "meta": meta,
                        "faiss_rank": None,
                        "faiss_score": 0.0,
                        "bm25_rank": bm25_rank,
                    }
                bm25_rank += 1

        # v3.1: Reciprocal Rank Fusion (RRF) for proper score blending
        results: List[SearchResult] = []
        for idx, info in candidate_ranks.items():
            meta = info["meta"]

            # RRF score: 1/(k + rank) for each retriever
            rrf_score = 0.0
            if info["faiss_rank"] is not None:
                rrf_score += 1.0 / (bm25_k + info["faiss_rank"])
            if info["bm25_rank"] is not None:
                rrf_score += 1.0 / (bm25_k + info["bm25_rank"])

            results.append(SearchResult(
                text=meta["text"],
                source=meta["source"],
                page_num=meta["page_num"],
                chunk_type=meta.get("chunk_type", "text"),
                score=round(rrf_score, 6),
                chunk_id=meta.get("chunk_id", ""),
            ))

        # Sort by combined RRF score (higher is better)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


def get_relevant_chunks(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    source_filter: Optional[str] = None,
) -> List[SearchResult]:
    """Alias for similarity_search with optional reranking."""
    return similarity_search(query, top_k, source_filter)


# ── Index Statistics ─────────────────────────────────────────────────────────

def get_index_stats() -> Dict[str, Any]:
    """Return statistics about the current index."""
    with _lock:
        _ensure_index_loaded()

        sources: Set[str] = set()
        source_counts: Dict[str, int] = {}
        for m in _metadata:
            src = m["source"]
            sources.add(src)
            source_counts[src] = source_counts.get(src, 0) + 1

        return {
            "total_vectors": len(_metadata),
            "dimension": EMBED_DIMENSION,
            "unique_sources": len(sources),
            "sources": sorted(sources),
            "source_breakdown": [
                {"source": s, "chunks": c} for s, c in sorted(source_counts.items())
            ],
        }


def get_storage_stats() -> Dict[str, Any]:
    """Return disk storage statistics for the index."""
    with _lock:
        def _size_mb(p: Path) -> float:
            return round(p.stat().st_size / (1024 * 1024), 2) if p.exists() else 0.0

        from config import UPLOAD_DIR
        uploads_size = sum(
            f.stat().st_size for f in UPLOAD_DIR.iterdir() if f.is_file()
        ) if UPLOAD_DIR.exists() else 0

        return {
            "index_size_mb": _size_mb(FAISS_INDEX_PATH),
            "metadata_size_mb": _size_mb(METADATA_PATH),
            "uploads_size_mb": round(uploads_size / (1024 * 1024), 2),
            "total_size_mb": round(
                (_size_mb(FAISS_INDEX_PATH) + _size_mb(METADATA_PATH) + uploads_size / (1024 * 1024)),
                2,
            ),
        }


def clear_index() -> None:
    """Delete the FAISS index and metadata from disk and memory."""
    global _faiss_index, _metadata, _id_counter, _bm25_model, _bm25_corpus

    with _lock:
        _faiss_index = _build_faiss_index()
        _metadata = []
        _id_counter = 0
        _bm25_model = None
        _bm25_corpus = []

        if FAISS_INDEX_PATH.exists():
            FAISS_INDEX_PATH.unlink()
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()

        logger.info("FAISS index and metadata cleared.")


def list_documents() -> List[Dict[str, Any]]:
    """List all indexed documents with metadata."""
    with _lock:
        _ensure_index_loaded()

        from config import UPLOAD_DIR
        doc_map: Dict[str, Dict[str, Any]] = {}

        for m in _metadata:
            src = m["source"]
            if src not in doc_map:
                filepath = UPLOAD_DIR / src
                doc_map[src] = {
                    "filename": src,
                    "suffix": Path(src).suffix,
                    "chunks": 0,
                    "size_mb": round(filepath.stat().st_size / (1024 * 1024), 2)
                              if filepath.exists() else 0.0,
                    "modified": filepath.stat().st_mtime
                               if filepath.exists() else None,
                }
            doc_map[src]["chunks"] += 1

        return sorted(doc_map.values(), key=lambda d: d["filename"])


# ── Export / Import (v3.1 — F5) ──────────────────────────────────────────────

def export_index() -> Dict[str, Any]:
    """Return index data ready for export (metadata + raw embeddings info)."""
    with _lock:
        _ensure_index_loaded()
        return {
            "metadata": _metadata,
            "total_vectors": len(_metadata),
            "dimension": EMBED_DIMENSION,
            "model": EMBED_MODEL_NAME,
        }


def import_index_data(metadata_list: List[Dict[str, Any]]) -> int:
    """Rebuild index from imported metadata."""
    global _faiss_index, _metadata, _id_counter

    with _lock:
        _metadata = metadata_list
        _rebuild_index_from_metadata()
        save_index()
        _rebuild_bm25()
        return len(_metadata)
