import httpx

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError
from app.core.i18n_replies import romanize_devanagari_to_hinglish
from app.providers.stt.base import STTProvider, STTResult

_PROMPTS_BY_LANG: dict[str, str] = {
    "en": (
        "Indian retail and kirana store conversation in English only. "
        "Products: Pepsi, Coca-Cola, Coke, Maggie Masala 70g, Maggie Masala 250g, Maggie Masala 500g, Chini, Tata Salt, Fortune Oil, Amul Milk, Nescafe Gold, Surf Excel. "
        "Terms: pieces, packets, kg, 70 gram, 250 gram, 500 gram, 750ml, litre, box, cash, online, GPay, Google Pay, PhonePe, Paytm, credit, 5000 each, 10000, sold, received, damaged, expired, returned."
    ),
    "hi": (
        "भारतीय किराना दुकान की बातचीत शुद्ध हिंदी (देवनागरी) में। "
        "प्रोडक्ट्स: पेप्सी, कोका-कोला, मैगी मसाला 70 ग्राम, ढाई सौ ग्राम (250g), पांच सौ ग्राम (500g), चीनी, टाटा नमक, अमूल दूध, नेस्कैफे गोल्ड, सर्फ एक्सेल। "
        "शब्द: दो पैकेट, एक पीस, किलो, सत्तर ग्राम, ढाई सौ ग्राम, पांच सौ ग्राम, पांच हजार, पांच-पांच हजार, दस हजार, लीटर, पेटी, कैश, ऑनलाइन, उधार, बिका, आया, खराब, एक्सपायर, वापस कर गया, 1 किलो के रुपये दिए और 1 किलो उधार।"
    ),
    "hinglish": (
        "Romanized Hinglish kirana conversation written strictly in English Latin letters (a-z), NEVER Devanagari script. "
        "Examples: 'Aaj chini ki kitni sale hui', '2 packet Maggie Masala 250 gram bik gayi', 'Customer 2 Maggie Masala 250 gram wapas kar gaya', "
        "'Maggie Masala 500 nahi 250 gram wali thi', '700 rupee nahi 100 rupee', 'dhai sau gram, paanch sau gram, sattar gram, 70g, 250g, 500g', "
        "'Supplier Sharma ji se 10000 ka maal udhaar aaya', 'Supplier Rahul aur Supplier Gita ko paanch paanch hazaar (5000-5000) ka udhaar diya', "
        "'Nitin ko 2 kg chini bechi, 1 kg ke rupaye diye aur 1 kg udhaar', 'Sorry usne 3 kg chini li thi, 2 kg ke rupaye de diye aur 1 kg udhaar', 'GPay se ek Coca-Cola li', 'Cash nahi online hua tha'."
    ),
}


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
        lang_mode = language_hint if language_hint in {"en", "hi", "hinglish"} else "hinglish"
        data = {
            "model": settings.GROQ_WHISPER_MODEL,
            "response_format": "verbose_json",
            "prompt": _PROMPTS_BY_LANG[lang_mode],
            "temperature": "0",
        }
        if lang_mode == "hi":
            data["language"] = "hi"
        elif lang_mode == "en":
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
        if lang_mode == "hinglish" and text:
            text = romanize_devanagari_to_hinglish(text)
        segments = payload.get("segments") or []

        # Guard against pure background noise / silence hallucinations
        avg_no_speech = 0.0
        if segments:
            avg_no_speech = sum(float(s.get("no_speech_prob", 0.0)) for s in segments) / len(segments)

        if not text or len(text) < 2 or avg_no_speech > 0.78:
            return STTResult(
                text="",
                detected_language=lang_mode,
                confidence=0.1,
                provider="groq_whisper",
                is_unclear=True,
            )

        confidence = max(0.05, min(0.99, 1.0 - avg_no_speech))

        return STTResult(
            text=text,
            detected_language=lang_mode,
            confidence=round(confidence, 3),
            provider="groq_whisper",
            is_unclear=False,
        )
