import { supabase } from "@/lib/supabase";
import type { LanguageMode } from "@/types/cue";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

let activeAudio: HTMLAudioElement | null = null;
let activeObjectUrl: string | null = null;
let activeController: AbortController | null = null;

function formatForSpeech(text: string, language: LanguageMode): string {
  const rupeeWord = language === "en" ? "rupees" : "rupaye";
  return text
    .replace(/₹\s*([\d,]+(?:\.\d+)?)/g, (_, num: string) => `${num.replace(/,/g, "")} ${rupeeWord}`)
    .replace(/→/g, " to ")
    .replace(/\s+/g, " ")
    .trim();
}

function speakBrowserFallback(text: string, language: LanguageMode): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(formatForSpeech(text, language));
    const voices = window.speechSynthesis.getVoices();

    const preferredLangs =
      language === "hi"
        ? ["hi-IN", "en-IN", "hi", "en"]
        : language === "hinglish"
          ? ["en-IN", "hi-IN", "en-GB", "en"]
          : ["en-IN", "en-US", "en"];

    const naturalMatch = voices.find(
      (v) =>
        preferredLangs.some((code) => v.lang.toLowerCase().startsWith(code.toLowerCase())) &&
        /natural|neural|google|neerja|swara|prabhat/i.test(v.name)
    );
    const fallbackMatch =
      naturalMatch ||
      voices.find((v) =>
        preferredLangs.some((code) => v.lang.toLowerCase().startsWith(code.toLowerCase()))
      );

    if (fallbackMatch) {
      utterance.voice = fallbackMatch;
      utterance.lang = fallbackMatch.lang;
    } else {
      utterance.lang = language === "hi" ? "hi-IN" : "en-IN";
    }

    utterance.rate = 0.96;
    utterance.pitch = 1.02;
    window.speechSynthesis.speak(utterance);
  } catch {
    // Graceful silent fallback when SpeechSynthesis is unavailable
  }
}

export function stopSpeaking(): void {
  if (activeController) {
    activeController.abort();
    activeController = null;
  }
  if (activeAudio) {
    try {
      activeAudio.pause();
      activeAudio.currentTime = 0;
    } catch {
      // ignore
    }
    activeAudio = null;
  }
  if (activeObjectUrl) {
    URL.revokeObjectURL(activeObjectUrl);
    activeObjectUrl = null;
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

/**
 * Natural Indian Neural Voice helper (Microsoft Edge Neural TTS via backend,
 * with graceful Web Speech API fallback when offline or unauthenticated).
 */
export async function speakReply(
  text: string,
  language: LanguageMode = "hinglish",
  enabled = true
): Promise<void> {
  if (!enabled || typeof window === "undefined" || !text.trim()) {
    return;
  }

  stopSpeaking();

  try {
    let token: string | undefined;
    if (supabase) {
      const { data } = await supabase.auth.getSession();
      token = data.session?.access_token;
    }
    if (token && navigator.onLine) {
      const controller = new AbortController();
      activeController = controller;
      const resp = await fetch(`${API_BASE}/voice/tts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ text, language }),
        signal: controller.signal,
      });
      if (resp.ok) {
        const blob = await resp.blob();
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        activeObjectUrl = url;
        const audio = new Audio(url);
        activeAudio = audio;
        audio.onended = () => {
          if (activeObjectUrl === url) {
            URL.revokeObjectURL(url);
            activeObjectUrl = null;
          }
          if (activeAudio === audio) {
            activeAudio = null;
          }
        };
        await audio.play();
        return;
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return;
    }
  }

  speakBrowserFallback(text, language);
}
