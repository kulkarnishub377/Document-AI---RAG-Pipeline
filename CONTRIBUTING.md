# Contributing to Document AI + RAG Pipeline v2.0

Thank you for your interest in contributing! This guide will help you get started.

---

## 🛠️ Development Setup

1. **Fork and clone** the repository
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```
3. **Install dependencies** (including dev tools):
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"
   ```
4. **Install Ollama** and pull models:
   ```bash
   ollama pull mistral
   ollama pull llava    # optional, for Vision LLM
   ```
5. **Copy environment config:**
   ```bash
   cp .env.example .env
   ```

---

## 🧪 Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_api.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

All tests must pass before submitting a PR. We currently have **30+ tests** across 6 files:

| Test File | Coverage |
|-----------|----------|
| `test_api.py` | 16 API endpoint tests (using `TestClient`) |
| `test_chunker.py` | Chunking logic (empty, text, table) |
| `test_config.py` | Config loading and env overrides |
| `test_pipeline.py` | Pipeline integration (startup, ingest, delete, analytics) |
| `test_reranker.py` | Reranking (scoring, sorting, top-k, failure handling) |
| `test_vector_store.py` | Vector store (dataclass, stats, reset) |

---

## 🎨 Code Style

- **Formatter**: `black` — run `black .` before committing
- **Linter**: `ruff` or `flake8`
- **Type hints**: Use `from __future__ import annotations` and type all public functions
- **Docstrings**: All public functions must have docstrings
- **Imports**: Use `TYPE_CHECKING` guard for circular/heavy imports

---

## 🏗️ Architecture

The project follows a clean, modular architecture with strict separation of concerns:

```
Stage 1 → ingestion/    — Load documents (PDF, images, DOCX, URLs)
Stage 2 → chunking/     — Split into semantic chunks with overlap
Stage 3 → embedding/    — Embed and index in FAISS + BM25
Stage 4 → retrieval/    — Cross-encoder reranking
Stage 5 → llm/          — LangChain LCEL prompt chains via Ollama
           api/          — FastAPI REST server (16 endpoints)
           frontend/     — Vanilla HTML/JS/CSS with glassmorphic dark theme
```

When adding features:
- **New parsers** → add to `ingestion/document_loader.py`
- **New LLM chains** → add to `llm/prompt_chains.py` using LCEL syntax
- **New API endpoints** → add to `api/app.py` with Pydantic models
- **Frontend features** → update `index.html`, `app.js`, and `style.css`

---

## 📝 Submitting Pull Requests

1. Create a descriptive branch: `git checkout -b feature/my-feature`
2. Write tests for new functionality
3. Run the full test suite: `python -m pytest tests/ -v`
4. Format code: `black .`
5. Write a clear PR description with:
   - What changed and why
   - How you tested it
   - Screenshots for UI changes
6. Link any related issues

---

## 🐳 Docker Testing

Test your changes in Docker before submitting:

```bash
docker build -t doc-rag-pipeline .
docker-compose up -d
# Verify at http://localhost:8000
docker-compose down
```

---

## 📋 Issue Guidelines

- **Bug reports**: Include steps to reproduce, expected vs actual behavior, and OS/Python version
- **Feature requests**: Describe the use case and proposed solution
- **Questions**: Use GitHub Discussions instead of Issues
