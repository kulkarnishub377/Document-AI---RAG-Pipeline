# Contributing to Document AI + RAG Pipeline

Thank you for your interest in contributing to this project!

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment.
4. Install dependencies: `pip install -r requirements.txt`
5. Install Ollama locally and run `ollama pull mistral`.

## Code Style

- Format your code with `black`.
- Run tests before submitting a PR using `pytest`.

## Architecture Note

The project is structured into clear, decoupled domains:
- `ingestion/` for parsing and loading files via OCR and PDF extractors
- `chunking/` for semantically splitting the extracted text and grouping tables
- `embedding/` for indexing to a FAISS vector store
- `retrieval/` for cross-encoder reranking
- `llm/` for LangChain summarization and field extraction
- `api/` for serving the FastAPI endpoints
- `frontend/` for the premium web-UI

Please adhere to this logic flow when making architectural changes to ensure cross-module compatibility.

## Submitting Pull Requests

1. Create a descriptive branch name.
2. Outline your changes and testing applied in your PR description.
3. Link relevant issues if applicable.
