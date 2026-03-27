# System Architecture 🏛️

Document AI + RAG Pipeline v3.0 is designed around a clean, modular architecture. This separation of concerns ensures that the system is testable, maintainable, and easily extensible.

## High-Level Flow

```
                    ┌──────────────────────────────────────────────────┐
                    │          Frontend (HTML/CSS/JS)                   │
                    │  Upload · Chat · Summary · Extract · Compare     │
                    │  Knowledge Graph · Analytics · Collaboration     │
                    └─────────────────┬────────────────────────────────┘
                                      │ REST API (FastAPI — 30+ endpoints)
                    ┌─────────────────▼────────────────────────────────┐
                    │  Stage 1: Load    │ PyMuPDF · PaddleOCR · python-│
                    │                   │ docx · openpyxl · python-pptx│
                    │                   │ · csv · BS4 · LLaVA          │
                    │  Stage 2: Chunk   │ Unicode sentence-aware + dedup│
                    │  Stage 3: Embed   │ SentenceTransformers → FAISS │
                    │                   │ (GPU-aware) + BM25            │
                    │  Stage 4: Retrieve│ Hybrid search + Cross-Encoder │
                    │  Stage 5: Answer  │ Mistral 7B via Ollama (LCEL)  │
                    └─────────────────────────────────────────────────────┘
```

## Module Breakdown

### 1. `ingestion/` — Document Loaders
- Parses `.pdf`, `.docx`, `.xlsx`, `.xls`, `.csv`, `.pptx`, `.png`, `.jpg`, `.tiff`, `.txt`, `.md`, and web URLs into normalized `PageData` objects
- Intelligently delegates: `PyMuPDF` for digital PDFs, `BeautifulSoup4` for web scraping, `python-docx` for Word, `openpyxl` for Excel, `python-pptx` for PowerPoint
- **Vision LLM integration** — uses Ollama's `llava` model for image/chart analysis with PaddleOCR fallback
- **Auto language detection** (`langdetect`) — detects document language and selects the optimal OCR engine dynamically
- Extracts tables intact before they enter the text stream
- **v3.0**: Added Excel/CSV/PPTX parsers with table extraction

### 2. `chunking/` — Semantic Chunker
- Slices `PageData` text into `Chunk` objects (default: 512 chars, 64 overlap)
- **Unicode-aware sentence splitting** — supports English, Hindi (।), Chinese/Japanese (。), Arabic (۔), and more
- Greedy packing algorithm that respects sentence boundaries
- Tables converted to Markdown → **atomic, indivisible chunks**
- SHA-256 deduplication saves vector database space

### 3. `embedding/` — Vector Store & Hybrid Search
- Encodes text into 384D dense vectors using `sentence-transformers/all-MiniLM-L6-v2`
- Stores vectors in an in-memory **FAISS** Flat Inner Product index
- **GPU auto-detection** — automatically uses `faiss-gpu` when NVIDIA GPUs are available
- **BM25 keyword index** (`rank_bm25`) for superior recall
- Thread-safe operations using `RLock`
- Serializes index + `metadata.json` to disk
- **v3.0 fix**: `delete_source()` now rebuilds the FAISS index (IndexFlatIP doesn't support `remove_ids`)

### 4. `retrieval/` — Cross-Encoder Reranker
- Pools top FAISS + BM25 candidates into a unified candidate set
- Passes through `cross-encoder/ms-marco-MiniLM-L6-v2` for bidirectional scoring
- Returns **top 5** most relevant chunks
- Graceful fallback if reranker fails

### 5. `llm/` — Prompt Chains (LCEL)
- **Modern LCEL** (`prompt | llm | StrOutputParser()`)
- Four specialized chains: **Q&A**, **Summarization**, **Extraction**, **Table Q&A**
- **Conversational memory** — both sync and streaming modes (v3.0 fix)
- **Ollama connectivity check** — validates connection before queries

### 6. `api/` — FastAPI Server (30+ Endpoints)
- REST + WebSocket endpoints
- **v3.0**: Rate limiting middleware, custom exception handlers, session management, knowledge graph API, document comparison, PDF annotation, cache management
- SSE streaming for real-time answer generation
- API versioning at `/api/v1/docs`

### 7. `utils/` — Utility Modules (v3.0)
- `cache.py` — LRU query cache with TTL
- `rate_limiter.py` — sliding-window per-IP rate limiter
- `sessions.py` — SQLite persistent chat sessions
- `exceptions.py` — custom exception hierarchy (8 classes)

### 8. `features/` — Feature Modules (v3.0)
- `knowledge_graph.py` — entity extraction + relationship mapping
- `collaboration.py` — WebSocket real-time collaboration rooms
- `pdf_annotator.py` — PDF highlighting with PyMuPDF
- `comparator.py` — document comparison via LLM

### 9. `frontend/` — Premium Web UI
- **Dark glassmorphic theme** with animated background grid and glow effects
- **XSS-safe rendering** — all user input sanitized
- **Confidence badges** — color-coded High/Medium/Low
- **Citation click-through**, **Analytics dashboard**, **Export conversations**
- SSE streaming via `ReadableStream` API

### 10. `tests/` — Test Suite (30+ tests)
- `test_api.py` — API endpoint tests using FastAPI `TestClient`
- `test_chunker.py` — Chunking edge cases
- `test_config.py` — Config loading and env variable overrides
- `test_pipeline.py` — Pipeline integration
- `test_reranker.py` — Reranking tests
- `test_vector_store.py` — Vector store operations

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
| `CACHE_ENABLED` | `true` | Query caching (v3.0) |
| `RATE_LIMIT_ENABLED` | `true` | API rate limiting (v3.0) |
| `KNOWLEDGE_GRAPH_ENABLED` | `true` | Knowledge graph (v3.0) |
| `WS_ENABLED` | `true` | WebSocket collaboration (v3.0) |
| `LOG_FORMAT` | `text` | Structured logging (v3.0) |
