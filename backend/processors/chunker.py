"""
Text chunker with metadata preservation.
Splits text into overlapping chunks while preserving source references.
"""

import tiktoken
from typing import Optional


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def chunk_text(
    text: str,
    source_type: str,
    source_name: str,
    source_ref: Optional[str] = None,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
) -> list[dict]:
    """
    Split text into overlapping chunks with metadata.
    
    Returns a list of dicts:
      {content, source_type, source_name, source_ref, metadata}
    """
    if not text or not text.strip():
        return []

    # Split by paragraphs first, then recombine into chunks
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If a single paragraph exceeds chunk_size, split it by sentences
        if para_tokens > chunk_size:
            # Flush current chunk first
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                # Keep overlap
                overlap_text = current_chunk[-1] if current_chunk else ""
                current_chunk = [overlap_text] if overlap_text else []
                current_tokens = count_tokens(overlap_text) if overlap_text else 0

            # Split long paragraph by sentences
            sentences = _split_sentences(para)
            for sent in sentences:
                sent_tokens = count_tokens(sent)
                if current_tokens + sent_tokens > chunk_size and current_chunk:
                    chunks.append("\n".join(current_chunk))
                    overlap_text = current_chunk[-1] if current_chunk else ""
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = count_tokens(overlap_text) if overlap_text else 0
                current_chunk.append(sent)
                current_tokens += sent_tokens
        else:
            if current_tokens + para_tokens > chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                # Keep overlap from end of previous chunk
                overlap_text = current_chunk[-1] if current_chunk else ""
                current_chunk = [overlap_text] if overlap_text else []
                current_tokens = count_tokens(overlap_text) if overlap_text else 0

            current_chunk.append(para)
            current_tokens += para_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # Build result with metadata
    result = []
    for i, chunk_text_content in enumerate(chunks):
        ref = source_ref or f"chunk {i + 1}"
        result.append({
            "content": chunk_text_content,
            "source_type": source_type,
            "source_name": source_name,
            "source_ref": ref,
            "metadata": {
                "chunk_index": i,
                "total_chunks": len(chunks),
            },
        })

    return result


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_pages(
    pages: list[dict],
    source_type: str,
    source_name: str,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
) -> list[dict]:
    """
    Chunk content that is already split by pages/slides/timestamps.
    
    Input: list of {text, ref} dicts (e.g., {text: "...", ref: "page 3"})
    """
    all_chunks = []
    for page in pages:
        page_chunks = chunk_text(
            text=page["text"],
            source_type=source_type,
            source_name=source_name,
            source_ref=page.get("ref"),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_chunks.extend(page_chunks)
    return all_chunks
