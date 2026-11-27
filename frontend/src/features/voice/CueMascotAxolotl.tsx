"use client";

import React, { useId } from "react";
import type { CueMascotProps } from "@/features/voice/CueMascot";

/**
 * Option 4 ("axolotl"): "Bloop" — Lilac-Lavender & Coral-Gill Chibi Pond Sprite
 * Wide squishy dome head, 3-frill feathery acoustic side gills on both sides,
 * wide-apart shiny boba eyes, cute curved crown crest & pastel belly.
 */
export function CueMascotAxolotl({ mood, lookX = 0, audioEnergy = 0 }: CueMascotProps) {
  const uid = useId();
  const sheenId = `${uid}-sheen`;
  const skinId = `${uid}-skin`;
  const gillId = `${uid}-gill`;
  const bellyId = `${uid}-belly`;
  const clampedX = Math.max(-1, Math.min(1, lookX));

  const stageTransform =
    mood === "idle"
      ? "translate(0px, 34px) scale(0.95)"
      : mood === "typing"
        ? `translate(${(clampedX * 2.3).toFixed(2)}px, 16px) scale(0.98)`
        : mood === "listening"
          ? `translate(0px, 5px) scale(${(1 + audioEnergy * 0.055).toFixed(3)})`
          : "translate(-2px, 8px) scale(0.97)";

  const headTransform =
    mood === "typing"
      ? `translate(${(clampedX * 1.6).toFixed(2)}px, -1px) rotate(${(clampedX * 8).toFixed(2)}deg)`
      : mood === "thinking"
        ? "translate(-1px, 0px) rotate(-9deg)"
        : mood === "listening"
          ? "translate(0px, -1px) rotate(0deg)"
          : "translate(0px, 0px) rotate(0deg)";

  const pupilTransform =
    mood === "typing"
      ? `translate(${(clampedX * 4).toFixed(2)}px, -3.2px)`
      : mood === "thinking"
        ? "translate(-2.4px, -2.4px)"
        : mood === "listening"
          ? "translate(0px, -0.7px) scale(1.08)"
          : "translate(0px, -0.3px)";

  // 3-frill acoustic side ear-gills flare wide when listening, droop softly when thinking
  const leftGillTransform =
    mood === "listening"
      ? "rotate(-15deg) translate(-1px, 0px) scale(1.06)"
      : mood === "thinking"
        ? "rotate(-12deg) translate(0px, 2px)"
        : mood === "typing"
          ? `rotate(${(clampedX * 4).toFixed(1)}deg)`
          : "rotate(0deg)";

  const rightGillTransform =
    mood === "listening"
      ? "rotate(15deg) translate(1px, 0px) scale(1.06)"
      : mood === "thinking"
        ? "rotate(12deg) translate(0px, 2px)"
        : mood === "typing"
          ? `rotate(${(clampedX * 4).toFixed(1)}deg)`
          : "rotate(0deg)";

  const leftHandTransform =
    mood === "listening"
      ? "translate(16px, 46px) rotate(-24deg)" // Cupping behind left ear-gills
      : mood === "thinking"
        ? "translate(32px, 77px) rotate(12deg)"
        : mood === "typing"
          ? "translate(33px, 68px) rotate(-8deg)"
          : "translate(32px, 60px) rotate(-8deg)"; // Clinging to bottom rim

  const rightHandTransform =
    mood === "listening"
      ? "translate(84px, 46px) rotate(24deg)" // Cupping behind right ear-gills
      : mood === "thinking"
        ? "translate(55px, 64px) rotate(-20deg)" // Finger resting under chin
        : mood === "typing"
          ? "translate(67px, 68px) rotate(8deg)"
          : "translate(68px, 60px) rotate(8deg)"; // Clinging to bottom rim

  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="relative z-10 w-full h-full select-none pointer-events-none overflow-visible"
    >
      <defs>
        <radialGradient id={sheenId} cx="50%" cy="22%" r="68%">
          <stop offset="0%" stopColor="#E9D5FF" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#E9D5FF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={skinId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#EDE9FE" />
          <stop offset="58%" stopColor="#C4B5FD" />
          <stop offset="100%" stopColor="#A78BFA" />
        </linearGradient>
        <linearGradient id={gillId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#F9A8D4" />
          <stop offset="100%" stopColor="#F43F5E" />
        </linearGradient>
        <linearGradient id={bellyId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FAF5FF" />
          <stop offset="100%" stopColor="#F3E8FF" />
        </linearGradient>
      </defs>

      {/* Soft dream-lavender spotlight */}
      <circle cx="50" cy="50" r="49" fill={`url(#${sheenId})`} />

      {/* Bottom ledge Bloop hangs onto in idle / typing */}
      {(mood === "idle" || mood === "typing") && (
        <path
          d="M 16 90 Q 50 97 84 90"
          fill="none"
          stroke="rgba(243,232,255,0.22)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}

      {/* Soft neutral pond-ripple arcs when listening */}
      {mood === "listening" && (
        <g stroke="#FCE7F3" strokeLinecap="round" fill="none">
          <path
            d="M 8 38 Q 4 45 8 52"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6 }}
          />
          <path
            d="M 92 38 Q 96 45 92 52"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6, animationDelay: "220ms" }}
          />
        </g>
      )}

      {/* Floating pearl thought bubbles while thinking */}
      {mood === "thinking" && (
        <g>
          <circle cx="72" cy="26" r="1.9" fill="#F3E8FF" className="animate-cue-thought-dot" style={{ animationDelay: "0ms" }} />
          <circle cx="77" cy="20.5" r="2.5" fill="#FAF5FF" className="animate-cue-thought-dot" style={{ animationDelay: "180ms" }} />
          <circle cx="81" cy="15.5" r="3.1" fill="#FFFFFF" className="animate-cue-thought-dot" style={{ animationDelay: "360ms" }} />
        </g>
      )}

      <g className="cue-spring-move" style={{ transform: stageTransform, transformOrigin: "50px 55px" }}>
        <g className={mood === "idle" ? "animate-cue-idle-bob" : mood === "listening" ? "animate-cue-listen-sway" : ""}>
          {/* Cute Curly Dorsal Fin Tail Peak */}
          <path d="M 65 82 Q 82 78 78 68 Q 74 75 67 74 Z" fill={`url(#${gillId})`} opacity="0.85" />

          {/* Plump Lilac Body & Pastel Oval Belly */}
          <path d="M 29 100 C 29 70 36 62 50 62 C 64 62 71 70 71 100 Z" fill={`url(#${skinId})`} />
          <ellipse cx="50" cy="83" rx="12.5" ry="15" fill={`url(#${bellyId})`} />

          {/* Head + 3-Frill Acoustic Gills */}
          <g className="cue-gaze-move" style={{ transform: headTransform, transformOrigin: "50px 49px" }}>
            {/* Left 3-Frill Feathery Gill-Ear */}
            <g className="cue-spring-move" style={{ transform: leftGillTransform, transformOrigin: "26px 47px" }}>
              <path d="M 27 42 Q 16 33 13 36 Q 14 42 25 46 Z" fill={`url(#${gillId})`} />
              <path d="M 25 47 Q 13 43 11 47 Q 13 52 24 50 Z" fill={`url(#${gillId})`} />
              <path d="M 26 52 Q 16 53 14 57 Q 18 60 27 55 Z" fill={`url(#${gillId})`} />
            </g>

            {/* Right 3-Frill Feathery Gill-Ear */}
            <g className="cue-spring-move" style={{ transform: rightGillTransform, transformOrigin: "74px 47px" }}>
              <path d="M 73 42 Q 84 33 87 36 Q 86 42 75 46 Z" fill={`url(#${gillId})`} />
              <path d="M 75 47 Q 87 43 89 47 Q 87 52 76 50 Z" fill={`url(#${gillId})`} />
              <path d="M 74 52 Q 84 53 86 57 Q 82 60 73 55 Z" fill={`url(#${gillId})`} />
            </g>

            {/* Cute Curly Head Wave Crest */}
            <path d="M 45 29.5 Q 50 21.5 55 29.5" fill={`url(#${gillId})`} />

            {/* Wide Squishy Salamander Dome Head */}
            <rect x="23" y="29" width="54" height="39" rx="19" fill={`url(#${skinId})`} />

            {/* Soft Rosy Coral Cheeks */}
            <ellipse cx="32.5" cy="54.5" rx="3.8" ry="2.2" fill="#F472B6" opacity={mood === "listening" ? 0.8 : 0.55} />
            <ellipse cx="67.5" cy="54.5" rx="3.8" ry="2.2" fill="#F472B6" opacity={mood === "listening" ? 0.8 : 0.55} />

            {/* Characteristic Wide-Apart Boba Eyes */}
            <g className="animate-cue-blink">
              <circle cx="35.5" cy="46.5" r="5" fill="#FAF5FF" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "35.5px 46.5px" }}>
                <circle cx="35.5" cy="46.5" r="3.9" fill="#1E1B4B" />
                <circle cx="34.1" cy="44.9" r="1.4" fill="#FFFFFF" />
                <circle cx="37" cy="48.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            <g className="animate-cue-blink">
              <circle cx="64.5" cy="46.5" r="5" fill="#FAF5FF" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "64.5px 46.5px" }}>
                <circle cx="64.5" cy="46.5" r="3.9" fill="#1E1B4B" />
                <circle cx="63.1" cy="44.9" r="1.4" fill="#FFFFFF" />
                <circle cx="66" cy="48.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            {/* Cute Expressive Axolotl Smile */}
            {mood === "listening" ? (
              <g>
                <path d="M 44 52 Q 50 58.5 56 52 Z" fill="#1E1B4B" />
                <ellipse cx="50" cy="55" rx="2.4" ry="1.2" fill="#FB7185" />
              </g>
            ) : mood === "thinking" ? (
              <path d="M 46.5 54.5 Q 50 52.8 53.5 54.8" fill="none" stroke="#1E1B4B" strokeWidth="1.7" strokeLinecap="round" />
            ) : mood === "typing" ? (
              <ellipse cx="50" cy="54" rx="2" ry="2.2" fill="#1E1B4B" />
            ) : (
              <path d="M 43.5 52 Q 50 56.8 56.5 52" fill="none" stroke="#1E1B4B" strokeWidth="1.8" strokeLinecap="round" />
            )}
          </g>

          {/* Stubby Arms Connecting Shoulder to Cupped Gills / Chin */}
          {mood === "listening" && (
            <g fill="none" stroke="#C4B5FD" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 31 70 Q 17 65 16 48" />
              <path d="M 69 70 Q 83 65 84 48" />
            </g>
          )}
          {mood === "thinking" && (
            <g fill="none" stroke="#C4B5FD" strokeWidth="5.4" strokeLinecap="round">
              <path d="M 31 71 Q 27 75 32 77" />
              <path d="M 69 70 Q 70 73 56 64.5" />
            </g>
          )}

          {/* Left Stubby Lilac Paw */}
          <g className="cue-spring-move" style={{ transform: leftHandTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.2" ry="4.2" fill="#DDD6FE" stroke="#8B5CF6" strokeWidth="0.8" />
            <ellipse cx="0" cy="-0.3" rx="2" ry="1.3" fill="#F9A8D4" opacity="0.8" />
          </g>

          {/* Right Stubby Lilac Paw */}
          <g className="cue-spring-move" style={{ transform: rightHandTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.2" ry="4.2" fill="#DDD6FE" stroke="#8B5CF6" strokeWidth="0.8" />
            <ellipse cx="0" cy="-0.3" rx="2" ry="1.3" fill="#F9A8D4" opacity="0.8" />
          </g>
        </g>
      </g>
    </svg>
  );
}
