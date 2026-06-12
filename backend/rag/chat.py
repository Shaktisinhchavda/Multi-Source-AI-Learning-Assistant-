"""
Chat engine — RAG-powered chat using Ollama or Gemini.
Builds a grounded prompt with retrieved context and conversation history.
"""

import httpx
import json
from typing import AsyncGenerator
from config import get_settings
from rag.embeddings import embed_query
from rag.vectorstore import search_similar


SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions based ONLY on the provided source material. Follow these rules strictly:

1. **Grounded answers**: Only answer using information from the provided context. Do not use prior knowledge.
2. **Citations**: Always cite the source when answering. Use the source reference provided (e.g., "According to page 3 of document.pdf..." or "At 3:22 in the video...").
3. **Simple explanations**: When asked to "explain in simple terms", break down complex concepts using analogies and simple language.
4. **Out of scope**: If a question cannot be answered from the provided material, say: "I couldn't find information about that in the provided sources. Could you rephrase your question or upload additional material?"
5. **Multiple sources**: If information comes from multiple sources, cite each one.
6. **Be concise**: Give clear, focused answers. Use bullet points or numbered lists when appropriate."""


def _build_context(retrieved_chunks: list[dict]) -> str:
    """Build a context string from retrieved chunks."""
    if not retrieved_chunks:
        return "No relevant content found in the provided sources."

    context_parts = []
    for i, chunk in enumerate(retrieved_chunks):
        source_info = f"[Source: {chunk['source_name']}"
        if chunk.get("source_ref"):
            source_info += f", {chunk['source_ref']}"
        source_info += f" | Relevance: {chunk.get('similarity', 0):.2f}]"

        context_parts.append(f"--- Context {i + 1} {source_info} ---\n{chunk['content']}")

    return "\n\n".join(context_parts)


def _build_messages(
    system_prompt: str,
    context: str,
    conversation_history: list[dict],
    user_message: str,
) -> list[dict]:
    """Build the message list for the LLM."""
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history (last 10 messages to keep within context)
    for msg in conversation_history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Build the user message with context
    augmented_message = f"""Here is the relevant source material:

{context}

---

User question: {user_message}"""

    messages.append({"role": "user", "content": augmented_message})
    return messages


async def generate_response(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
) -> dict:
    """
    Full RAG pipeline:
    1. Embed the query
    2. Retrieve relevant chunks
    3. Generate a grounded response
    
    Returns: {response: str, sources: [{source_name, source_ref}]}
    """
    # Step 1: Embed the user query
    query_embedding = await embed_query(user_message)

    # Step 2: Retrieve relevant chunks
    retrieved = await search_similar(session_id, query_embedding, match_count=5)

    # Step 3: Build context and generate
    context = _build_context(retrieved)
    messages = _build_messages(SYSTEM_PROMPT, context, conversation_history, user_message)

    settings = get_settings()

    if settings.llm_provider == "ollama":
        response_text = await _chat_ollama(messages, settings)
    else:
        response_text = await _chat_gemini(messages, settings)

    # Extract unique sources for citation
    sources = []
    seen = set()
    for chunk in retrieved:
        key = f"{chunk['source_name']}|{chunk.get('source_ref', '')}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "source_name": chunk["source_name"],
                "source_type": chunk.get("source_type", ""),
                "source_ref": chunk.get("source_ref", ""),
            })

    return {
        "response": response_text,
        "sources": sources,
    }


async def generate_response_stream(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Streaming RAG pipeline — yields tokens as they arrive.
    First yields a JSON sources line, then text tokens.
    """
    # Step 1 & 2: Embed and retrieve
    query_embedding = await embed_query(user_message)
    retrieved = await search_similar(session_id, query_embedding, match_count=5)

    # Extract sources
    sources = []
    seen = set()
    for chunk in retrieved:
        key = f"{chunk['source_name']}|{chunk.get('source_ref', '')}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "source_name": chunk["source_name"],
                "source_type": chunk.get("source_type", ""),
                "source_ref": chunk.get("source_ref", ""),
            })

    # Yield sources metadata first
    yield json.dumps({"type": "sources", "data": sources}) + "\n"

    # Step 3: Build context and stream
    context = _build_context(retrieved)
    messages = _build_messages(SYSTEM_PROMPT, context, conversation_history, user_message)

    settings = get_settings()

    if settings.llm_provider == "ollama":
        async for token in _stream_ollama(messages, settings):
            yield json.dumps({"type": "token", "data": token}) + "\n"
    else:
        async for token in _stream_gemini(messages, settings):
            yield json.dumps({"type": "token", "data": token}) + "\n"

    yield json.dumps({"type": "done"}) + "\n"


async def _chat_ollama(messages: list[dict], settings) -> str:
    """Non-streaming chat via Ollama."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def _stream_ollama(messages: list[dict], settings) -> AsyncGenerator[str, None]:
    """Streaming chat via Ollama."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    if not data.get("done", False):
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token


async def _chat_gemini(messages: list[dict], settings) -> str:
    """Gemini chat — placeholder for Phase 5."""
    raise NotImplementedError("Gemini chat not yet implemented. Use ollama for development.")


async def _stream_gemini(messages: list[dict], settings) -> AsyncGenerator[str, None]:
    """Gemini streaming — placeholder for Phase 5."""
    raise NotImplementedError("Gemini streaming not yet implemented.")
    yield  # Make it a generator
