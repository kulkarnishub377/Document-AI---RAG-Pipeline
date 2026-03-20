# System Architecture 🏛️

Document AI + RAG Pipeline is designed around a clean, modular architecture. This separation of concerns ensures that the system is testable, maintainable, and easily extensible.

## Module Breakdown

1. **`ingestion/` (Document Loaders)**
   - Responsible for taking physical files (`.pdf`, `.docx`, `.png`, `.txt`) or Web URLs and converting them into normalized `PageData` objects.
   - It intelligently delegates parsing: `PyMuPDF` for digital PDFs, `beautifulsoup4` for web scraping, and `python-docx` for Word documents.
   - For images, it utilizes Ollama's `llava` Vision LLM to automatically describe visual diagrams and charts, seamlessly falling back to `PaddleOCR` if unavailable.
   - Distinctly, it attempts to extract tables intact before they hit the text stream.

2. **`chunking/` (Semantic Chunker)**
   - Takes `PageData` and slices text into smaller `Chunk` objects (default 512 characters, 64 overlap). 
   - Uses a greedy packing algorithmic approach that respects sentence boundaries (to avoid cutting thoughts in half).
   - Secures tabular data: Lists of row-arrays from the ingestion phase are converted to Markdown tables and treated as atomic, indivisible chunks.
   - Uses SHA-256 hashing to deduplicate chunks, saving vector database space.

3. **`embedding/` (Vector Store & Hybrid Search)**
   - Encodes text into 384D dense vectors using `sentence-transformers/all-MiniLM-L6-v2`.
   - Stores the vectors locally using an in-memory `FAISS` Flat Inner Product (cosine similarity) index.
   - Automatically maintains a companion **BM25 keyword index** (`rank_bm25`) for supreme recall on exact terminology.
   - Serializes the vectors to disk alongside a `metadata.json` lookup file.
   - Implements strict chunk-lifecycle management, allowing surgical deletion of individual documents without rebuilding the FAISS or BM25 index.

4. **`retrieval/` (Cross-Encoder Reranker)**
   - Casts a wide search net by pooling the top FAISS candidates and top BM25 candidates into a unified candidate pool.
   - This module loops those pooled candidates through an advanced `cross-encoder` model capable of bidirectional context checking.
   - Sorts the final array down to the 5 most profoundly relevant contextual chunks.

5. **`llm/` (Prompt Chains)**
   - Houses the LangChain orchestration logic.
   - Connects to the local `Ollama` daemon.
   - Maintains continuous **Conversational Memory** by actively parsing and injecting thread history backwards into the system prompt context.
   - Implements specific PromptTemplates: QA (strict fact-checking base), Summary, Table Analysis, and JSON Key-Value Extraction.

6. **`api/` (FastAPI Server)**
   - Exposes REST endpoints (`/query`, `/query-stream`, `/ingest`, `/ingest/url`, `/extract`, `/document/{filename}`).
   - Specifically streams incremental Server-Sent Event (SSE) packets so users don't wait for massive block generation.
   - Serves the frontend static assets and protects the pipeline with request validation via Pydantic models.

7. **`frontend/` (Static UI)**
   - A vanilla HTML/JS/CSS web dashboard built around smooth user experience.
   - Consumes SSE data via the `ReadableStream` JS interface for real-time ChatGPT-like typing effects.
   - Full history tracking (persisted to `localStorage`) and one-click individual document deletion directly from the indexed list sidebar.
