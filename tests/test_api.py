# tests/test_api.py
# ─────────────────────────────────────────────────────────────────────────────
# API Endpoint Tests using FastAPI's TestClient
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


def test_query_ollama_offline():
    """Test that query returns 503 when Ollama is not reachable."""
    with patch("api.app.check_ollama_connection", return_value=False):
        resp = client.post("/query", json={"question": "What is this?"})
        assert resp.status_code == 503
        assert "Ollama" in resp.json()["detail"]


def test_query_success():
    """Test successful query with mocked pipeline."""
    with patch("api.app.check_ollama_connection", return_value=True), \
         patch("pipeline.query") as mock_query:
        mock_query.return_value = {
            "answer": "The total is $100.",
            "sources": [
                {"source": "invoice.pdf", "page": 1, "excerpt": "Total: $100", "score": 0.95, "chunk_type": "text"}
            ],
        }
        
        resp = client.post("/query", json={"question": "What is the total?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["sources"]) == 1


def test_summarize_endpoint():
    """Test summarization endpoint."""
    with patch("api.app.check_ollama_connection", return_value=True), \
         patch("pipeline.get_summary") as mock_summary:
        mock_summary.return_value = {
            "summary": "This document is about testing.",
            "sources": [],
        }
        
        resp = client.post("/summarize", json={"topic": "testing"})
        assert resp.status_code == 200
        assert "summary" in resp.json()


def test_extract_endpoint():
    """Test extraction endpoint."""
    with patch("api.app.check_ollama_connection", return_value=True), \
         patch("pipeline.extract") as mock_extract:
        mock_extract.return_value = {
            "fields": {"invoice_number": "INV-001", "total": "$100"},
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
    with patch("api.app.check_ollama_connection", return_value=True), \
         patch("pipeline.query_table") as mock_table:
        mock_table.return_value = {
            "answer": "Row 3 total is $50.",
            "sources": [],
        }
        
        resp = client.post("/table-query", json={"question": "What is in row 3?"})
        assert resp.status_code == 200
        assert "answer" in resp.json()


def test_compare_endpoint_exposes_analysis_alias():
    """Test that compare responses expose both analysis and compatibility aliases."""
    with patch("api.app.check_ollama_connection", return_value=True), \
         patch("pipeline.compare_documents") as mock_compare:
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
    """Test deleting a document that doesn't exist."""
    with patch("pipeline.delete_document") as mock_delete:
        mock_delete.side_effect = FileNotFoundError("not found")
        resp = client.delete("/document/nonexistent.pdf")
        assert resp.status_code == 404


def test_validation_error_format():
    """Test that validation errors return a clean format."""
    resp = client.post("/extract", json={"fields": []})  # empty fields list not allowed
    assert resp.status_code == 422
    data = resp.json()
    assert "errors" in data
