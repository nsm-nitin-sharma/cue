from abc import ABC, abstractmethod
from typing import Any
from app.domain.schemas.intents import IntentProposal


class LLMProvider(ABC):
    @abstractmethod
    async def parse_utterance(
        self,
        *,
        utterance: str,
        language_hint: str,
        context_summary: dict[str, Any],
        catalog_hints: list[dict[str, Any]],
        customer_hints: list[dict[str, Any]],
    ) -> IntentProposal:
        raise NotImplementedError
