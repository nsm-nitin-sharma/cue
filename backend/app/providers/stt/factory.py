from app.core.config import get_settings
from app.providers.stt.base import STTProvider
from app.providers.stt.faster_whisper import FasterWhisperProvider, IndicConformerProvider
from app.providers.stt.gemini_audio import GeminiAudioSTTProvider
from app.providers.stt.groq_whisper import GroqWhisperProvider


def get_stt_provider() -> STTProvider:
    provider = get_settings().STT_PROVIDER.strip().lower()
    if provider == "gemini_audio":
        return GeminiAudioSTTProvider()
    if provider == "faster_whisper":
        return FasterWhisperProvider()
    if provider == "indic_conformer":
        return IndicConformerProvider()
    return GroqWhisperProvider()
