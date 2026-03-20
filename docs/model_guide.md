# Model Download & Setup Guide 🧠

Document AI + RAG Pipeline v2.0 runs 100% offline. This guide covers everything you need to download and configure.

---

## 1. LLM Generation (Mistral 7B via Ollama)

We use [Ollama](https://ollama.com/) for local LLM inference — it packages models efficiently and provides a high-performance REST API.

### Installation
1. Navigate to **[ollama.com/download](https://ollama.com/download)**
2. Select your OS (Windows / macOS / Linux) and install

### Downloading Models

```bash
# Required — primary text reasoning model
ollama pull mistral           # ~4.1 GB

# Optional — Vision LLM for image/chart analysis
ollama pull llava             # ~4.7 GB
```

> **Hardware requirements**: 8 GB RAM minimum. Ideally an Apple Silicon Mac or a PC with a dedicated NVIDIA GPU for best performance.

### Running the Server

Ollama usually runs as a background service automatically. If the frontend shows "Ollama offline":

```bash
ollama serve
```

Default: `http://localhost:11434` (matches `OLLAMA_BASE_URL` in `.env.example`).

### Docker Mode

When using Docker Compose, Ollama runs as a separate container:

```bash
docker-compose up -d
docker exec rag-ollama ollama pull mistral
docker exec rag-ollama ollama pull llava    # optional
```

---

## 2. Embedding & Reranking Models

These models download **automatically** on first run — no manual setup needed.

### Models Used

| Model | Size | Dimensions | Purpose |
|-------|------|------------|---------|
| `sentence-transformers/all-MiniLM-L6-v2` | ~90 MB | 384 | Converts document chunks into dense vectors for semantic search |
| `cross-encoder/ms-marco-MiniLM-L6-v2` | ~80 MB | — | Pairwise comparison between query and candidates for precision reranking |

### Multilingual Mode

When `MULTILINGUAL_MODE=true` in `.env`, a different embedding model is used:

| Model | Size | Dimensions | Purpose |
|-------|------|------------|---------|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | ~470 MB | 384 | Supports 50+ languages including Hindi, Chinese, Japanese, Arabic, etc. |

Enable it in `.env`:
```
MULTILINGUAL_MODE=true
MULTILINGUAL_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

### Cache Locations

| OS | Location |
|----|----------|
| Linux/Mac | `~/.cache/huggingface/hub/` |
| Windows | `C:\Users\{User}\.cache\huggingface\hub\` |

### Pre-downloading (Offline Environments)

For air-gapped machines, run this on an internet-connected computer:

```python
from sentence_transformers import SentenceTransformer, CrossEncoder

# Standard models
SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

# Multilingual model (optional)
SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

print("✓ All models downloaded!")
```

Then copy `~/.cache/huggingface/hub/` to the target machine.

---

## 3. OCR Models (PaddleOCR)

PaddleOCR downloads its inference models **automatically** on first image ingestion.

| Component | Size |
|-----------|------|
| Detection model | ~5 MB |
| Direction classifier | ~5 MB |
| Recognition model | ~10 MB |
| **Total** | **~20 MB** |

Cache location: `~/.paddleocr/`

### Multi-Language OCR

When `MULTILINGUAL_MODE=true`, the system auto-detects document language and switches OCR engines:

| Language | OCR Code | Auto-Download |
|----------|----------|---------------|
| English | `en` | ✓ |
| Hindi | `hi` | ✓ |
| Chinese | `ch` | ✓ |
| Japanese | `japan` | ✓ |
| Korean | `korean` | ✓ |
| French | `fr` | ✓ |
| German | `german` | ✓ |
| Arabic | `ar` | ✓ |
| Russian | `ru` | ✓ |
| Spanish | `es` | ✓ |

The language is detected using `langdetect` and the correct OCR engine is loaded dynamically.

You can also set a fixed language: `OCR_LANGUAGE=ch` in `.env`.

---

## 4. GPU Acceleration (Optional)

### FAISS GPU

For NVIDIA GPU acceleration of vector search:

```bash
pip install faiss-gpu
# or
pip install -e ".[gpu]"
```

Set `ENABLE_GPU=auto` in `.env` (default) to auto-detect, or `ENABLE_GPU=true` to force GPU.

### Embedding GPU

SentenceTransformers automatically uses CUDA if PyTorch detects a GPU. No extra config needed.

---

## Quick Reference

| Component | Model | Size | Auto-Download |
|-----------|-------|------|---------------|
| LLM | Mistral 7B | 4.1 GB | `ollama pull mistral` |
| Vision LLM | LLaVA | 4.7 GB | `ollama pull llava` |
| Embeddings | all-MiniLM-L6-v2 | 90 MB | ✓ |
| Multilingual Embeddings | paraphrase-multilingual | 470 MB | ✓ |
| Reranker | ms-marco-MiniLM-L6-v2 | 80 MB | ✓ |
| OCR (English) | PaddleOCR PP-OCRv4 | 20 MB | ✓ |
| **Total (minimal)** | | **~4.3 GB** | |
| **Total (everything)** | | **~9.5 GB** | |
