# Contributing to Document AI + RAG Pipeline

Thank you for your interest in contributing! Here's how you can help.

## 🚀 Quick Start for Contributors

```bash
# 1. Fork and clone
git clone https://github.com/<your-fork>/Document-AI---RAG-Pipeline.git
cd Document-AI---RAG-Pipeline

# 2. Install dependencies (production + dev)
pip install -r requirements.txt
pip install -e ".[dev]"

# 3. Run tests
python -m pytest tests/ -v

# 4. Start dev server
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

## 📋 Development Workflow

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write your code** following the project structure:
   - New parsers → `ingestion/document_loader.py`
   - New chains → `llm/prompt_chains.py`
   - New features → `features/` directory
   - New utilities → `utils/` directory

3. **Write tests** for your changes:
   ```bash
   python -m pytest tests/ -v --tb=short
   ```

4. **Ensure code quality**:
   ```bash
   ruff check .        # Linting
   black .             # Formatting
   ```

5. **Submit a Pull Request** to `main` with a clear description.

## 🏗️ Architecture Overview

```
config.py           → Central configuration (single source of truth)
pipeline.py         → Orchestrator (wires all stages)
api/app.py          → FastAPI server (30+ endpoints)
ingestion/          → Document loaders (PDF, Excel, PPTX, etc.)
chunking/           → Sentence-aware semantic chunking
embedding/          → FAISS + BM25 hybrid search
retrieval/          → Cross-encoder reranking
llm/                → LCEL prompt chains (Q&A, summary, extract, table)
features/           → v3.0 feature modules (KG, collaboration, etc.)
utils/              → Utilities (cache, rate limiter, sessions, exceptions)
tests/              → pytest test suite
```

## 📝 Coding Standards

- **Python 3.10+** with type hints
- **Black** for formatting (line length: 88)
- **Ruff** for linting
- **Loguru** for logging (use `from loguru import logger`)
- All settings in `config.py` — no magic numbers in code
- Custom exceptions in `utils/exceptions.py`

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_api.py -v
```

## 🐛 Reporting Bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

## 💡 Feature Requests

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md) and describe:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered
