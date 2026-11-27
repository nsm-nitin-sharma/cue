"use client";

import React from "react";
import { CueMascotClassic } from "@/features/voice/CueMascotClassic";
import { CueMascotFox } from "@/features/voice/CueMascotFox";
import { CueMascotOwl } from "@/features/voice/CueMascotOwl";
import { CueMascotAxolotl } from "@/features/voice/CueMascotAxolotl";
import type { MascotVariant } from "@/types/cue";

export type CueMood = "idle" | "typing" | "listening" | "thinking";
export type { MascotVariant };

export const ACTIVE_MASCOT: MascotVariant = "fox";

export const MASCOT_CATALOG: { id: MascotVariant; name: string; tagline: string }[] = [
  { id: "fox", name: "Kiko", tagline: "Shopkeeper fox" },
  { id: "owl", name: "Ollie", tagline: "Spectacled owl" },
  { id: "axolotl", name: "Bloop", tagline: "Lilac pond sprite" },
  { id: "classic", name: "Cue", tagline: "Original plush buddy" },
];

export interface CueMascotProps {
  mood: CueMood;
  /** Normalized horizontal caret coordinate: -1 (left) .. 0 (center) .. +1 (right) */
  lookX?: number;
  /** Normalized audio energy: 0 .. 1 during live microphone input */
  audioEnergy?: number;
  /** Optional variant override */
  variant?: MascotVariant;
}

export function CueMascot({ variant = ACTIVE_MASCOT, ...props }: CueMascotProps) {
  switch (variant) {
    case "classic":
      return <CueMascotClassic {...props} />;
    case "owl":
      return <CueMascotOwl {...props} />;
    case "axolotl":
      return <CueMascotAxolotl {...props} />;
    case "fox":
    default:
      return <CueMascotFox {...props} />;
  }
}

export { CueMascotClassic, CueMascotFox, CueMascotOwl, CueMascotAxolotl };
