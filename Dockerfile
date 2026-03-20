# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — Document AI + RAG Pipeline
# ─────────────────────────────────────────────────────────────────────────────
# Build:   docker build -t doc-rag-pipeline .
# Run:     docker run -p 8000:8000 --env OLLAMA_BASE_URL=http://host.docker.internal:11434 doc-rag-pipeline
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System deps for PaddleOCR and PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache-friendly layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create data directories
RUN mkdir -p data/uploads data/index

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["python", "run.py"]
