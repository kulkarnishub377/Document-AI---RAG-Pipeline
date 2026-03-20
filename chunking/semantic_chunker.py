# chunking/semantic_chunker.py
# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Semantic Chunking
#
# Responsibilities:
#   • Split page text into overlapping chunks that respect sentence boundaries
#   • Attach rich metadata to every chunk (source, page, chunk_id, hash)
#   • Keep tables as single atomic chunks (never split a table mid-row)
#   • Deduplicate chunks by content hash
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger

from config import CHUNK_SIZE, CHUNK_OVERLAP


# ── Output data container ────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A single chunk of text ready for embedding."""
    chunk_id:   str          # sha256 of content (dedup key)
    source:     str          # original file name
    page_num:   int          # 1-based page number
    chunk_idx:  int          # position within the page
    text:       str          # the actual text to embed
    chunk_type: str = "text" # "text" | "table"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    """Return a 16-char hex digest for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _split_into_sentences(text: str) -> List[str]:
    """
    Simple sentence splitter using punctuation boundaries.
    Avoids splitting on abbreviations like 'Dr.' or 'e.g.' by
    requiring the following token to start with a capital letter or digit.
    """
    pattern = r'(?<=[.!?])\s+(?=[A-Z0-9])'
    sentences = re.split(pattern, text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _sentences_to_chunks(sentences: List[str],
                          max_chars: int = CHUNK_SIZE,
                          overlap_chars: int = CHUNK_OVERLAP) -> List[str]:
    """
    Greedy packing: keep adding sentences until the chunk would exceed
    max_chars, then start a new chunk with overlap_chars from the end
    of the previous chunk.
    """
    if not sentences:
        return []

    chunks: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        # If a single sentence is larger than the limit, keep it as-is
        if sent_len >= max_chars:
            if current_parts:
                chunks.append(" ".join(current_parts))
            chunks.append(sent)
            current_parts = []
            current_len   = 0
            continue

        if current_len + sent_len + 1 > max_chars and current_parts:
            chunks.append(" ".join(current_parts))

            # Build overlap from the tail of current chunk
            overlap_text = ""
            for part in reversed(current_parts):
                if len(overlap_text) + len(part) + 1 <= overlap_chars:
                    overlap_text = part + " " + overlap_text
                else:
                    break
            current_parts = [overlap_text.strip()] if overlap_text.strip() else []
            current_len   = len(overlap_text)

        current_parts.append(sent)
        current_len += sent_len + 1

    if current_parts:
        chunks.append(" ".join(current_parts))

    return [c.strip() for c in chunks if c.strip()]


def _table_to_markdown(table: List[List[str]]) -> str:
    """Convert a 2D list (rows × cols) to a Markdown table string."""
    if not table:
        return ""
    rows = []
    for i, row in enumerate(table):
        row_str = " | ".join(str(cell).strip() for cell in row)
        rows.append(f"| {row_str} |")
        if i == 0:
            sep = " | ".join(["---"] * len(row))
            rows.append(f"| {sep} |")
    return "\n".join(rows)


# ── Public API ───────────────────────────────────────────────────────────────

def chunk_pages(pages) -> List[Chunk]:
    """
    Convert a list of PageData objects into a deduplicated list of Chunks.

    Each text page is split into sentence-aware overlapping chunks.
    Tables are kept as single atomic chunks — never split mid-row.

    Usage:
        chunks = chunk_pages(pages)
        print(len(chunks), "chunks created")
    """
    if not pages:
        logger.warning("chunk_pages called with empty page list — returning []")
        return []

    all_chunks: List[Chunk] = []
    seen_hashes: set         = set()
    global_idx               = 0
    skipped                  = 0

    for page in pages:
        chunk_idx_on_page = 0

        # ── Text chunks ──────────────────────────────────────────────────
        if page.text.strip():
            sentences     = _split_into_sentences(page.text)
            text_segments = _sentences_to_chunks(sentences)

            for seg in text_segments:
                h = _sha256(seg)
                if h in seen_hashes:
                    skipped += 1
                    continue
                seen_hashes.add(h)

                all_chunks.append(Chunk(
                    chunk_id   = h,
                    source     = page.source,
                    page_num   = page.page_num,
                    chunk_idx  = chunk_idx_on_page,
                    text       = seg,
                    chunk_type = "text",
                ))
                chunk_idx_on_page += 1
                global_idx        += 1

        # ── Table chunks (kept atomic — never split a table) ─────────────
        for tbl in page.tables:
            md = _table_to_markdown(tbl)
            if not md.strip():
                continue
            h = _sha256(md)
            if h in seen_hashes:
                skipped += 1
                continue
            seen_hashes.add(h)

            all_chunks.append(Chunk(
                chunk_id   = h,
                source     = page.source,
                page_num   = page.page_num,
                chunk_idx  = chunk_idx_on_page,
                text       = md,
                chunk_type = "table",
            ))
            chunk_idx_on_page += 1
            global_idx        += 1

    text_chunks  = sum(1 for c in all_chunks if c.chunk_type == "text")
    table_chunks = sum(1 for c in all_chunks if c.chunk_type == "table")
    logger.info(
        f"Chunking complete: {len(all_chunks)} chunks "
        f"({text_chunks} text, {table_chunks} table) from "
        f"{len(pages)} pages  |  {skipped} duplicates skipped  |  "
        f"CHUNK_SIZE={CHUNK_SIZE}, OVERLAP={CHUNK_OVERLAP}"
    )
    return all_chunks
