"use client";

import React from "react";
import { PackagePlus, Check, X, Mic } from "lucide-react";
import type { BaseUnit, NewProductDraft } from "@/types/cue";

export function NewEntityPopup({
  draft,
  onChange,
  onConfirm,
  onCancel,
}: {
  draft: NewProductDraft | null;
  onChange: (next: NewProductDraft) => void;
  onConfirm: (draft: NewProductDraft) => void;
  onCancel: () => void;
}) {
  if (!draft) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-ink/30 backdrop-blur-[2px] p-4">
      <div className="w-full max-w-md bg-paper-elevated border border-rule-strong rounded-xl shadow-dock p-6 animate-slip-in">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-vermilion-soft text-vermilion flex items-center justify-center border border-vermilion/20">
              <PackagePlus className="w-4 h-4" />
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-vermilion">
                Unlisted SKU Detected
              </p>
              <h3 className="text-sm font-semibold text-ink">
                Kya naya product add karun?
              </h3>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="p-1.5 rounded-lg text-ink-muted hover:text-ink hover:bg-paper-subtle transition-colors"
            aria-label="Cancel new product"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="mt-2.5 text-xs text-ink-secondary leading-relaxed">
          &ldquo;{draft.name}&rdquo; catalog mein nahi mila. Verify details and say{" "}
          <span className="font-medium text-ink">&ldquo;Yes / Haan add kar do&rdquo;</span> or click Confirm.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-ink-secondary mb-1">
              Product Name
            </label>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => onChange({ ...draft, name: e.target.value })}
              className="w-full px-3 py-2 text-sm rounded-lg bg-paper border border-rule focus:outline-none focus:border-ink"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-secondary mb-1">
                Opening Qty
              </label>
              <input
                type="number"
                min={0}
                value={draft.quantity}
                onChange={(e) => onChange({ ...draft, quantity: Number(e.target.value) || 0 })}
                className="w-full px-3 py-2 text-sm font-mono tabular-nums rounded-lg bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-ink-secondary mb-1">
                Base Unit
              </label>
              <select
                value={draft.baseUnit}
                onChange={(e) => onChange({ ...draft, baseUnit: e.target.value as BaseUnit })}
                className="w-full px-3 py-2 text-sm rounded-lg bg-paper border border-rule focus:outline-none focus:border-ink"
              >
                <option value="piece">Piece / Bottle</option>
                <option value="packet">Packet</option>
                <option value="kg">Kilogram (kg)</option>
                <option value="litre">Litre (L)</option>
                <option value="box">Box / Peti</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-secondary mb-1">
                Purchase Rate (₹)
              </label>
              <input
                type="number"
                min={0}
                value={draft.costPrice}
                onChange={(e) => onChange({ ...draft, costPrice: e.target.value })}
                className="w-full px-3 py-2 text-sm font-mono tabular-nums rounded-lg bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-ink-secondary mb-1">
                Selling Price (₹)
              </label>
              <input
                type="number"
                min={0}
                value={draft.sellingPrice}
                onChange={(e) => onChange({ ...draft, sellingPrice: e.target.value })}
                className="w-full px-3 py-2 text-sm font-mono tabular-nums rounded-lg bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
            <Mic className="w-3.5 h-3.5 text-vermilion" />
            Say &ldquo;Yes&rdquo; or confirm
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={onCancel}
              className="px-3.5 py-2 rounded-lg text-xs font-medium text-ink-secondary border border-rule hover:bg-paper-subtle transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => onConfirm(draft)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-ink text-white hover:bg-ink/90 transition-colors"
            >
              <Check className="w-3.5 h-3.5" />
              Confirm &amp; Add
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
