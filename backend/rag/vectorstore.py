"""
Vector store — Supabase pgvector operations for storing and searching embeddings.
"""

import json
from supabase import create_client, Client
from config import get_settings


def _get_client() -> Client:
    """Get Supabase client."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


async def store_chunks(
    session_id: str,
    source_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> int:
    """
    Store text chunks with their embeddings in Supabase.
    
    Returns: number of chunks stored.
    """
    client = _get_client()

    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append({
            "session_id": session_id,
            "source_id": source_id,
            "content": chunk["content"],
            "embedding": embedding,
            "source_type": chunk["source_type"],
            "source_name": chunk["source_name"],
            "source_ref": chunk.get("source_ref"),
            "metadata": json.dumps(chunk.get("metadata", {})),
        })

    # Insert in batches of 50
    batch_size = 50
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        result = client.table("documents").insert(batch).execute()
        total += len(result.data)

    return total


async def search_similar(
    session_id: str,
    query_embedding: list[float],
    match_count: int = 5,
) -> list[dict]:
    """
    Find the most similar document chunks using pgvector cosine similarity.
    """
    client = _get_client()

    result = client.rpc(
        "match_documents",
        {
            "query_embedding": query_embedding,
            "match_count": match_count,
            "filter_session_id": session_id,
        },
    ).execute()

    return result.data or []
