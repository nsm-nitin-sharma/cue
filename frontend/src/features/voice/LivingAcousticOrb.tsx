"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Keyboard, ArrowUp, X, Loader2 } from "lucide-react";
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

export function LivingAcousticOrb() {
  const {
    language,
    voicePhase,
    setVoicePhase,
    statusMessage,
    setStatusMessage,
    submitCommand,
    submitAudioTurn,
    isLiveBackend,
    isOffline,
  } = useCueWorkspace() as ReturnType<typeof useCueWorkspace> & { setStatusMessage?: (m: string) => void };

  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [audioEnergy, setAudioEnergy] = useState(0);
  const [freqBars, setFreqBars] = useState<number[]>([0.2, 0.35, 0.5, 0.35, 0.2]);
  const [showTypeBar, setShowTypeBar] = useState(false);
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
  const discardOnStopRef = useRef<boolean>(false);
  const isRecordingRef = useRef<boolean>(false);

  const cleanupStreams = useCallback(() => {
    isRecordingRef.current = false;
    setIsRecording(false);
    setAudioEnergy(0);
    setFreqBars([0.2, 0.35, 0.5, 0.35, 0.2]);
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    try {
      recognitionRef.current?.stop();
    } catch {
      // Ignore already stopped
    }
    recognitionRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
  }, []);

  const cancelRecording = useCallback(() => {
    discardOnStopRef.current = true;
    const recorder = mediaRecorderRef.current;
    chunksRef.current = [];
    setLiveTranscript("");
    liveTranscriptRef.current = "";
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = () => {
        chunksRef.current = [];
        discardOnStopRef.current = false;
      };
      recorder.stop();
    } else {
      discardOnStopRef.current = false;
    }
    cleanupStreams();
    setVoicePhase("idle");
    if (typeof setStatusMessage === "function") setStatusMessage("Cancelled");
  }, [cleanupStreams, setStatusMessage, setVoicePhase]);

  const stopRecording = useCallback(() => {
    discardOnStopRef.current = false;
    const recorder = mediaRecorderRef.current;
    const capturedText = liveTranscriptRef.current.trim();
    setLiveTranscript("");
    liveTranscriptRef.current = "";

    cleanupStreams();

    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = () => {
        if (discardOnStopRef.current) {
          chunksRef.current = [];
          discardOnStopRef.current = false;
          return;
        }
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
  }, [cleanupStreams, isLiveBackend, setVoicePhase, submitAudioTurn, submitCommand]);

  const startRecording = useCallback(async () => {
    stopSpeaking();
    discardOnStopRef.current = false;
    setMicError(null);
    setLiveTranscript("");
    liveTranscriptRef.current = "";
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
        setAudioEnergy(Math.min(1, avg / 95));
        const bands = [2, 5, 9, 14, 20].map((idx) =>
          Math.max(0.18, Math.min(1, (dataArray[idx] ?? 0) / 140))
        );
        setFreqBars(bands);
        animFrameRef.current = requestAnimationFrame(sampleEnergy);
      };
      sampleEnergy();

      isRecordingRef.current = true;
      setIsRecording(true);
      setVoicePhase("listening");

      // Always enable Web Speech API strictly for live on-screen caption preview while speaking
      const win = window as unknown as {
        SpeechRecognition?: new () => SpeechRecognitionInstanceLike;
        webkitSpeechRecognition?: new () => SpeechRecognitionInstanceLike;
      };
      const SpeechRec = win.SpeechRecognition || win.webkitSpeechRecognition;
      if (SpeechRec) {
        const startPreviewRec = () => {
          if (!isRecordingRef.current) return;
          try {
            const rec = new SpeechRec() as SpeechRecognitionInstanceLike & { onend?: () => void };
            rec.lang = language === "hi" ? "hi-IN" : "en-IN";
            rec.continuous = true;
            rec.interimResults = true;
            rec.onresult = (event) => {
              let combined = "";
              for (let i = 0; i < event.results.length; i += 1) {
                combined += event.results[i][0].transcript + " ";
              }
              const clean = combined.trim();
              if (clean) {
                liveTranscriptRef.current = clean;
                setLiveTranscript(clean);
              }
            };
            rec.onerror = () => {};
            rec.onend = () => {
              if (isRecordingRef.current) {
                setTimeout(startPreviewRec, 120);
              }
            };
            rec.start();
            recognitionRef.current = rec;
          } catch {
            // Ignore caption preview init errors; MediaRecorder still captures audio cleanly
          }
        };
        startPreviewRec();
      }
    } catch {
      cleanupStreams();
      setMicError("Microphone permission required — or use Type command.");
      setShowTypeBar(true);
      setVoicePhase("error");
    }
  }, [cleanupStreams, language, setVoicePhase]);

  const isProcessing = voicePhase === "transcribing" || voicePhase === "validating";

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      if (e.key === "Escape") {
        if (isRecording) {
          e.preventDefault();
          cancelRecording();
          return;
        }
        if (showTypeBar) {
          e.preventDefault();
          setShowTypeBar(false);
          return;
        }
      }
      if (e.key === "/" && !isRecording && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault();
        setShowTypeBar(true);
        return;
      }
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
  }, [cancelRecording, isProcessing, isRecording, showTypeBar, startRecording, stopRecording]);

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
    <div className="relative z-20 pb-5 pt-6 px-4 flex flex-col items-center bg-gradient-to-t from-paper via-paper/95 to-transparent backdrop-blur-[2px]">
      {/* Live Speech Caption + Dynamic Equalizer */}
      {isRecording && (
        <div className="mb-4 max-w-xl text-center bg-paper-elevated/95 border border-rule-strong rounded-2xl px-5 py-3 shadow-dock animate-slip-in">
          <div className="flex items-center justify-center gap-2 mb-1.5">
            <span className="flex items-end gap-0.5 h-3">
              {freqBars.map((b, i) => (
                <span
                  key={i}
                  className="w-0.5 rounded-full bg-vermilion transition-all duration-75"
                  style={{ height: `${Math.round(b * 12)}px` }}
                />
              ))}
            </span>
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-vermilion">
              Listening · Audio Active
            </p>
          </div>
          <p className="text-base sm:text-lg font-medium tracking-tight text-ink leading-snug">
            {liveTranscript || "Listening — speak now (press Esc or Cancel to discard)…"}
          </p>
        </div>
      )}

      {/* Prominent Command Input Bar */}
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

      {/* Precision Enterprise Living Voice Core */}
      <div className="relative flex items-center justify-center my-1">
        <div className="relative flex items-center justify-center">
          {/* Fluid Ambient Rotating Halo */}
          <span
            className={`absolute -inset-3 rounded-full pointer-events-none transition-all duration-300 ${
              isProcessing
                ? "opacity-25 bg-gradient-to-tr from-ochre/25 via-transparent to-vermilion/20 animate-orb-halo"
                : isRecording
                  ? "bg-gradient-to-tr from-vermilion/35 via-ochre/20 to-vermilion/35 blur-md"
                  : "bg-gradient-to-tr from-vermilion/25 via-transparent to-sage/20 blur-[5px] animate-orb-halo"
            }`}
            style={
              isRecording
                ? { transform: `scale(${ring2Scale})`, opacity: 0.45 + audioEnergy * 0.55 }
                : undefined
            }
          />

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
                  ? "Stop and send voice command"
                  : "Start voice command"
            }
            className={`relative w-[76px] h-[76px] rounded-full flex flex-col items-center justify-center overflow-hidden transition-all duration-300 shadow-orb border ${
              isProcessing
                ? "bg-paper-subtle border-rule-strong text-ink-muted cursor-not-allowed scale-95"
                : isRecording
                  ? "bg-gradient-to-b from-vermilion to-[#C93B1F] border-vermilion text-white scale-105"
                  : "bg-gradient-to-b from-[#1E293B] to-ink hover:from-vermilion hover:to-[#C93B1F] border-ink hover:border-vermilion text-white animate-orb-breathe"
            }`}
          >
            {isProcessing ? (
              <Loader2 className="w-6 h-6 animate-spin" />
            ) : isRecording ? (
              <div className="flex items-center justify-center gap-1 h-6">
                {freqBars.map((b, i) => (
                  <span
                    key={i}
                    className="w-1 rounded-full bg-white transition-all duration-75"
                    style={{ height: `${Math.max(6, Math.round(b * 24))}px` }}
                  />
                ))}
              </div>
            ) : (
              <div className="relative flex flex-col items-center justify-center gap-0.5">
                <Mic className="w-5 h-5 stroke-[1.8]" />
                <div className="flex items-end gap-[2px] h-1.5 opacity-75">
                  <span className="w-[2px] h-full rounded-full bg-white/80 animate-orb-wave" style={{ animationDelay: "0ms" }} />
                  <span className="w-[2px] h-full rounded-full bg-white/95 animate-orb-wave" style={{ animationDelay: "180ms" }} />
                  <span className="w-[2px] h-full rounded-full bg-white/80 animate-orb-wave" style={{ animationDelay: "360ms" }} />
                </div>
              </div>
            )}
          </button>
        </div>

        {/* Tactile Type Command Pill (when idle) / Cancel Pill (while speaking) */}
        {isRecording ? (
          <button
            type="button"
            onClick={cancelRecording}
            aria-label="Cancel voice recording"
            className="absolute left-[calc(50%+54px)] inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-medium bg-paper-elevated border border-rule-strong text-ink-secondary hover:text-crimson hover:border-crimson/40 shadow-slip transition-all duration-200 animate-panel-expand active:scale-95"
          >
            <X className="w-3.5 h-3.5" />
            <span>Cancel</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setShowTypeBar((v) => !v)}
            aria-label="Type command"
            aria-expanded={showTypeBar}
            title="Type a command (Press /)"
            className={`absolute left-[calc(50%+54px)] inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-medium border shadow-slip transition-all duration-200 active:scale-95 ${
              showTypeBar
                ? "bg-ink text-paper-elevated border-ink hover:bg-ink/90"
                : "bg-paper-elevated border-rule-strong text-ink hover:border-ink hover:bg-white"
            }`}
          >
            <Keyboard className="w-3.5 h-3.5 shrink-0" />
            <span>Type</span>
            <span
              className={`hidden sm:inline font-mono text-[10px] px-1 py-0.2 rounded ${
                showTypeBar ? "bg-white/15 text-white/80" : "bg-paper-subtle text-ink-muted"
              }`}
            >
              /
            </span>
          </button>
        )}
      </div>

      {/* Institutional Status & Clean Keyboard Hints */}
      <div className="mt-3 flex flex-col items-center gap-1.5">
        <div className="flex items-center gap-2">
          <StatusPill tone={phaseTone} dot={voicePhase === "listening" || isProcessing}>
            {isRecording
              ? "Tap orb to send · Esc to cancel"
              : isProcessing
                ? "Processing..."
                : isOffline
                  ? "Offline Queue Ready"
                  : statusMessage}
          </StatusPill>
          {micError && <span className="text-[11px] text-crimson">{micError}</span>}
        </div>

        <p className="hidden sm:block text-[11px] font-mono text-ink-muted">
          Space · Speak &nbsp;·&nbsp; / · Type &nbsp;·&nbsp; Two-finger swipe · Switch tabs
        </p>
      </div>
    </div>
  );
}
