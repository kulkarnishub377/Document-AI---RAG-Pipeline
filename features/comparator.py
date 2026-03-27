# features/comparator.py
# ─────────────────────────────────────────────────────────────────────────────
# Document Comparison Mode — compare two documents and find differences.
# Uses the LLM to analyze and compare content from different sources.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

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

    Args:
        doc_a_chunks: SearchResult objects from document A
        doc_b_chunks: SearchResult objects from document B
        doc_a_name: filename of document A
        doc_b_name: filename of document B
        question: optional specific comparison question

    Returns:
        dict with comparison analysis, differences, and similarities
    """
    from llm.prompt_chains import _get_llm

    llm = _get_llm()

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

    answer = llm.invoke(comparison_prompt)

    return {
        "doc_a": doc_a_name,
        "doc_b": doc_b_name,
        "analysis": answer.strip(),
        "doc_a_chunks": len(doc_a_chunks),
        "doc_b_chunks": len(doc_b_chunks),
        "question": question or "General comparison",
    }


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
