from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Ollama (local dev)
    ollama_base_url: str = "http://localhost:11434"

    # LLM Provider toggle
    llm_provider: str = "ollama"  # "ollama" or "gemini"

    # Gemini (production)
    gemini_api_key: str = ""

    # Model names
    ollama_chat_model: str = "qwen2.5:1.5b"
    ollama_embed_model: str = "nomic-embed-text"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
