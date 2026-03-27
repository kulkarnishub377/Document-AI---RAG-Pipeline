# config.py — Single source of truth for all pipeline settings
# ─────────────────────────────────────────────────────────────────────────────
# Every configurable value lives here. Change settings in this file or
# override them with environment variables / a .env file.
# v3.0 — Added: caching, rate limiting, SQLite sessions, knowledge graph,
#         WebSocket, PDF annotation, document comparison, API versioning,
#         Excel/CSV/PPTX support
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv  # type: ignore
from loguru import logger       # type: ignore

# ── Load .env file if present ─────────────────────────────────────────────────
load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parent
DATA_DIR      = BASE_DIR / "data"
UPLOAD_DIR    = DATA_DIR / "uploads"
INDEX_DIR     = DATA_DIR / "index"
FRONTEND_DIR  = BASE_DIR / "frontend"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH    = INDEX_DIR / "metadata.json"

# ── Models ────────────────────────────────────────────────────────────────────
# Embedding model  (auto-downloads ~90 MB on first run, cached in ~/.cache)
EMBED_MODEL_NAME = os.getenv(
    "EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBED_DIMENSION  = int(os.getenv("EMBED_DIMENSION", "384"))

# Reranker  (auto-downloads ~80 MB on first run)
RERANKER_MODEL_NAME = os.getenv(
    "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L6-v2"
)
RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K", "5"))

# Ollama LLM  (must run: ollama pull mistral)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")

# ── OCR ───────────────────────────────────────────────────────────────────────
OCR_LANGUAGE       = os.getenv("OCR_LANGUAGE", "en")
OCR_USE_ANGLE_CLS  = os.getenv("OCR_USE_ANGLE_CLS", "true").lower() == "true"

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

# ── Retrieval ─────────────────────────────────────────────────────────────────
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "20"))

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST    = os.getenv("API_HOST", "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT", "8000"))
API_VERSION = os.getenv("API_VERSION", "v1")

# ── File Upload Limits ────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB   = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp",
    ".docx", ".txt", ".md",
    ".xlsx", ".csv",      # Spreadsheets (v3.0)
    ".pptx",                       # Presentations (v3.0)
}

# ── GPU Acceleration ──────────────────────────────────────────────────────────
ENABLE_GPU = os.getenv("ENABLE_GPU", "auto").lower()  # "auto" | "true" | "false"

# ── Multi-Language ────────────────────────────────────────────────────────────
MULTILINGUAL_MODE = os.getenv("MULTILINGUAL_MODE", "false").lower() == "true"
MULTILINGUAL_EMBED_MODEL = os.getenv(
    "MULTILINGUAL_EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
MULTILINGUAL_EMBED_DIMENSION = int(os.getenv("MULTILINGUAL_EMBED_DIMENSION", "384"))

# ── Query Caching (v3.0) ─────────────────────────────────────────────────────
CACHE_ENABLED    = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_MAX_SIZE   = int(os.getenv("CACHE_MAX_SIZE", "128"))
CACHE_TTL_SECS   = int(os.getenv("CACHE_TTL_SECS", "3600"))  # 1 hour

# ── Rate Limiting (v3.0) ─────────────────────────────────────────────────────
RATE_LIMIT_ENABLED   = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS  = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))   # per window
RATE_LIMIT_WINDOW    = int(os.getenv("RATE_LIMIT_WINDOW", "60"))     # seconds

# ── SQLite Sessions (v3.0) ───────────────────────────────────────────────────
SQLITE_DB_PATH = DATA_DIR / os.getenv("SQLITE_DB_NAME", "sessions.db")

# ── Knowledge Graph (v3.0) ───────────────────────────────────────────────────
KNOWLEDGE_GRAPH_ENABLED = os.getenv("KNOWLEDGE_GRAPH_ENABLED", "true").lower() == "true"
KG_DATA_PATH = DATA_DIR / "knowledge_graph.json"

# ── WebSocket Collaboration (v3.0) ───────────────────────────────────────────
WS_ENABLED = os.getenv("WS_ENABLED", "true").lower() == "true"

# ── PDF Annotation (v3.0) ────────────────────────────────────────────────────
ANNOTATED_PDF_DIR = DATA_DIR / "annotated"
ANNOTATED_PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL  = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "text" | "json"

# Remove default loguru handler and add a custom one
logger.remove()

if LOG_FORMAT == "json":
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format="{message}",
        serialize=True,
    )
else:
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

logger.add(
    DATA_DIR / "pipeline.log",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
)

# ── Version ───────────────────────────────────────────────────────────────────
__version__ = "3.0.0"
