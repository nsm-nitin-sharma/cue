from app.core.exceptions import AudioValidationError
from app.providers.stt.base import STTProvider, STTResult


class FasterWhisperProvider(STTProvider):
    """
    Optional self-hosted local OpenAI Whisper adapter (CTranslate2).
    Disabled by default to preserve local PC CPU/RAM; enable via STT_PROVIDER=faster_whisper
    after installing `faster-whisper`.
    """

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language_hint: str = "hinglish",
    ) -> STTResult:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise AudioValidationError(
                "faster-whisper is not installed locally. Use STT_PROVIDER=groq_whisper or install faster-whisper."
            ) from exc

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(tmp_path, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
            if not text:
                return STTResult(text="", detected_language=language_hint, confidence=0.1, provider="faster_whisper", is_unclear=True)
            return STTResult(
                text=text,
                detected_language=getattr(info, "language", language_hint) or language_hint,
                confidence=0.85,
                provider="faster_whisper",
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class IndicConformerProvider(STTProvider):
    """
    Modular AI4Bharat IndicConformer adapter for regional Indian language evaluation.
    """

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language_hint: str = "hinglish",
    ) -> STTResult:
        raise AudioValidationError(
            "AI4Bharat IndicConformer adapter is configured as an evaluation plugin. "
            "Set STT_PROVIDER=groq_whisper for active Hindi/Hinglish/English support."
        )
