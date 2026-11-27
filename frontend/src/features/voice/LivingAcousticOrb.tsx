"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Keyboard, ArrowUp, X } from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { StatusPill } from "@/components/ui/LedgerPrimitives";
import { stopSpeaking } from "@/lib/tts";
import { CueMascot, type CueMood } from "@/features/voice/CueMascot";

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

// Toggle to false to immediately revert to the previous compact non-jiggly mic orb
const USE_LARGE_JIGGLY_ORB = true;

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
  const [isActivelyTyping, setIsActivelyTyping] = useState(false);
  const [caretLookX, setCaretLookX] = useState(-0.85);
  const [micError, setMicError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const orbRef = useRef<HTMLButtonElement | null>(null);
  const measureCanvasRef = useRef<HTMLCanvasElement | null>(null);

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

  const updateCaretGaze = useCallback((el: HTMLInputElement | null) => {
    if (!el) return;
    const caretIdx = el.selectionStart ?? el.value.length;
    const textBefore = el.value.slice(0, caretIdx);
    const style = window.getComputedStyle(el);

    if (!measureCanvasRef.current && typeof document !== "undefined") {
      measureCanvasRef.current = document.createElement("canvas");
    }
    const ctx = measureCanvasRef.current?.getContext("2d");
    let textWidthPx = caretIdx * 7.5;
    if (ctx) {
      ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      textWidthPx = ctx.measureText(textBefore).width;
    }

    const inputRect = el.getBoundingClientRect();
    const padLeft = parseFloat(style.paddingLeft) || 0;
    const padRight = parseFloat(style.paddingRight) || 0;
    const innerWidth = Math.max(1, inputRect.width - padLeft - padRight);
    const localCaretX = Math.max(0, Math.min(innerWidth, textWidthPx - el.scrollLeft));
    const caretViewportX = inputRect.left + padLeft + localCaretX;

    const orbCenterX = orbRef.current
      ? orbRef.current.getBoundingClientRect().left + orbRef.current.getBoundingClientRect().width / 2
      : inputRect.left + inputRect.width / 2;

    const halfSpan = Math.max(110, inputRect.width * 0.48);
    const ratio = Math.max(-1, Math.min(1, (caretViewportX - orbCenterX) / halfSpan));
    setCaretLookX(ratio);
  }, []);

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    const cmd = textInput;
    setTextInput("");
    setIsActivelyTyping(false);
    await submitCommand(cmd);
  };

  useEffect(() => {
    if (showTypeBar) {
      setIsActivelyTyping(true);
      requestAnimationFrame(() => updateCaretGaze(inputRef.current));
    } else {
      setIsActivelyTyping(false);
      setCaretLookX(0);
    }
  }, [showTypeBar, updateCaretGaze]);

  const cueMood: CueMood = isRecording
    ? "listening"
    : isProcessing
      ? "thinking"
      : showTypeBar && isActivelyTyping
        ? "typing"
        : "idle";

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

  const ring1Scale = isRecording ? 1.12 + audioEnergy * 0.28 : 1;

  return (
    <div className="relative z-20 pb-5 pt-6 px-4 flex flex-col items-center bg-gradient-to-t from-paper via-paper/95 to-transparent backdrop-blur-[2px]">
      {/* Live Speech Caption + Dynamic Equalizer */}
      {isRecording && (
        <div className="mb-6 max-w-xl text-center bg-paper-elevated/95 border border-rule-strong rounded-2xl px-5 py-3 shadow-dock animate-slip-in">
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
            ref={inputRef}
            type="text"
            autoFocus
            value={textInput}
            onFocus={(e) => {
              setIsActivelyTyping(true);
              updateCaretGaze(e.currentTarget);
            }}
            onBlur={() => setIsActivelyTyping(false)}
            onChange={(e) => {
              setTextInput(e.target.value);
              setIsActivelyTyping(true);
              const target = e.currentTarget;
              updateCaretGaze(target);
              requestAnimationFrame(() => updateCaretGaze(inputRef.current));
            }}
            onKeyUp={(e) => {
              setIsActivelyTyping(true);
              updateCaretGaze(e.currentTarget);
            }}
            onClick={(e) => {
              setIsActivelyTyping(true);
              updateCaretGaze(e.currentTarget);
            }}
            onSelect={(e) => {
              updateCaretGaze(e.currentTarget);
            }}
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

      {/* Living Cue Mascot Voice Core (Monochrome Obsidian Portal — No Red/Blue Gradient Halos) */}
      <div className="relative flex items-center justify-center my-1">
        <div className="relative flex items-center justify-center">
          {/* Subtle neutral monochrome audio ripple only while actively listening */}
          {isRecording && (
            <span
              aria-hidden="true"
              className="absolute w-[106px] h-[106px] rounded-full border border-ink/20 pointer-events-none transition-transform duration-75"
              style={{ transform: `scale(${ring1Scale})`, opacity: 0.2 + audioEnergy * 0.5 }}
            />
          )}

          <button
            ref={orbRef}
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
            className={`group relative ${
              USE_LARGE_JIGGLY_ORB ? "w-[96px] h-[96px]" : "w-[76px] h-[76px]"
            } rounded-full flex flex-col items-center justify-center overflow-hidden shadow-orb border bg-[#0F172A] text-white orb-spring-transition ${
              isProcessing
                ? "border-[#334155] cursor-not-allowed scale-95"
                : isRecording
                  ? "border-[#334155] scale-105"
                  : "border-[#1E293B] hover:border-[#475569] hover:scale-105 active:scale-95"
            }`}
          >
            {/* Subtle top mic glyph when Cue is idling & peeking from below */}
            <Mic
              aria-hidden="true"
              className={`pointer-events-none absolute top-[15px] z-20 w-[18px] h-[18px] text-white/80 stroke-[1.9] transition-all duration-300 ease-out ${
                cueMood === "idle"
                  ? "opacity-90 translate-y-0 scale-100"
                  : "opacity-0 -translate-y-2 scale-75"
              }`}
            />

            {/* Cute Interactive Cue Character */}
            <CueMascot mood={cueMood} lookX={caretLookX} audioEnergy={audioEnergy} />
          </button>
        </div>

        {/* Tactile Type Command Pill (when idle) / Cancel Pill (while speaking) */}
        {isRecording ? (
          <button
            type="button"
            onClick={cancelRecording}
            aria-label="Cancel voice recording"
            className={`absolute ${
              USE_LARGE_JIGGLY_ORB ? "left-[calc(50%+82px)]" : "left-[calc(50%+68px)]"
            } inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-medium bg-paper-elevated border border-rule-strong text-ink-secondary hover:text-crimson hover:border-crimson/40 shadow-slip transition-all duration-200 animate-panel-expand active:scale-95`}
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
            title="Type command"
            className={`absolute ${
              USE_LARGE_JIGGLY_ORB ? "left-[calc(50%+82px)]" : "left-[calc(50%+68px)]"
            } w-10 h-10 rounded-full flex items-center justify-center border shadow-slip transition-all duration-200 active:scale-95 ${
              showTypeBar
                ? "bg-ink text-paper-elevated border-ink hover:bg-ink/90"
                : "bg-paper-elevated border-rule-strong text-ink hover:border-ink hover:bg-white"
            }`}
          >
            <Keyboard className="w-4 h-4 shrink-0" />
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
          Space · Speak &nbsp;·&nbsp; / · Type
        </p>
      </div>
    </div>
  );
}
