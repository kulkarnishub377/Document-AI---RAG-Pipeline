# features/pdf_annotator.py
# ─────────────────────────────────────────────────────────────────────────────
# PDF Annotation Export — highlights source passages in the original PDF.
# Uses PyMuPDF (fitz) to add highlight annotations at the exact locations
# where the answer was sourced from.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
from loguru import logger

from config import ANNOTATED_PDF_DIR, UPLOAD_DIR


def annotate_pdf(
    source_filename: str,
    highlights: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Create an annotated copy of a PDF with highlighted source passages.

    Args:
        source_filename: name of the original PDF in uploads/
        highlights: list of dicts with keys:
            - page_num (int): 1-based page number
            - text (str): text to search and highlight
            - color (tuple): RGB highlight color, default yellow

    Returns:
        Path to the annotated PDF, or None if source is not a PDF.
    """
    source_path = UPLOAD_DIR / source_filename
    if not source_path.exists():
        logger.warning(f"Source PDF not found: {source_path}")
        return None

    if source_path.suffix.lower() != ".pdf":
        logger.info(f"Skipping annotation — not a PDF: {source_filename}")
        return None

    try:
        doc = fitz.open(str(source_path))
    except Exception as e:
        logger.error(f"Failed to open PDF for annotation: {e}")
        return None

    annotated_count = 0

    for hl in highlights:
        page_num = hl.get("page_num", 1) - 1  # Convert to 0-based
        search_text = hl.get("text", "").strip()
        color = hl.get("color", (1, 1, 0))  # Yellow default

        if page_num < 0 or page_num >= len(doc):
            continue
        if not search_text:
            continue

        page = doc[page_num]

        # Search for the text on the page
        # Use first 80 chars to improve matching
        search_snippet = search_text[:80]
        instances = page.search_for(search_snippet)

        if not instances:
            # Try with less text for fuzzy matching
            words = search_text.split()[:5]
            if words:
                instances = page.search_for(" ".join(words))

        for rect in instances:
            highlight = page.add_highlight_annot(rect)
            highlight.set_colors(stroke=color)
            highlight.set_info(
                title="Document AI",
                content=f"Source passage for Q&A answer",
            )
            highlight.update()
            annotated_count += 1

    if annotated_count == 0:
        doc.close()
        logger.info("No text matches found for highlighting.")
        return None

    # Save annotated PDF
    output_name = f"annotated_{source_filename}"
    output_path = ANNOTATED_PDF_DIR / output_name
    doc.save(str(output_path))
    doc.close()

    logger.info(
        f"PDF annotated: {annotated_count} highlights → {output_path.name}"
    )
    return str(output_path)


def annotate_from_sources(
    sources: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Annotate multiple PDFs based on source citations from a query response.

    Args:
        sources: list of source dicts with 'source', 'page', 'excerpt' keys

    Returns:
        dict mapping source filename → annotated PDF path
    """
    # Group highlights by source file
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for src in sources:
        fname = src.get("source", "")
        if not fname.endswith(".pdf"):
            continue
        if fname not in by_source:
            by_source[fname] = []
        by_source[fname].append({
            "page_num": src.get("page", 1),
            "text": src.get("excerpt", ""),
        })

    results = {}
    for fname, highlights in by_source.items():
        path = annotate_pdf(fname, highlights)
        if path:
            results[fname] = path

    return results


def list_annotated() -> List[Dict[str, Any]]:
    """List all annotated PDFs with metadata."""
    if not ANNOTATED_PDF_DIR.exists():
        return []

    files = []
    for f in sorted(ANNOTATED_PDF_DIR.iterdir()):
        if f.suffix.lower() == ".pdf":
            files.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "path": str(f),
            })
    return files


def cleanup_annotated() -> int:
    """Remove all annotated PDFs. Returns count of files removed."""
    count = 0
    if ANNOTATED_PDF_DIR.exists():
        for f in ANNOTATED_PDF_DIR.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
    logger.info(f"Cleaned up {count} annotated PDFs.")
    return count
