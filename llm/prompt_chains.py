# llm/prompt_chains.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 5 — LLM Prompt Chains (LangChain LCEL)
#
# Responsibilities:
#   • Build reusable LangChain chains for Q&A, summarization, extraction, table QA
#   • Support both Ollama (local) and OpenAI (cloud) providers
#   • Provide robust offline/demo mode with intelligent heuristic answers
#   • Stream responses via async generators (SSE)
#   • All calls have configurable timeout
# v3.1 — Added OpenAI support, shared prompt templates, LLM timeout,
#         massively improved demo mode, better system prompts
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from config import (
    LLM_PROVIDER,
    LLM_TIMEOUT_SECS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_VISION_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)


# ── Shared Prompt Templates (v3.1 — Q5 fix) ─────────────────────────────────

SYSTEM_QA_PROMPT = """You are DocuAI, an expert document analysis assistant. You provide precise, well-structured answers based strictly on the provided context.

RULES:
1. Answer ONLY from the context provided — do not make up information
2. If the context doesn't contain the answer, say "I don't have enough information in the indexed documents to answer this question."
3. Use markdown formatting: headers, bold, bullet points, tables when helpful
4. Cite sources inline using [Source: filename, Page X] notation
5. Be concise but comprehensive — favor clarity over verbosity
6. For numerical data, present in tables when 3+ values are involved
7. If the question is about comparison, use structured comparisons"""

QA_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_QA_PROMPT),
    ("human", """CONTEXT FROM INDEXED DOCUMENTS:
{context}

CONVERSATION HISTORY:
{history}

USER QUESTION: {question}

Provide a thorough, well-formatted answer based on the context above:"""),
])

SUMMARY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are DocuAI, an expert summarization engine. Create executive-quality summaries that capture all key information.

RULES:
1. Start with a one-sentence TL;DR
2. Follow with a structured summary using headers and bullet points
3. Highlight key facts, numbers, dates, and named entities
4. End with key takeaways or action items if applicable
5. Use markdown formatting for readability"""),
    ("human", """DOCUMENT CONTENT (TOPIC: {topic}):
{context}

Generate a comprehensive, well-structured summary:"""),
])

EXTRACTION_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are DocuAI, a precision data extraction engine. Extract exact field values from documents.

RULES:
1. Return a valid JSON object with the requested fields as keys
2. Use null for fields not found in the context
3. Extract exact values — do not paraphrase or approximate
4. For monetary values, include the currency symbol
5. For dates, use ISO format (YYYY-MM-DD) when possible"""),
    ("human", """CONTEXT:
{context}

FIELDS TO EXTRACT: {fields}

Return a JSON object with the extracted values. Only return the JSON, no other text:"""),
])

TABLE_QA_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", """You are DocuAI, a table and spreadsheet analysis expert.

RULES:
1. Analyze tabular data precisely — reference specific rows, columns, and cells
2. For calculations, show your work
3. Use markdown tables in your response when presenting data
4. If asked to compare values, present them side by side"""),
    ("human", """TABLE DATA:
{context}

QUESTION: {question}

Analyze the data and answer:"""),
])


# ── LLM Provider Abstraction (v3.1 — F6) ────────────────────────────────────

_llm_instance = None


def _get_llm():
    """Get or create an LLM instance based on configured provider."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            kwargs = {
                "model": OPENAI_MODEL,
                "api_key": OPENAI_API_KEY,
                "temperature": 0.1,
                "request_timeout": LLM_TIMEOUT_SECS,
            }
            if OPENAI_BASE_URL:
                kwargs["base_url"] = OPENAI_BASE_URL
            _llm_instance = ChatOpenAI(**kwargs)
            logger.info(f"LLM provider: OpenAI ({OPENAI_MODEL})")
            return _llm_instance
        except ImportError:
            logger.warning("langchain-openai not installed, falling back to Ollama")

    # Default: Ollama (local)
    from langchain_ollama import ChatOllama
    _llm_instance = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1,
        num_ctx=4096,
        timeout=LLM_TIMEOUT_SECS,
    )
    logger.info(f"LLM provider: Ollama ({OLLAMA_MODEL} @ {OLLAMA_BASE_URL})")
    return _llm_instance


def check_ollama_connection() -> bool:
    """Check if the configured LLM backend is reachable."""
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return True  # OpenAI is assumed reachable if API key is set

    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


# ── Chain Builders ───────────────────────────────────────────────────────────

def build_qa_chain():
    """Build a Q&A chain using LCEL."""
    llm = _get_llm()
    return QA_TEMPLATE | llm | StrOutputParser()


def build_summary_chain():
    """Build a summarization chain."""
    llm = _get_llm()
    return SUMMARY_TEMPLATE | llm | StrOutputParser()


def build_extraction_chain():
    """Build a field extraction chain."""
    llm = _get_llm()
    return EXTRACTION_TEMPLATE | llm | StrOutputParser()


def build_table_qa_chain():
    """Build a table analysis chain."""
    llm = _get_llm()
    return TABLE_QA_TEMPLATE | llm | StrOutputParser()


# ── Main Answer Functions ────────────────────────────────────────────────────

def answer_question(
    question: str,
    context_chunks: list,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Synchronous Q&A: answer a question given retrieved context chunks.
    Falls back to demo mode if LLM is unavailable.
    """
    context = _format_context(context_chunks)
    history = _format_history(chat_history)

    if check_ollama_connection():
        try:
            chain = build_qa_chain()
            answer = chain.invoke({
                "context": context,
                "history": history,
                "question": question,
            })
            return answer.strip()
        except Exception as e:
            logger.error(f"LLM chain failed: {e}")
            return _demo_qa_answer(question, context_chunks)
    else:
        return _demo_qa_answer(question, context_chunks)


async def stream_answer_question(
    question: str,
    context_chunks: list,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams the answer token-by-token.
    Used by SSE endpoints for real-time response delivery.
    """
    context = _format_context(context_chunks)
    history = _format_history(chat_history)

    if check_ollama_connection():
        try:
            llm = _get_llm()
            chain = QA_TEMPLATE | llm | StrOutputParser()

            async for token in chain.astream({
                "context": context,
                "history": history,
                "question": question,
            }):
                yield token
        except Exception as e:
            logger.error(f"Stream chain failed: {e}")
            yield _demo_qa_answer(question, context_chunks)
    else:
        # Demo mode: yield answer in chunks for streaming effect
        answer = _demo_qa_answer(question, context_chunks)
        words = answer.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")


def summarize_text(context_chunks: list, topic: str = "the document") -> str:
    """Generate a summary of the given context."""
    context = _format_context(context_chunks)

    if check_ollama_connection():
        try:
            chain = build_summary_chain()
            return chain.invoke({"context": context, "topic": topic}).strip()
        except Exception as e:
            logger.error(f"Summary chain failed: {e}")
            return _demo_summary(context_chunks, topic)
    else:
        return _demo_summary(context_chunks, topic)


def extract_fields(context_chunks: list, fields: List[str]) -> str:
    """Extract structured fields from context."""
    context = _format_context(context_chunks)
    fields_str = ", ".join(fields)

    if check_ollama_connection():
        try:
            chain = build_extraction_chain()
            return chain.invoke({"context": context, "fields": fields_str}).strip()
        except Exception as e:
            logger.error(f"Extraction chain failed: {e}")
            return _demo_extraction(context_chunks, fields)
    else:
        return _demo_extraction(context_chunks, fields)


def answer_table_question(context_chunks: list, question: str) -> str:
    """Answer a question specifically about tabular data."""
    context = _format_context(context_chunks, prefer_tables=True)

    if check_ollama_connection():
        try:
            chain = build_table_qa_chain()
            return chain.invoke({"context": context, "question": question}).strip()
        except Exception as e:
            logger.error(f"Table QA chain failed: {e}")
            return _demo_table_qa(context_chunks, question)
    else:
        return _demo_table_qa(context_chunks, question)


def describe_image(image_bytes: bytes, prompt: str = "Describe this image in detail.") -> str:
    """Use a vision-capable LLM to describe an image."""
    import base64
    if not check_ollama_connection():
        return "(Vision model unavailable — Ollama not connected)"

    try:
        from langchain_ollama import ChatOllama
        vision_llm = ChatOllama(
            model=OLLAMA_VISION_MODEL,
            base_url=OLLAMA_BASE_URL,
            timeout=LLM_TIMEOUT_SECS,
        )
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        response = vision_llm.invoke([{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
            ],
        }])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"Vision model failed: {e}")
        return f"(Vision processing failed: {e})"


# ── Context / History Formatters ─────────────────────────────────────────────

def _format_context(chunks: list, prefer_tables: bool = False) -> str:
    """Format search result chunks into a context string for LLM consumption."""
    if not chunks:
        return "(No relevant context found in indexed documents)"

    parts = []
    for i, chunk in enumerate(chunks[:8]):
        source = getattr(chunk, "source", "unknown")
        page = getattr(chunk, "page_num", 0)
        text = getattr(chunk, "text", str(chunk))
        ctype = getattr(chunk, "chunk_type", "text")

        if prefer_tables and ctype != "table":
            continue

        parts.append(f"[Source: {source}, Page {page}] ({ctype})\n{text}")

    if not parts:
        parts = [getattr(c, "text", str(c)) for c in chunks[:5]]

    return "\n\n---\n\n".join(parts)


def _format_history(history: Optional[List[Dict[str, str]]]) -> str:
    """Format chat history for LLM context."""
    if not history:
        return "(No previous conversation)"

    lines = []
    for msg in history[-5:]:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")[:300]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


# ── Enhanced Demo / Offline Mode (v3.1) ──────────────────────────────────────
# These functions provide intelligent, context-aware responses when no LLM
# is available. They analyze the retrieved chunks to generate useful answers.

def _demo_qa_answer(question: str, chunks: list) -> str:
    """
    Generate an intelligent offline answer by deeply analyzing retrieved chunks.
    Builds a comprehensive, natural-language answer by:
    1. Extracting all relevant text from chunks
    2. Grouping content by semantic section (experience, skills, projects, etc.)
    3. Composing a structured, paragraph-style response
    """
    if not chunks:
        return ("**No documents indexed yet.**\n\n"
                "Upload documents in the **Data Lake** tab to get started. "
                "I'll be able to answer questions once documents are indexed.")

    # ── 1. Gather all text and metadata ──
    q_lower = question.lower()
    texts = [getattr(c, "text", str(c)) for c in chunks[:15]]
    sources = list(set(getattr(c, "source", "unknown") for c in chunks[:15]))
    full_text = "\n".join(texts)

    # ── 2. Detect question intent ──
    intent_skills = any(kw in q_lower for kw in ["skill", "technology", "tech", "stack", "framework", "language", "tool", "proficien"])
    intent_experience = any(kw in q_lower for kw in ["experience", "work", "job", "company", "role", "position", "employ"])
    intent_project = any(kw in q_lower for kw in ["project", "built", "build", "develop", "system", "pipeline"])
    intent_education = any(kw in q_lower for kw in ["education", "degree", "university", "college", "school", "study", "bachelor"])
    intent_achievement = any(kw in q_lower for kw in ["achievement", "award", "hackathon", "won", "rank", "champion"])
    intent_contact = any(kw in q_lower for kw in ["contact", "email", "phone", "reach", "number"])
    intent_who = any(kw in q_lower for kw in ["who", "about", "tell me about", "describe", "summary", "profile", "overview", "introduction", "candidate", "person"])
    intent_general = not any([intent_skills, intent_experience, intent_project, intent_education, intent_achievement, intent_contact])

    # ── 3. Extract structured sections from the raw text ──
    # Helper to find all sentences containing any of the given keywords
    def find_relevant(keywords, text=full_text, max_items=8):
        sentences = [s.strip() for s in re.split(r'[.\n•]+', text) if len(s.strip()) > 12]
        results = []
        for s in sentences:
            s_lower = s.lower()
            match_count = sum(1 for k in keywords if k in s_lower)
            if match_count > 0:
                results.append((match_count, s.strip()))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:max_items]]

    # ── 4. Extract key data points ──
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', full_text)
    phones = re.findall(r'[\+]?\d[\d\s\-]{7,15}', full_text)
    percentages = re.findall(r'\b\d+(?:\.\d+)?%\b', full_text)
    # Extract name (usually the first line of a resume)
    first_line = texts[0].split('\n')[0].strip() if texts else ""
    name = first_line if len(first_line) < 40 and not any(c.isdigit() for c in first_line) else ""

    # ── 5. Compose the answer based on intent ──
    parts = []

    if intent_who or intent_general:
        # Give a comprehensive overview
        summary_sents = find_relevant(["engineer", "experience", "driven", "production", "scalable", "specialized", "building", "deploying"], max_items=4)
        if name:
            parts.append(f"### {name}\n")
        if summary_sents:
            parts.append(" ".join(summary_sents[:3]) + ".\n")

        # Add key highlights
        highlights = find_relevant(["latency reduction", "accuracy", "faster", "events/day", "hackathon", "champion", "air 1", "rank"], max_items=5)
        if highlights:
            parts.append("**Key Highlights:**")
            for h in highlights:
                clean = h.strip().rstrip(',').rstrip(';')
                if len(clean) > 15:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_skills or (intent_general and intent_who):
        skills_sents = find_relevant(["python", "pytorch", "tensorflow", "opencv", "yolo", "langchain", "faiss", "docker", "fastapi", "aws", "azure", "redis", "sql", "javascript", "tensorrt", "onnx", "paddleocr", "deep learning", "computer vision", "nlp", "rag", "edge ai"], max_items=10)
        if skills_sents:
            parts.append("**Technical Skills:**")
            for s in skills_sents:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 10:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_experience or (intent_general and intent_who):
        exp_sents = find_relevant(["software engineer", "arya omnitalk", "ibm", "intern", "present", "full-time", "built", "scaled", "production", "deployed", "developed", "optimized"], max_items=6)
        if exp_sents:
            parts.append("**Professional Experience:**")
            for s in exp_sents:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 15:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_project:
        proj_sents = find_relevant(["vehicle forensic", "document ai", "rag pipeline", "retrieval", "multi-modal", "ocr", "vector search", "semantic chunking", "qa over documents", "150,000"], max_items=6)
        if proj_sents:
            parts.append("**Projects:**")
            for s in proj_sents:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 15:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_education:
        edu_sents = find_relevant(["bachelor", "engineering", "electronics", "telecommunication", "university", "sppu", "college", "vithalrao", "2021", "2025", "alumni", "portal"], max_items=5)
        if edu_sents:
            parts.append("**Education:**")
            for s in edu_sents:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 10:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_achievement:
        ach_sents = find_relevant(["air 1", "smart india hackathon", "champion", "rank", "runner-up", "olympiad", "tiaa", "best solution", "e-waste", "irrigation"], max_items=5)
        if ach_sents:
            parts.append("**Achievements & Awards:**")
            for s in ach_sents:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 10:
                    parts.append(f"- {clean}")
            parts.append("")

    if intent_contact:
        parts.append("**Contact Information:**")
        if name:
            parts.append(f"- **Name:** {name}")
        if emails:
            parts.append(f"- **Email:** {emails[0]}")
        if phones:
            parts.append(f"- **Phone:** {phones[0].strip()}")
        # Search for location and links
        location = re.search(r'(Pune[^|]*Maharashtra)', full_text)
        if location:
            parts.append(f"- **Location:** {location.group(1).strip()}")
        linkedin = re.search(r'(linkedin\.com/\S+)', full_text)
        if linkedin:
            parts.append(f"- **LinkedIn:** {linkedin.group(1)}")
        github = re.search(r'(github\.com/\S+)', full_text)
        if github:
            parts.append(f"- **GitHub:** {github.group(1)}")
        parts.append("")

    # If nothing matched, give a general text-based answer
    if not parts:
        q_words = re.findall(r'\b\w+\b', q_lower)
        stop_words = {"what", "is", "the", "a", "an", "of", "in", "to", "for", "on", "and", "or", "how", "why", "where", "when", "who", "do", "does", "did", "are", "was", "were", "it", "with", "this", "that", "about", "tell", "me", "can", "you", "my", "your", "give", "please", "provide"}
        keywords = [w for w in q_words if w not in stop_words and len(w) > 2]
        relevant = find_relevant(keywords, max_items=6) if keywords else find_relevant(["experience", "skill", "project"], max_items=5)
        if relevant:
            parts.append("**Based on the documents analyzed:**\n")
            for s in relevant:
                clean = s.strip().rstrip(',').rstrip(';')
                if len(clean) > 15:
                    parts.append(f"- {clean}")
            parts.append("")

    # ── Footer ──
    if percentages or emails:
        data_parts = []
        if percentages:
            data_parts.append(f"**Key Metrics:** {', '.join(list(dict.fromkeys(percentages))[:5])}")
        if emails:
            data_parts.append(f"**Contact:** {', '.join(list(dict.fromkeys(emails))[:2])}")
        parts.append("\n" + " | ".join(data_parts))

    parts.append(f"\n**Sources:** {', '.join(sources[:3])}")

    return "\n".join(parts)


def _demo_summary(chunks: list, topic: str) -> str:
    """Generate an offline summary from chunks."""
    if not chunks:
        return "**No content available to summarize.** Please ingest documents first."

    texts = [getattr(c, "text", str(c)) for c in chunks[:8]]
    sources = list(set(getattr(c, "source", "unknown") for c in chunks[:8]))
    combined = "\n".join(texts)

    # Word count and key stats
    words = combined.split()
    sentences = re.split(r'[.!?]+', combined)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    parts = [
        f"**📝 Document Summary**\n",
        f"**Topic:** {topic}",
        f"**Sources:** {', '.join(sources[:5])}",
        f"**Content Stats:** ~{len(words)} words across {len(chunks)} passages\n",
        "**Key Passages:**",
    ]

    for i, sent in enumerate(sentences[:8], 1):
        parts.append(f"{i}. {sent[:200]}...")

    # Extract most frequent significant words
    word_freq: Dict[str, int] = {}
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but", "not", "with", "this", "that", "it"}
    for w in words:
        w_clean = w.lower().strip(".,!?;:()[]{}\"'")
        if len(w_clean) > 3 and w_clean not in stop_words:
            word_freq[w_clean] = word_freq.get(w_clean, 0) + 1

    top_terms = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_terms:
        parts.append(f"\n**Key Terms:** {', '.join(f'**{t[0]}** ({t[1]}x)' for t in top_terms)}")

    parts.append("\n> 💡 *Connect Ollama for AI-powered summarization*")
    return "\n\n".join(parts)


def _demo_extraction(chunks: list, fields: List[str]) -> str:
    """Generate offline field extraction from chunks."""
    import json as _json

    combined = " ".join(getattr(c, "text", str(c)) for c in chunks[:5])
    result = {}

    for field in fields:
        field_lower = field.lower().replace("_", " ").replace("-", " ")

        # Try to find the value in context
        patterns = [
            rf'{re.escape(field_lower)}\s*[:=]\s*(.+?)(?:\n|$)',
            rf'{re.escape(field)}\s*[:=]\s*(.+?)(?:\n|$)',
        ]

        value = None
        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                value = match.group(1).strip()[:200]
                break

        # Try to match specific field types
        if value is None:
            if any(kw in field_lower for kw in ["amount", "total", "price", "cost", "fee"]):
                money = re.findall(r'[\$€£₹]\s*[\d,]+\.?\d*', combined)
                value = money[0] if money else None
            elif any(kw in field_lower for kw in ["date", "dated", "due"]):
                date_match = re.findall(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', combined)
                value = date_match[0] if date_match else None
            elif any(kw in field_lower for kw in ["email", "mail"]):
                email_match = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}', combined)
                value = email_match[0] if email_match else None
            elif any(kw in field_lower for kw in ["phone", "tel", "mobile"]):
                phone = re.findall(r'[\+]?[\d\s\-\(\)]{7,15}', combined)
                value = phone[0].strip() if phone else None

        result[field] = value if value else f"(not found in context — demo mode)"

    return _json.dumps(result, indent=2, ensure_ascii=False)


def _demo_table_qa(chunks: list, question: str) -> str:
    """Generate offline table analysis."""
    table_chunks = [c for c in chunks if getattr(c, "chunk_type", "") == "table"]

    if not table_chunks:
        return ("**No table data found** in the indexed documents for this query.\n\n"
                "Try uploading an Excel or CSV file, or a PDF with tables.")

    parts = ["**📊 Table Analysis**\n"]

    for i, tc in enumerate(table_chunks[:3], 1):
        text = getattr(tc, "text", str(tc))
        source = getattr(tc, "source", "unknown")
        page = getattr(tc, "page_num", "?")
        parts.append(f"**Table {i}** — *[{source}, Page {page}]*\n```\n{text[:500]}\n```\n")

    parts.append("> 💡 *Connect Ollama for AI-powered table analysis*")
    return "\n\n".join(parts)
