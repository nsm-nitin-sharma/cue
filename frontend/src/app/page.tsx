"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, Volume2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { LivingAcousticOrb } from "@/features/voice/LivingAcousticOrb";
import { ReceiptSlipCard } from "@/features/voice/ReceiptSlipCard";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { speakReply } from "@/lib/tts";

export default function VoiceDeskPage() {
  const {
    activeConversation,
    activeDate,
    setActiveDate,
    conversations,
    selectClarificationCandidate,
    undoReceipt,
    language,
    ttsEnabled,
  } = useCueWorkspace();

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation.entries.length, activeDate]);

  const todayDate = conversations[0]?.date;
  const entries = activeConversation.entries;

  return (
    <AppShell>
      <div className="flex-1 flex flex-col min-h-0 justify-between">
        {/* Quiet History Stream (Centered Editorial Column, Zero Clutter) */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 pt-6 pb-4">
          <div className="max-w-2xl mx-auto">
            {activeDate !== todayDate && todayDate && (
              <div className="mb-6 pb-3 border-b border-rule flex items-center justify-between">
                <p className="text-xs text-ink-secondary">
                  Viewing <span className="font-medium text-ink">{activeConversation.label}</span> ({activeConversation.date})
                </p>
                <button
                  type="button"
                  onClick={() => setActiveDate(todayDate)}
                  className="text-xs font-medium text-vermilion hover:underline"
                >
                  Back to Today
                </button>
              </div>
            )}

            {/* Serene Empty Hero When Day Has Few/No Turns */}
            {entries.length <= 2 && activeDate === todayDate && (
              <div className="mb-10 pt-4 sm:pt-8 text-center">
                <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-muted">
                  Voice-First Business OS
                </p>
                <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-ink mt-2">
                  Just speak your business.
                </h1>
                <p className="text-sm text-ink-secondary mt-2 max-w-md mx-auto leading-relaxed">
                  Record stock, sales, expenses, or ask about udhaar in Hindi, Hinglish, or English.
                </p>
              </div>
            )}

            {/* Editorial Dialogue & Tactile Slips */}
            <div className="space-y-7">
              {entries.map((entry, idx) => {
                const isLatest = idx === entries.length - 1;
                const isUser = entry.role === "user";

                if (isUser) {
                  return (
                    <div
                      key={entry.id}
                      className="flex items-baseline justify-between gap-4 border-l-2 border-vermilion/40 pl-4 py-0.5 animate-slip-in"
                    >
                      <p className="text-[15px] sm:text-base font-medium text-ink leading-snug">
                        &ldquo;{entry.content}&rdquo;
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
                        className={`leading-relaxed text-ink-secondary ${
                          isLatest ? "text-base sm:text-[17px] text-ink font-normal" : "text-sm"
                        }`}
                      >
                        {entry.content}
                      </p>
                      <button
                        type="button"
                        onClick={() => speakReply(entry.content, language, true || ttsEnabled)}
                        className="p-1.5 rounded-full text-ink-muted hover:text-vermilion hover:bg-paper-elevated transition-colors shrink-0"
                        title="Replay voice"
                        aria-label="Replay spoken response"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Focused Clarification Gestures ("Do you mean Coca-Cola?", Price, Variants) */}
                    {entry.clarification?.candidates && entry.clarification.candidates.length > 0 && (
                      <div className="mt-3.5 flex flex-wrap gap-2">
                        {entry.clarification.candidates.map((cand) => (
                          <button
                            key={cand.id}
                            type="button"
                            onClick={() => selectClarificationCandidate(cand)}
                            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-vermilion hover:bg-vermilion-soft/45 transition-all shadow-sm"
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

                    {/* > 30 Days Memory Boundary Link */}
                    {entry.clarification?.kind === "memory_boundary" && (
                      <div className="mt-3">
                        <Link
                          href="/reports"
                          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-ink transition-colors"
                        >
                          Open Permanent Reports
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    )}

                    {/* Tactile Paper-Slip Receipt Card */}
                    {entry.receipt && (
                      <ReceiptSlipCard receipt={entry.receipt} onUndo={undoReceipt} />
                    )}
                  </div>
                );
              })}
            </div>

            <div ref={bottomRef} />
          </div>
        </div>

        {/* Hero Sculptural Living Acoustic Orb (Anchored Bottom-Center) */}
        <LivingAcousticOrb />
      </div>
    </AppShell>
  );
}
