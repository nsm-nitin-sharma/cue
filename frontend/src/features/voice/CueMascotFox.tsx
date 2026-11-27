"use client";

import React, { useId } from "react";
import type { CueMascotProps } from "@/features/voice/CueMascot";

/**
 * Option 2 ("fox"): "Kiko" — Warm Tangerine-Cream Chibi Shopkeeper Fox/Cat
 * Completely distinct pointed-ear silhouette, cream cheek tufts, :3 whiskers,
 * espresso-dipped paws, and golden shop-bell collar.
 */
export function CueMascotFox({ mood, lookX = 0, audioEnergy = 0 }: CueMascotProps) {
  const uid = useId();
  const sheenId = `${uid}-sheen`;
  const furId = `${uid}-fur`;
  const creamId = `${uid}-cream`;
  const clampedX = Math.max(-1, Math.min(1, lookX));

  // Fox Choreography: sneaky prowl idle, low crouch slide on typing, keen angled listening, swishing tail think
  const stageTransform =
    mood === "idle"
      ? "translate(0px, 34px) scale(0.95)"
      : mood === "typing"
        ? `translate(${(clampedX * 5.2).toFixed(2)}px, 19px) scale(0.97)`
        : mood === "listening"
          ? `translate(0px, 5px) scale(${(1 + audioEnergy * 0.05).toFixed(3)})`
          : "translate(-2px, 8px) scale(0.97)";

  // Alert fox angles head keenly when listening, stays sleek & focused along crouch when typing
  const headTransform =
    mood === "typing"
      ? `translate(${(clampedX * 2).toFixed(2)}px, -1px) rotate(${(clampedX * 4.5).toFixed(2)}deg)`
      : mood === "thinking"
        ? "translate(-1px, 0px) rotate(-11deg)"
        : mood === "listening"
          ? "translate(0px, -1px) rotate(-4deg)"
          : "translate(0px, 0px) rotate(0deg)";

  // Expressive eye pupil offset
  const pupilTransform =
    mood === "typing"
      ? `translate(${(clampedX * 4.6).toFixed(2)}px, -3.6px)`
      : mood === "thinking"
        ? "translate(2.5px, -2.5px)"
        : mood === "listening"
          ? "translate(0px, -0.7px) scale(1.07)"
          : "translate(0px, -0.3px)";

  // Pointed triangular ear reactions (swept back when prowling/typing, left ear flopped flat when thinking)
  const leftEarTransform =
    mood === "thinking"
      ? "rotate(-42deg) translate(-3px, 3px)"
      : mood === "listening"
        ? "rotate(-12deg) scale(1.06)"
        : mood === "typing"
          ? "rotate(-2deg) scale(1.02)"
          : "rotate(-9deg)";

  const rightEarTransform =
    mood === "thinking"
      ? "rotate(8deg)"
      : mood === "listening"
        ? "rotate(12deg) scale(1.06)"
        : mood === "typing"
          ? "rotate(2deg) scale(1.02)"
          : "rotate(2deg)";

  // Espresso-dipped paw coordinates: cheek scratch when thinking, low crouch grip when typing
  const leftPawTransform =
    mood === "listening"
      ? "translate(17px, 36px) rotate(-32deg)"
      : mood === "thinking"
        ? "translate(32px, 76px) rotate(14deg)"
        : mood === "typing"
          ? "translate(32px, 64px) rotate(-12deg)"
          : "translate(32px, 60px) rotate(-6deg)";

  const rightPawTransform =
    mood === "listening"
      ? "translate(83px, 36px) rotate(32deg)"
      : mood === "thinking"
        ? "translate(63px, 57px) rotate(-32deg)" // Scratches side of cheek
        : mood === "typing"
          ? "translate(68px, 64px) rotate(12deg)"
          : "translate(68px, 60px) rotate(6deg)";

  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="relative z-10 w-full h-full select-none pointer-events-none overflow-visible"
    >
      <defs>
        <radialGradient id={sheenId} cx="50%" cy="22%" r="68%">
          <stop offset="0%" stopColor="#FFF7ED" stopOpacity="0.1" />
          <stop offset="100%" stopColor="#FFF7ED" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={furId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FDBA74" />
          <stop offset="65%" stopColor="#FB923C" />
          <stop offset="100%" stopColor="#EA580C" />
        </linearGradient>
        <linearGradient id={creamId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFDF9" />
          <stop offset="100%" stopColor="#FFEDD5" />
        </linearGradient>
      </defs>

      {/* Soft warm spotlight */}
      <circle cx="50" cy="50" r="49" fill={`url(#${sheenId})`} />

      {/* Subtle bottom rim ledge paws grip in idle / typing */}
      {(mood === "idle" || mood === "typing") && (
        <path
          d="M 16 90 Q 50 97 84 90"
          fill="none"
          stroke="rgba(255,247,237,0.22)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}

      {/* Subtle clean sound ripples near ear tips when listening */}
      {mood === "listening" && (
        <g stroke="#FFF7ED" strokeLinecap="round" fill="none">
          <path
            d="M 11 22 Q 7 28 11 34"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6 }}
          />
          <path
            d="M 89 22 Q 93 28 89 34"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6, animationDelay: "200ms" }}
          />
        </g>
      )}

      {/* Sparkling golden idea stars top-right while thinking */}
      {mood === "thinking" && (
        <g fill="#FDE68A">
          <path d="M 73 24 L 74 26 L 76 27 L 74 28 L 73 30 L 72 28 L 70 27 L 72 26 Z" className="animate-cue-thought-dot" style={{ animationDelay: "0ms" }} />
          <path d="M 78 16.5 L 79.3 19.2 L 82 20.5 L 79.3 21.8 L 78 24.5 L 76.7 21.8 L 74 20.5 L 76.7 19.2 Z" className="animate-cue-thought-dot" style={{ animationDelay: "200ms" }} />
        </g>
      )}

      <g className="cue-spring-move" style={{ transform: stageTransform, transformOrigin: "50px 55px" }}>
        <g className={mood === "idle" ? "animate-fox-prowl" : mood === "listening" ? "animate-cue-listen-sway" : ""}>
          {/* Fluffy Fox Tail peeking & swishing in Thinking */}
          {mood === "thinking" && (
            <g className="animate-fox-tail">
              <path d="M 32 82 Q 12 72 16 56 Q 26 60 32 76 Z" fill="#FB923C" />
              <path d="M 16 56 Q 21 58 23 62 Q 19 64 15.5 60 Z" fill="#FFF7ED" />
            </g>
          )}
          {/* Fox Torso + Scalloped Cream Shopkeeper Chest Bib */}
          <path d="M 30 100 C 30 70 37 62 50 62 C 63 62 70 70 70 100 Z" fill={`url(#${furId})`} />
          <path d="M 39 64 Q 50 67 61 64 L 58 84 L 54 79 L 50 86 L 46 79 L 42 84 Z" fill={`url(#${creamId})`} />

          {/* Shopkeeper Neck Strap + Golden Lucky Bell */}
          <path d="M 35 63.5 Q 50 69 65 63.5" fill="none" stroke="#431407" strokeWidth="2.6" strokeLinecap="round" />
          <g className={mood === "listening" ? "animate-cue-bell" : ""}>
            <circle cx="50" cy="68.5" r="3.6" fill="#FBBF24" stroke="#92400E" strokeWidth="0.8" />
            <circle cx="48.9" cy="67.4" r="1" fill="#FEF3C7" />
            <path d="M 48 69.5 Q 50 70.8 52 69.5" fill="none" stroke="#78350F" strokeWidth="0.9" strokeLinecap="round" />
          </g>

          {/* Sculpted Fox Head + Tall Pointed Ears */}
          <g className="cue-gaze-move" style={{ transform: headTransform, transformOrigin: "50px 50px" }}>
            {/* Left Pointed Fox Ear with Espresso Tip */}
            <g className="cue-spring-move" style={{ transform: leftEarTransform, transformOrigin: "31px 35px" }}>
              <path d="M 23 39 L 19 14 L 41 31 Z" fill="#FB923C" stroke="#EA580C" strokeWidth="0.6" strokeLinejoin="round" />
              <path d="M 21.6 22.8 L 19 14 L 28.4 20.9 Z" fill="#292524" />
              <path d="M 25.5 36 L 23.2 21.5 L 36.2 31 Z" fill={`url(#${creamId})`} />
            </g>

            {/* Right Pointed Fox Ear with Espresso Tip */}
            <g className="cue-spring-move" style={{ transform: rightEarTransform, transformOrigin: "69px 35px" }}>
              <path d="M 77 39 L 81 14 L 59 31 Z" fill="#FB923C" stroke="#EA580C" strokeWidth="0.6" strokeLinejoin="round" />
              <path d="M 78.4 22.8 L 81 14 L 71.6 20.9 Z" fill="#292524" />
              <path d="M 74.5 36 L 76.8 21.5 L 63.8 31 Z" fill={`url(#${creamId})`} />
            </g>

            {/* Head Silhouette with Cute Pointed Cheek Fur Tufts */}
            <path
              d="M 50 28 C 66 28 74 36 74 44 L 81 48 L 76 52.5 L 79 56.5 C 70 63.5 60 66.5 50 66.5 C 40 66.5 30 63.5 21 56.5 L 24 52.5 L 19 48 L 26 44 C 26 36 34 28 50 28 Z"
              fill={`url(#${furId})`}
            />

            {/* Cream Fox Cheek Mask (classic fox V-crest dipping to nose bridge!) */}
            <path
              d="M 22 55.5 Q 32 49 45 54 Q 50 56 55 54 Q 68 49 78 55.5 C 70 63 60 66.5 50 66.5 C 40 66.5 30 63 22 55.5 Z"
              fill={`url(#${creamId})`}
            />

            {/* Little Forehead Flame/Diamond Mark */}
            <path d="M 50 32 L 52.5 36.5 L 50 41 L 47.5 36.5 Z" fill="#FFEDD5" opacity="0.85" />

            {/* Crisp Little Fox Whiskers */}
            <g stroke="#7C2D12" strokeWidth="0.95" strokeLinecap="round" opacity="0.65">
              <path d="M 28 53.5 L 18 52" />
              <path d="M 28 56 L 19 57.5" />
              <path d="M 72 53.5 L 82 52" />
              <path d="M 72 56 L 81 57.5" />
            </g>

            {/* Cute Little Cream Brow Pips (Expressive!) */}
            <ellipse
              cx="38.5"
              cy={mood === "thinking" ? 39 : 40}
              rx="2.3"
              ry="1.2"
              fill="#FFF7ED"
              opacity="0.9"
              transform={mood === "thinking" ? "rotate(-10 38.5 39)" : "rotate(-8 38.5 40)"}
            />
            <ellipse
              cx="61.5"
              cy={mood === "thinking" ? 41 : 40}
              rx="2.3"
              ry="1.2"
              fill="#FFF7ED"
              opacity="0.9"
              transform={mood === "thinking" ? "rotate(12 61.5 41)" : "rotate(8 61.5 40)"}
            />

            {/* Left Expressive Eye */}
            <g className="animate-cue-blink">
              <circle cx="38.5" cy="47.5" r="5.3" fill="#FFFDF9" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "38.5px 47.5px" }}>
                <circle cx="38.5" cy="47.5" r="3.9" fill="#1C1917" />
                <circle cx="37.1" cy="45.9" r="1.45" fill="#FFFFFF" />
                <circle cx="40.1" cy="49.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            {/* Right Expressive Eye */}
            <g className="animate-cue-blink">
              <circle cx="61.5" cy="47.5" r="5.3" fill="#FFFDF9" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "61.5px 47.5px" }}>
                <circle cx="61.5" cy="47.5" r="3.9" fill="#1C1917" />
                <circle cx="60.1" cy="45.9" r="1.45" fill="#FFFFFF" />
                <circle cx="63.1" cy="49.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            {/* Tiny Button Fox Nose */}
            <path d="M 47.6 54.4 Q 50 53.5 52.4 54.4 Q 51.2 56.8 50 57 Q 48.8 56.8 47.6 54.4 Z" fill="#292524" />

            {/* Expressive ":3" Mouth */}
            {mood === "listening" ? (
              <g>
                <path d="M 45.8 58.2 Q 50 64.2 54.2 58.2 Z" fill="#292524" />
                <ellipse cx="50" cy="60.8" rx="2.1" ry="1.1" fill="#FB7185" />
              </g>
            ) : mood === "thinking" ? (
              <path d="M 47.5 60 Q 50 58.6 52.6 60.2" fill="none" stroke="#292524" strokeWidth="1.5" strokeLinecap="round" />
            ) : mood === "typing" ? (
              <ellipse cx="50" cy="60" rx="1.8" ry="2" fill="#292524" />
            ) : (
              <path
                d="M 46.2 58.4 Q 48.1 61 50 58.6 Q 51.9 61 53.8 58.4"
                fill="none"
                stroke="#292524"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
          </g>

          {/* Connecting Fox Arms in Listening & Thinking poses */}
          {mood === "listening" && (
            <g fill="none" stroke="#FB923C" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 32 71 Q 16 62 17.5 38" />
              <path d="M 68 71 Q 84 62 82.5 38" />
            </g>
          )}
          {mood === "thinking" && (
            <g fill="none" stroke="#FB923C" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 32 71 Q 28 74 32 76" />
              <path d="M 68 71 Q 73 66 63 58" />
            </g>
          )}

          {/* Left Espresso-Dipped Paw */}
          <g className="cue-spring-move" style={{ transform: leftPawTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.5" ry="4.4" fill="#292524" stroke="#431407" strokeWidth="0.8" />
            <ellipse cx="0" cy="-0.4" rx="2.2" ry="1.4" fill="#FDA4AF" opacity="0.8" />
          </g>

          {/* Right Espresso-Dipped Paw */}
          <g className="cue-spring-move" style={{ transform: rightPawTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.5" ry="4.4" fill="#292524" stroke="#431407" strokeWidth="0.8" />
            <ellipse cx="0" cy="-0.4" rx="2.2" ry="1.4" fill="#FDA4AF" opacity="0.8" />
          </g>
        </g>
      </g>
    </svg>
  );
}
