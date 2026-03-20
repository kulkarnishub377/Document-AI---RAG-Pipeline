# llm/prompt_chains.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 5 — LLM Prompt Chains  (via Ollama + LangChain LCEL)
#
# Four reusable chains:
#   1. answer_question   – general document Q&A with source citations
#   2. summarize         – concise summary of retrieved context
#   3. extract_fields    – structured key-value extraction (returns JSON)
#   4. table_qa          – question answering specifically over tables
#
# All chains run against a local Ollama server (no API key needed).
# Make sure Ollama is running:  ollama serve  (auto-starts on most OS)
#
# NOTE: Uses modern LCEL (LangChain Expression Language) pipe syntax
#       instead of deprecated LLMChain.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

# Forward ref for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from embedding.vector_store import SearchResult


# ── Singleton LLM ─────────────────────────────────────────────────────────────

_llm: Optional[OllamaLLM] = None


def _get_llm() -> OllamaLLM:
    """Connect to the Ollama LLM (must be running locally)."""
    global _llm
    if _llm is None:
        if not check_ollama_connection():
            raise ConnectionError(
                f"Ollama is not reachable at {OLLAMA_BASE_URL}. "
                "Start it with: ollama serve"
            )
        logger.info(f"Connecting to Ollama model: {OLLAMA_MODEL}  "
                    f"at {OLLAMA_BASE_URL}")
        _llm = OllamaLLM(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.1,          # low = factual, consistent
            num_predict=1024,         # max tokens in response
        )
        logger.info("LLM ready.")
    return _llm


def check_ollama_connection() -> bool:
    """Test if Ollama is responding. Returns True if healthy."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


# ── Helper: format retrieved chunks into a context block ─────────────────────

def _format_context(results: List[SearchResult]) -> str:
    """
    Convert search results into a numbered context string for the prompt.
    Each source is labelled so the LLM can cite it.
    """
    lines = []
    for r in results:
        header = f"[Source {r.rank}: {r.source}, page {r.page_num}]"
        lines.append(f"{header}\n{r.text}\n")
    return "\n".join(lines)


def _extract_sources(results: List[SearchResult]) -> List[Dict]:
    """Extract source metadata for the response payload."""
    return [
        {
            "source":     r.source,
            "page":       r.page_num,
            "excerpt":    r.text[:200] + ("…" if len(r.text) > 200 else ""),
            "score":      round(r.score, 3),
            "chunk_type": r.chunk_type,
        }
        for r in results
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Chain 1 — General Document Q&A (Streaming & Memory)
# ─────────────────────────────────────────────────────────────────────────────

_QA_SYSTEM_PROMPT = """You are a helpful document assistant.
Answer the question using ONLY the information provided in the context.
If the answer is not in the context, say "I could not find this information in the uploaded documents."
Always mention which source (file name and page) your answer comes from.
Be precise, concise, and factual."""


def _format_history(history: Optional[List[Dict[str, str]]] = None) -> str:
    if not history:
        return ""
    lines = ["CHAT HISTORY:"]
    # Only take last 5 turns to not overflow context
    for msg in history[-5:]:
        role = "USER" if msg.get("role") == "user" else "AI"
        lines.append(f"{role}: {msg.get('content')}")
    lines.append("")
    return "\n".join(lines)


async def stream_answer_question(
    query: str,
    results: List[SearchResult],
    history: Optional[List[Dict[str, str]]] = None
):
    """
    Asynchronous generator yielding SSE JSON chunks for real-time streaming.
    Includes chat history for conversational memory.
    """
    if not results:
        yield f"data: {json.dumps({'delta': 'No relevant documents found.', 'sources': []})}\n\n"
        yield "data: [DONE]\n\n"
        return

    llm = _get_llm()
    context = _format_context(results)
    history_str = _format_history(history)
    
    prompt_text = f"""{_QA_SYSTEM_PROMPT}

{history_str}
CONTEXT:
{context}

QUESTION:
{query}

ANSWER:"""

    logger.info(f"Running Streaming Q&A chain | query: '{query[:60]}' | chunks: {len(results)}")

    sources = _extract_sources(results)
    # Yield sources first
    yield f"data: {json.dumps({'sources': sources})}\n\n"

    try:
        async for chunk in llm.astream(prompt_text):
            # langchain_ollama yields strings directly or AIMessageChunk
            text = chunk if isinstance(chunk, str) else chunk.content
            yield f"data: {json.dumps({'delta': text})}\n\n"
    except Exception as e:
        logger.error(f"Streaming failed: {e}")
        yield f"data: {json.dumps({'delta': f' [Error streaming: {e}]'})}\n\n"

    yield "data: [DONE]\n\n"


def answer_question(query: str, results: List[SearchResult]) -> Dict[str, Any]:
    """
    Answer a question synchronously with full system prompt and source citations.
    """
    if not results:
        return {"answer": "No relevant documents found.", "sources": []}

    llm     = _get_llm()
    context = _format_context(results)
    
    prompt_text = f"""{_QA_SYSTEM_PROMPT}

CONTEXT:
{context}

QUESTION:
{query}

ANSWER:"""
    
    logger.info(f"Running synchronous Q&A chain | query: '{query[:60]}' | chunks: {len(results)}")
    t0 = time.perf_counter()
    answer = llm.invoke(prompt_text)
    logger.info(f"Q&A done in {time.perf_counter() - t0:.2f}s")
    
    return {
        "answer":  answer.strip(),
        "sources": _extract_sources(results),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chain 2 — Summarization  (LCEL pipe syntax)
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARY_TEMPLATE = PromptTemplate(
    input_variables=["context"],
    template="""You are a document summarization assistant.
Read the following document excerpts and produce a clear, concise summary.
Focus on the main topic, key facts, and important conclusions.
Use bullet points for key findings.

DOCUMENT EXCERPTS:
{context}

SUMMARY:""",
)


def summarize(results: List[SearchResult]) -> Dict[str, Any]:
    """
    Produce a bullet-point summary of the retrieved content.

    Returns:
        {
          "summary": str,
          "sources": [...]
        }
    """
    if not results:
        return {"summary": "No content to summarize.", "sources": []}

    llm     = _get_llm()
    context = _format_context(results)

    # Modern LCEL pipe syntax (replaces deprecated LLMChain)
    chain = _SUMMARY_TEMPLATE | llm | StrOutputParser()

    logger.info(f"Running summarization chain  |  chunks: {len(results)}")
    t0     = time.perf_counter()
    summary_text = chain.invoke({"context": context})
    logger.info(f"Summary generated in {time.perf_counter() - t0:.2f}s")

    return {
        "summary": summary_text.strip(),
        "sources": _extract_sources(results),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chain 3 — Structured Key-Field Extraction  (LCEL pipe syntax)
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACT_TEMPLATE = PromptTemplate(
    input_variables=["context", "fields"],
    template="""You are a document data extraction assistant.
Extract the following fields from the document context below.
Return ONLY a valid JSON object with the field names as keys.
If a field is not found, use null as the value.
Do NOT include any explanation or markdown — only raw JSON.

FIELDS TO EXTRACT:
{fields}

DOCUMENT CONTEXT:
{context}

JSON OUTPUT:""",
)


def extract_fields(results: List[SearchResult], fields: List[str]) -> Dict[str, Any]:
    """
    Extract specific fields from document context as structured JSON.

    Args:
        results: retrieved chunks
        fields:  list of field names e.g. ["invoice_number", "date", "total_amount"]

    Returns:
        {
          "fields": {"invoice_number": "INV-001", "date": "2024-01-15", ...},
          "sources": [...]
        }
    """
    if not results:
        return {"fields": {f: None for f in fields}, "sources": []}

    llm         = _get_llm()
    context     = _format_context(results)
    fields_str  = "\n".join(f"- {f}" for f in fields)

    # Modern LCEL pipe syntax
    chain = _EXTRACT_TEMPLATE | llm | StrOutputParser()

    logger.info(f"Running extraction chain  |  fields: {fields}  |  "
                f"chunks: {len(results)}")

    t0       = time.perf_counter()
    raw_text = chain.invoke({"context": context, "fields": fields_str})
    raw_text = raw_text.strip()
    logger.info(f"Extraction done in {time.perf_counter() - t0:.2f}s")

    # Strip markdown code fences if the model added them
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$",          "", raw_text)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(f"JSON parse failed, returning raw text.  "
                       f"Raw output: {raw_text[:200]}")
        parsed = {"raw_output": raw_text}

    return {
        "fields":  parsed,
        "sources": _extract_sources(results),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chain 4 — Table Q&A  (LCEL pipe syntax)
# ─────────────────────────────────────────────────────────────────────────────

_TABLE_QA_TEMPLATE = PromptTemplate(
    input_variables=["table", "question"],
    template="""You are a table analysis assistant.
The following is a table extracted from a document (in Markdown format).
Answer the question using ONLY the data in this table.
If the answer requires a calculation (sum, average, etc.), show your working.

TABLE:
{table}

QUESTION:
{question}

ANSWER:""",
)


def table_qa(query: str, results: List[SearchResult]) -> Dict[str, Any]:
    """
    Answer questions specifically about tables found in the documents.
    Filters results to only table-type chunks automatically.

    Returns:
        {
          "answer":  str,
          "sources": [...]
        }
    """
    # Filter to table chunks only
    table_results = [r for r in results if r.chunk_type == "table"]

    if not table_results:
        logger.info("No table chunks in results — falling back to regular Q&A")
        return answer_question(query, results)

    llm   = _get_llm()
    best  = table_results[0]

    # Modern LCEL pipe syntax
    chain = _TABLE_QA_TEMPLATE | llm | StrOutputParser()

    logger.info(f"Running table Q&A  |  query: '{query[:60]}'")
    t0          = time.perf_counter()
    answer_text = chain.invoke({"table": best.text, "question": query})
    logger.info(f"Table Q&A done in {time.perf_counter() - t0:.2f}s")

    return {
        "answer":  answer_text.strip(),
        "sources": _extract_sources(table_results),
    }
