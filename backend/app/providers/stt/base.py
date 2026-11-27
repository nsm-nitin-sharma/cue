from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class STTResult:
    text: str
    detected_language: str
    confidence: float
    provider: str
    is_unclear: bool = False


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language_hint: str = "hinglish",
    ) -> STTResult:
        raise NotImplementedError
