"""
Chat API — RAG-powered chat with streaming support.
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client
from config import get_settings
from rag.chat import generate_response, generate_response_stream

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str
    stream: bool = True


def _is_out_of_scope_decline(content: str) -> bool:
    """Detect the standard grounded-answer refusal."""
    return "couldn't find information about that in the provided sources" in content.lower()


@router.post("")
async def chat(body: ChatRequest):
    """
    Send a message and get a RAG-powered response.
    Supports both streaming (SSE) and non-streaming modes.
    """
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    # Verify session exists
    session = client.table("sessions").select("id").eq("id", body.session_id).execute()
    if not session.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if any sources are loaded
    sources = (
        client.table("sources")
        .select("id")
        .eq("session_id", body.session_id)
        .eq("status", "ready")
        .execute()
    )
    if not sources.data:
        raise HTTPException(
            status_code=400,
            detail="No sources loaded yet. Please upload a document or add a URL first.",
        )

    # Get conversation history
    history_result = (
        client.table("messages")
        .select("role, content")
        .eq("session_id", body.session_id)
        .order("created_at")
        .execute()
    )
    conversation_history = history_result.data or []

    # Save user message
    client.table("messages").insert({
        "session_id": body.session_id,
        "role": "user",
        "content": body.message,
    }).execute()

    if body.stream:
        return StreamingResponse(
            _stream_chat(body.session_id, body.message, conversation_history, client),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming response
        result = await generate_response(
            session_id=body.session_id,
            user_message=body.message,
            conversation_history=conversation_history,
        )

        # Save assistant message
        result_sources = [] if _is_out_of_scope_decline(result["response"]) else result["sources"]
        client.table("messages").insert({
            "session_id": body.session_id,
            "role": "assistant",
            "content": result["response"],
            "sources": result_sources,
        }).execute()

        return {
            **result,
            "sources": result_sources,
        }


async def _stream_chat(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
    client,
):
    """Stream chat responses as SSE events."""
    full_response = ""
    sources_data = []

    async for chunk in generate_response_stream(
        session_id=session_id,
        user_message=user_message,
        conversation_history=conversation_history,
    ):
        parsed = json.loads(chunk)

        if parsed["type"] == "sources":
            sources_data = parsed["data"]
            yield f"data: {chunk}\n\n"
        elif parsed["type"] == "token":
            full_response += parsed["data"]
            yield f"data: {chunk}\n\n"
        elif parsed["type"] == "done":
            # Save the complete assistant message
            if _is_out_of_scope_decline(full_response):
                sources_data = []
            client.table("messages").insert({
                "session_id": session_id,
                "role": "assistant",
                "content": full_response,
                "sources": sources_data,
            }).execute()
            yield f"data: {chunk}\n\n"
