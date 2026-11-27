"use client";

import React, { useState } from "react";
import { RotateCcw, ShieldCheck, ShieldAlert, Clock, History } from "lucide-react";
import { formatINR, formatShortOp } from "@/lib/format";
import { StatusPill } from "@/components/ui/LedgerPrimitives";
import type { ReceiptSlip } from "@/types/cue";

export function ReceiptSlipCard({
  receipt,
  onUndo,
}: {
  receipt: ReceiptSlip;
  onUndo: (operationId: string) => void;
}) {
  const [showAudit, setShowAudit] = useState(false);

  const accentHex =
    receipt.status === "blocked" || receipt.kind === "damage" || receipt.kind === "expiry"
      ? "#B91C1C"
      : receipt.status === "pending_sync" || receipt.status === "corrected"
        ? "#B45309"
        : receipt.status === "undone"
          ? "#667085"
          : "#15803D";

  const pillTone =
    receipt.status === "blocked"
      ? "crimson"
      : receipt.status === "pending_sync" || receipt.status === "corrected"
        ? "ochre"
        : receipt.status === "undone"
          ? "neutral"
          : "sage";

  const statusLabel =
    receipt.status === "pending_sync"
      ? "Pending Sync"
      : receipt.status === "corrected"
        ? "Corrected"
        : receipt.status === "undone"
          ? "Reversed"
          : receipt.status === "blocked"
            ? "Blocked"
            : "Verified";

  return (
    <div
      className="receipt-slip rounded-xl p-4 pl-5 mt-3 max-w-2xl animate-slip-in"
      style={{ "--slip-accent": accentHex } as React.CSSProperties}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {receipt.status === "blocked" ? (
              <ShieldAlert className="w-3.5 h-3.5 text-crimson shrink-0" />
            ) : receipt.status === "pending_sync" ? (
              <Clock className="w-3.5 h-3.5 text-ochre shrink-0" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5 text-sage shrink-0" />
            )}
            <h4 className="text-[13px] font-semibold text-ink tracking-tight">
              {receipt.title}
            </h4>
          </div>
          <p className="text-[11px] text-ink-muted mt-0.5">{receipt.subtitle}</p>
        </div>

        <StatusPill tone={pillTone}>{statusLabel}</StatusPill>
      </div>

      {receipt.lines.length > 0 && (
        <div className="mt-3 pt-2.5 border-t border-rule space-y-1.5">
          {receipt.lines.map((line, idx) => {
            const valTone =
              line.tone === "sage"
                ? "text-sage font-medium"
                : line.tone === "crimson"
                  ? "text-crimson font-medium"
                  : line.tone === "ochre"
                    ? "text-ochre font-medium"
                    : "text-ink";
            return (
              <div key={idx} className="flex items-center justify-between text-xs gap-4">
                <span className="text-ink-secondary">{line.label}</span>
                <span className={`font-mono tabular-nums ${valTone}`}>{line.value}</span>
              </div>
            );
          })}
        </div>
      )}

      {receipt.amountINR !== undefined && (
        <div className="mt-2.5 pt-2.5 border-t border-rule flex items-baseline justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
            Net Amount
          </span>
          <span className="text-base font-mono font-semibold tabular-nums text-ink">
            {formatINR(receipt.amountINR)}
          </span>
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-rule/60 flex items-center justify-between text-[11px] text-ink-muted">
        <div className="flex items-center gap-2 font-mono">
          <span>{formatShortOp(receipt.operationId)}</span>
          <span>·</span>
          <span>{receipt.transactionDate}</span>
        </div>

        <div className="flex items-center gap-1.5">
          {receipt.auditTrail && receipt.auditTrail.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAudit((v) => !v)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md hover:bg-paper-subtle text-ink-secondary transition-colors"
            >
              <History className="w-3 h-3" />
              Audit ({receipt.auditTrail.length})
            </button>
          )}
          {receipt.reversible && receipt.status === "saved" && (
            <button
              type="button"
              onClick={() => onUndo(receipt.operationId)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-rule hover:border-rule-strong hover:bg-paper-subtle text-ink-secondary hover:text-ink transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              Reverse
            </button>
          )}
        </div>
      </div>

      {showAudit && receipt.auditTrail && (
        <div className="mt-2 pt-2 border-t border-rule space-y-1 text-[11px] text-ink-secondary">
          {receipt.auditTrail.map((a, i) => (
            <div key={i} className="flex items-center justify-between font-mono">
              <span>
                [{a.timestamp}] {a.action}
              </span>
              <span className="text-ink-muted">{a.summary}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
