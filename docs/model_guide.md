# Model Download & Setup Guide 🧠

To make Document AI + RAG Pipeline operate 100% offline, you need to download and configure open-source models for **text embedding**, **cross-encoder reranking**, and **language generation**.

## 1. LLM Generation (Mistral 7B via Ollama)

We use [Ollama](https://ollama.com/) because it packages models effectively and provides a high-performance, robust local API out of the box.

### Installation
1. Navigate to **[ollama.com/download](https://ollama.com/download)**.
2. Select your Operating System (Windows / macOS / Linux) and install the application.

### Downloading the Model
Once Ollama is installed, open a command prompt or terminal and run:

```bash
ollama pull mistral
ollama pull llava
```

**Note:** The `mistral` model is roughly **4.1 GB** and is used for text reasoning. The `llava` model is roughly **4.7 GB** and is used for Vision integration (analyzing images and charts). They require at least 8 GB of RAM to run effectively, and ideally an Apple Silicon Mac or a PC with a dedicated Nvidia GPU.

### Running the Server
Ollama usually runs as a background service automatically. However, if the frontend says "Ollama offline", you can start it manually:

```bash
ollama serve
```
By default, this server listens on `http://localhost:11434`. This matches the default `OLLAMA_BASE_URL` in our `.env.example`.

---

## 2. Embedding & Reranking Models

We rely on the incredibly efficient `sentence-transformers` library from HuggingFace to convert your documents into numerical vectors (for search) and to intelligently rerank results.

Unlike Ollama, **you do not need to download these manually**.

The first time you run `python pipeline.py` or `uvicorn api.app:app`, the system will automatically download them into your local HuggingFace cache directory (`~/.cache/huggingface/` on Linux/Mac or `C:\Users\{User}\.cache\huggingface\` on Windows).

### The Models Used
1. **Embedding**: `sentence-transformers/all-MiniLM-L6-v2`
   - Size: ~90 MB
   - Purpose: Converts document chunks into 384-dimensional vectors. Extremely fast and lightweight.
2. **Reranking**: `cross-encoder/ms-marco-MiniLM-L6-v2`
   - Size: ~80 MB
   - Purpose: Performs a highly accurate pairwise comparison between your direct question and the retrieved chunks to eliminate irrelevant results.

### Pre-downloading (Offline Environments)
If you intend to host the RAG pipeline on an isolated machine with completely zero internet access, you can run this script on an internet-connected computer to pre-cache the models:

```python
from sentence_transformers import SentenceTransformer, CrossEncoder

# Downloads to ~/.cache/huggingface/
SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
print("Models downloaded successfully!")
```

Then, copy the `~/.cache/huggingface/hub/` directory to your isolated machine.

---

## 3. OCR Models (PaddleOCR)

We use **PaddleOCR** to extract text from scanned PDFs and Images (`.png`, `.jpg`, `.tiff`). 

Similar to SentenceTransformers, PaddleOCR will automatically download its lightweight English inference models (Detection, Direction Classification, and Recognition) the very first time an image is ingested. 

- **Size**: ~20 MB total
- **Location**: `~/.paddleocr/`

If you change the `OCR_LANGUAGE` in your `.env` to `ch` (Chinese) or `fr` (French), it will download the respective language models dynamically.
