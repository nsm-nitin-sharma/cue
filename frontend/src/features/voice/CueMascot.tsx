"use client";

import React from "react";
import { CueMascotClassic } from "@/features/voice/CueMascotClassic";
import { CueMascotBot } from "@/features/voice/CueMascotBot";

export type CueMood = "idle" | "typing" | "listening" | "thinking";
export type MascotVariant = "classic" | "bot";

// Change to "classic" to immediately revert back to the original marshmallow plush mascot
export const ACTIVE_MASCOT: MascotVariant = "bot";

export interface CueMascotProps {
  mood: CueMood;
  /** Normalized horizontal caret coordinate: -1 (left) .. 0 (center) .. +1 (right) */
  lookX?: number;
  /** Normalized audio energy: 0 .. 1 during live microphone input */
  audioEnergy?: number;
  /** Optional variant override ("classic" | "bot") */
  variant?: MascotVariant;
}

export function CueMascot({ variant = ACTIVE_MASCOT, ...props }: CueMascotProps) {
  if (variant === "classic") {
    return <CueMascotClassic {...props} />;
  }
  return <CueMascotBot {...props} />;
}

export { CueMascotClassic, CueMascotBot };
