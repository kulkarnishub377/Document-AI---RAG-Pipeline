# utils/exceptions.py
# ─────────────────────────────────────────────────────────────────────────────
# Custom exception hierarchy for clean error handling throughout the pipeline.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    def __init__(self, message: str = "An error occurred in the pipeline."):
        self.message = message
        super().__init__(self.message)


class DocumentNotFoundError(PipelineError):
    """Raised when a requested document is not found."""
    def __init__(self, source: str):
        super().__init__(f"Document not found: '{source}'")
        self.source = source


class UnsupportedFileTypeError(PipelineError):
    """Raised when user uploads an unsupported file format."""
    def __init__(self, suffix: str, allowed: set):
        super().__init__(
            f"Unsupported file type '{suffix}'. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
        self.suffix = suffix


class FileTooLargeError(PipelineError):
    """Raised when uploaded file exceeds size limit."""
    def __init__(self, size_mb: float, max_mb: int):
        super().__init__(f"File too large: {size_mb:.1f} MB (max: {max_mb} MB)")
        self.size_mb = size_mb


class OllamaNotReachableError(PipelineError):
    """Raised when Ollama LLM server is not reachable."""
    def __init__(self, url: str):
        super().__init__(
            f"Ollama LLM server is not reachable at {url}. "
            "Start it with: ollama serve"
        )
        self.url = url


class IndexNotFoundError(PipelineError):
    """Raised when FAISS index is not found on disk."""
    def __init__(self):
        super().__init__(
            "No FAISS index found. Ingest at least one document first."
        )


class RateLimitExceededError(PipelineError):
    """Raised when API rate limit is exceeded."""
    def __init__(self, limit: int, window: int):
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window} seconds."
        )
        self.limit = limit
        self.window = window


class IngestionError(PipelineError):
    """Raised when document ingestion fails."""
    def __init__(self, filename: str, reason: str):
        super().__init__(f"Ingestion failed for '{filename}': {reason}")
        self.filename = filename
