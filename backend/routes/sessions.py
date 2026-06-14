"""
Sessions API — create and manage chat sessions.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from config import get_settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
    id: str
    created_at: str
    sources: list = []


@router.post("", response_model=SessionResponse)
async def create_session():
    """Create a new chat session."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.",
        )

    client = create_client(settings.supabase_url, settings.supabase_key)

    try:
        result = client.table("sessions").insert({"metadata": {}}).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase session insert failed: {str(e)}",
        ) from e

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create session")

    session = result.data[0]
    return SessionResponse(
        id=session["id"],
        created_at=session["created_at"],
        sources=[],
    )


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session info including loaded sources."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    # Get session
    session_result = client.table("sessions").select("*").eq("id", session_id).execute()
    if not session_result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get sources for this session
    sources_result = (
        client.table("sources")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )

    return {
        "session": session_result.data[0],
        "sources": sources_result.data or [],
    }


@router.get("/{session_id}/history")
async def get_history(session_id: str):
    """Get conversation history for a session."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    result = (
        client.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )

    return {"messages": result.data or []}
