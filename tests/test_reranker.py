# tests/test_reranker.py
# ─────────────────────────────────────────────────────────────────────────────
# Reranker Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
import pytest

from embedding.vector_store import SearchResult
from retrieval.reranker import rerank


def _make_result(text: str, score: float, rank: int) -> SearchResult:
    """Create a dummy SearchResult for testing."""
    return SearchResult(
        chunk_id=f"test_{rank}",
        source="test.pdf",
        page_num=1,
        chunk_type="text",
        text=text,
        score=score,
        rank=rank,
    )


def test_rerank_empty_candidates():
    """Reranking an empty list should return an empty list."""
    result = rerank("any query", [])
    assert result == []


@patch("retrieval.reranker._get_reranker")
def test_rerank_scores_and_sorts(mock_reranker):
    """Reranker should re-score and sort candidates by new score (descending)."""
    # Prepare mock cross-encoder
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9, 0.5]  # Scores for 3 candidates
    mock_reranker.return_value = mock_model

    candidates = [
        _make_result("text A", 0.8, 1),
        _make_result("text B", 0.7, 2),
        _make_result("text C", 0.6, 3),
    ]

    results = rerank("test query", candidates, top_k=2)

    assert len(results) == 2
    # B should be first (score 0.9 > C 0.5 > A 0.1)
    assert results[0].text == "text B"
    assert results[0].rank == 1
    assert results[1].text == "text C"
    assert results[1].rank == 2


@patch("retrieval.reranker._get_reranker")
def test_rerank_top_k_limits(mock_reranker):
    """Reranker should return at most top_k results."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5, 0.3, 0.8, 0.1, 0.9]
    mock_reranker.return_value = mock_model

    candidates = [_make_result(f"text {i}", 0.5, i) for i in range(5)]

    results = rerank("test query", candidates, top_k=3)
    assert len(results) == 3


@patch("retrieval.reranker._get_reranker")
def test_rerank_updates_rank_field(mock_reranker):
    """Each result should have its rank field updated to sequential 1-based values."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5, 0.9]
    mock_reranker.return_value = mock_model

    candidates = [
        _make_result("text A", 0.8, 1),
        _make_result("text B", 0.7, 2),
    ]

    results = rerank("test query", candidates, top_k=5)
    ranks = [r.rank for r in results]
    assert ranks == [1, 2]


def test_rerank_graceful_model_failure():
    """If the reranker model fails to load, original results should be returned."""
    candidates = [
        _make_result("text A", 0.8, 1),
        _make_result("text B", 0.7, 2),
        _make_result("text C", 0.6, 3),
    ]

    with patch("retrieval.reranker._get_reranker", side_effect=Exception("Model load failed")):
        results = rerank("test query", candidates, top_k=2)
        # Should fall back to returning first top_k candidates unchanged
        assert len(results) == 2
