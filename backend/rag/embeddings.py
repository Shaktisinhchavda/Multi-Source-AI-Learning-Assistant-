"""
Embedding service — generates vector embeddings via Ollama or Gemini.
"""

import httpx
from config import get_settings
from rag.gemini import post_json_with_retries


async def embed_texts(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.
    Uses Ollama nomic-embed-text in dev, Gemini in production.
    """
    settings = get_settings()

    if settings.llm_provider == "ollama":
        return await _embed_ollama(texts, settings)
    else:
        return await _embed_gemini(texts, settings, task_type)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    result = await embed_texts([text], task_type="RETRIEVAL_QUERY")
    return result[0]


async def _embed_ollama(texts: list[str], settings) -> list[list[float]]:
    """Generate embeddings via Ollama API."""
    embeddings = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            response = await client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={
                    "model": settings.ollama_embed_model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])
    return embeddings


async def _embed_gemini(
    texts: list[str],
    settings,
    task_type: str,
) -> list[list[float]]:
    """Generate embeddings via Gemini API (production)."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")

    embeddings = []
    url = (
        f"{settings.gemini_base_url}/models/"
        f"{settings.gemini_embed_model}:embedContent"
    )
    params = {"key": settings.gemini_api_key}

    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            data = await post_json_with_retries(
                client=client,
                url=url,
                params=params,
                payload={
                    "content": {
                        "parts": [{"text": text}],
                    },
                    "taskType": task_type,
                    "outputDimensionality": settings.gemini_embed_dimensions,
                },
                settings=settings,
                operation="embedding",
            )
            embeddings.append(data["embedding"]["values"])

    return embeddings
