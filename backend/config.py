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
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Model names
    ollama_chat_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "nomic-embed-text"
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_embed_dimensions: int = 768
    gemini_max_retries: int = 4
    gemini_retry_base_seconds: float = 2.0
    gemini_retry_max_seconds: float = 30.0

    # YouTube ingestion
    youtube_cookies_file: str = ""
    youtube_cookies_b64: str = ""
    youtube_audio_fallback: bool = True
    youtube_audio_max_mb: int = 25
    youtube_proxy: str = ""
    youtube_user_agent: str = ""
    youtube_player_clients: str = "web,web_safari,mweb,android"
    youtube_visitor_data: str = ""
    youtube_po_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
