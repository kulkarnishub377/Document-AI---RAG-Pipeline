# Document AI + RAG Pipeline

End-to-end pipeline to extract, index, and query documents using OCR, FAISS,
sentence-transformers, and a local Mistral 7B LLM — all 100% free.

---

## System Requirements (8 GB RAM spec)

- Python 3.10 or 3.11
- 8 GB RAM
- ~6 GB free disk space (for models + index)
- Windows 10 / Ubuntu 20.04+ / macOS 12+

---

## Step 1 — Install Ollama (local LLM runner)

Download from https://ollama.com and install it.
Then pull the Mistral model (one-time, ~4 GB download):

```bash
ollama pull mistral
```

Verify it works:
```bash
ollama run mistral "Hello, are you working?"
```

---

## Step 2 — Clone and set up the Python environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

The first run will also auto-download:
- PaddleOCR weights (~45 MB) on first OCR call
- all-MiniLM-L6-v2 embedding model (~90 MB) on first embed call
- ms-marco reranker (~80 MB) on first rerank call

These are cached in `~/.cache/` and only download once.

---

## Step 3 — Run the pipeline

### Option A — Command line (quickest test)

```bash
# Ingest a document and enter interactive Q&A
python pipeline.py data/uploads/your_document.pdf
```

### Option B — REST API

```bash
# Make sure Ollama is running first
ollama serve   # (it may start automatically — check with: ollama list)

# Start the API
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000/docs in your browser — interactive Swagger UI.

---

## API Usage Examples

### Upload a document
```bash
curl -X POST http://localhost:8000/ingest \
     -F "file=@invoice.pdf"
```

### Ask a question
```bash
curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the total amount on the invoice?"}'
```

### Extract structured fields
```bash
curl -X POST http://localhost:8000/extract \
     -H "Content-Type: application/json" \
     -d '{"fields": ["invoice_number", "vendor_name", "due_date", "total_amount"]}'
```

### Summarize
```bash
curl -X POST http://localhost:8000/summarize \
     -H "Content-Type: application/json" \
     -d '{"topic": "payment terms and conditions"}'
```

### Table question
```bash
curl -X POST http://localhost:8000/table-query \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the highest value in the pricing table?"}'
```

### Check index status
```bash
curl http://localhost:8000/status
```

---

## Python API Usage

```python
import pipeline

# Ingest one document
pipeline.ingest("invoice.pdf")

# Ingest all documents in a folder
pipeline.ingest_folder("data/uploads/")

# Q&A
result = pipeline.query("What is the vendor name?")
print(result["answer"])
print(result["sources"])

# Extract fields as JSON
result = pipeline.extract(["invoice_number", "date", "total"])
print(result["fields"])
# → {"invoice_number": "INV-001", "date": "2024-01-15", "total": "₹45,000"}

# Summarize
result = pipeline.get_summary("key terms")
print(result["summary"])

# Table Q&A
result = pipeline.query_table("What is the sum of the amount column?")
print(result["answer"])
```

---

## Project Structure

```
doc_rag_pipeline/
│
├── config.py                   ← all settings (models, paths, chunk size)
├── pipeline.py                 ← main orchestrator — start here
├── requirements.txt
│
├── ingestion/
│   └── document_loader.py      ← Stage 1: OCR + PDF + DOCX parsing
│
├── chunking/
│   └── semantic_chunker.py     ← Stage 2: sentence-aware chunking
│
├── embedding/
│   └── vector_store.py         ← Stage 3: embed + FAISS index
│
├── retrieval/
│   └── reranker.py             ← Stage 4: cross-encoder reranking
│
├── llm/
│   └── prompt_chains.py        ← Stage 5: LangChain + Ollama chains
│
├── api/
│   └── app.py                  ← FastAPI REST endpoints
│
└── data/
    ├── uploads/                ← put your documents here
    └── index/                  ← FAISS index saved here automatically
```

---

## Switching Models (if low on RAM)

Edit `config.py`:

```python
# For 4 GB RAM — use smaller LLM
OLLAMA_MODEL = "llama3.2:3b"    # instead of "mistral"

# For faster embedding (slightly lower quality)
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # already the lightest

# For larger context window
CHUNK_SIZE = 256   # reduce if running out of memory
```

---

## Supported File Types

| Format | Parser used | Notes |
|--------|-------------|-------|
| PDF (native) | pdfplumber | Text-selectable PDFs from Word/Excel |
| PDF (scanned) | PaddleOCR | Auto-detected, slower but accurate |
| PNG / JPG / TIFF | PaddleOCR | Single-page images |
| DOCX | python-docx | Word documents |
