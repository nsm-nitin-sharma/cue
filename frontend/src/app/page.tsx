"use client";

import React, { useLayoutEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, Volume2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { LivingAcousticOrb } from "@/features/voice/LivingAcousticOrb";
import { ReceiptSlipCard } from "@/features/voice/ReceiptSlipCard";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { speakReply } from "@/lib/tts";

export default function VoiceDeskPage() {
  const {
    store,
    activeConversation,
    activeDate,
    setActiveDate,
    conversations,
    selectClarificationCandidate,
    undoReceipt,
    language,
    ttsEnabled,
  } = useCueWorkspace();

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const hasMountedRef = useRef(false);
  const prevDateRef = useRef<string>(activeDate);
  const prevCountRef = useRef<number>(activeConversation.entries.length);

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    const count = activeConversation.entries.length;
    const isInitialOrDateSwitch =
      !hasMountedRef.current || prevDateRef.current !== activeDate || prevCountRef.current === 0;

    if (isInitialOrDateSwitch) {
      if (container) {
        container.scrollTop = container.scrollHeight;
      } else {
        bottomRef.current?.scrollIntoView({ behavior: "auto" });
      }
      hasMountedRef.current = true;
    } else if (count > prevCountRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }

    prevDateRef.current = activeDate;
    prevCountRef.current = count;
  }, [activeConversation.entries.length, activeDate]);

  const todayDate = conversations[0]?.date;
  const entries = activeConversation.entries;

  return (
    <AppShell>
      <div className="relative flex-1 flex flex-col min-h-0 overflow-hidden">
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 sm:px-8 pt-7 pb-60">
          <div className="max-w-2xl mx-auto">
            {activeDate !== todayDate && todayDate && (
              <div className="mb-6 pb-3 border-b border-rule flex items-center justify-between">
                <p className="text-xs text-ink-secondary">
                  Session: <span className="font-semibold text-ink">{activeConversation.label}</span>{" "}
                  <span className="font-mono text-ink-muted">({activeConversation.date})</span>
                </p>
                <button
                  type="button"
                  onClick={() => setActiveDate(todayDate)}
                  className="text-xs font-medium text-vermilion hover:underline"
                >
                  Return to Today
                </button>
              </div>
            )}

            {/* Authoritative Quiet Studio Header */}
            {entries.length <= 2 && activeDate === todayDate && (
              <div className="mb-9 pt-2 sm:pt-5 border-b border-rule pb-6">
                <p className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted">
                  {store.name} · {activeConversation.date} · IST
                </p>
                <h1 className="text-2xl sm:text-[26px] font-semibold tracking-tight text-ink mt-1.5">
                  Voice Operations Console
                </h1>
                <p className="text-sm text-ink-secondary mt-1 leading-relaxed">
                  Speak naturally in Hindi, Hinglish, or English to record inventory, sales, expenses, or verify customer balances.
                </p>
              </div>
            )}

            {/* Structured Conversational Ledger */}
            <div className="space-y-6">
              {entries.map((entry, idx) => {
                const isLatest = idx === entries.length - 1;
                const isUser = entry.role === "user";

                if (isUser) {
                  return (
                    <div
                      key={entry.id}
                      className="flex items-baseline justify-between gap-4 border-l-2 border-ink pl-3.5 py-0.5 animate-slip-in"
                    >
                      <p className="text-sm sm:text-[15px] font-medium text-ink leading-snug">
                        {entry.content}
                      </p>
                      <span className="text-[10px] font-mono text-ink-muted shrink-0">
                        {entry.timestamp}
                      </span>
                    </div>
                  );
                }

                return (
                  <div
                    key={entry.id}
                    className={`animate-slip-in ${isLatest ? "opacity-100" : "opacity-90"}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p
                        className={`leading-relaxed ${
                          isLatest
                            ? "text-[15px] sm:text-base text-ink font-normal"
                            : "text-sm text-ink-secondary"
                        }`}
                      >
                        {entry.content}
                      </p>
                      <button
                        type="button"
                        onClick={() => speakReply(entry.content, language, true || ttsEnabled)}
                        className="p-1.5 rounded-md text-ink-muted hover:text-vermilion hover:bg-paper-elevated transition-colors shrink-0"
                        title="Replay voice"
                        aria-label="Replay spoken response"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {entry.clarification?.candidates && entry.clarification.candidates.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {entry.clarification.candidates.map((cand) => (
                          <button
                            key={cand.id}
                            type="button"
                            onClick={() => selectClarificationCandidate(cand)}
                            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-vermilion hover:bg-vermilion-soft transition-all shadow-sm"
                          >
                            <span>{cand.label}</span>
                            {cand.meta && (
                              <span className="text-[11px] font-mono text-ink-muted">
                                {cand.meta}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    )}

                    {entry.clarification?.kind === "memory_boundary" && (
                      <div className="mt-3">
                        <Link
                          href="/reports"
                          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-ink transition-colors"
                        >
                          Open Ledger Archive
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    )}

                    {(entry.receipts && entry.receipts.length > 0
                      ? entry.receipts
                      : entry.receipt
                        ? [entry.receipt]
                        : []
                    ).map((slip) => (
                      <ReceiptSlipCard
                        key={slip.id}
                        receipt={slip}
                        onUndo={undoReceipt}
                        storeName={store.name}
                        storeCity={store.city}
                      />
                    ))}
                  </div>
                );
              })}
            </div>

            <div ref={bottomRef} />
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30">
          <div className="pointer-events-auto">
            <LivingAcousticOrb />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
