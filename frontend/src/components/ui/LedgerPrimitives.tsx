"use client";

import React from "react";
import { ShieldAlert, X, Check } from "lucide-react";
import { formatINR } from "@/lib/format";
import type { PendingConfirmation } from "@/types/cue";

export function StatusPill({
  tone = "neutral",
  children,
  dot = false,
}: {
  tone?: "neutral" | "sage" | "ochre" | "crimson" | "vermilion";
  children: React.ReactNode;
  dot?: boolean;
}) {
  const styles: Record<string, string> = {
    neutral: "bg-paper-subtle text-ink-secondary border-rule",
    sage: "bg-sage-soft text-sage border-sage/20",
    ochre: "bg-ochre-soft text-ochre border-ochre/20",
    crimson: "bg-crimson-soft text-crimson border-crimson/20",
    vermilion: "bg-vermilion-soft text-vermilion border-vermilion/25",
  };

  const dotColors: Record<string, string> = {
    neutral: "bg-ink-muted",
    sage: "bg-sage",
    ochre: "bg-ochre",
    crimson: "bg-crimson",
    vermilion: "bg-vermilion animate-pulse",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium tracking-wide border ${styles[tone]}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotColors[tone]}`} />}
      {children}
    </span>
  );
}

export function Amount({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  return <span className={`font-mono tabular-nums ${className}`}>{formatINR(value)}</span>;
}

export function ConfirmDrawer({
  confirmation,
  onConfirm,
  onCancel,
}: {
  confirmation: PendingConfirmation | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!confirmation) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-ink/25 backdrop-blur-[2px] p-4">
      <div className="w-full max-w-md bg-paper-elevated border border-rule-strong rounded-2xl shadow-dock p-6 animate-slip-in">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-ochre-soft text-ochre flex items-center justify-center border border-ochre/20">
              <ShieldAlert className="w-4.5 h-4.5" />
            </div>
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-ochre">
                Tier-3 Security Gate · ≥ ₹5,000
              </p>
              <h3 className="text-base font-semibold text-ink">{confirmation.title}</h3>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="p-1.5 rounded-lg text-ink-muted hover:text-ink hover:bg-paper-subtle transition-colors"
            aria-label="Close confirmation"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mt-4 p-4 rounded-xl bg-paper border border-rule space-y-2">
          <div className="flex items-center justify-between text-xs text-ink-secondary">
            <span>Details</span>
            <span className="font-mono text-[11px] text-ink-muted">
              #{confirmation.operationId.slice(0, 8).toUpperCase()}
            </span>
          </div>
          <p className="text-sm font-medium text-ink">{confirmation.description}</p>
          {confirmation.amountINR !== undefined && (
            <div className="pt-2 border-t border-rule flex items-baseline justify-between">
              <span className="text-xs text-ink-secondary">Transaction Value</span>
              <span className="text-xl font-mono font-semibold tabular-nums text-ink">
                {formatINR(confirmation.amountINR)}
              </span>
            </div>
          )}
          <p className="text-xs text-ink-secondary pt-1">{confirmation.impactSummary}</p>
        </div>

        <p className="mt-3 text-xs text-ink-muted">
          You can confirm by saying <span className="font-medium text-ink">&ldquo;Yes&rdquo;</span> or clicking Confirm below.
        </p>

        <div className="mt-5 flex items-center justify-end gap-2.5">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-xl text-xs font-medium text-ink-secondary border border-rule hover:bg-paper-subtle transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium bg-ink text-paper-elevated hover:bg-ink/90 transition-colors"
          >
            <Check className="w-3.5 h-3.5" />
            Confirm & Save
          </button>
        </div>
      </div>
    </div>
  );
}
