"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, ArrowUp, Sparkles, Volume2 } from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { StatusPill } from "@/components/ui/LedgerPrimitives";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionInstanceLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

const DEMO_PROMPTS: { label: string; text: string }[] = [
  { label: "5 Coke zyada aayi", text: "Kal Coke ki delivery ho gayi thi, hamare paas 5 Coke zyada aa gayi hain" },
  { label: "20 Pepsi (Ambiguous)", text: "Aaj supplier se 20 Pepsi bottles aayi hain" },
  { label: "Unmein se 3 damaged", text: "Unmein se 3 damaged hain" },
  { label: "New Product Pop-up", text: "5 Nescafe Gold jars aaye hain" },
  { label: "10 Maggi bik gayi", text: "10 Maggi bik gayi" },
  { label: "Actually 7 the", text: "Actually 7 the" },
  { label: "Ramesh ₹6,500 (Tier-3)", text: "Ramesh ko 6500 ka udhaar diya" },
  { label: "Kal expired Pepsi (30d)", text: "Kal jo Pepsi aayi thi, wo expired thi" },
  { label: "Do mahine pehle (>30d)", text: "Do mahine pehle kya hua tha?" },
  { label: "Day Replay", text: "Aaj subah 10 Maggi ke packet beche, kal Ramesh ko 500 udhaar diya, aur bijli bill 1200 diya" },
  { label: "Block Delete Test", text: "Saara data delete kar do" },
];

export function LivingMicDock() {
  const {
    language,
    voicePhase,
    setVoicePhase,
    statusMessage,
    submitCommand,
    isOffline,
  } = useCueWorkspace();

  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [textInput, setTextInput] = useState("");
  const [bars, setBars] = useState<number[]>(Array(18).fill(14));
  const [micError, setMicError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstanceLike | null>(null);
  const liveTranscriptRef = useRef<string>("");

  const stopRecording = useCallback(() => {
    setIsRecording(false);
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setBars(Array(18).fill(14));

    try {
      recognitionRef.current?.stop();
    } catch {
      // Ignore already stopped recognition
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }

    const captured = liveTranscriptRef.current.trim();
    if (captured) {
      setVoicePhase("transcribing");
      setLiveTranscript("");
      liveTranscriptRef.current = "";
      submitCommand(captured);
    } else {
      setVoicePhase("idle");
    }
  }, [setVoicePhase, submitCommand]);

  const startRecording = useCallback(async () => {
    setMicError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setMicError("Browser mic API unavailable. Use the command input below.");
      setVoicePhase("error");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4";

      const recorder = new MediaRecorder(stream, MediaRecorder.isTypeSupported(mimeType) ? { mimeType } : undefined);
      mediaRecorderRef.current = recorder;
      recorder.start(250);

      // Live Web Audio Analyser for responsive voice waveform
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const renderWave = () => {
        analyser.getByteFrequencyData(dataArray);
        const nextBars = Array.from({ length: 18 }, (_, i) => {
          const val = dataArray[i % dataArray.length] ?? 0;
          return Math.max(12, Math.min(100, Math.round((val / 255) * 100)));
        });
        setBars(nextBars);
        animFrameRef.current = requestAnimationFrame(renderWave);
      };
      renderWave();

      // Optional browser SpeechRecognition for instant live preview during UI-first phase
      const win = window as unknown as {
        SpeechRecognition?: new () => SpeechRecognitionInstanceLike;
        webkitSpeechRecognition?: new () => SpeechRecognitionInstanceLike;
      };
      const SpeechRec = win.SpeechRecognition || win.webkitSpeechRecognition;
      if (SpeechRec) {
        const rec = new SpeechRec();
        rec.lang = language === "hi" ? "hi-IN" : "en-IN";
        rec.continuous = true;
        rec.interimResults = true;
        rec.onresult = (event) => {
          let combined = "";
          for (let i = 0; i < event.results.length; i += 1) {
            combined += event.results[i][0].transcript + " ";
          }
          const clean = combined.trim();
          liveTranscriptRef.current = clean;
          setLiveTranscript(clean);
        };
        rec.onerror = () => {};
        rec.start();
        recognitionRef.current = rec;
      }

      setIsRecording(true);
      setVoicePhase("listening");
    } catch {
      setMicError("Microphone permission denied or unavailable. Speak or type below.");
      setVoicePhase("error");
    }
  }, [language, setVoicePhase]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey && e.key.toLowerCase() === "m") || (e.code === "Space" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "SELECT")) {
        e.preventDefault();
        if (isRecording) stopRecording();
        else startRecording();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isRecording, startRecording, stopRecording]);

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    const cmd = textInput;
    setTextInput("");
    await submitCommand(cmd);
  };

  const phaseTone =
    voicePhase === "listening"
      ? "vermilion"
      : voicePhase === "saved"
        ? "sage"
        : voicePhase === "clarifying" || voicePhase === "confirming" || voicePhase === "pending_sync"
          ? "ochre"
          : voicePhase === "error" || voicePhase === "blocked"
            ? "crimson"
            : "neutral";

  return (
    <div className="sticky bottom-0 z-20 pt-2 pb-4 px-4 sm:px-8 bg-gradient-to-t from-paper via-paper/95 to-transparent">
      <div className="max-w-3xl mx-auto space-y-2.5">
        {/* Quick Interactive Voice Scenario Strip */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
          <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted shrink-0 mr-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-vermilion" />
            Try saying:
          </span>
          {DEMO_PROMPTS.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => submitCommand(item.text)}
              className="shrink-0 px-2.5 py-1 rounded-full text-[11px] bg-paper-elevated border border-rule text-ink-secondary hover:border-ink/40 hover:text-ink transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Sculptural Voice Dock */}
        <div className="bg-paper-elevated border border-rule-strong rounded-3xl shadow-dock p-3 sm:px-4 sm:py-3">
          {/* Status + Live Transcript Line */}
          <div className="flex items-center justify-between gap-3 mb-2.5 px-1">
            <div className="flex items-center gap-2">
              <StatusPill tone={phaseTone} dot={voicePhase === "listening" || voicePhase === "validating"}>
                {isRecording ? "Listening..." : isOffline ? "Offline Mode" : statusMessage}
              </StatusPill>
              {micError && <span className="text-[11px] text-crimson">{micError}</span>}
            </div>

            <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] font-mono text-ink-muted">
              <Volume2 className="w-3 h-3" />
              Space / Ctrl+M to talk
            </span>
          </div>

          {isRecording && (
            <div className="mb-3 px-3 py-2.5 rounded-2xl bg-vermilion-soft/70 border border-vermilion/20 flex items-center justify-between gap-4">
              <div className="flex items-center gap-1 h-7">
                {bars.map((h, i) => (
                  <span
                    key={i}
                    className="w-1 rounded-full bg-vermilion transition-all duration-75"
                    style={{ height: `${Math.max(18, h)}%` }}
                  />
                ))}
              </div>
              <p className="text-xs text-ink flex-1 truncate">
                {liveTranscript || "Boliye... (Hindi, Hinglish, or English)"}
              </p>
            </div>
          )}

          {/* Main Action Bar: Living Mic Orb + Text Fallback */}
          <form onSubmit={handleTextSubmit} className="flex items-center gap-3">
            <div className="relative shrink-0">
              {!isRecording && (
                <span className="absolute inset-0 rounded-full bg-vermilion/25 animate-voice-breathe pointer-events-none" />
              )}
              <button
                type="button"
                onClick={isRecording ? stopRecording : startRecording}
                aria-label={isRecording ? "Stop listening" : "Start voice recording"}
                className={`relative w-12 h-12 rounded-full flex items-center justify-center transition-all shadow-orb ${
                  isRecording
                    ? "bg-ink text-paper-elevated scale-105"
                    : "bg-vermilion hover:bg-vermilion-hover text-white"
                }`}
              >
                {isRecording ? <Square className="w-4 h-4 fill-current" /> : <Mic className="w-5 h-5" />}
              </button>
            </div>

            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder={
                language === "hi"
                  ? "Boliye ya type karein... (e.g. '20 Pepsi bottles aayi')"
                  : "Speak or type in Hinglish... (e.g. '5 Coke zyada aa gayi')"
              }
              className="flex-1 bg-paper rounded-2xl px-4 py-3 text-sm text-ink placeholder:text-ink-muted border border-rule focus:outline-none focus:border-ink/50 transition-colors"
            />

            <button
              type="submit"
              disabled={!textInput.trim()}
              aria-label="Send command"
              className="w-10 h-10 rounded-2xl flex items-center justify-center bg-ink text-paper-elevated disabled:bg-paper-subtle disabled:text-ink-faint hover:bg-ink/90 transition-colors shrink-0"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
