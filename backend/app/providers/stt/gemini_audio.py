import base64
import httpx

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.providers.stt.base import STTProvider, STTResult


class GeminiAudioSTTProvider(STTProvider):
    """Fallback free cloud STT using Google Gemini multimodal audio input."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language_hint: str = "hinglish",
    ) -> STTResult:
        settings = get_settings()
        if not settings.GEMINI_API_KEY:
            raise AudioValidationError("GEMINI_API_KEY is missing for Gemini Audio STT.")

        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
        mime = (content_type or "audio/webm").split(";")[0].strip()

        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Transcribe this Indian kirana shopkeeper audio verbatim in Hindi/Hinglish/English. "
                                "Output ONLY the spoken words. If silence or unintelligible noise, output [UNCLEAR]."
                            )
                        },
                        {"inlineData": {"mimeType": mime, "data": b64_audio}},
                    ]
                }
            ]
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=body)

        if resp.status_code != 200:
            raise AudioValidationError("Gemini audio transcription failed. Please retry.")

        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = (parts[0].get("text", "") if parts else "").strip()
        if not text or "[UNCLEAR]" in text.upper():
            return STTResult(text="", detected_language=language_hint, confidence=0.1, provider="gemini_audio", is_unclear=True)

        return STTResult(text=text, detected_language=language_hint, confidence=0.88, provider="gemini_audio")
