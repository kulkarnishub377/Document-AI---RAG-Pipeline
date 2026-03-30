# features/comparator.py
# ─────────────────────────────────────────────────────────────────────────────
# Document Comparison Mode — compare two documents and find differences.
# v3.1 — Fixed config import, improved offline comparison
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import re
from typing import Any, Dict, List

from loguru import logger


def compare_documents(
    doc_a_chunks: List[Any],
    doc_b_chunks: List[Any],
    doc_a_name: str,
    doc_b_name: str,
    question: str = "",
) -> Dict[str, Any]:
    """
    Compare content from two documents using the LLM.
    Falls back to lexical comparison if LLM is unavailable.
    """
    from llm.prompt_chains import _get_llm, check_ollama_connection

    # Build context for each document
    context_a = "\n\n".join(
        f"[{doc_a_name}, page {c.page_num}]\n{c.text}" for c in doc_a_chunks[:5]
    )
    context_b = "\n\n".join(
        f"[{doc_b_name}, page {c.page_num}]\n{c.text}" for c in doc_b_chunks[:5]
    )

    comparison_prompt = f"""You are a document comparison analyst.
Compare the following two documents and provide a detailed analysis.

DOCUMENT A: {doc_a_name}
{context_a}

DOCUMENT B: {doc_b_name}
{context_b}

{f'SPECIFIC QUESTION: {question}' if question else ''}

Provide your analysis in this format:
## Summary
Brief overview of both documents.

## Key Similarities
- Bullet points of what is similar

## Key Differences
- Bullet points of what differs

## Unique to {doc_a_name}
- Items only in Document A

## Unique to {doc_b_name}
- Items only in Document B

ANALYSIS:"""

    logger.info(f"Comparing documents: {doc_a_name} vs {doc_b_name}")

    if check_ollama_connection():
        try:
            llm = _get_llm()
            response = llm.invoke(comparison_prompt)
            answer = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.warning(f"LLM comparison failed ({e}), using lexical fallback")
            answer = _lexical_comparison(doc_a_chunks, doc_b_chunks, doc_a_name, doc_b_name)
    else:
        answer = _lexical_comparison(doc_a_chunks, doc_b_chunks, doc_a_name, doc_b_name)

    return {
        "doc_a": doc_a_name,
        "doc_b": doc_b_name,
        "analysis": answer.strip(),
        "doc_a_chunks": len(doc_a_chunks),
        "doc_b_chunks": len(doc_b_chunks),
        "question": question or "General comparison",
    }


def _lexical_comparison(
    doc_a_chunks: List[Any],
    doc_b_chunks: List[Any],
    doc_a_name: str,
    doc_b_name: str,
) -> str:
    """Fallback comparison using lexical overlap analysis."""
    def normalize_tokens(text: str) -> set:
        return {t for t in re.findall(r"\w+", text.lower()) if len(t) > 2}

    text_a = "\n".join(c.text for c in doc_a_chunks[:10])
    text_b = "\n".join(c.text for c in doc_b_chunks[:10])
    tokens_a = normalize_tokens(text_a)
    tokens_b = normalize_tokens(text_b)

    common = sorted(tokens_a & tokens_b)
    only_a = sorted(tokens_a - tokens_b)
    only_b = sorted(tokens_b - tokens_a)

    overlap_pct = round(len(common) / max(len(tokens_a | tokens_b), 1) * 100)

    common_preview = ", ".join(common[:20]) if common else "No clear overlap found"
    only_a_preview = ", ".join(only_a[:20]) if only_a else "No strongly unique terms"
    only_b_preview = ", ".join(only_b[:20]) if only_b else "No strongly unique terms"

    snippet_a = (doc_a_chunks[0].text[:300] + "...") if doc_a_chunks else ""
    snippet_b = (doc_b_chunks[0].text[:300] + "...") if doc_b_chunks else ""

    return (
        "## Summary *(Demo Mode — Lexical Analysis)*\n"
        f"Compared **{doc_a_name}** ({len(doc_a_chunks)} passages) "
        f"and **{doc_b_name}** ({len(doc_b_chunks)} passages).\n"
        f"Vocabulary overlap: **{overlap_pct}%**\n\n"
        "## Key Similarities\n"
        f"- Shared terms ({len(common)} total): {common_preview}\n\n"
        "## Key Differences\n"
        f"- Terms unique to {doc_a_name} ({len(only_a)}): {only_a_preview}\n"
        f"- Terms unique to {doc_b_name} ({len(only_b)}): {only_b_preview}\n\n"
        f"## Unique to {doc_a_name}\n"
        f"- Representative snippet: {snippet_a}\n\n"
        f"## Unique to {doc_b_name}\n"
        f"- Representative snippet: {snippet_b}\n\n"
        "> 💡 *Connect Ollama for AI-powered document comparison*"
    )


def get_document_chunks(source_name: str, query: str = "") -> List[Any]:
    """Retrieve chunks for a specific document from the index."""
    from embedding.vector_store import similarity_search, get_index_stats

    stats = get_index_stats()
    if stats.get("total_vectors", 0) == 0:
        return []

    search_query = query or f"content of {source_name}"
    results = similarity_search(search_query, top_k=50)

    # Filter to only chunks from the specified source
    return [r for r in results if r.source == source_name]
