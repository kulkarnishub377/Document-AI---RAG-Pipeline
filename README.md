# 📄 Document AI + RAG Pipeline v2.0

> Upload any document (PDF, image, Word, text, or web URL) and ask questions in plain English.  
> Fully local, private, and powered by Mistral via Ollama.

![License](https://img.shields.io/badge/License-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **5-Stage RAG Pipeline** | Load → Chunk → Embed/Index → Retrieve/Rerank → LLM Answer |
| **Hybrid Search** | FAISS (semantic) + BM25 (keyword) for best-of-both-worlds retrieval |
| **Cross-Encoder Reranking** | Re-scores candidates for higher precision |
| **Multi-Format Support** | PDF (native + scanned), PNG/JPG/TIFF, Word DOCX, TXT, Markdown, Web URLs |
| **Vision LLM Integration** | Uses LLaVA for image analysis with OCR fallback |
| **Streaming Responses** | Real-time SSE streaming for natural chat experience |
| **Conversational Memory** | Chat history maintained for contextual follow-up questions |
| **Confidence Scores** | Color-coded confidence badges (High/Medium/Low) on every source |
| **Analytics Dashboard** | Storage usage, per-document breakdown, Ollama status |
| **Export Conversations** | Copy as Markdown or download conversation history |
| **Citation Click-Through** | Click any source to view the full retrieved chunk |
| **Multi-Language Support** | Auto-detect document language, dynamic OCR engine switching |
| **GPU Auto-Detection** | Automatically uses FAISS GPU when NVIDIA GPU is available |
| **Batch Upload** | Upload multiple documents at once |
| **Docker Support** | One-command deployment with Docker Compose |
| **100% Local** | No data leaves your machine — complete privacy |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                     Frontend (HTML/CSS/JS)                         │
│  ┌──────────┐  ┌────────┐  ┌─────────┐  ┌────────┐  ┌─────────┐ │
│  │ Upload   │  │ Q&A    │  │ Summary │  │ Extract│  │ Table   │ │
│  │ Zone     │  │ Chat   │  │ Tab     │  │ Tab    │  │ Q&A Tab │ │
│  └──────────┘  └────────┘  └─────────┘  └────────┘  └─────────┘ │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ REST API (FastAPI)
┌──────────────────────────────▼─────────────────────────────────────┐
│  Stage 1: Load          │ PyMuPDF, PaddleOCR, python-docx, BS4    │
│  Stage 2: Chunk          │ Sentence-aware semantic chunking         │
│  Stage 3: Embed + Index  │ SentenceTransformers → FAISS + BM25    │
│  Stage 4: Retrieve       │ Hybrid search + Cross-Encoder reranking │
│  Stage 5: Answer         │ Mistral 7B via Ollama (LCEL chains)     │
└────────────────────────────────────────────────────────────────────┘
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
git clone https://github.com/your-repo/document-ai-rag.git
cd document-ai-rag
pip install -r requirements.txt

# 2. Pull the LLM model
ollama pull mistral

# 3. Configure (optional)
cp .env.example .env
# Edit .env to customize settings

# 4. Run
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 📁 Project Structure

```
Document AI + RAG Pipeline/
├── api/
│   └── app.py                 # FastAPI REST server (16 endpoints)
├── chunking/
│   └── semantic_chunker.py    # Unicode-aware sentence chunking
├── embedding/
│   └── vector_store.py        # FAISS + BM25 hybrid index (GPU-aware)
├── frontend/
│   ├── index.html             # UI with modals and analytics
│   ├── css/style.css          # Premium dark glassmorphic theme
│   └── js/app.js              # Client logic (XSS-safe, streaming)
├── ingestion/
│   └── document_loader.py     # Multi-format loader with lang detection
├── llm/
│   └── prompt_chains.py       # 4 LCEL chains (Q&A, summary, extract, table)
├── retrieval/
│   └── reranker.py            # Cross-encoder reranking
├── tests/
│   ├── test_api.py            # 16 API endpoint tests
│   ├── test_chunker.py        # Chunking unit tests
│   ├── test_config.py         # Config override tests
│   ├── test_pipeline.py       # Pipeline integration tests
│   ├── test_reranker.py       # Reranker unit tests
│   └── test_vector_store.py   # Vector store unit tests
├── config.py                  # Central configuration (env-driven)
├── pipeline.py                # Pipeline orchestrator + analytics
├── run.py                     # Entry point
├── Dockerfile                 # Container build
├── docker-compose.yml         # Full stack deployment
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Modern Python packaging
├── .env.example               # Configuration template
└── README.md                  # This file
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve frontend UI |
| `GET` | `/health` | Health check |
| `GET` | `/status` | Index stats + Ollama status |
| `GET` | `/analytics` | Detailed storage & document analytics |
| `POST` | `/ingest` | Upload a single document |
| `POST` | `/ingest/url` | Ingest a web URL |
| `POST` | `/ingest/batch` | Upload multiple documents at once |
| `POST` | `/query` | Ask a question (sync) |
| `POST` | `/query-stream` | Ask a question (streaming SSE) |
| `POST` | `/summarize` | Summarize by topic |
| `POST` | `/extract` | Extract structured fields as JSON |
| `POST` | `/table-query` | Ask about tables |
| `POST` | `/clear` | Clear the entire index |
| `DELETE` | `/document/{filename}` | Delete a specific document |

### Example: Query a Document

```bash
# 1. Ingest a PDF
curl -X POST http://localhost:8000/ingest -F "file=@invoice.pdf"

# 2. Ask a question
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the total amount on the invoice?"}'

# 3. Extract fields
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"fields": ["invoice_number", "date", "total_amount", "vendor"]}'

# 4. Ingest a web page
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation"}'
```

---

## ⚙️ Configuration

All settings can be configured via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `mistral` | LLM model name |
| `EMBED_MODEL_NAME` | `all-MiniLM-L6-v2` | Embedding model |
| `CHUNK_SIZE` | `512` | Chunk size in characters |
| `RETRIEVAL_TOP_K` | `20` | FAISS candidates to retrieve |
| `RERANKER_TOP_K` | `5` | Final results after reranking |
| `ENABLE_GPU` | `auto` | GPU mode: `auto`, `true`, `false` |
| `MULTILINGUAL_MODE` | `false` | Auto-detect document language |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |

See [`.env.example`](.env.example) for the full list.

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

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.
