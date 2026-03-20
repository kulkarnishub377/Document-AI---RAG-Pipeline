# tests/test_vector_store.py
# ─────────────────────────────────────────────────────────────────────────────
# Vector Store Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

import numpy as np
import pytest

from embedding.vector_store import SearchResult, get_index_stats, reset_index


def test_search_result_dataclass():
    """Test SearchResult construction."""
    result = SearchResult(
        chunk_id="abc123",
        source="test.pdf",
        page_num=1,
        chunk_type="text",
        text="Hello world",
        score=0.95,
        rank=1,
    )
    assert result.chunk_id == "abc123"
    assert result.score == 0.95
    assert result.rank == 1
    assert result.chunk_type == "text"


def test_search_result_fields():
    """Test all SearchResult fields are accessible."""
    result = SearchResult(
        chunk_id="id1",
        source="doc.pdf",
        page_num=3,
        chunk_type="table",
        text="| col1 | col2 |",
        score=0.5,
        rank=2,
    )
    assert result.source == "doc.pdf"
    assert result.page_num == 3
    assert result.chunk_type == "table"
    assert "col1" in result.text


def test_get_index_stats_empty():
    """Test stats when no index exists."""
    with patch("embedding.vector_store.FAISS_INDEX_PATH", Path("/nonexistent/path")):
        with patch("embedding.vector_store._faiss_index", None):
            stats = get_index_stats()
            # Should indicate empty or not loaded
            assert stats["total_vectors"] == 0


def test_reset_index_clears_state():
    """Test that reset clears in-memory state."""
    import embedding.vector_store as vs
    
    # Save original state
    orig_index = vs._faiss_index
    orig_meta = vs._metadata
    orig_bm25 = vs._bm25_index
    
    # Set some dummy state
    vs._faiss_index = MagicMock()
    vs._metadata = {"0": {"text": "test"}}
    vs._bm25_index = MagicMock()
    
    # Patch file paths to avoid touching real files
    with patch.object(vs, 'FAISS_INDEX_PATH', Path("/tmp/test_faiss.idx")), \
         patch.object(vs, 'METADATA_PATH', Path("/tmp/test_meta.json")):
        reset_index()
    
    # Verify state is cleared
    assert vs._faiss_index is None
    assert vs._metadata == {}
    assert vs._bm25_index is None
    
    # Restore original state
    vs._faiss_index = orig_index
    vs._metadata = orig_meta
    vs._bm25_index = orig_bm25
