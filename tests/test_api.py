# tests/test_api.py
# ─────────────────────────────────────────────────────────────────────────────
# API Endpoint Tests using FastAPI's TestClient
# v3.1 — Fixed broken mocks (Bug #2, #3), added tests for new endpoints
# ─────────────────────────────────────────────────────────────────────────────

import io
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health_endpoint():
    """Test that the health check returns OK."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_status_endpoint():
    """Test that the status endpoint returns expected fields."""
    with patch("pipeline.status") as mock_status:
        mock_status.return_value = {
            "status": "empty",
            "total_vectors": 0,
            "dimension": 384,
            "unique_sources": 0,
            "sources": [],
            "ollama": "not reachable",
        }
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_vectors" in data
        assert "ollama" in data


def test_analytics_endpoint():
    """Test that the analytics endpoint returns detailed stats."""
    with patch("pipeline.get_analytics") as mock_analytics:
        mock_analytics.return_value = {
            "status": "empty",
            "total_vectors": 0,
            "dimension": 384,
            "unique_sources": 0,
            "sources": [],
            "storage": {"index_size_mb": 0, "metadata_size_mb": 0, "uploads_size_mb": 0, "total_size_mb": 0},
            "source_breakdown": [],
            "ollama": "not reachable",
        }
        resp = client.get("/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage" in data
        assert "source_breakdown" in data


def test_ingest_unsupported_file():
    """Test that uploading an unsupported file type returns 400."""
    file = io.BytesIO(b"not a real file")
    resp = client.post("/ingest", files={"file": ("test.xyz", file, "application/octet-stream")})
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_ingest_rejects_path_traversal_filename():
    """Test that filenames cannot escape the uploads directory."""
    file = io.BytesIO(b"This is a harmless test document.")
    resp = client.post("/ingest", files={"file": ("../escape.txt", file, "text/plain")})
    assert resp.status_code == 400


def test_ingest_success():
    """Test successful document ingestion."""
    with patch("pipeline.ingest") as mock_ingest:
        mock_ingest.return_value = {
            "file": "test.txt",
            "pages": 1,
            "chunks": 3,
            "index_size": 3,
            "time_seconds": 0.5,
        }

        file_content = b"This is a test document with enough content to process."
        resp = client.post(
            "/ingest",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file"] == "test.txt"
        assert data["chunks"] == 3


def test_ingest_url_endpoint():
    """Test that the URL ingestion endpoint exists and works."""
    with patch("pipeline.ingest_url") as mock_ingest_url:
        mock_ingest_url.return_value = {
            "file": "example.com - Example",
            "pages": 1,
            "chunks": 5,
            "index_size": 5,
            "time_seconds": 1.2,
        }

        resp = client.post(
            "/ingest/url",
            json={"url": "https://example.com"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunks"] == 5


def test_query_requires_question():
    """Test that query endpoint validates required fields."""
    resp = client.post("/query", json={})
    assert resp.status_code == 422


def test_query_success():
    """Test successful query with mocked pipeline.
    v3.1 (Bug #2): Now correctly mocks pipeline.query instead of checking ollama separately.
    """
    with patch("pipeline.query") as mock_query:
        mock_query.return_value = {
            "answer": "The total is $100.",
            "sources": [
                {"source": "invoice.pdf", "page": 1, "excerpt": "Total: $100", "score": 0.95, "chunk_type": "text"}
            ],
            "response_time_ms": 150,
        }

        resp = client.post("/query", json={"question": "What is the total?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["sources"]) == 1


def test_summarize_endpoint():
    """Test summarization endpoint."""
    with patch("pipeline.get_summary") as mock_summary:
        mock_summary.return_value = {
            "summary": "This document is about testing.",
            "sources": [],
        }

        resp = client.post("/summarize", json={"topic": "testing"})
        assert resp.status_code == 200
        assert "summary" in resp.json()


def test_extract_endpoint():
    """Test extraction endpoint."""
    with patch("pipeline.extract") as mock_extract:
        mock_extract.return_value = {
            "fields": {"invoice_number": "INV-001", "total": "$100"},
            "extracted_data": {"invoice_number": "INV-001", "total": "$100"},
            "sources": [],
        }

        resp = client.post("/extract", json={"fields": ["invoice_number", "total"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "fields" in data
        assert data["fields"]["invoice_number"] == "INV-001"
        assert "extracted_data" in data


def test_table_query_endpoint():
    """Test table query endpoint."""
    with patch("pipeline.query_table") as mock_table:
        mock_table.return_value = {
            "answer": "Row 3 total is $50.",
            "sources": [],
        }

        resp = client.post("/table-query", json={"question": "What is in row 3?"})
        assert resp.status_code == 200
        assert "answer" in resp.json()


def test_compare_endpoint_exposes_analysis_alias():
    """Test that compare responses expose both analysis and compatibility aliases."""
    with patch("pipeline.compare_documents") as mock_compare:
        mock_compare.return_value = {
            "analysis": "Documents differ in one clause.",
            "doc_a": "a.pdf",
            "doc_b": "b.pdf",
        }

        resp = client.post(
            "/compare",
            json={"doc_a": "a.pdf", "doc_b": "b.pdf", "question": "What changed?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis"] == "Documents differ in one clause."
        assert data["comparison"] == "Documents differ in one clause."


def test_clear_endpoint():
    """Test clearing the index."""
    with patch("pipeline.clear_index") as mock_clear:
        mock_clear.return_value = {"status": "index cleared successfully"}
        resp = client.post("/clear")
        assert resp.status_code == 200
        assert resp.json()["status"] == "index cleared successfully"


def test_delete_document_not_found():
    """Test deleting a document that doesn't exist.
    v3.1 (Bug #3): Uses DocumentNotFoundError instead of FileNotFoundError.
    """
    from utils.exceptions import DocumentNotFoundError
    with patch("pipeline.delete_document") as mock_delete:
        mock_delete.side_effect = DocumentNotFoundError("nonexistent.pdf")
        resp = client.delete("/document/nonexistent.pdf")
        assert resp.status_code == 404


def test_validation_error_format():
    """Test that validation errors return a clean format."""
    resp = client.post("/extract", json={"fields": []})  # empty fields list not allowed
    assert resp.status_code == 422


# ── v3.1 New Endpoint Tests ──────────────────────────────────────────────────

def test_semantic_search_endpoint():
    """Test semantic search endpoint (F7)."""
    with patch("pipeline.semantic_search") as mock_search:
        mock_search.return_value = [
            {"text": "Sample text", "source": "doc.pdf", "page": 1, "chunk_type": "text", "score": 0.9, "chunk_id": "abc"},
        ]

        resp = client.post("/search", json={"query": "test search", "top_k": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["total"] == 1


def test_batch_query_endpoint():
    """Test batch Q&A endpoint (F14)."""
    with patch("pipeline.batch_query") as mock_batch:
        mock_batch.return_value = [
            {"question": "Q1?", "answer": "A1", "sources": [], "response_time_ms": 100},
        ]

        resp = client.post("/query/batch", json={"questions": ["Q1?"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["answer"] == "A1"


def test_export_endpoint():
    """Test export endpoint (F5)."""
    with patch("pipeline.export_index_zip") as mock_export:
        mock_export.return_value = b"PK\x03\x04" + b"\x00" * 100  # Minimal zip-like data

        resp = client.get("/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"


def test_versions_endpoint():
    """Test document versions endpoint (F2)."""
    with patch("pipeline.get_all_versions") as mock_versions:
        mock_versions.return_value = {"doc.pdf": [{"version": 1, "chunks": 10, "pages": 3}]}

        resp = client.get("/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "doc.pdf" in data


def test_knowledge_graph_endpoint():
    """Test knowledge graph endpoint."""
    with patch("features.knowledge_graph.knowledge_graph") as mock_kg:
        mock_kg.get_graph_data.return_value = {"nodes": [], "edges": [], "total_entities": 0, "total_relationships": 0}

        resp = client.get("/knowledge-graph")
        assert resp.status_code == 200


def test_query_analytics_endpoint():
    """Test query analytics endpoint (F10)."""
    with patch("features.query_analytics.query_analytics") as mock_qa:
        mock_qa.get_stats.return_value = {
            "total_queries": 10,
            "successful_queries": 9,
            "failed_queries": 1,
            "cached_queries": 3,
            "avg_response_time_ms": 200,
            "popular_questions": [],
            "popular_sources": [],
            "queries_by_mode": {"qa": 10},
            "queries_today": 5,
            "trend": [],
        }

        resp = client.get("/query-analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 10


def test_sessions_crud():
    """Test session create, list, delete."""
    # Create
    resp = client.post("/sessions", json={"title": "Test Session"})
    assert resp.status_code == 200
    session_id = resp.json()["id"]

    # List
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Get
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200

    # Delete
    resp = client.delete(f"/sessions/{session_id}")
    assert resp.status_code == 200


def test_cache_clear():
    """Test cache clearing endpoint."""
    resp = client.post("/cache/clear")
    assert resp.status_code == 200
    assert "entries_removed" in resp.json()


def test_crawl_urls_endpoint():
    """Test crawl URL management (F9)."""
    resp = client.get("/crawl/urls")
    assert resp.status_code == 200
    assert "urls" in resp.json()
