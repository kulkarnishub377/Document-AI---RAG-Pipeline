# 📄 DocuAI Studio V3

> Upload any document (PDF, image, DOCX, Excel, PowerPoint, CSV, text, or web URL) and ask questions in plain English.
> Fully local, private, and powered by Mistral via Ollama.

<!-- Status Badges -->

![Version](https://img.shields.io/badge/Version-3.0.0-blueviolet?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)
[![CI](https://github.com/kulkarnishub377/Document-AI---RAG-Pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/kulkarnishub377/Document-AI---RAG-Pipeline/actions/workflows/ci.yml)

<!-- Technology Badges -->

![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-LCEL-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![Ollama](https://img.shields.io/badge/LLM-Mistral_via_Ollama-black?style=flat-square)
![FAISS](https://img.shields.io/badge/Vector_Store-FAISS-3B5998?style=flat-square&logo=meta&logoColor=white)
![PaddleOCR](https://img.shields.io/badge/OCR-PaddleOCR-2B6CB0?style=flat-square)
![BM25](https://img.shields.io/badge/Search-Hybrid_(FAISS+BM25)-orange?style=flat-square)
![SentenceTransformers](https://img.shields.io/badge/Embeddings-MiniLM--L6--v2-yellow?style=flat-square)
![CrossEncoder](https://img.shields.io/badge/Reranker-Cross--Encoder-red?style=flat-square)
![SQLite](https://img.shields.io/badge/Sessions-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![WebSocket](https://img.shields.io/badge/Collab-WebSocket-brightgreen?style=flat-square)
![Frontend](https://img.shields.io/badge/Frontend-Vanilla_JS-F7DF1E?style=flat-square&logo=javascript&logoColor=black)

---

## ✨ What's New in v3.0

| Feature                              | Description                                                      |
| ------------------------------------ | ---------------------------------------------------------------- |
| 📊**Excel/CSV/PPTX Support**   | Parse spreadsheets and presentations natively                    |
| 💬**Persistent Chat Sessions** | SQLite-backed conversation persistence across browsers           |
| ⚡**Query Caching (LRU)**      | TTL-based cache avoids redundant LLM calls                       |
| 🔗**Knowledge Graph**          | Entity extraction + relationship mapping with visualization data |
| 📄**PDF Annotation Export**    | Highlighted source passages in downloadable PDFs                 |
| 🔍**Document Comparison**      | Side-by-side analysis of two documents                           |
| 🌐**Real-time Collaboration**  | WebSocket multi-user Q&A in shared rooms                         |
| 🛡️**Rate Limiting**          | Sliding-window rate limiter per client IP                        |
| 🎯**Source-Filtered Queries**  | Target Q&A to a specific document                                |
| 🧠**Conversational Memory**    | Full chat history for both sync and streaming modes              |
| 🔧**Custom Exceptions**        | Structured error hierarchy for clean API responses               |
| 📝**Structured JSON Logging**  | Production-ready log format option                               |

---

## 🧠 How It Works

RAG (Retrieval-Augmented Generation) lets an AI answer questions about your specific documents. Instead of guessing from training data, it:

1. **Reads and indexes** your documents (text extraction + semantic embedding).
2. **Finds the most relevant passages** when you ask a question (FAISS + BM25 + reranking).
3. **Feeds those passages to Mistral 7B** as context.
4. **Writes a grounded answer** with citations to your actual documents.

Nothing leaves your machine. No API keys. No cloud.

---

## 🏗️ Architecture

```
                    ┌──────────────────────────────────────────────────┐
                    │          Frontend (HTML/CSS/JS)                   │
                    │  Upload · Chat · Summary · Extract · Compare     │
                    │  Knowledge Graph · Analytics · Collaboration     │
                    └─────────────────┬────────────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────────────┐
                    │        FastAPI REST + WebSocket Server            │
                    │  30+ endpoints · Rate limiting · Sessions        │
                    └─────────────────┬────────────────────────────────┘
                                      │
    ┌─────────┬───────────┬──────────┼──────────┬──────────┬──────────┐
    │ Stage 1 │  Stage 2  │ Stage 3  │  Stage 4 │ Stage 5  │ Features │
    │  LOAD   │  CHUNK    │ EMBED    │ RETRIEVE │ ANSWER   │  v3.0    │
    ├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┤
    │ PyMuPDF │ Sentence  │ MiniLM   │ Hybrid   │ Mistral  │ Sessions │
    │ Paddle  │ Unicode   │ FAISS    │ FAISS+   │ 7B via   │ Cache    │
    │ OCR     │ Table-    │ GPU-     │ BM25     │ Ollama   │ KGraph   │
    │ openpyxl│ Atomic    │ aware    │ Cross-   │ LCEL     │ Compare  │
    │ pptx    │ Dedup     │ Index    │ Encoder  │ Stream   │ Annotate │
    │ BS4     │ SHA-256   │ Save     │ Rerank   │ History  │ WS/Collab│
    └─────────┴───────────┴──────────┴──────────┴──────────┴──────────┘
```

### Data Flow

```
Document → OCR/Parse → Sentence Chunk → Embed (384D) → FAISS Index
                                                             ↓
Question → Embed → FAISS Search (top 20) → BM25 Boost → Rerank (top 5)
                                                             ↓
                                              Mistral 7B → Answer + Sources
                                                             ↓
                                              Cache → Session → WebSocket
```

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Start everything (app + Ollama)
docker-compose up -d

# Pull the LLM model (first time only)
docker exec rag-ollama ollama pull mistral

# Open the UI
open http://localhost:8000
```

### Option 2: Local Install

**Prerequisites:**

- Python 3.10+
- [Ollama](https://ollama.ai/) installed and running

```bash
# 1. Clone & install
git clone https://github.com/kulkarnishub377/Document-AI---RAG-Pipeline.git
cd Document-AI---RAG-Pipeline
pip install -r requirements.txt

# 2. Pull the LLM model
ollama pull mistral

# 3. Configure (optional)
cp .env.example .env
# Edit .env to customize settings

# 4. Run application
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 📁 Project Structure

```
DocuAI Studio/
├── api/
│   └── app.py                 # FastAPI REST + WebSocket server (30+ endpoints)
├── chunking/
│   └── semantic_chunker.py    # Unicode-aware sentence chunking with dedup
├── embedding/
│   └── vector_store.py        # FAISS + BM25 hybrid index (GPU-aware)
├── features/                  # 🆕 v3.0 Feature Modules
│   ├── knowledge_graph.py     # Entity extraction + relationship mapping
│   ├── collaboration.py       # WebSocket real-time multi-user Q&A
│   ├── pdf_annotator.py       # PDF highlighting with source passages
│   └── comparator.py          # Document comparison analysis
├── frontend/
│   ├── index.html             # UI with modals, analytics, and collaboration
│   ├── css/style.css          # Premium dark glassmorphic theme
│   └── js/app.js              # Client logic (XSS-safe, streaming, sessions)
├── ingestion/
│   └── document_loader.py     # Multi-format loader (PDF/Excel/PPTX/CSV/Image/Web)
├── llm/
│   └── prompt_chains.py       # 4 LCEL chains + streaming + chat history
├── retrieval/
│   └── reranker.py            # Cross-encoder reranking
├── utils/                     # 🆕 v3.0 Utilities
│   ├── cache.py               # LRU query cache with TTL
│   ├── rate_limiter.py        # Sliding-window rate limiter
│   ├── sessions.py            # SQLite persistent chat sessions
│   └── exceptions.py          # Custom exception hierarchy
├── tests/
│   ├── test_api.py            # 16+ API endpoint tests
│   ├── test_chunker.py        # Chunking unit tests
│   ├── test_config.py         # Config override tests
│   ├── test_pipeline.py       # Pipeline integration tests
│   ├── test_reranker.py       # Reranker unit tests
│   └── test_vector_store.py   # Vector store unit tests
├── config.py                  # Central configuration (env-driven, 30+ settings)
├── pipeline.py                # Pipeline orchestrator + caching + KG
├── run.py                     # Entry point
├── Dockerfile                 # Container build (with healthcheck)
├── docker-compose.yml         # Full stack: app + Ollama
├── pyproject.toml             # Modern Python packaging
├── requirements.txt           # Python dependencies
├── Makefile                   # Dev shortcuts (test, lint, format, docker)
├── CHANGELOG.md               # Version history
├── CONTRIBUTING.md            # Contribution guidelines
├── .env.example               # Configuration template
└── README.md                  # This file
```

---

## 🔌 API Reference (30+ Endpoints)

### Core

| Method  | Endpoint       | Description                        |
| ------- | -------------- | ---------------------------------- |
| `GET` | `/`          | Serve frontend UI                  |
| `GET` | `/health`    | Health check with version          |
| `GET` | `/status`    | Index stats + Ollama status        |
| `GET` | `/analytics` | Storage, cache, document breakdown |

### Ingestion

| Method   | Endpoint          | Description                                                  |
| -------- | ----------------- | ------------------------------------------------------------ |
| `POST` | `/ingest`       | Upload a single document (PDF/Excel/PPTX/Image/DOCX/CSV/TXT) |
| `POST` | `/ingest/url`   | Ingest a web URL                                             |
| `POST` | `/ingest/batch` | Upload multiple documents at once                            |

### Query & AI

| Method   | Endpoint          | Description                                                 |
| -------- | ----------------- | ----------------------------------------------------------- |
| `POST` | `/query`        | Ask a question (sync, with source filtering & chat history) |
| `POST` | `/query-stream` | Ask a question (streaming SSE)                              |
| `POST` | `/summarize`    | Summarize documents by topic                                |
| `POST` | `/extract`      | Extract structured fields as JSON                           |
| `POST` | `/table-query`  | Ask about tables                                            |
| `POST` | `/compare`      | 🆕 Compare two documents                                    |
| `POST` | `/annotate`     | 🆕 Q&A with highlighted PDF export                          |

### Sessions (v3.0)

| Method     | Endpoint                    | Description               |
| ---------- | --------------------------- | ------------------------- |
| `POST`   | `/sessions`               | Create a new chat session |
| `GET`    | `/sessions`               | List recent sessions      |
| `GET`    | `/sessions/{id}`          | Get session details       |
| `GET`    | `/sessions/{id}/messages` | Get messages in a session |
| `POST`   | `/sessions/{id}/messages` | Add a message             |
| `DELETE` | `/sessions/{id}`          | Delete a session          |

### Knowledge Graph (v3.0)

| Method  | Endpoint                           | Description                     |
| ------- | ---------------------------------- | ------------------------------- |
| `GET` | `/knowledge-graph`               | Full graph data (nodes + edges) |
| `GET` | `/knowledge-graph/entities`      | Search entities                 |
| `GET` | `/knowledge-graph/entity/{name}` | Entity details + neighbors      |

### Management

| Method     | Endpoint                  | Description                    |
| ---------- | ------------------------- | ------------------------------ |
| `POST`   | `/clear`                | Clear the entire index         |
| `DELETE` | `/document/{filename}`  | Delete a specific document     |
| `GET`    | `/documents`            | 🆕 List all uploaded documents |
| `GET`    | `/cache/stats`          | 🆕 Cache statistics            |
| `POST`   | `/cache/clear`          | 🆕 Clear query cache           |
| `GET`    | `/annotated`            | 🆕 List annotated PDFs         |
| `GET`    | `/annotated/{filename}` | 🆕 Download annotated PDF      |
| `WS`     | `/ws/{room_id}`         | 🆕 Real-time collaboration     |

---

### Example: Query a Document

```bash
# 1. Ingest a PDF
curl -X POST http://localhost:8000/ingest -F "file=@invoice.pdf"

# 2. Ask a question
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the total amount on the invoice?"}'

# Example response:
# {
#   "answer": "The total amount on the invoice is $2,450.00, as stated on page 2...",
#   "sources": [
#     {
#       "source": "invoice.pdf",
#       "page": 2,
#       "excerpt": "Total amount due: $2,450.00",
#       "score": 0.95,
#       "chunk_type": "text"
#     }
#   ]
# }
```

### Example: Compare Two Documents

```bash
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"doc_a": "contract_v1.pdf", "doc_b": "contract_v2.pdf", "question": "What clauses changed?"}'
```

### Example: Upload Excel

```bash
curl -X POST http://localhost:8000/ingest -F "file=@financial_report.xlsx"
curl -X POST http://localhost:8000/query \
  -d '{"question": "What was the Q3 revenue?"}'
```

---

## ⚙️ Configuration

All settings can be configured via environment variables or a `.env` file:

| Variable                    | Default              | Description                            |
| --------------------------- | -------------------- | -------------------------------------- |
| `OLLAMA_MODEL`            | `mistral`          | LLM model name                         |
| `EMBED_MODEL_NAME`        | `all-MiniLM-L6-v2` | Embedding model                        |
| `CHUNK_SIZE`              | `512`              | Chunk size in characters               |
| `RETRIEVAL_TOP_K`         | `20`               | FAISS candidates to retrieve           |
| `RERANKER_TOP_K`          | `5`                | Final results after reranking          |
| `ENABLE_GPU`              | `auto`             | GPU mode:`auto`, `true`, `false` |
| `MULTILINGUAL_MODE`       | `false`            | Auto-detect document language          |
| `MAX_FILE_SIZE_MB`        | `50`               | Max upload size                        |
| `CACHE_ENABLED`           | `true`             | 🆕 Enable query caching                |
| `CACHE_MAX_SIZE`          | `128`              | 🆕 Max cached queries                  |
| `CACHE_TTL_SECS`          | `3600`             | 🆕 Cache TTL in seconds                |
| `RATE_LIMIT_ENABLED`      | `true`             | 🆕 Enable rate limiting                |
| `RATE_LIMIT_REQUESTS`     | `60`               | 🆕 Max requests per window             |
| `RATE_LIMIT_WINDOW`       | `60`               | 🆕 Window size (seconds)               |
| `KNOWLEDGE_GRAPH_ENABLED` | `true`             | 🆕 Enable KG extraction                |
| `WS_ENABLED`              | `true`             | 🆕 Enable WebSocket collaboration      |
| `LOG_FORMAT`              | `text`             | 🆕 Log format:`text` or `json`     |

See [`.env.example`](.env.example) for the full list.

---

## 🗺️ Roadmap

- [X] Multi-format document support (PDF, Image, DOCX, Excel, PPTX, CSV) ✅
- [X] Persistent conversation sessions with SQLite ✅
- [X] Knowledge graph extraction ✅
- [X] Document comparison ✅
- [X] PDF annotation export ✅
- [X] Real-time WebSocket collaboration ✅
- [X] Query caching with TTL ✅
- [X] API rate limiting ✅
- [ ] User authentication for multi-user deployments
- [X] Evaluation dashboard using RAGAS metrics
- [ ] Webhook support for document change notifications
- [ ] Scheduled ingestion from folders/S3

---

## 🔧 Troubleshooting

**Ollama connection refused**
Make sure Ollama is running: `ollama serve`
Check it responds: `curl http://localhost:11434/api/tags`

**PaddleOCR first run is slow**
It downloads ~45 MB of model weights on first OCR call. This is normal — subsequent runs are fast.

**Out of memory during query**
Switch to a smaller LLM: set `OLLAMA_MODEL=llama3.2:3b` in `.env`
Or reduce `RETRIEVAL_TOP_K=10` to process fewer candidates.

**FAISS index not found error**
Ingest at least one document first before querying:
`curl -X POST http://localhost:8000/ingest -F "file=@test.pdf"`

**Rate limit exceeded**
Increase `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` in `.env`, or set `RATE_LIMIT_ENABLED=false`.

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_api.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Write tests for your changes
4. Run `python -m pytest tests/ -v` to make sure everything passes
5. Submit a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.
