"""
PDF processor — extracts text page-by-page and chunks it.
"""

import io
from PyPDF2 import PdfReader
from .chunker import chunk_pages


def extract_pdf_pages(file_bytes: bytes) -> list[dict]:
    """
    Extract text from each page of a PDF.
    Returns list of {text, ref} dicts.
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({
                "text": text.strip(),
                "ref": f"page {i + 1}",
            })
    return pages


def process_pdf(file_bytes: bytes, filename: str) -> dict:
    """
    Full PDF processing pipeline:
    1. Extract pages
    2. Chunk with page references
    3. Generate a brief summary (first ~500 chars)
    
    Returns: {chunks: [...], summary: str, page_count: int}
    """
    pages = extract_pdf_pages(file_bytes)

    if not pages:
        raise ValueError(f"Could not extract any text from '{filename}'. The PDF may be image-based.")

    chunks = chunk_pages(
        pages=pages,
        source_type="pdf",
        source_name=filename,
    )

    # Create a summary from the first page content
    all_text = " ".join(p["text"] for p in pages[:2])
    summary = all_text[:500].strip()
    if len(all_text) > 500:
        summary += "..."

    return {
        "chunks": chunks,
        "summary": summary,
        "page_count": len(pages),
    }
