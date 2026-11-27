import httpx

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.providers.stt.base import STTProvider, STTResult

_KIRANA_VOCAB_PROMPT = (
    "Indian kirana store conversation in Hindi, Hinglish, and English. "
    "Products: Pepsi, Coca-Cola, Coke, Maggi, Maggie Masala, Tata Salt, Fortune Oil, Amul Milk, Parle-G, Nescafe. "
    "Terms: bottles, packet, gram, peti, box, kilo, litre, cash, online, GPay, Google Pay, PhonePe, Paytm, "
    "udhaar, bik gayi, aayi hain, damaged, expired, bijli bill, Ramesh, Sunita, actually, nahi, payment pending."
)


class GroqWhisperProvider(STTProvider):
    """Zero-PC-load free cloud STT powered by Groq Whisper Large v3 Turbo."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language_hint: str = "hinglish",
    ) -> STTResult:
        settings = get_settings()
        if not settings.GROQ_API_KEY:
            raise AudioValidationError("GROQ_API_KEY is not configured on the server.")

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "User-Agent": "Cue-Backend/1.0",
        }
        files = {
            "file": (filename or "recording.webm", audio_bytes, content_type or "audio/webm"),
        }
        data = {
            "model": settings.GROQ_WHISPER_MODEL,
            "response_format": "verbose_json",
            "prompt": _KIRANA_VOCAB_PROMPT,
            "temperature": "0",
        }
        if language_hint == "hi":
            data["language"] = "hi"
        elif language_hint == "en":
            data["language"] = "en"

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
            )

        if resp.status_code != 200:
            raise AudioValidationError("Speech transcription service temporarily unavailable. Please retry.")

        payload = resp.json()
        text = (payload.get("text") or "").strip()
        segments = payload.get("segments") or []

        # Guard against pure background noise / silence hallucinations
        avg_no_speech = 0.0
        if segments:
            avg_no_speech = sum(float(s.get("no_speech_prob", 0.0)) for s in segments) / len(segments)

        if not text or len(text) < 2 or avg_no_speech > 0.78:
            return STTResult(
                text="",
                detected_language=language_hint,
                confidence=0.1,
                provider="groq_whisper",
                is_unclear=True,
            )

        detected_lang = payload.get("language") or language_hint
        norm_lang = "hi" if detected_lang.startswith("hi") else ("en" if detected_lang == "en" else "hinglish")
        confidence = max(0.05, min(0.99, 1.0 - avg_no_speech))

        return STTResult(
            text=text,
            detected_language=norm_lang,
            confidence=round(confidence, 3),
            provider="groq_whisper",
            is_unclear=False,
        )
