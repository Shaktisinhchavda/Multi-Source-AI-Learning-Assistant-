"""
Embedding service — generates vector embeddings via Ollama or Gemini.
"""

import httpx
from config import get_settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.
    Uses Ollama nomic-embed-text in dev, Gemini in production.
    """
    settings = get_settings()

    if settings.llm_provider == "ollama":
        return await _embed_ollama(texts, settings)
    else:
        return await _embed_gemini(texts, settings)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    result = await embed_texts([text])
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


async def _embed_gemini(texts: list[str], settings) -> list[list[float]]:
    """Generate embeddings via Gemini API (production)."""
    # Placeholder — will implement in Phase 5
    raise NotImplementedError("Gemini embeddings not yet implemented. Use ollama for development.")
