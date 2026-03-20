# retrieval/reranker.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Cross-Encoder Reranker
#
# Why reranking?
#   FAISS (bi-encoder) retrieves fast but sometimes returns chunks that are
#   only superficially similar to the query.  The cross-encoder scores each
#   (query, chunk) pair together — much more accurate, but too slow to run
#   over the whole index.  So we use FAISS to get top-20 candidates first,
#   then rerank down to top-5 for the LLM.
#
# Model: cross-encoder/ms-marco-MiniLM-L6-v2  (~80 MB, CPU-friendly)
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from typing import List, Optional

from loguru import logger
from sentence_transformers import CrossEncoder

from config import RERANKER_MODEL_NAME, RERANKER_TOP_K
from embedding.vector_store import SearchResult


# ── Singleton ─────────────────────────────────────────────────────────────────

_reranker: Optional[CrossEncoder] = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info(f"Loading reranker: {RERANKER_MODEL_NAME}  "
                    "(first run downloads ~80 MB)…")
        _reranker = CrossEncoder(RERANKER_MODEL_NAME, max_length=512)
        logger.info("Reranker ready.")
    return _reranker


# ── Public API ────────────────────────────────────────────────────────────────

def rerank(query: str,
           candidates: List[SearchResult],
           top_k: int = RERANKER_TOP_K) -> List[SearchResult]:
    """
    Re-score candidates using the cross-encoder and return the top_k best.

    The returned list is sorted by reranker score (descending — higher = better).
    Each result gets its .rank field updated to reflect the new order.

    Usage:
        candidates = similarity_search(query, top_k=20)
        final      = rerank(query, candidates, top_k=5)
    """
    if not candidates:
        return []

    reranker = _get_reranker()

    pairs  = [(query, r.text) for r in candidates]
    scores = reranker.predict(pairs)         # returns numpy array of floats

    # Attach new scores and sort
    scored = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )

    top = scored[:top_k]
    results: List[SearchResult] = []
    for new_rank, (score, result) in enumerate(top, start=1):
        result.score = float(score)
        result.rank  = new_rank
        results.append(result)

    logger.debug(
        f"Reranked {len(candidates)} → {len(results)} chunks  |  "
        f"top score: {results[0].score:.3f}  query: '{query[:60]}'"
    )
    return results
