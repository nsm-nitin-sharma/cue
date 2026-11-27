import json
from typing import Any
import httpx

from app.core.config import get_settings
from app.domain.schemas.intents import IntentProposal
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini import _SYSTEM_INSTRUCTION, _extract_json_block, deterministic_fallback_parse


class OllamaLLMProvider(LLMProvider):
    """Optional local open-weight LLM adapter (disabled by default)."""

    async def parse_utterance(
        self,
        *,
        utterance: str,
        language_hint: str,
        context_summary: dict[str, Any],
        catalog_hints: list[dict[str, Any]],
        customer_hints: list[dict[str, Any]],
    ) -> IntentProposal:
        settings = get_settings()
        prompt = (
            f"{_SYSTEM_INSTRUCTION}\n\n"
            f"CONTEXT:\n{json.dumps({'context': context_summary, 'catalog': catalog_hints[:20]})}\n\n"
            f"<user_utterance>\n{utterance}\n</user_utterance>"
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "format": "json", "stream": False},
                )
            if resp.status_code == 200:
                raw_text = resp.json().get("response", "")
                return IntentProposal.model_validate(_extract_json_block(raw_text))
        except Exception:
            pass
        return deterministic_fallback_parse(utterance, language_hint)
