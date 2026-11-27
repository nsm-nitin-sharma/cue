"use client";

import React, { useId } from "react";
import type { CueMascotProps } from "@/features/voice/CueMascot";

/** Option 1 ("classic"): Cozy marshmallow plush Cue buddy — preserved intact for instant revert. */
export function CueMascotClassic({ mood, lookX = 0, audioEnergy = 0 }: CueMascotProps) {
  const uid = useId();
  const sheenId = `${uid}-sheen`;
  const bodyId = `${uid}-body`;
  const earId = `${uid}-ear`;
  const clampedX = Math.max(-1, Math.min(1, lookX));

  const stageTransform =
    mood === "idle"
      ? "translate(0px, 34px) scale(0.95)"
      : mood === "typing"
        ? `translate(${(clampedX * 2.5).toFixed(2)}px, 16px) scale(0.98)`
        : mood === "listening"
          ? `translate(0px, 4px) scale(${(1 + audioEnergy * 0.055).toFixed(3)})`
          : "translate(-2px, 8px) scale(0.97)";

  const headTransform =
    mood === "typing"
      ? `translate(${(clampedX * 1.8).toFixed(2)}px, -1px) rotate(${(clampedX * 8.5).toFixed(2)}deg)`
      : mood === "thinking"
        ? "translate(-1px, 0px) rotate(-9deg)"
        : mood === "listening"
          ? "translate(0px, -1px) rotate(0deg)"
          : "translate(0px, 0px) rotate(0deg)";

  const pupilTransform =
    mood === "typing"
      ? `translate(${(clampedX * 4.1).toFixed(2)}px, -3.4px)`
      : mood === "thinking"
        ? "translate(-2.4px, -2.5px)"
        : mood === "listening"
          ? "translate(0px, -0.8px) scale(1.06)"
          : "translate(0px, -0.4px)";

  const earLeftTransform =
    mood === "listening"
      ? "rotate(-20deg) translate(-1px, 0px)"
      : mood === "typing"
        ? `rotate(${(-8 + clampedX * 4).toFixed(1)}deg)`
        : mood === "thinking"
          ? "rotate(-14deg)"
          : "rotate(-10deg)";

  const earRightTransform =
    mood === "listening"
      ? "rotate(20deg) translate(1px, 0px)"
      : mood === "typing"
        ? `rotate(${(8 + clampedX * 4).toFixed(1)}deg)`
        : mood === "thinking"
          ? "rotate(6deg)"
          : "rotate(10deg)";

  const leftPawTransform =
    mood === "listening"
      ? "translate(16px, 48px) rotate(-26deg)"
      : mood === "thinking"
        ? "translate(32px, 77px) rotate(10deg)"
        : mood === "typing"
          ? "translate(34px, 68px) rotate(-8deg)"
          : "translate(33px, 59px) rotate(-8deg)";

  const rightPawTransform =
    mood === "listening"
      ? "translate(84px, 48px) rotate(26deg)"
      : mood === "thinking"
        ? "translate(54.5px, 65px) rotate(-18deg)"
        : mood === "typing"
          ? "translate(66px, 68px) rotate(8deg)"
          : "translate(67px, 59px) rotate(8deg)";

  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="relative z-10 w-full h-full select-none pointer-events-none overflow-visible"
    >
      <defs>
        <radialGradient id={sheenId} cx="50%" cy="22%" r="65%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.11" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={bodyId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="72%" stopColor="#F8FAFC" />
          <stop offset="100%" stopColor="#E2E8F0" />
        </linearGradient>
        <linearGradient id={earId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FFE4E6" />
          <stop offset="100%" stopColor="#FECDD3" />
        </linearGradient>
      </defs>

      <circle cx="50" cy="50" r="49" fill={`url(#${sheenId})`} />

      {(mood === "idle" || mood === "typing") && (
        <path
          d="M 16 90 Q 50 97 84 90"
          fill="none"
          stroke="rgba(255,255,255,0.18)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}

      {mood === "listening" && (
        <g stroke="#FFFFFF" strokeLinecap="round" fill="none">
          <path
            d="M 8 43 Q 4 49 8 55"
            strokeWidth="1.7"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6 }}
          />
          <path
            d="M 92 43 Q 96 49 92 55"
            strokeWidth="1.7"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.35 + audioEnergy * 0.6, animationDelay: "220ms" }}
          />
          {audioEnergy > 0.14 && (
            <>
              <path d="M 4.5 39 Q 0 49 4.5 59" strokeWidth="1.2" strokeOpacity="0.45" />
              <path d="M 95.5 39 Q 100 49 95.5 59" strokeWidth="1.2" strokeOpacity="0.45" />
            </>
          )}
        </g>
      )}

      {mood === "thinking" && (
        <g>
          <circle
            cx="72"
            cy="27"
            r="1.9"
            fill="#F8FAFC"
            className="animate-cue-thought-dot"
            style={{ animationDelay: "0ms" }}
          />
          <circle
            cx="77"
            cy="21"
            r="2.6"
            fill="#FFFFFF"
            className="animate-cue-thought-dot"
            style={{ animationDelay: "200ms" }}
          />
          <circle
            cx="81"
            cy="15.5"
            r="3.2"
            fill="#FFFFFF"
            className="animate-cue-thought-dot"
            style={{ animationDelay: "400ms" }}
          />
        </g>
      )}

      <g className="cue-spring-move" style={{ transform: stageTransform, transformOrigin: "50px 55px" }}>
        <g className={mood === "idle" ? "animate-cue-idle-bob" : mood === "listening" ? "animate-cue-listen-sway" : ""}>
          <path d="M 27 100 C 27 72 36 62 50 62 C 64 62 73 72 73 100 Z" fill={`url(#${bodyId})`} />
          <path
            d="M 52.8 77.5 A 4.2 4.2 0 1 0 52.8 83.2"
            fill="none"
            stroke="#CBD5E1"
            strokeWidth="2.1"
            strokeLinecap="round"
          />

          <g className="cue-gaze-move" style={{ transform: headTransform, transformOrigin: "50px 52px" }}>
            <g className="cue-spring-move" style={{ transform: earLeftTransform, transformOrigin: "26px 47px" }}>
              <ellipse cx="22.5" cy="46.5" rx="7.5" ry="12.5" fill={`url(#${bodyId})`} />
              <ellipse cx="23.2" cy="47" rx="4" ry="8" fill={`url(#${earId})`} />
            </g>

            <g className="cue-spring-move" style={{ transform: earRightTransform, transformOrigin: "74px 47px" }}>
              <g className={mood === "idle" ? "animate-cue-ear-twitch" : ""}>
                <ellipse cx="77.5" cy="46.5" rx="7.5" ry="12.5" fill={`url(#${bodyId})`} />
                <ellipse cx="76.8" cy="47" rx="4" ry="8" fill={`url(#${earId})`} />
              </g>
            </g>

            <path
              d="M 48 26.5 C 45.5 18 54.5 16 56.5 20.5"
              fill="none"
              stroke="#FFFFFF"
              strokeWidth="3.2"
              strokeLinecap="round"
            />

            <rect x="24" y="25" width="52" height="45" rx="22" fill={`url(#${bodyId})`} />
            <path
              d="M 29 61 Q 50 69 71 61"
              fill="none"
              stroke="#E2E8F0"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.7"
            />

            <ellipse cx="32" cy="53.5" rx="4.2" ry="2.5" fill="#FDA4AF" opacity={mood === "listening" ? 0.85 : 0.65} />
            <ellipse cx="68" cy="53.5" rx="4.2" ry="2.5" fill="#FDA4AF" opacity={mood === "listening" ? 0.85 : 0.65} />

            {mood === "thinking" && (
              <>
                <path d="M 35 39 Q 39 36.8 43 38.5" fill="none" stroke="#64748B" strokeWidth="1.6" strokeLinecap="round" />
                <path d="M 57 40.5 Q 61 39.8 65 40.8" fill="none" stroke="#64748B" strokeWidth="1.6" strokeLinecap="round" />
              </>
            )}
            {mood === "typing" && (
              <>
                <path d="M 35.5 39.2 Q 39 37.2 42.5 39" fill="none" stroke="#94A3B8" strokeWidth="1.4" strokeLinecap="round" />
                <path d="M 57.5 39 Q 61 37.2 64.5 39.2" fill="none" stroke="#94A3B8" strokeWidth="1.4" strokeLinecap="round" />
              </>
            )}

            <g className="animate-cue-blink">
              <ellipse cx="39" cy="46.5" rx="5.2" ry="5.8" fill="#F1F5F9" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "39px 46.5px" }}>
                <circle cx="39" cy="46.5" r="4.1" fill="#0F172A" />
                <circle cx="37.6" cy="44.8" r="1.45" fill="#FFFFFF" />
                <circle cx="40.6" cy="48.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            <g className="animate-cue-blink">
              <ellipse cx="61" cy="46.5" rx="5.2" ry="5.8" fill="#F1F5F9" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "61px 46.5px" }}>
                <circle cx="61" cy="46.5" r="4.1" fill="#0F172A" />
                <circle cx="59.6" cy="44.8" r="1.45" fill="#FFFFFF" />
                <circle cx="62.6" cy="48.1" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            {mood === "listening" ? (
              <g>
                <path d="M 45.5 55.2 Q 50 61.2 54.5 55.2 Z" fill="#0F172A" />
                <ellipse cx="50" cy="57.7" rx="2.3" ry="1.2" fill="#FB7185" />
              </g>
            ) : mood === "thinking" ? (
              <path d="M 47.2 57.6 Q 50 56.2 52.8 58" fill="none" stroke="#0F172A" strokeWidth="1.9" strokeLinecap="round" />
            ) : mood === "typing" ? (
              <ellipse cx="50" cy="57.4" rx="1.9" ry="2.2" fill="#0F172A" />
            ) : (
              <path d="M 46.5 56.4 Q 50 59.6 53.5 56.4" fill="none" stroke="#0F172A" strokeWidth="1.9" strokeLinecap="round" />
            )}
          </g>

          {mood === "listening" && (
            <g fill="none" stroke="#F8FAFC" strokeWidth="6" strokeLinecap="round">
              <path d="M 31 71 Q 16 68 17 50" />
              <path d="M 69 71 Q 84 68 83 50" />
            </g>
          )}
          {mood === "thinking" && (
            <g fill="none" stroke="#F8FAFC" strokeWidth="6" strokeLinecap="round">
              <path d="M 31 71 Q 27 75 32 77" />
              <path d="M 69 71 Q 71 75 56 66" />
            </g>
          )}

          <g className="cue-spring-move" style={{ transform: leftPawTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.6" ry="4.4" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1" />
            <ellipse cx="0" cy="-0.4" rx="2.4" ry="1.6" fill="#FFE4E6" opacity="0.85" />
          </g>

          <g className="cue-spring-move" style={{ transform: rightPawTransform, transformOrigin: "0px 0px" }}>
            <ellipse cx="0" cy="0" rx="5.6" ry="4.4" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="1" />
            <ellipse cx="0" cy="-0.4" rx="2.4" ry="1.6" fill="#FFE4E6" opacity="0.85" />
          </g>
        </g>
      </g>
    </svg>
  );
}
