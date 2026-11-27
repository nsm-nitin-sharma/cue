"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, ShieldCheck, Activity, ArrowRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";

export default function ReportsPage() {
  const router = useRouter();
  const { todayStats, movements, sales, expenses, submitCommand } = useCueWorkspace();
  const [replayText, setReplayText] = useState(
    "Aaj subah 10 Maggi ke packet beche, kal Ramesh ko 500 udhaar diya, aur bijli bill 1200 diya"
  );

  const handleRunReplay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replayText.trim()) return;
    await submitCommand(replayText);
    router.push("/");
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-7">
          <div>
            <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
              Summaries, Audit &amp; Future BI Foundation
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
              Business Day Replay &amp; Reports
            </h1>
            <p className="text-xs text-ink-secondary mt-1">
              Permanent ledger records across all dates (even beyond the 30-day conversational chat window).
            </p>
          </div>

          {/* Business Day Replay Card */}
          <form
            onSubmit={handleRunReplay}
            className="bg-paper-elevated border border-rule-strong rounded-3xl p-6 shadow-slip space-y-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-ink flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-vermilion" />
                  Business Day Replay
                </h2>
                <p className="text-xs text-ink-secondary mt-0.5">
                  Narrate your full day in one breath — Cue extracts multiple transactions, resolves relative dates (aaj/kal), and builds a summary.
                </p>
              </div>
              <StatusPill tone="sage">Asia/Kolkata</StatusPill>
            </div>

            <textarea
              rows={3}
              value={replayText}
              onChange={(e) => setReplayText(e.target.value)}
              className="w-full px-4 py-3 text-sm rounded-2xl bg-paper border border-rule focus:outline-none focus:border-ink"
            />

            <div className="flex justify-end">
              <button
                type="submit"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium bg-vermilion hover:bg-vermilion-hover text-white transition-colors"
              >
                Process Day Replay in Voice Desk
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>

          {/* Daily Financial Snapshot */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-2xl bg-paper-elevated border border-rule">
              <p className="text-[11px] font-mono uppercase text-ink-muted">Today Sales</p>
              <Amount value={todayStats.salesTotal} className="text-xl font-semibold text-ink mt-1 block" />
            </div>
            <div className="p-4 rounded-2xl bg-paper-elevated border border-rule">
              <p className="text-[11px] font-mono uppercase text-ink-muted">Today Expenses</p>
              <Amount value={todayStats.expensesTotal} className="text-xl font-semibold text-crimson mt-1 block" />
            </div>
            <div className="p-4 rounded-2xl bg-paper-elevated border border-rule">
              <p className="text-[11px] font-mono uppercase text-ink-muted">Total Receivable</p>
              <Amount value={todayStats.outstandingTotal} className="text-xl font-semibold text-ochre mt-1 block" />
            </div>
            <div className="p-4 rounded-2xl bg-paper-elevated border border-rule">
              <p className="text-[11px] font-mono uppercase text-ink-muted">Total Records</p>
              <p className="text-xl font-mono font-semibold tabular-nums text-ink mt-1">
                {sales.length + expenses.length + movements.length}
              </p>
            </div>
          </div>

          {/* Section 10: Future BI Readiness & Immutable Audit Trail */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-5 rounded-2xl bg-paper-elevated border border-rule space-y-2.5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <Activity className="w-4 h-4 text-vermilion" />
                  Business Intelligence Foundation
                </h3>
                <StatusPill tone="neutral">Collecting Data</StatusPill>
              </div>
              <p className="text-xs text-ink-secondary leading-relaxed">
                Clean daily movement velocity, stockout crossings ({todayStats.lowStockProducts.length} active watch items), and transaction date snapshots are being collected for future low-stock forecasting and unusual-sales detection.
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-paper-elevated border border-rule space-y-2.5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-sage" />
                  Immutable Audit Ledger
                </h3>
                <StatusPill tone="sage">Append-Only</StatusPill>
              </div>
              <p className="text-xs text-ink-secondary leading-relaxed">
                Every voice command carries a unique <span className="font-mono">operation_id</span>. Corrections and reversals append compensating entries rather than deleting historical records.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
