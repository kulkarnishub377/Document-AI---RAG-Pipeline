# tests/conftest.py
# ─────────────────────────────────────────────────────────────────────────────
# Shared pytest fixtures for all test modules
# v3.1 — Added fixtures for new features
# ─────────────────────────────────────────────────────────────────────────────

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest  # type: ignore


@pytest.fixture
def tmp_upload_dir(tmp_path):
    """Create a temporary upload directory for testing."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return upload_dir


@pytest.fixture
def tmp_index_dir(tmp_path):
    """Create a temporary index directory for testing."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    return index_dir


@pytest.fixture
def mock_ollama():
    """Mock Ollama connection as available."""
    with patch("llm.prompt_chains.check_ollama_connection", return_value=True) as mock:
        yield mock


@pytest.fixture
def mock_ollama_offline():
    """Mock Ollama connection as unavailable."""
    with patch("llm.prompt_chains.check_ollama_connection", return_value=False) as mock:
        yield mock


@pytest.fixture
def sample_text_file(tmp_upload_dir):
    """Create a sample text file for ingestion tests."""
    file_path = tmp_upload_dir / "sample.txt"
    file_path.write_text(
        "This is a sample document for testing the Document AI pipeline. "
        "It contains multiple sentences to verify chunking behavior. "
        "The quick brown fox jumps over the lazy dog. "
        "This document should be long enough to produce at least one chunk.",
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def sample_pdf_bytes():
    """Return minimal PDF bytes for upload testing (not a real PDF, just for file handling)."""
    return b"%PDF-1.4 minimal test content for file handling"


@pytest.fixture
def mock_pipeline_status():
    """Mock pipeline status response."""
    return {
        "status": "loaded",
        "total_vectors": 100,
        "dimension": 384,
        "unique_sources": 3,
        "sources": ["doc1.pdf", "doc2.pdf", "doc3.txt"],
        "ollama": "connected",
    }


@pytest.fixture
def mock_query_response():
    """Mock a standard pipeline query response."""
    return {
        "answer": "The total is $100 as stated on page 2.",
        "sources": [
            {
                "source": "invoice.pdf",
                "page": 2,
                "excerpt": "Total amount due: $100.00",
                "score": 0.92,
                "chunk_type": "text",
            },
            {
                "source": "invoice.pdf",
                "page": 1,
                "excerpt": "Invoice #INV-2024-001",
                "score": 0.71,
                "chunk_type": "text",
            },
        ],
        "response_time_ms": 250,
    }


@pytest.fixture
def mock_batch_response():
    """Mock batch Q&A response."""
    return {
        "results": [
            {"question": "What is the total?", "answer": "$100", "sources": [], "response_time_ms": 100},
            {"question": "Who signed?", "answer": "John Doe", "sources": [], "response_time_ms": 120},
        ],
        "total": 2,
    }


@pytest.fixture
def mock_search_response():
    """Mock semantic search response."""
    return {
        "results": [
            {"text": "Sample chunk text", "source": "doc.pdf", "page": 1, "chunk_type": "text", "score": 0.95, "chunk_id": "abc123"},
        ],
        "total": 1,
        "query": "test query",
    }
