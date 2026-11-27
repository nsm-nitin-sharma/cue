"use client";

import React from "react";
import { CueMascotClassic } from "@/features/voice/CueMascotClassic";
import { CueMascotFox } from "@/features/voice/CueMascotFox";

export type CueMood = "idle" | "typing" | "listening" | "thinking";
export type MascotVariant = "classic" | "fox";

// Change to "classic" to immediately revert back to the first mascot version
export const ACTIVE_MASCOT: MascotVariant = "fox";

export interface CueMascotProps {
  mood: CueMood;
  /** Normalized horizontal caret coordinate: -1 (left) .. 0 (center) .. +1 (right) */
  lookX?: number;
  /** Normalized audio energy: 0 .. 1 during live microphone input */
  audioEnergy?: number;
  /** Optional variant override ("classic" | "fox") */
  variant?: MascotVariant;
}

export function CueMascot({ variant = ACTIVE_MASCOT, ...props }: CueMascotProps) {
  if (variant === "classic") {
    return <CueMascotClassic {...props} />;
  }
  return <CueMascotFox {...props} />;
}

export { CueMascotClassic, CueMascotFox };
