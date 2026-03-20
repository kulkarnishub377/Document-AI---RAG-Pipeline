# System Architecture 🏛️

Document AI + RAG Pipeline v2.0 is designed around a clean, modular architecture. This separation of concerns ensures that the system is testable, maintainable, and easily extensible.

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Frontend (HTML/CSS/JS)                          │
│  Upload Zone · Mode Tabs · Streaming Chat · Analytics · Export · Modals│
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ REST API (FastAPI — 16 endpoints)
┌──────────────────────────────▼──────────────────────────────────────────┐
│  Stage 1: Load       │ PyMuPDF · PaddleOCR · python-docx · BS4 · LLaVA│
│  Stage 2: Chunk      │ Unicode sentence-aware chunking with overlap    │
│  Stage 3: Embed      │ SentenceTransformers → FAISS (GPU-aware) + BM25│
│  Stage 4: Retrieve   │ Hybrid search + Cross-Encoder reranking         │
│  Stage 5: Answer     │ Mistral 7B via Ollama (LCEL prompt chains)      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Breakdown

### 1. `ingestion/` — Document Loaders
- Parses `.pdf`, `.docx`, `.png`, `.jpg`, `.tiff`, `.txt`, `.md`, and web URLs into normalized `PageData` objects
- Intelligently delegates: `PyMuPDF` for digital PDFs, `BeautifulSoup4` for web scraping, `python-docx` for Word
- **Vision LLM integration** — uses Ollama's `llava` model for image/chart analysis with PaddleOCR fallback
- **Auto language detection** (`langdetect`) — detects document language and selects the optimal OCR engine dynamically
- Extracts tables intact before they enter the text stream

### 2. `chunking/` — Semantic Chunker
- Slices `PageData` text into `Chunk` objects (default: 512 chars, 64 overlap)
- **Unicode-aware sentence splitting** — supports English, Hindi (।), Chinese/Japanese (。), Arabic (۔), and more
- Greedy packing algorithm that respects sentence boundaries to avoid cutting thoughts mid-sentence
- Tables are converted to Markdown and treated as **atomic, indivisible chunks**
- SHA-256 deduplication saves vector database space

### 3. `embedding/` — Vector Store & Hybrid Search
- Encodes text into 384D dense vectors using `sentence-transformers/all-MiniLM-L6-v2`
- Stores vectors in an in-memory **FAISS** Flat Inner Product (cosine similarity) index
- **GPU auto-detection** — automatically uses `faiss-gpu` when NVIDIA GPUs are available
- **BM25 keyword index** (`rank_bm25`) runs alongside FAISS for superior recall
- Thread-safe operations using `RLock` for concurrent access
- Serializes index + `metadata.json` to disk for persistence
- Surgical deletion of individual documents without full rebuild

### 4. `retrieval/` — Cross-Encoder Reranker
- Pools top FAISS candidates and top BM25 candidates into a unified candidate set
- Passes candidates through `cross-encoder/ms-marco-MiniLM-L6-v2` for bidirectional context scoring
- Sorts and prunes to the **top 5** most relevant chunks
- Graceful fallback: returns FAISS results as-is if reranker fails to load

### 5. `llm/` — Prompt Chains (LCEL)
- **Migrated from deprecated `LLMChain` to modern LCEL** (`prompt | llm | StrOutputParser()`)
- Connects to local `Ollama` daemon for Mistral 7B inference
- Four specialized chains:
  - **Q&A** — strict fact-checking with source citations (streaming + sync)
  - **Summarization** — bullet-point document summaries
  - **Extraction** — structured JSON key-value extraction
  - **Table Q&A** — table-specific analysis with calculation support
- **Conversational memory** — injects last 5 conversation turns into context
- **Ollama connectivity check** — validates connection before queries, returns clear 503 errors

### 6. `api/` — FastAPI Server (16 Endpoints)
- REST endpoints: `/ingest`, `/ingest/url`, `/ingest/batch`, `/query`, `/query-stream`, `/summarize`, `/extract`, `/table-query`, `/status`, `/analytics`, `/health`, `/clear`, `/document/{filename}`
- **SSE streaming** for real-time answer generation
- **Custom validation error handler** for clean 422 responses
- `Cache-Control` headers for static assets
- Pydantic request/response models with `score` and `chunk_type` fields

### 7. `frontend/` — Premium Web UI
- **Dark glassmorphic theme** with animated background grid and glow effects
- **XSS-safe rendering** — all user input sanitized with `escapeHtml()` or `textContent`
- **Confidence badges** — color-coded High/Medium/Low on every source citation
- **Citation click-through** — click a source to view the full chunk in a modal
- **Analytics dashboard** — interactive modal showing storage, per-document breakdown
- **Export conversations** — copy as Markdown to clipboard or download as file
- SSE streaming via `ReadableStream` API for real-time typing effects
- Full history tracking persisted to `localStorage`

### 8. `tests/` — Comprehensive Test Suite (30+ tests)
- `test_api.py` — 16 API endpoint tests using FastAPI `TestClient`
- `test_chunker.py` — Chunking edge cases (empty, text, table)
- `test_config.py` — Config loading and env variable overrides
- `test_pipeline.py` — Pipeline integration (startup, ingest, delete, analytics)
- `test_reranker.py` — Reranking (scoring, sorting, top-k, failure handling)
- `test_vector_store.py` — Vector store operations and state management

## Docker Deployment

```yaml
services:
  ollama:   # LLM server
    image: ollama/ollama:latest
    ports: ["11434:11434"]

  app:      # RAG Pipeline
    build: .
    ports: ["8000:8000"]
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on: [ollama]
```

## Configuration

All settings are centralized in `config.py` and overridable via `.env`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ENABLE_GPU` | `auto` | GPU acceleration mode |
| `MULTILINGUAL_MODE` | `false` | Auto language detection |
| `CHUNK_SIZE` | `512` | Characters per chunk |
| `RETRIEVAL_TOP_K` | `20` | FAISS search candidates |
| `RERANKER_TOP_K` | `5` | Final results after reranking |
