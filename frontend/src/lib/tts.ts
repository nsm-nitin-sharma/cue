import type { LanguageMode } from "@/types/cue";

/**
 * Browser SpeechSynthesis helper tuned for Indian English (en-IN) & Hindi (hi-IN).
 * Fails silently and gracefully on headless or voice-less browsers.
 */
export function speakReply(
  text: string,
  language: LanguageMode = "hinglish",
  enabled = true
): void {
  if (!enabled || typeof window === "undefined" || !("speechSynthesis" in window)) {
    return;
  }

  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();

    const preferredLangs =
      language === "hi"
        ? ["hi-IN", "en-IN", "hi", "en"]
        : language === "hinglish"
          ? ["en-IN", "hi-IN", "en-GB", "en"]
          : ["en-IN", "en-US", "en"];

    for (const langCode of preferredLangs) {
      const match = voices.find((v) =>
        v.lang.toLowerCase().startsWith(langCode.toLowerCase())
      );
      if (match) {
        utterance.voice = match;
        utterance.lang = match.lang;
        break;
      }
    }

    if (!utterance.lang) {
      utterance.lang = language === "hi" ? "hi-IN" : "en-IN";
    }

    utterance.rate = 0.98;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  } catch {
    // Graceful silent fallback when SpeechSynthesis is unavailable
  }
}

export function stopSpeaking(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}
