# CHANGELOG

## [3.1.0] — 2026-03-30

### 🐛 Bug Fixes
- **FAISS Race Condition** — Added thread-safe locking to `similarity_search()` preventing corrupted reads under concurrent API requests
- **BM25 Score Fusion** — Replaced zero-score BM25 candidate insertion with proper Reciprocal Rank Fusion (RRF) for accurate hybrid search scoring
- **Chunk Overlap Mismatch** — Fixed `overlap_text` / `overlap_str` variable mismatch in semantic chunker causing inconsistent chunk sizes
- **Deprecated `datetime.utcnow()`** — Replaced all occurrences across 4 modules with timezone-aware `datetime.now(timezone.utc)`
- **Deprecated `@app.on_event("startup")`** — Migrated to FastAPI `lifespan` context manager
- **Scanned PDF File Handle Leak** — Wrapped PyMuPDF operations in `try/finally` to ensure file handles are always released
- **WebSocket Event Loop Blocking** — Wrapped synchronous `pipeline.query()` calls in `asyncio.to_thread()` within WebSocket handler
- **Duplicate File Upload** — Auto-deletes old index entries when re-uploading the same filename
- **Test Mock Targets** — Fixed `test_query_ollama_offline` patching wrong module and `test_delete_document_not_found` using wrong exception type
- **URL Parsing Failures** — Added retry logic with exponential backoff for web page fetching

### 🔒 Security
- **Configurable CORS** — CORS origins now configurable via `CORS_ORIGINS` environment variable (was hardcoded `*`)
- **Filename Sanitization** — Enhanced `_safe_filename()` with Windows reserved name checks (`CON`, `PRN`, etc.) and hidden file protection
- **WebSocket Input Validation** — Added message type and question length limits to WebSocket handler

### 🚀 Performance
- **Async Pipeline Operations** — All synchronous pipeline calls now wrapped in `asyncio.to_thread()` across all FastAPI endpoints
- **Efficient Index Deletion** — Switched from full index rebuild to `IndexIDMap.remove_ids()` for source deletion
- **Auto-IVF Index** — Automatically upgrades from flat index to IVF when vector count exceeds configurable threshold (default: 50K)
- **Lazy Module Imports** — Heavy modules (`pdfplumber`, `fitz`, `python-docx`) are now lazy-loaded only when needed
- **Capped KG Relationships** — Limited entity extraction to top-10 per chunk to prevent O(n²) relationship building

### ✨ New Features
- **[F2] Document Versioning** — Tracks upload history with version numbers, timestamps, and chunk counts per document
- **[F3] Async Ingestion** — New `/ingest/async` endpoint for background document processing with task status tracking
- **[F4] Multi-modal Q&A** — LLaVA vision model integration for asking questions about images/charts within documents
- **[F5] Export / Import Index** — Download and upload the complete FAISS index + metadata as a `.zip` file for backup/migration
- **[F6] Configurable LLM Providers** — Support for both Ollama (default) and OpenAI API backends, switchable via `LLM_PROVIDER` env var
- **[F7] Semantic Search** — Dedicated `/search` endpoint returning ranked passages without LLM generation
- **[F8] Enhanced Document Preview** — In-browser preview for PDFs, images, and text files with download fallback
- **[F9] Scheduled Web Crawling** — Background thread auto-refreshes web URL sources on configurable intervals
- **[F10] Query Analytics Dashboard** — Tracks query frequency, response times, popular documents, cached queries, and failure rates
- **[F11] Markdown Rendering** — Integrated `marked.js` for full markdown rendering in chat responses (tables, code blocks, headers, etc.)
- **[F13] Knowledge Graph Visualization** — Canvas-based force-directed graph renderer showing entity relationships
- **[F14] Batch Q&A** — Submit multiple questions at once, get answers as a table or downloadable CSV
- **[F16] Plugin System Hooks** — Lazy-import architecture for custom document parsers
- **[F18] Mobile Sidebar Toggle** — Responsive sidebar with toggle button and overlay for mobile devices
- **[F20] Incremental Embedding Updates** — Auto-detects re-uploads and replaces old index entries instead of duplicating

### 🎨 Frontend
- Integrated `marked.js` CDN for proper markdown rendering in all text views
- Added Semantic Search view with ranked results, scores, and source filtering
- Added Batch Q&A view with CSV export functionality
- Added Knowledge Graph Explorer with interactive canvas visualization and entity list
- Added Query Analytics section to the dashboard
- Added mobile sidebar toggle button with overlay
- Improved chat empty state with quick prompt suggestions
- Added Export/Import buttons to Data Lake view
- Improved chat message copy functionality
- Added document search filtering in Data Lake table
- Improved responsive design for mobile screens

### 📖 Documentation
- Updated `.env.example` with all configuration options
- Updated `README.md` with v3.1 features and architecture
- Added this CHANGELOG

### 🔧 Code Quality
- Removed `pyre-ignore` annotations and `Any` type abuse in chunker
- Extracted shared prompt templates (eliminated duplication between sync/stream)
- Added proper type annotations to vector store functions
- Added corrupted metadata JSON error handling
- Fixed comparator `DEMO_MODE` import to use runtime check
- Improved session manager `get_session` query reliability
- Added room cleanup for stale WebSocket connections

---

## [3.0.0] — 2026-03-15

### Features
- Full RAG pipeline with FAISS + BM25 hybrid search
- Multi-format document ingestion (PDF, DOCX, XLSX, CSV, PPTX, Images)
- PaddleOCR PP-OCRv4 for scanned document processing
- LLaVA vision model for image description
- Semantic chunking with sentence-aware boundaries
- Cross-encoder reranking for precision
- Real-time WebSocket collaboration
- PDF source annotation with highlighted passages
- RAGAS-inspired evaluation dashboard
- Knowledge graph extraction
- Document comparison engine
- SQLite session persistence
- Query caching with LRU + TTL
- Rate limiting
- Docker + Docker Compose deployment
- Glassmorphic premium web UI
