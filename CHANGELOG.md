# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-03-27

### Added
- **Excel/CSV/PPTX support** — parse `.xlsx`, `.xls`, `.csv`, and `.pptx` files natively via `openpyxl` and `python-pptx`
- **Persistent chat sessions (SQLite)** — `utils/sessions.py` manages conversations across browsers with CRUD API
- **Query response caching** — `utils/cache.py` provides thread-safe LRU cache with configurable TTL
- **Document comparison mode** — `features/comparator.py` analyzes two documents for similarities and differences
- **Knowledge graph extraction** — `features/knowledge_graph.py` builds entity-relationship graphs with co-occurrence tracking
- **PDF annotation export** — `features/pdf_annotator.py` highlights source passages in PDFs using PyMuPDF
- **Real-time collaboration** — `features/collaboration.py` enables multi-user WebSocket Q&A rooms
- **API rate limiting** — `utils/rate_limiter.py` with sliding-window per-IP limiting + `X-RateLimit-*` headers
- **Source-filtered queries** — restrict Q&A to a specific document via `source_filter` parameter
- **Custom exception hierarchy** — `utils/exceptions.py` with 8 specific exception classes
- **Structured JSON logging** — `LOG_FORMAT=json` for production systems
- **API versioning** — OpenAPI docs at `/api/v1/docs`
- **Document listing endpoint** — `GET /documents` returns all uploaded files
- **Cache management API** — `GET /cache/stats` and `POST /cache/clear`
- **Session CRUD API** — 6 endpoints for managing persistent chat sessions
- **Knowledge graph API** — 3 endpoints for entity search and graph data
- **30+ total endpoints** (up from 14 in v2.0)

### Changed
- **`pipeline.py` rewritten** — integrated caching, knowledge graph, comparison, and source filtering
- **`config.py` expanded** — 30+ configurable settings (up from 15)
- **`api/app.py` rewritten** — all endpoints now `async`, using custom exceptions
- **Sync Q&A now supports chat history** — `answer_question()` accepts `history` parameter
- **`ALLOWED_EXTENSIONS` consolidated** — single source of truth in `config.py` (was duplicated in 4 places)

### Fixed
- **Critical: `delete_source()` FAISS crash** — `IndexFlatIP` doesn't support `remove_ids()`; now rebuilds index from remaining vectors
- **BM25 thread safety** — build/read operations moved inside `_lock`
- **Chat history ignored in sync mode** — sync `/query` now passes history to LLM

### Security
- Rate limiting prevents API abuse
- Custom exception classes prevent leaking internal errors

## [2.0.0] - 2026-03-20

### Added
- **Analytics dashboard** — new `/analytics` endpoint and interactive UI modal with storage breakdown
- **Confidence scores** — color-coded High/Medium/Low badges on source citations
- **Citation click-through** — click a source to view the full chunk text in a modal
- **Export conversations** — copy as Markdown or download as file
- **Multi-language support** — auto language detection via `langdetect` with dynamic OCR engine switching
- **GPU auto-detection** — uses `faiss-gpu` when NVIDIA GPU is available (`ENABLE_GPU` config)
- **Batch upload** — new `/ingest/batch` endpoint for multi-file uploads
- **URL ingestion** — new `/ingest/url` endpoint with frontend form
- **Docker support** — `Dockerfile` and `docker-compose.yml` for one-command deployment
- **Comprehensive test suite** — 30+ tests across 6 test files (API, pipeline, reranker, vector store, chunker, config)
- **Vision LLM integration** — LLaVA for image analysis with OCR fallback
- **GitHub CI/CD** — automated linting, testing, and Docker build via GitHub Actions
- **Project templates** — bug report, feature request, and PR templates

### Changed
- **Migrated to LCEL** — replaced all deprecated `LLMChain` with `prompt | llm | StrOutputParser()`
- **Unicode sentence splitting** — supports Hindi (।), Chinese/Japanese (。), Arabic (۔)
- **Improved error handling** — 503 when Ollama is offline, cleaner 422 validation errors
- **Cache-Control headers** — 1-hour caching for static frontend assets
- **Type hints** — added throughout all modules

### Fixed
- **Missing `/ingest/url` endpoint** — frontend called it but backend didn't have it
- **Async streaming** — `query_stream` was `def` calling async generator, now `async def`
- **FAISS IDSelectorBatch crash** — passed Python list instead of `np.int64` array
- **Deadlock in `delete_source()`** — changed `threading.Lock` to `threading.RLock`
- **Lost system prompt** — sync `answer_question()` was missing instruction text
- **XSS vulnerability** — all `innerHTML` now uses `escapeHtml()` sanitization
- **pyproject.toml desync** — synced pinned versions with requirements.txt

### Security
- Fixed XSS vulnerability in frontend JavaScript
- Added input sanitization for all user-supplied content

## [1.0.0] - 2024-12-01

### Added
- Initial release
- 5-stage RAG pipeline (Load → Chunk → Embed → Retrieve → Answer)
- PDF, image, DOCX, TXT document support
- PaddleOCR for scanned documents
- FAISS vector store with BM25 hybrid search
- Cross-encoder reranking
- Mistral 7B via Ollama for generation
- FastAPI REST API with streaming SSE
- Premium dark-themed web UI
- Conversation history
- Document deletion
