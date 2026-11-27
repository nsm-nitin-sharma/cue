from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "Cue Voice-First Business OS"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # AI & Speech (Free Tier Split)
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    STT_PROVIDER: str = "groq_whisper"
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"

    # Optional Local Adapters
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    FASTER_WHISPER_MODEL_SIZE: str = "base"

    # Hardcore Security & Business Policy Guardrails
    HIGH_VALUE_CONFIRM_THRESHOLD_INR: float = 5000.0
    MAX_AUDIO_UPLOAD_MB: int = 10
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    CONVERSATION_MEMORY_DAYS: int = 30
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"
    CONFIRMATION_TOKEN_TTL_SECONDS: int = 300
    MAX_BATCH_OPERATIONS: int = 25
    MAX_QTY_PER_OPERATION: float = 10000.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_audio_bytes(self) -> int:
        return self.MAX_AUDIO_UPLOAD_MB * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
