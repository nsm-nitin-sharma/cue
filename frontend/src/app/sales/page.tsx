"use client";

import React from "react";
import { RotateCcw } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatShortOp } from "@/lib/format";

export default function SalesPage() {
  const { sales, undoReceipt, todayStats } = useCueWorkspace();

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Revenue &amp; Credit Billing
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Sales Ledger
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Cash, partial, and udhaar bills with business transaction dates separate from entry timestamps.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="px-4 py-2.5 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Today Cash</p>
                <Amount value={todayStats.cashTotal} className="text-sm font-semibold text-sage" />
              </div>
              <div className="px-4 py-2.5 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Today Udhaar</p>
                <Amount value={todayStats.udhaarTotal} className="text-sm font-semibold text-ochre" />
              </div>
            </div>
          </div>

          <div className="bg-paper-elevated border border-rule rounded-2xl shadow-slip overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-rule bg-paper/70 text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                    <th className="py-3 px-4">Biz Date</th>
                    <th className="py-3 px-4">Customer</th>
                    <th className="py-3 px-4">Items</th>
                    <th className="py-3 px-4">Payment</th>
                    <th className="py-3 px-4 text-right">Total</th>
                    <th className="py-3 px-4 text-right">Status</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule text-sm">
                  {sales.map((s) => (
                    <tr key={s.id} className="hover:bg-paper/60 transition-colors">
                      <td className="py-3.5 px-4">
                        <p className="font-mono text-xs text-ink">{s.transactionDate}</p>
                        <p className="font-mono text-[10px] text-ink-muted">{formatShortOp(s.operationId)}</p>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-ink">{s.customerName}</td>
                      <td className="py-3.5 px-4 text-xs text-ink-secondary">
                        {s.items.length > 0
                          ? s.items.map((it) => `${it.quantity} ${it.unit} ${it.productName}`).join(", ")
                          : "Direct credit entry"}
                      </td>
                      <td className="py-3.5 px-4">
                        <StatusPill tone={s.paymentStatus === "paid" ? "sage" : "ochre"}>
                          {s.paymentStatus}
                        </StatusPill>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <Amount value={s.totalAmount} className="font-semibold text-ink" />
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <StatusPill
                          tone={
                            s.status === "active"
                              ? "sage"
                              : s.status === "corrected"
                                ? "ochre"
                                : "neutral"
                          }
                        >
                          {s.status}
                        </StatusPill>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        {s.status !== "voided" && (
                          <button
                            type="button"
                            onClick={() => undoReceipt(s.operationId)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-rule text-xs text-ink-secondary hover:text-ink hover:bg-paper-subtle"
                          >
                            <RotateCcw className="w-3 h-3" />
                            Reverse
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
