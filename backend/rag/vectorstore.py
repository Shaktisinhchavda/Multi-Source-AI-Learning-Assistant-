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


async def get_session_chunks(
    session_id: str,
    source_type: str | None = None,
    limit: int = 60,
) -> list[dict]:
    """
    Fetch stored chunks directly for fallback/context coverage.
    Useful for broad source-level questions where vector search may be too narrow.
    """
    client = _get_client()

    query = (
        client.table("documents")
        .select("content, source_type, source_name, source_ref, source_id, created_at")
        .eq("session_id", session_id)
        .order("created_at")
        .limit(limit)
    )

    if source_type:
        query = query.eq("source_type", source_type)

    result = query.execute()
    return result.data or []


async def get_session_sources(session_id: str) -> list[dict]:
    """Fetch ready sources for a session."""
    client = _get_client()

    result = (
        client.table("sources")
        .select("id, source_name, source_type")
        .eq("session_id", session_id)
        .eq("status", "ready")
        .order("created_at")
        .execute()
    )
    return result.data or []


async def get_chunks_for_sources(
    session_id: str,
    source_ids: list[str],
    limit: int = 80,
) -> list[dict]:
    """Fetch stored chunks for specific source IDs."""
    if not source_ids:
        return []

    client = _get_client()

    result = (
        client.table("documents")
        .select("content, source_type, source_name, source_ref, source_id, created_at")
        .eq("session_id", session_id)
        .in_("source_id", source_ids)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data or []
