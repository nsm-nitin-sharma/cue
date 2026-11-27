"use client";

import React from "react";
import type { CueMascotProps } from "@/features/voice/CueMascot";

/**
 * Option 2 ("bot"): "Cue-Bit" — Chibi Ceramic Pocket-Bot with glossy digital visor,
 * luminous expressive eyes, glowing spring antenna, ear-cup pods & chest mini-equalizer.
 */
export function CueMascotBot({ mood, lookX = 0, audioEnergy = 0 }: CueMascotProps) {
  const clampedX = Math.max(-1, Math.min(1, lookX));

  // Position inside the 100x100 circular portal
  const stageTransform =
    mood === "idle"
      ? "translate(0px, 34px) scale(0.95)"
      : mood === "typing"
        ? `translate(${(clampedX * 2.2).toFixed(2)}px, 16px) scale(0.98)`
        : mood === "listening"
          ? `translate(0px, 5px) scale(${(1 + audioEnergy * 0.05).toFixed(3)})`
          : "translate(-2px, 8px) scale(0.97)";

  // Head + visor + antenna tilt toward text caret when typing, or sideways when thinking
  const headTransform =
    mood === "typing"
      ? `translate(${(clampedX * 1.6).toFixed(2)}px, -1px) rotate(${(clampedX * 8.5).toFixed(2)}deg)`
      : mood === "thinking"
        ? "translate(-1px, 0px) rotate(-10deg)"
        : mood === "listening"
          ? "translate(0px, -1px) rotate(0deg)"
          : "translate(0px, 0px) rotate(0deg)";

  // Luminous OLED eyes gaze inside the dark visor screen
  const screenGazeTransform =
    mood === "typing"
      ? `translate(${(clampedX * 5.2).toFixed(2)}px, -3.1px)`
      : mood === "thinking"
        ? "translate(-3px, -2.2px)"
        : mood === "listening"
          ? "translate(0px, -0.6px) scale(1.06)"
          : "translate(0px, 0px)";

  // Articulated ceramic pill hands
  const leftHandTransform =
    mood === "listening"
      ? "translate(13.5px, 43px) rotate(-18deg)" // Cupping left ear-pod
      : mood === "thinking"
        ? "translate(31px, 76px) rotate(12deg)" // Relaxed at side
        : mood === "typing"
          ? "translate(33px, 67px) rotate(-8deg)" // Resting on bottom sill
          : "translate(32px, 58px) rotate(-6deg)"; // Clinging to bottom rim

  const rightHandTransform =
    mood === "listening"
      ? "translate(86.5px, 43px) rotate(18deg)" // Cupping right ear-pod
      : mood === "thinking"
        ? "translate(55.5px, 63px) rotate(-22deg)" // Resting under visor chin
        : mood === "typing"
          ? "translate(67px, 67px) rotate(8deg)" // Resting on bottom sill
          : "translate(68px, 58px) rotate(6deg)"; // Clinging to bottom rim

  // Chest equalizer bar heights (5 live bars driven smoothly by audioEnergy)
  const eqHeights = [
    mood === "listening" ? 2.5 + audioEnergy * 4.5 : 2.2,
    mood === "listening" ? 3.5 + audioEnergy * 5.5 : 3.4,
    mood === "listening" ? 4.2 + audioEnergy * 6.0 : 4.5,
    mood === "listening" ? 3.5 + audioEnergy * 5.5 : 3.4,
    mood === "listening" ? 2.5 + audioEnergy * 4.5 : 2.2,
  ];

  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="relative z-10 w-full h-full select-none pointer-events-none overflow-visible"
    >
      <defs>
        <radialGradient id="cueBotStageSheen" cx="50%" cy="20%" r="68%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="cueBotCeramic" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="70%" stopColor="#F8FAFC" />
          <stop offset="100%" stopColor="#E2E8F0" />
        </linearGradient>
        <linearGradient id="cueBotVisor" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#0B1120" />
          <stop offset="100%" stopColor="#162033" />
        </linearGradient>
      </defs>

      {/* Soft neutral spotlight (monochrome stage) */}
      <circle cx="50" cy="50" r="49" fill="url(#cueBotStageSheen)" />

      {/* Bottom rim ledge Cue-Bit hangs onto when peeking */}
      {(mood === "idle" || mood === "typing") && (
        <path
          d="M 16 90 Q 50 97 84 90"
          fill="none"
          stroke="rgba(255,255,255,0.2)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}

      {/* Subtle neutral sound-wave arcs outside ear-pods when listening */}
      {mood === "listening" && (
        <g stroke="#FFFFFF" strokeLinecap="round" fill="none">
          <path
            d="M 8 37 Q 3.5 43 8 49"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6 }}
          />
          <path
            d="M 92 37 Q 96.5 43 92 49"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6, animationDelay: "200ms" }}
          />
        </g>
      )}

      {/* Floating hologram thought dots when thinking */}
      {mood === "thinking" && (
        <g>
          <circle cx="72" cy="24" r="1.9" fill="#F8FAFC" className="animate-cue-thought-dot" style={{ animationDelay: "0ms" }} />
          <circle cx="77.5" cy="18.5" r="2.5" fill="#FFFFFF" className="animate-cue-thought-dot" style={{ animationDelay: "190ms" }} />
          <circle cx="82" cy="13.5" r="3.1" fill="#FFFFFF" className="animate-cue-thought-dot" style={{ animationDelay: "380ms" }} />
        </g>
      )}

      {/* Stage Motion Wrapper */}
      <g className="cue-spring-move" style={{ transform: stageTransform, transformOrigin: "50px 52px" }}>
        <g className={mood === "idle" ? "animate-cue-idle-bob" : mood === "listening" ? "animate-cue-listen-sway" : ""}>
          {/* Cute Rounded Pebble Body */}
          <path d="M 31 100 C 31 70 37 62 50 62 C 63 62 69 70 69 100 Z" fill="url(#cueBotCeramic)" />

          {/* Metallic Neck Ring */}
          <rect x="41" y="59.5" width="18" height="4.5" rx="2.2" fill="#CBD5E1" />

          {/* Chest Mini Acoustic Display Pill */}
          <rect x="40" y="70" width="20" height="10.5" rx="4.2" fill="#0F172A" stroke="#CBD5E1" strokeWidth="0.9" />
          <g fill="#FFFFFF">
            {eqHeights.map((h, i) => (
              <rect
                key={i}
                x={43.6 + i * 2.9}
                y={75.25 - h / 2}
                width="1.6"
                height={h}
                rx="0.8"
                opacity={mood === "thinking" ? 0.55 + (i % 2) * 0.35 : 0.92}
                className={mood === "thinking" ? "animate-cue-thought-dot" : undefined}
                style={mood === "thinking" ? { animationDelay: `${i * 140}ms` } : undefined}
              />
            ))}
          </g>

          {/* Tilting Helmet Head + Acoustic Ear-Pods + Antenna */}
          <g className="cue-gaze-move" style={{ transform: headTransform, transformOrigin: "50px 46px" }}>
            {/* Top Spring Antenna + Glowing Tip */}
            <path d="M 50 23.5 Q 48.5 19 50 15" fill="none" stroke="#CBD5E1" strokeWidth="2.4" strokeLinecap="round" />
            {mood === "listening" && (
              <circle
                cx="50"
                cy="13.5"
                r="6.2"
                fill="none"
                stroke="#FFFFFF"
                strokeWidth="1.2"
                className="animate-cue-wave-arc"
              />
            )}
            <circle cx="50" cy="13.5" r="3.4" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="0.8" />
            <circle cx="49" cy="12.5" r="1.1" fill="#F8FAFC" opacity="0.9" />

            {/* Left Acoustic Headphone Ear-Pod */}
            <g
              className="cue-spring-move"
              style={{
                transform: mood === "listening" ? "translate(-1.5px, 0px) scale(1.06)" : "translate(0px, 0px)",
                transformOrigin: "21px 43px",
              }}
            >
              <rect x="16.5" y="34.5" width="7" height="17" rx="3.5" fill="#CBD5E1" />
              <rect x="18" y="36.5" width="5" height="13" rx="2.5" fill="#FFFFFF" />
            </g>

            {/* Right Acoustic Headphone Ear-Pod */}
            <g
              className="cue-spring-move"
              style={{
                transform: mood === "listening" ? "translate(1.5px, 0px) scale(1.06)" : "translate(0px, 0px)",
                transformOrigin: "79px 43px",
              }}
            >
              <rect x="76.5" y="34.5" width="7" height="17" rx="3.5" fill="#CBD5E1" />
              <rect x="77" y="36.5" width="5" height="13" rx="2.5" fill="#FFFFFF" />
            </g>

            {/* Ceramic Pebble Helmet Shell */}
            <rect x="22" y="23" width="56" height="39" rx="18" fill="url(#cueBotCeramic)" />

            {/* Glossy Dark Digital Visor Screen */}
            <rect x="27" y="28.5" width="46" height="28" rx="12.5" fill="url(#cueBotVisor)" stroke="#334155" strokeWidth="1" />

            {/* Subtle Visor Glass Glare Streak */}
            <path d="M 32 33.2 Q 39 30.8 46.5 31.8" fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="1.5" strokeLinecap="round" />

            {/* Expressive Digital Screen Content (moves smoothly with gaze/caret) */}
            <g className="cue-gaze-move" style={{ transform: screenGazeTransform, transformOrigin: "50px 42.5px" }}>
              {/* Warm Digital Cheek Blush Pips inside visor */}
              <ellipse cx="33" cy="48.8" rx="3.3" ry="1.8" fill="#FDA4AF" opacity={mood === "listening" ? 0.8 : 0.55} />
              <ellipse cx="67" cy="48.8" rx="3.3" ry="1.8" fill="#FDA4AF" opacity={mood === "listening" ? 0.8 : 0.55} />

              {/* Left Luminous OLED Eye + Natural Blink */}
              <g className="animate-cue-blink">
                {mood === "listening" ? (
                  <>
                    <rect x="36.2" y="35.6" width="6.8" height="10.2" rx="3.4" fill="#FFFFFF" />
                    <circle cx="38.2" cy="38.2" r="1.3" fill="#0B1120" opacity="0.25" />
                  </>
                ) : mood === "thinking" ? (
                  <>
                    <rect x="36.5" y="37.2" width="6.2" height="7.4" rx="3.1" fill="#FFFFFF" />
                    <path d="M 35.5 34.5 L 43.2 35.5" stroke="#94A3B8" strokeWidth="1.3" strokeLinecap="round" />
                  </>
                ) : (
                  <rect x="36.5" y="36.4" width="6.2" height="9.2" rx="3.1" fill="#FFFFFF" />
                )}
              </g>

              {/* Right Luminous OLED Eye + Natural Blink */}
              <g className="animate-cue-blink">
                {mood === "listening" ? (
                  <>
                    <rect x="57" y="35.6" width="6.8" height="10.2" rx="3.4" fill="#FFFFFF" />
                    <circle cx="59" cy="38.2" r="1.3" fill="#0B1120" opacity="0.25" />
                  </>
                ) : mood === "thinking" ? (
                  <>
                    <rect x="57.3" y="38.5" width="6.2" height="5.5" rx="2.75" fill="#FFFFFF" />
                    <path d="M 56.8 36.2 L 64 35.4" stroke="#94A3B8" strokeWidth="1.3" strokeLinecap="round" />
                  </>
                ) : (
                  <rect x="57.3" y="36.4" width="6.2" height="9.2" rx="3.1" fill="#FFFFFF" />
                )}
              </g>

              {/* Digital Expression Mouth */}
              {mood === "listening" ? (
                <path d="M 46.5 48.2 Q 50 52.8 53.5 48.2 Z" fill="#FFFFFF" />
              ) : mood === "thinking" ? (
                <path d="M 47.5 49.5 Q 50 48.2 52.5 49.6" fill="none" stroke="#FFFFFF" strokeWidth="1.7" strokeLinecap="round" />
              ) : mood === "typing" ? (
                <circle cx="50" cy="49.2" r="1.9" fill="#FFFFFF" />
              ) : (
                <path d="M 46.5 48.4 Q 50 51.4 53.5 48.4" fill="none" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" />
              )}
            </g>
          </g>

          {/* Connecting Rounded Ceramic Arms in Listening & Thinking poses */}
          {mood === "listening" && (
            <g fill="none" stroke="#F8FAFC" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 32 70 Q 15 66 14 45" />
              <path d="M 68 70 Q 85 66 86 45" />
            </g>
          )}
          {mood === "thinking" && (
            <g fill="none" stroke="#F8FAFC" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 32 70 Q 27 74 31 76" />
              <path d="M 68 70 Q 71 73 57 64" />
            </g>
          )}

          {/* Left Ceramic Pill Hand */}
          <g className="cue-spring-move" style={{ transform: leftHandTransform, transformOrigin: "0px 0px" }}>
            <rect x="-5.4" y="-4" width="10.8" height="8" rx="4" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1" />
            <circle cx="0" cy="0" r="1.6" fill="#E2E8F0" />
          </g>

          {/* Right Ceramic Pill Hand */}
          <g className="cue-spring-move" style={{ transform: rightHandTransform, transformOrigin: "0px 0px" }}>
            <rect x="-5.4" y="-4" width="10.8" height="8" rx="4" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1" />
            <circle cx="0" cy="0" r="1.6" fill="#E2E8F0" />
          </g>
        </g>
      </g>
    </svg>
  );
}
