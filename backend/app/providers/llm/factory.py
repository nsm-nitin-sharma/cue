from app.core.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini import GeminiLLMProvider
from app.providers.llm.ollama import OllamaLLMProvider


def get_llm_provider() -> LLMProvider:
    if get_settings().LLM_PROVIDER.strip().lower() == "ollama":
        return OllamaLLMProvider()
    return GeminiLLMProvider()
