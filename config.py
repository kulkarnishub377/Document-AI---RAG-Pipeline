# config.py  –  all settings in one place, change here only
import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
UPLOAD_DIR    = DATA_DIR / "uploads"
INDEX_DIR     = DATA_DIR / "index"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

FAISS_INDEX_PATH    = INDEX_DIR / "faiss.index"
METADATA_PATH       = INDEX_DIR / "metadata.json"

# ── Models ───────────────────────────────────────────────────────────────────
# Embedding model  (auto-downloads ~90 MB on first run, stored in ~/.cache)
EMBED_MODEL_NAME    = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIMENSION     = 384          # must match the model above

# Reranker  (auto-downloads ~80 MB on first run)
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_TOP_K      = 5            # final chunks sent to LLM after reranking

# Ollama LLM  (must run: ollama pull mistral  before starting)
OLLAMA_BASE_URL     = "http://localhost:11434"
OLLAMA_MODEL        = "mistral"    # change to "llama3.2:3b" for lower RAM

# ── OCR ──────────────────────────────────────────────────────────────────────
OCR_LANGUAGE        = "en"         # e.g. "en", "ch", "hi"  (PaddleOCR codes)
OCR_USE_ANGLE_CLS   = True         # rotated-text detection

# ── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_SIZE          = 512          # characters per chunk
CHUNK_OVERLAP       = 64           # overlap between consecutive chunks

# ── Retrieval ────────────────────────────────────────────────────────────────
RETRIEVAL_TOP_K     = 20           # candidates fetched from FAISS before rerank

# ── API ──────────────────────────────────────────────────────────────────────
API_HOST            = "0.0.0.0"
API_PORT            = 8000
