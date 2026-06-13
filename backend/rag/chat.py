"""
Chat engine — RAG-powered chat using Ollama or Gemini.
Builds a grounded prompt with retrieved context and conversation history.
"""

import httpx
import asyncio
import json
import re
from typing import AsyncGenerator
from config import get_settings
from rag.embeddings import embed_query
from rag.vectorstore import (
    search_similar,
    get_session_chunks,
    get_session_sources,
    get_chunks_for_sources,
)
from rag.gemini import post_json_with_retries, RETRYABLE_STATUS_CODES, extract_error_message


SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions based ONLY on the provided source material. Follow these rules strictly:

1. **Grounded answers**: Only answer using information from the provided context. Do not use prior knowledge.
2. **Citations**: Always cite the source when answering. Use the source reference provided (e.g., "According to page 3 of document.pdf..." or "At 3:22 in the video...").
3. **Simple explanations**: When asked to "explain in simple terms", break down complex concepts using analogies and simple language.
4. **Out of scope**: If a question cannot be answered from the provided material, say: "I couldn't find information about that in the provided sources. Could you rephrase your question or upload additional material?"
5. **Multiple sources**: If information comes from multiple sources, cite each one.
6. **Source-wise summaries**: When the user asks for a summary, overview, main points, or explanation across multiple sources, organize the answer by source title. Do not organize by retrieved context number.
7. **Be concise**: Give clear, focused answers. Use bullet points or numbered lists when appropriate."""


def _build_context(retrieved_chunks: list[dict]) -> str:
    """Build a source-grouped context string from retrieved chunks."""
    if not retrieved_chunks:
        return "No relevant content found in the provided sources."

    grouped: dict[str, dict] = {}
    for chunk in retrieved_chunks:
        source_name = chunk["source_name"]
        group = grouped.setdefault(
            source_name,
            {
                "source_type": chunk.get("source_type", ""),
                "chunks": [],
            },
        )
        group["chunks"].append(chunk)

    source_parts = []
    for source_index, (source_name, group) in enumerate(grouped.items(), start=1):
        source_type = group["source_type"]
        lines = [
            f"=== Source {source_index}: {source_name} ({source_type}) ==="
        ]

        for chunk_index, chunk in enumerate(group["chunks"], start=1):
            ref = chunk.get("source_ref") or f"part {chunk_index}"
            ref_info = f"[Reference: {ref}"
            if "similarity" in chunk and chunk.get("similarity") is not None:
                ref_info += f" | Relevance: {chunk.get('similarity', 0):.2f}"
            ref_info += "]"
            lines.append(f"{ref_info}\n{chunk['content']}")

        source_parts.append("\n\n".join(lines))

    return "\n\n".join(source_parts)


def _is_broad_source_question(user_message: str) -> bool:
    """Detect questions that need source coverage rather than narrow retrieval."""
    text = user_message.lower()
    patterns = [
        r'\b(summarize|summary|overview|main idea|main points|key points)\b',
        r'\b(what is this|what are these|what does it say|explain this)\b',
        r'\b(compare|combine|all sources|uploaded sources|provided sources)\b',
        r'\b(document|pdf|ppt|pptx|slides?|webpage|website|video|youtube|transcript|lecture|talk)\b',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _requested_source_types(user_message: str) -> set[str]:
    """Infer source types mentioned directly in the user's question."""
    text = user_message.lower()
    requested = set()

    if re.search(r'\b(youtube|video|transcript|lecture|talk)\b', text):
        requested.add("youtube")
    if re.search(r'\b(pdf|document|paper|file)\b', text):
        requested.add("pdf")
    if re.search(r'\b(ppt|pptx|powerpoint|slides?|deck|presentation)\b', text):
        requested.add("pptx")
    if re.search(r'\b(webpage|website|web page|site|article|url|link)\b', text):
        requested.add("webpage")

    return requested


def _source_key(chunk: dict, source_name_to_id: dict[str, str] | None = None) -> str:
    """Stable key for grouping chunks by uploaded source."""
    source_id = chunk.get("source_id")
    if source_id:
        return source_id

    source_name = chunk.get("source_name", "")
    if source_name_to_id and source_name in source_name_to_id:
        return source_name_to_id[source_name]

    return source_name


def _source_tokens(source_name: str) -> set[str]:
    """Extract meaningful tokens from a source name for mention matching."""
    tokens = re.findall(r'[a-z0-9]+', source_name.lower())
    ignored = {
        "pdf", "ppt", "pptx", "youtube", "webpage", "website", "http",
        "https", "www", "com", "ai", "the", "and", "for", "with",
    }
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in ignored
    }


def _requested_source_keys(user_message: str, sources: list[dict]) -> set[str]:
    """Infer specific source names mentioned in the user's question."""
    message_tokens = set(re.findall(r'[a-z0-9]+', user_message.lower()))
    source_tokens_by_key: dict[str, set[str]] = {}

    for source in sources:
        key = source["id"]
        source_tokens_by_key[key] = _source_tokens(source.get("source_name", ""))

    requested = set()
    for key, tokens in source_tokens_by_key.items():
        if tokens and tokens.intersection(message_tokens):
            requested.add(key)

    return requested


def _sample_evenly(chunks: list[dict], count: int) -> list[dict]:
    """Pick chunks across a source so context is not only from the start."""
    if count <= 0 or not chunks:
        return []
    if count >= len(chunks):
        return chunks
    if count == 1:
        return [chunks[0]]

    last_index = len(chunks) - 1
    indexes = {
        round(i * last_index / (count - 1))
        for i in range(count)
    }
    return [chunks[i] for i in sorted(indexes)]


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    """Keep retrieved chunks unique while preserving order."""
    deduped = []
    seen = set()
    for chunk in chunks:
        key = (
            chunk.get("source_name"),
            chunk.get("source_ref"),
            chunk.get("content"),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(chunk)
    return deduped


async def _retrieve_context_chunks(
    session_id: str,
    user_message: str,
    match_count: int = 8,
) -> list[dict]:
    """
    Retrieve context with vector search plus source coverage fallback.
    Broad questions and source-type questions often need sampled chunks from
    the stored source, even when semantic search is weak or too narrow.
    """
    query_embedding = await embed_query(user_message)
    retrieved = await search_similar(session_id, query_embedding, match_count=match_count)
    sources = await get_session_sources(session_id)
    source_name_to_id = {
        source["source_name"]: source["id"]
        for source in sources
    }

    all_chunks = await get_session_chunks(
        session_id=session_id,
        limit=160,
    )
    if not all_chunks:
        return retrieved

    requested_types = _requested_source_types(user_message)
    requested_source_keys = _requested_source_keys(user_message, sources)
    broad_question = _is_broad_source_question(user_message)
    no_vector_context = not retrieved

    if requested_source_keys:
        source_chunks = await get_chunks_for_sources(
            session_id,
            list(requested_source_keys),
            limit=120,
        )
        source_retrieved = [
            chunk for chunk in retrieved
            if _source_key(chunk, source_name_to_id) in requested_source_keys
        ]

        chunks_by_source: dict[str, list[dict]] = {}
        for chunk in source_chunks:
            chunks_by_source.setdefault(_source_key(chunk, source_name_to_id), []).append(chunk)

        coverage = []
        for chunks in chunks_by_source.values():
            source_type = chunks[0].get("source_type", "")
            sample_count = 4 if source_type == "youtube" else 3
            coverage.extend(_sample_evenly(chunks, count=sample_count))

        return _dedupe_chunks([*source_retrieved, *coverage])[:10]

    if not broad_question and not requested_types and not no_vector_context:
        return retrieved

    retrieved_source_keys = {
        _source_key(chunk, source_name_to_id)
        for chunk in retrieved
    }

    chunks_by_source: dict[str, list[dict]] = {}
    for chunk in all_chunks:
        source_type = chunk.get("source_type")
        source_key = _source_key(chunk, source_name_to_id)

        if requested_types and source_type not in requested_types:
            continue

        if not broad_question and not no_vector_context and source_key in retrieved_source_keys:
            continue

        chunks_by_source.setdefault(source_key, []).append(chunk)

    coverage = []
    for chunks in chunks_by_source.values():
        source_type = chunks[0].get("source_type", "")
        sample_count = 4 if source_type == "youtube" else 3
        coverage.extend(_sample_evenly(chunks, count=sample_count))

    if not coverage:
        return retrieved

    return _dedupe_chunks([*coverage, *retrieved])[:14]


def _build_messages(
    system_prompt: str,
    context: str,
    conversation_history: list[dict],
    user_message: str,
) -> list[dict]:
    """Build the message list for the LLM."""
    messages = [{"role": "system", "content": system_prompt}]
    broad_question = _is_broad_source_question(user_message)

    # Add conversation history for follow-ups, but keep source summaries clean.
    if not broad_question:
        for msg in conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    source_summary_instruction = ""
    if broad_question:
        source_titles = re.findall(r'^=== Source \d+: (.+?) \(.+?\) ===$', context, flags=re.MULTILINE)
        if source_titles:
            format_lines = []
            for index, title in enumerate(source_titles, start=1):
                format_lines.append(
                    f"## Source {index}: {title}\n"
                    "A clear 3-5 sentence overview of this source.\n\n"
                    "Key takeaways:\n"
                    "- ...\n"
                    "- ...\n"
                    "- ..."
                )
            required_format = "\n\n".join(format_lines)
        else:
            required_format = (
                "## Source 1: <source title>\n"
                "A clear 3-5 sentence overview of this source.\n\n"
                "Key takeaways:\n"
                "- ...\n"
                "- ...\n"
                "- ..."
            )

        source_summary_instruction = """
MANDATORY RESPONSE FORMAT FOR THIS QUESTION:
- Organize the answer source-wise using the exact source titles below.
- Do not write "Context 1", "Context 2", "retrieved context", or a separate context-wise summary.
- Do not merge unrelated sources into one summary.
- Do not repeat the user's question.
- Do not include "Important references" unless the user asks for citations.
- Use a clear, concise overview for each source: not one line, not a long dump.
- If a source has many topics, branch inside that source only using bullets.
- Keep all details from a source under that source's heading.
- End without adding a separate combined summary unless the user explicitly asks for comparison.

Use this structure:
{required_format}""".format(required_format=required_format)

    # Build the user message with context
    augmented_message = f"""Here is the relevant source material:

{context}

---
{source_summary_instruction}

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
    # Step 1 & 2: Retrieve relevant chunks
    retrieved = await _retrieve_context_chunks(session_id, user_message)

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
    # Step 1 & 2: Retrieve relevant chunks
    retrieved = await _retrieve_context_chunks(session_id, user_message)

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
    """Non-streaming chat via Gemini."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")

    payload = _build_gemini_payload(messages)
    async with httpx.AsyncClient(timeout=120.0) as client:
        data = await post_json_with_retries(
            client=client,
            url=_gemini_url(settings, "generateContent"),
            params={"key": settings.gemini_api_key},
            payload=payload,
            settings=settings,
            operation="chat",
        )
        return _extract_gemini_text(data)


async def _stream_gemini(messages: list[dict], settings) -> AsyncGenerator[str, None]:
    """Streaming chat via Gemini SSE."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")

    payload = _build_gemini_payload(messages)
    async with httpx.AsyncClient(timeout=120.0) as client:
        max_retries = max(0, settings.gemini_max_retries)
        for attempt in range(max_retries + 1):
            async with client.stream(
                "POST",
                _gemini_url(settings, "streamGenerateContent"),
                params={
                    "key": settings.gemini_api_key,
                    "alt": "sse",
                },
                json=payload,
            ) as response:
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                    await asyncio.sleep(
                        min(
                            settings.gemini_retry_base_seconds * (2 ** attempt),
                            settings.gemini_retry_max_seconds,
                        )
                    )
                    continue
                if response.status_code >= 400:
                    await response.aread()
                    detail = extract_error_message(response)
                    if response.status_code == 429:
                        detail = (
                            "Gemini rate limit reached. Please wait a bit and try again. "
                            f"Details: {detail}"
                        )
                    raise ValueError(
                        f"Gemini streaming chat request failed with HTTP "
                        f"{response.status_code}: {detail}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line.removeprefix("data: ").strip())
                    token = _extract_gemini_text(data)
                    if token:
                        yield token
                return


def _gemini_url(settings, action: str) -> str:
    """Build a Gemini model action URL."""
    return (
        f"{settings.gemini_base_url}/models/"
        f"{settings.gemini_chat_model}:{action}"
    )


def _build_gemini_payload(messages: list[dict]) -> dict:
    """Convert local chat messages to Gemini generateContent payload."""
    system_parts = []
    contents = []

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            system_parts.append({"text": content})
            continue

        contents.append({
            "role": "model" if role == "assistant" else "user",
            "parts": [{"text": content}],
        })

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}

    return payload


def _extract_gemini_text(data: dict) -> str:
    """Extract text from a Gemini response chunk."""
    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    return "".join(part.get("text", "") for part in parts)
