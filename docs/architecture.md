# System Architecture 🏛️

Document AI + RAG Pipeline is designed around a clean, modular architecture. This separation of concerns ensures that the system is testable, maintainable, and easily extensible.

## Module Breakdown

1. **`ingestion/` (Document Loaders)**
   - Responsible for taking physical files (`.pdf`, `.docx`, `.png`, `.txt`) and converting them into normalized `PageData` objects.
   - It intelligently delegates parsing: `PyMuPDF` for digital PDFs, `PaddleOCR` for images/scanned PDFs, and `python-docx` for Word documents.
   - Distinctly, it attempts to extract tables intact before they hit the text stream.

2. **`chunking/` (Semantic Chunker)**
   - Takes `PageData` and slices text into smaller `Chunk` objects (default 512 characters, 64 overlap). 
   - Uses a greedy packing algorithmic approach that respects sentence boundaries (to avoid cutting thoughts in half).
   - Secures tabular data: Lists of row-arrays from the ingestion phase are converted to Markdown tables and treated as atomic, indivisible chunks.
   - Uses SHA-256 hashing to deduplicate chunks, saving vector database space.

3. **`embedding/` (Vector Store)**
   - Encodes text into 384D dense vectors using `sentence-transformers/all-MiniLM-L6-v2`.
   - Stores the vectors locally using an in-memory `FAISS` Flat Inner Product (cosine similarity) index.
   - Serializes the vectors to disk alongside a `metadata.json` lookup file.

4. **`retrieval/` (Reranker)**
   - Initial FAISS searches cast a wide net (Top 20 candidates).
   - This module loops those 20 candidates through an advanced `cross-encoder` model capable of bidirectional context checking.
   - Sorts the final array down to the 5 most profoundly relevant contextual chunks.

5. **`llm/` (Prompt Chains)**
   - Houses the LangChain orchestration logic.
   - Connects to the local `Ollama` daemon.
   - Implements specific PromptTemplates: QA (strict fact-checking base), Summary, Table Analysis, and JSON Key-Value Extraction.

6. **`api/` (FastAPI Server)**
   - Exposes REST endpoints (`/query`, `/summarize`, `/ingest`, `/extract`).
   - Serves the frontend static assets.
   - Protects the pipeline with request validation via Pydantic models.

7. **`frontend/` (Static UI)**
   - A vanilla HTML/JS/CSS web dashboard built around smooth user experience.
   - Real-time indexing progress and robust error handling.
