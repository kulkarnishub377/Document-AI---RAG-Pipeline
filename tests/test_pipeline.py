# tests/test_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

import pipeline


def test_startup_handles_empty_index():
    """Startup should succeed even when no index exists."""
    with patch("pipeline.get_index_stats") as mock_stats, \
         patch("pipeline.check_ollama_connection", return_value=False):
        mock_stats.return_value = {"total_vectors": 0}
        
        info = pipeline.startup()
        assert "index" in info
        assert "ollama" in info
        assert info["ollama"] == "not reachable"


def test_startup_with_existing_index():
    """Startup should report an existing index."""
    with patch("pipeline.get_index_stats") as mock_stats, \
         patch("pipeline.check_ollama_connection", return_value=True):
        mock_stats.return_value = {"total_vectors": 100}
        
        info = pipeline.startup()
        assert "100" in str(info["index"])
        assert info["ollama"] == "connected"


def test_status_returns_stats():
    """Status should include index stats and ollama status."""
    with patch("pipeline.get_index_stats") as mock_stats, \
         patch("pipeline.check_ollama_connection", return_value=True):
        mock_stats.return_value = {
            "status": "loaded",
            "total_vectors": 50,
            "dimension": 384,
            "unique_sources": 2,
        }
        
        result = pipeline.status()
        assert result["total_vectors"] == 50
        assert result["ollama"] == "connected"


def test_clear_index():
    """Clear should delegate to reset_index."""
    with patch("pipeline.reset_index") as mock_reset:
        result = pipeline.clear_index()
        mock_reset.assert_called_once()
        assert "cleared" in result["status"]


def test_ingest_empty_chunks():
    """Ingest should handle documents that produce no chunks."""
    with patch("pipeline.load_document") as mock_load, \
         patch("pipeline.chunk_pages") as mock_chunk, \
         patch("pipeline.get_index_stats") as mock_stats:
        
        mock_load.return_value = [MagicMock(text="", tables=[])]
        mock_chunk.return_value = []
        mock_stats.return_value = {"total_vectors": 0}
        
        result = pipeline.ingest("test.txt")
        assert result["chunks"] == 0


def test_delete_document_not_found():
    """Delete should raise FileNotFoundError for unknown sources."""
    with patch("pipeline.delete_source", return_value=0):
        with pytest.raises(FileNotFoundError):
            pipeline.delete_document("nonexistent.pdf")


def test_get_analytics():
    """Analytics should return storage and breakdown info."""
    with patch("pipeline.get_index_stats") as mock_stats, \
         patch("pipeline.check_ollama_connection", return_value=True), \
         patch("pipeline.UPLOAD_DIR", Path("/tmp/test_uploads")):
        mock_stats.return_value = {
            "status": "empty",
            "total_vectors": 0,
            "dimension": 384,
            "unique_sources": 0,
            "sources": [],
        }
        
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = pipeline.get_analytics()
        
        assert "storage" in result
        assert "source_breakdown" in result
        assert result["ollama"] == "connected"
