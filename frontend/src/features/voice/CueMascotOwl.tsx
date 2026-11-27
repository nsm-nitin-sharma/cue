"use client";

import React, { useId } from "react";
import type { CueMascotProps } from "@/features/voice/CueMascot";

/**
 * Option 3 ("owl"): "Ollie" — Emerald-Teal Feathered Shopkeeper Owl
 * Round brushed-gold reading spectacles, sweeping feathered ear-tufts,
 * creamy heart-shaped facial disc, amber diamond beak & expressive wings.
 */
export function CueMascotOwl({ mood, lookX = 0, audioEnergy = 0 }: CueMascotProps) {
  const uid = useId();
  const sheenId = `${uid}-sheen`;
  const featherId = `${uid}-feather`;
  const wingId = `${uid}-wing`;
  const faceId = `${uid}-face`;
  const clampedX = Math.max(-1, Math.min(1, lookX));

  // Owl Choreography: calm perched micro-swivel in idle, level neck-glide in typing, hovering wing-cup in listening
  const stageTransform =
    mood === "idle"
      ? "translate(0px, 34px) scale(0.95)"
      : mood === "typing"
        ? `translate(${(clampedX * 2.5).toFixed(2)}px, 16px) scale(0.98)`
        : mood === "listening"
          ? `translate(0px, 5px) scale(${(1 + audioEnergy * 0.045).toFixed(3)})`
          : "translate(-2px, 8px) scale(0.97)";

  // Owls keep head level while swiveling glasses horizontally toward text caret!
  const headTransform =
    mood === "typing"
      ? `translate(${(clampedX * 3.4).toFixed(2)}px, -1.5px) rotate(${(clampedX * 3.5).toFixed(2)}deg)`
      : mood === "thinking"
        ? "translate(-1px, 0px) rotate(-11deg)"
        : mood === "listening"
          ? "translate(0px, -1px) rotate(0deg)"
          : "translate(0px, 0px) rotate(0deg)";

  const pupilTransform =
    mood === "typing"
      ? `translate(${(clampedX * 4).toFixed(2)}px, -3.2px)`
      : mood === "thinking"
        ? "translate(-2.4px, -2.2px)"
        : mood === "listening"
          ? "translate(0px, -0.6px) scale(1.08)"
          : "translate(0px, 0px)";

  const leftTuftTransform =
    mood === "listening"
      ? "rotate(-16deg) scale(1.06)"
      : mood === "thinking"
        ? "rotate(-22deg)"
        : mood === "typing"
          ? `rotate(${(clampedX * 5).toFixed(1)}deg)`
          : "rotate(-6deg)";

  const rightTuftTransform =
    mood === "listening"
      ? "rotate(16deg) scale(1.06)"
      : mood === "thinking"
        ? "rotate(4deg)"
        : mood === "typing"
          ? `rotate(${(clampedX * 5).toFixed(1)}deg)`
          : "rotate(6deg)";

  // Curved feathered wings
  const leftWingTransform =
    mood === "listening"
      ? "translate(17px, 33px) rotate(-32deg) scale(0.95)" // Cupping behind left ear-tuft
      : mood === "thinking"
        ? "translate(28px, 75px) rotate(12deg) scale(0.9)" // Folded calmly
        : mood === "typing"
          ? "translate(31px, 66px) rotate(-8deg) scale(0.9)" // Resting on sill
          : "translate(30px, 58px) rotate(-10deg) scale(0.88)"; // Gripping bottom ledge

  const rightWingTransform =
    mood === "listening"
      ? "translate(83px, 33px) rotate(32deg) scale(-0.95, 0.95)" // Cupping behind right ear-tuft
      : mood === "thinking"
        ? "translate(55px, 61px) rotate(-28deg) scale(-0.82, 0.82)" // Wingtip tucked under beak
        : mood === "typing"
          ? "translate(69px, 66px) rotate(8deg) scale(-0.9, 0.9)" // Resting on sill
          : "translate(70px, 58px) rotate(10deg) scale(-0.88, 0.88)"; // Gripping bottom ledge

  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className="relative z-10 w-full h-full select-none pointer-events-none overflow-visible"
    >
      <defs>
        <radialGradient id={sheenId} cx="50%" cy="22%" r="68%">
          <stop offset="0%" stopColor="#99F6E4" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#99F6E4" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={featherId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#2DD4BF" />
          <stop offset="62%" stopColor="#0D9488" />
          <stop offset="100%" stopColor="#0F766E" />
        </linearGradient>
        <linearGradient id={wingId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#14B8A6" />
          <stop offset="100%" stopColor="#115E59" />
        </linearGradient>
        <linearGradient id={faceId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#FEFCE8" />
          <stop offset="100%" stopColor="#FEF3C7" />
        </linearGradient>
      </defs>

      {/* Soft peacock-teal portal glow */}
      <circle cx="50" cy="50" r="49" fill={`url(#${sheenId})`} />

      {/* Subtle ledge in idle / typing */}
      {(mood === "idle" || mood === "typing") && (
        <path
          d="M 16 90 Q 50 97 84 90"
          fill="none"
          stroke="rgba(254,252,232,0.22)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      )}

      {/* Warm golden hoot-wave ripples beside ear-tufts when listening */}
      {mood === "listening" && (
        <g stroke="#FDE68A" strokeLinecap="round" fill="none">
          <path
            d="M 10 21 Q 6 27 10 33"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.4 + audioEnergy * 0.55 }}
          />
          <path
            d="M 90 21 Q 94 27 90 33"
            strokeWidth="1.6"
            className="animate-cue-wave-arc"
            style={{ opacity: 0.4 + audioEnergy * 0.55, animationDelay: "220ms" }}
          />
        </g>
      )}

      {/* Golden wisdom diamond sparks while thinking */}
      {mood === "thinking" && (
        <g fill="#FBBF24">
          <path d="M 73 22.5 L 75 25 L 73 27.5 L 71 25 Z" className="animate-cue-thought-dot" style={{ animationDelay: "0ms" }} />
          <path d="M 79 14.5 L 82 18 L 79 21.5 L 76 18 Z" className="animate-cue-thought-dot" style={{ animationDelay: "220ms" }} />
        </g>
      )}

      <g className="cue-spring-move" style={{ transform: stageTransform, transformOrigin: "50px 55px" }}>
        <g className={mood === "idle" ? "animate-owl-perch" : mood === "listening" ? "animate-owl-hover" : ""}>
          {/* Plump Pear-Shaped Teal Owl Torso */}
          <path d="M 27 100 C 27 65 36 58 50 58 C 64 58 73 65 73 100 Z" fill={`url(#${featherId})`} />

          {/* Creamy Owl Belly & Scalloped Feather Chevrons */}
          <ellipse cx="50" cy="83" rx="14.5" ry="18" fill={`url(#${faceId})`} />
          <g fill="none" stroke="#14B8A6" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" opacity="0.65">
            <path d="M 43 72 L 45.5 74.5 L 48 72" />
            <path d="M 52 72 L 54.5 74.5 L 57 72" />
            <path d="M 47.5 78.5 L 50 81 L 52.5 78.5" />
          </g>

          {/* Tilting Owl Head + Feathered Ear-Tufts + Golden Spectacles */}
          <g className="cue-gaze-move" style={{ transform: headTransform, transformOrigin: "50px 46px" }}>
            {/* Sweeping Left Ear-Tuft */}
            <g className="cue-spring-move" style={{ transform: leftTuftTransform, transformOrigin: "31px 32px" }}>
              <path d="M 28 34 Q 19 20 18 14 Q 28 21 37 29 Z" fill={`url(#${featherId})`} />
              <path d="M 27 31 Q 22 21 20 16.5 Q 26 22 33 28 Z" fill="#99F6E4" opacity="0.7" />
            </g>

            {/* Sweeping Right Ear-Tuft */}
            <g className="cue-spring-move" style={{ transform: rightTuftTransform, transformOrigin: "69px 32px" }}>
              <path d="M 72 34 Q 81 20 82 14 Q 72 21 63 29 Z" fill={`url(#${featherId})`} />
              <path d="M 73 31 Q 78 21 80 16.5 Q 74 22 67 28 Z" fill="#99F6E4" opacity="0.7" />
            </g>

            {/* Round Owl Head */}
            <ellipse cx="50" cy="45" rx="25" ry="20.5" fill={`url(#${featherId})`} />

            {/* Heart-Shaped Creamy Facial Disc */}
            <circle cx="39" cy="45" r="12.5" fill={`url(#${faceId})`} />
            <circle cx="61" cy="45" r="12.5" fill={`url(#${faceId})`} />
            <path d="M 33 54 Q 50 61 67 54 L 50 60 Z" fill={`url(#${faceId})`} />

            {/* Soft Peach Cheeks */}
            <ellipse cx="31.5" cy="51.5" rx="3.2" ry="1.8" fill="#FDA4AF" opacity="0.6" />
            <ellipse cx="68.5" cy="51.5" rx="3.2" ry="1.8" fill="#FDA4AF" opacity="0.6" />

            {/* Expressive Luminous Eyes Inside Glasses */}
            <g className="animate-cue-blink">
              <circle cx="39" cy="45" r="5.5" fill="#FFFFFF" />
              <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "39px 45px" }}>
                <circle cx="39" cy="45" r="4.1" fill="#0F172A" />
                <circle cx="37.6" cy="43.3" r="1.45" fill="#FFFFFF" />
                <circle cx="40.6" cy="46.5" r="0.65" fill="#FFFFFF" opacity="0.85" />
              </g>
            </g>

            <g className="animate-cue-blink">
              <circle cx="61" cy="45" r="5.5" fill="#FFFFFF" />
              {mood === "thinking" ? (
                <path d="M 56.8 45.2 Q 61 42.2 65.2 45.2" fill="none" stroke="#0F172A" strokeWidth="2.1" strokeLinecap="round" />
              ) : (
                <g className="cue-gaze-move" style={{ transform: pupilTransform, transformOrigin: "61px 45px" }}>
                  <circle cx="61" cy="45" r="4.1" fill="#0F172A" />
                  <circle cx="59.6" cy="43.3" r="1.45" fill="#FFFFFF" />
                  <circle cx="62.6" cy="46.5" r="0.65" fill="#FFFFFF" opacity="0.85" />
                </g>
              )}
            </g>

            {/* Iconic Brushed-Gold Reading Spectacles */}
            <g fill="none" stroke="#F59E0B" strokeWidth="1.9" strokeLinecap="round">
              <circle cx="39" cy="45" r="8.6" />
              <circle cx="61" cy="45" r="8.6" />
              <path d="M 47.6 44.5 Q 50 42.5 52.4 44.5" />
            </g>
            {/* Subtle Glass Lens Glints */}
            <path d="M 33.5 40.5 Q 35.5 38.5 38 38.8" fill="none" stroke="rgba(255,255,255,0.65)" strokeWidth="1.1" strokeLinecap="round" />
            <path d="M 55.5 40.5 Q 57.5 38.5 60 38.8" fill="none" stroke="rgba(255,255,255,0.65)" strokeWidth="1.1" strokeLinecap="round" />

            {/* Golden Amber Beak */}
            {mood === "listening" ? (
              <g>
                <path d="M 46.8 49.5 L 53.2 49.5 L 50 53 Z" fill="#F59E0B" />
                <path d="M 47.6 52.5 L 52.4 52.5 L 50 56.5 Z" fill="#D97706" />
                <ellipse cx="50" cy="52.6" rx="1.6" ry="1.1" fill="#451A03" />
              </g>
            ) : (
              <path d="M 46.8 49.2 L 53.2 49.2 L 50 55.2 Z" fill="#F59E0B" stroke="#D97706" strokeWidth="0.6" strokeLinejoin="round" />
            )}
          </g>

          {/* Connecting Feathered Wings in Listening & Thinking */}
          {mood === "listening" && (
            <g fill="none" stroke={`url(#${wingId})`} strokeWidth="5.4" strokeLinecap="round">
              <path d="M 29 69 Q 13 58 17 34" />
              <path d="M 71 69 Q 87 58 83 34" />
            </g>
          )}
          {mood === "thinking" && (
            <g fill="none" stroke={`url(#${wingId})`} strokeWidth="5.2" strokeLinecap="round">
              <path d="M 70 69 Q 72 72 56 61" />
            </g>
          )}

          {/* Left Feathered Wingtip */}
          <g className="cue-spring-move" style={{ transform: leftWingTransform, transformOrigin: "0px 0px" }}>
            <path d="M -5 -4 C -7 1 -4 6 2 5 C 6 4 7 -2 3 -5 Z" fill={`url(#${wingId})`} stroke="#99F6E4" strokeWidth="0.6" />
          </g>

          {/* Right Feathered Wingtip */}
          <g className="cue-spring-move" style={{ transform: rightWingTransform, transformOrigin: "0px 0px" }}>
            <path d="M -5 -4 C -7 1 -4 6 2 5 C 6 4 7 -2 3 -5 Z" fill={`url(#${wingId})`} stroke="#99F6E4" strokeWidth="0.6" />
          </g>
        </g>
      </g>
    </svg>
  );
}
