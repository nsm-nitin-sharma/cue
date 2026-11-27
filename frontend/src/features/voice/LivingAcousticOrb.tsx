"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, Keyboard, ListChecks, ArrowUp, X, Loader2 } from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { StatusPill } from "@/components/ui/LedgerPrimitives";
import { stopSpeaking } from "@/lib/tts";

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

const SAMPLE_FLOWS: { title: string; subtitle: string; text: string }[] = [
  {
    title: "5 Coke zyada aa gayi",
    subtitle: "Triggers 'Do you mean Coca-Cola?' + alias learning + purchase price prompt",
    text: "Kal Coke ki delivery ho gayi thi, hamare paas 5 Coke zyada aa gayi hain",
  },
  {
    title: "20 Pepsi bottles aayi",
    subtitle: "Disambiguates 500ml vs 2L before modifying stock",
    text: "Aaj supplier se 20 Pepsi bottles aayi hain",
  },
  {
    title: "Unmein se 3 damaged hain",
    subtitle: "Contextual follow-up remembering last Pepsi batch (+17 net)",
    text: "Unmein se 3 damaged hain",
  },
  {
    title: "5 Nescafe Gold jars aaye",
    subtitle: "Unlisted item → voice confirmation + New Product Pop-up",
    text: "5 Nescafe Gold jars aaye hain",
  },
  {
    title: "10 Maggi bik gayi → Actually 7 the",
    subtitle: "Speak first, then say 'Actually 7 the' for audited reversal",
    text: "10 Maggi bik gayi",
  },
  {
    title: "Ramesh ko ₹6,500 udhaar diya",
    subtitle: "Duplicate customer disambiguation + ≥ ₹5,000 security gate",
    text: "Ramesh ko 6500 ka udhaar diya",
  },
  {
    title: "Kal jo Pepsi aayi thi, wo expired thi",
    subtitle: "30-day memory retrieves yesterday's Pepsi delivery",
    text: "Kal jo Pepsi aayi thi, wo expired thi",
  },
  {
    title: "Do mahine pehle kya hua tha?",
    subtitle: "Verifies > 30 days conversational memory boundary guard",
    text: "Do mahine pehle kya hua tha?",
  },
  {
    title: "Saara data delete kar do",
    subtitle: "Verifies SecurityPolicyEngine destructive command block",
    text: "Saara data delete kar do",
  },
];

export function LivingAcousticOrb() {
  const {
    language,
    voicePhase,
    setVoicePhase,
    statusMessage,
    submitCommand,
    submitAudioTurn,
    isLiveBackend,
    isOffline,
  } = useCueWorkspace();

  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [audioEnergy, setAudioEnergy] = useState(0);
  const [showTypeBar, setShowTypeBar] = useState(false);
  const [showSamples, setShowSamples] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [micError, setMicError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const mimeTypeRef = useRef<string>("audio/webm");
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstanceLike | null>(null);
  const liveTranscriptRef = useRef<string>("");

  const stopRecording = useCallback(() => {
    setIsRecording(false);
    setAudioEnergy(0);
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    try {
      recognitionRef.current?.stop();
    } catch {
      // Ignore already stopped
    }

    const recorder = mediaRecorderRef.current;
    const capturedText = liveTranscriptRef.current.trim();
    setLiveTranscript("");
    liveTranscriptRef.current = "";

    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeTypeRef.current });
        chunksRef.current = [];
        if (isLiveBackend && blob.size > 400) {
          submitAudioTurn(blob, capturedText);
        } else if (capturedText) {
          setVoicePhase("transcribing");
          submitCommand(capturedText);
        } else {
          setVoicePhase("idle");
        }
      };
      recorder.stop();
    } else if (capturedText) {
      setVoicePhase("transcribing");
      submitCommand(capturedText);
    } else {
      setVoicePhase("idle");
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
  }, [isLiveBackend, setVoicePhase, submitAudioTurn, submitCommand]);

  const startRecording = useCallback(async () => {
    stopSpeaking();
    setMicError(null);
    setShowSamples(false);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setMicError("Microphone unavailable. Use command input.");
      setShowTypeBar(true);
      setVoicePhase("error");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4";

      const recorder = new MediaRecorder(
        stream,
        MediaRecorder.isTypeSupported(mimeType) ? { mimeType } : undefined
      );
      chunksRef.current = [];
      mimeTypeRef.current = mimeType;
      recorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      mediaRecorderRef.current = recorder;
      recorder.start(250);

      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const sampleEnergy = () => {
        analyser.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / Math.max(1, dataArray.length);
        setAudioEnergy(Math.min(1, avg / 110));
        animFrameRef.current = requestAnimationFrame(sampleEnergy);
      };
      sampleEnergy();

      const win = window as unknown as {
        SpeechRecognition?: new () => SpeechRecognitionInstanceLike;
        webkitSpeechRecognition?: new () => SpeechRecognitionInstanceLike;
      };
      const SpeechRec = !(isLiveBackend && !isOffline)
        ? win.SpeechRecognition || win.webkitSpeechRecognition
        : undefined;
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
      setMicError("Microphone permission required — or use Type command.");
      setShowTypeBar(true);
      setVoicePhase("error");
    }
  }, [language, setVoicePhase]);

  const isProcessing = voicePhase === "transcribing" || voicePhase === "validating";

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      if (
        (e.ctrlKey && e.key.toLowerCase() === "m") ||
        (e.code === "Space" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT")
      ) {
        e.preventDefault();
        if (isProcessing) return;
        if (isRecording) stopRecording();
        else startRecording();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isProcessing, isRecording, startRecording, stopRecording]);

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

  const ring1Scale = isRecording ? 1.14 + audioEnergy * 0.36 : 1;
  const ring2Scale = isRecording ? 1.28 + audioEnergy * 0.58 : 1;

  return (
    <div className="relative z-20 pb-6 pt-3 px-4 flex flex-col items-center bg-gradient-to-t from-paper via-paper/95 to-transparent">
      {/* Live Editorial Speech Caption */}
      {isRecording && (
        <div className="mb-5 max-w-xl text-center animate-slip-in">
          <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-vermilion mb-1.5">
            Listening · Audio Stream Active
          </p>
          <p className="text-xl sm:text-2xl font-medium tracking-tight text-ink leading-snug">
            {liveTranscript || "“Speak naturally in Hindi, Hinglish, or English…”"}
          </p>
        </div>
      )}

      {/* Optional Sample Scenarios Popover */}
      {showSamples && (
        <div className="mb-4 w-full max-w-lg bg-paper-elevated border border-rule-strong rounded-xl shadow-dock p-4 animate-slip-in">
          <div className="flex items-center justify-between mb-3 px-1">
            <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
              Verification Scenarios
            </span>
            <button
              type="button"
              onClick={() => setShowSamples(false)}
              className="p-1 rounded-md text-ink-muted hover:text-ink"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1">
            {SAMPLE_FLOWS.map((s) => (
              <button
                key={s.title}
                type="button"
                onClick={() => {
                  setShowSamples(false);
                  submitCommand(s.text);
                }}
                className="w-full text-left px-3 py-2.5 rounded-lg bg-paper hover:bg-vermilion-soft/60 border border-rule hover:border-vermilion/35 transition-colors"
              >
                <p className="text-xs font-semibold text-ink">{s.title}</p>
                <p className="text-[11px] text-ink-muted mt-0.5">{s.subtitle}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Optional Command Input Bar */}
      {showTypeBar && (
        <form
          onSubmit={handleTextSubmit}
          className="mb-4 w-full max-w-lg flex items-center gap-2 bg-paper-elevated border border-rule-strong rounded-xl p-1.5 pl-3.5 shadow-dock animate-slip-in"
        >
          <input
            type="text"
            autoFocus
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Enter Hinglish, Hindi, or English command..."
            className="flex-1 bg-transparent text-sm text-ink placeholder:text-ink-muted focus:outline-none"
          />
          <button
            type="submit"
            disabled={!textInput.trim()}
            className="w-8 h-8 rounded-lg flex items-center justify-center bg-ink text-paper-elevated disabled:bg-paper-subtle disabled:text-ink-faint transition-colors"
          >
            <ArrowUp className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setShowTypeBar(false)}
            className="p-1.5 rounded-lg text-ink-muted hover:text-ink"
            aria-label="Hide typing bar"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </form>
      )}

      {/* Precision Enterprise Voice Console Core */}
      <div className="relative flex items-center justify-center my-1">
        <span
          className={`absolute w-20 h-20 rounded-full border border-vermilion/25 pointer-events-none transition-transform duration-75 ${
            isRecording ? "" : "animate-halo-outer"
          }`}
          style={isRecording ? { transform: `scale(${ring2Scale})`, opacity: 0.25 + audioEnergy * 0.45 } : undefined}
        />

        <span
          className={`absolute w-20 h-20 rounded-full bg-vermilion/10 pointer-events-none transition-transform duration-75 ${
            isRecording ? "" : "animate-halo-idle"
          }`}
          style={isRecording ? { transform: `scale(${ring1Scale})`, opacity: 0.35 + audioEnergy * 0.5 } : undefined}
        />

        <button
          type="button"
          disabled={isProcessing}
          onClick={isRecording ? stopRecording : startRecording}
          aria-label={
            isProcessing
              ? "Processing command"
              : isRecording
                ? "Stop listening"
                : "Start voice command"
          }
          className={`relative w-[74px] h-[74px] rounded-full flex items-center justify-center transition-all duration-300 shadow-orb border ${
            isProcessing
              ? "bg-paper-subtle border-rule-strong text-ink-muted cursor-not-allowed scale-95"
              : isRecording
                ? "bg-vermilion border-vermilion text-white scale-105"
                : "bg-ink hover:bg-vermilion border-ink hover:border-vermilion text-white animate-orb-breathe"
          }`}
        >
          {isProcessing ? (
            <Loader2 className="w-6 h-6 animate-spin" />
          ) : isRecording ? (
            <Square className="w-5 h-5 fill-current" />
          ) : (
            <Mic className="w-6 h-6 stroke-[1.75]" />
          )}
        </button>
      </div>

      {/* Institutional Status & Quiet Actions */}
      <div className="mt-3 flex flex-col items-center gap-2">
        <div className="flex items-center gap-2">
          <StatusPill tone={phaseTone} dot={voicePhase === "listening" || isProcessing}>
            {isRecording
              ? "Listening"
              : isProcessing
                ? "Processing..."
                : isOffline
                  ? "Offline Queue Ready"
                  : statusMessage}
          </StatusPill>
          {micError && <span className="text-[11px] text-crimson">{micError}</span>}
        </div>

        <div className="flex items-center gap-3.5 text-[11px] text-ink-muted">
          <span className="hidden sm:inline font-mono">Space · Speak</span>
          <span className="hidden sm:inline text-rule-strong">·</span>
          <button
            type="button"
            onClick={() => {
              setShowTypeBar((v) => !v);
              setShowSamples(false);
            }}
            className="inline-flex items-center gap-1 hover:text-ink transition-colors"
          >
            <Keyboard className="w-3.5 h-3.5" />
            Type command
          </button>
          <span className="text-rule-strong">·</span>
          <button
            type="button"
            onClick={() => {
              setShowSamples((v) => !v);
              setShowTypeBar(false);
            }}
            className="inline-flex items-center gap-1 hover:text-vermilion transition-colors"
          >
            <ListChecks className="w-3.5 h-3.5 text-ink-secondary" />
            Test scenarios
          </button>
        </div>
      </div>
    </div>
  );
}
