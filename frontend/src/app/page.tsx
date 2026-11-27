"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { CalendarDays, WifiOff, RefreshCw, ArrowRight, Volume2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { LivingMicDock } from "@/features/voice/LivingMicDock";
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
    offlineQueue,
    isOffline,
    syncOfflineQueue,
    language,
    ttsEnabled,
  } = useCueWorkspace();

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation.entries.length, activeDate]);

  const todayDate = conversations[0]?.date;

  return (
    <AppShell showPulseRail>
      <div className="flex-1 flex flex-col min-h-0 paper-grain">
        {/* Day Context Header */}
        <div className="px-4 sm:px-8 py-3 border-b border-rule bg-paper/90 backdrop-blur-sm flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <CalendarDays className="w-4 h-4 text-vermilion shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-semibold text-ink truncate">
                  {activeConversation.label}&apos;s Ledger Chat
                </h1>
                <span className="text-[11px] font-mono text-ink-muted">
                  {activeConversation.date}
                </span>
              </div>
              <p className="text-[11px] text-ink-muted truncate">
                One continuous chat per day · 30-day cross-day memory active
              </p>
            </div>
          </div>

          {activeDate !== todayDate && todayDate && (
            <button
              type="button"
              onClick={() => setActiveDate(todayDate)}
              className="text-xs font-medium text-vermilion hover:underline shrink-0"
            >
              Jump to Today
            </button>
          )}
        </div>

        {/* Offline Queue Banner */}
        {(isOffline || offlineQueue.length > 0) && (
          <div className="mx-4 sm:mx-8 mt-3 px-4 py-2.5 rounded-2xl bg-ochre-soft border border-ochre/25 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 text-xs text-ochre">
              <WifiOff className="w-4 h-4 shrink-0" />
              <span>
                {isOffline
                  ? `Offline Mode active — ${offlineQueue.length} voice command(s) queued in IndexedDB.`
                  : `${offlineQueue.length} offline command(s) ready to sync in FIFO order.`}
              </span>
            </div>
            {!isOffline && offlineQueue.length > 0 && (
              <button
                type="button"
                onClick={() => syncOfflineQueue()}
                className="inline-flex items-center gap-1 text-xs font-medium text-ink bg-paper-elevated px-3 py-1 rounded-xl border border-rule hover:bg-paper transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Sync Now
              </button>
            )}
          </div>
        )}

        {/* Conversational Ledger Stream */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {activeConversation.entries.map((entry) => {
              const isUser = entry.role === "user";
              return (
                <div
                  key={entry.id}
                  className={`flex flex-col ${isUser ? "items-end" : "items-start"} animate-slip-in`}
                >
                  <div className="flex items-center gap-2 mb-1 px-1">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
                      {isUser ? "Owner" : "Cue"}
                    </span>
                    <span className="text-[10px] font-mono text-ink-faint">
                      {entry.timestamp}
                    </span>
                  </div>

                  {isUser ? (
                    <div className="max-w-lg px-4 py-2.5 rounded-2xl rounded-tr-sm bg-ink text-paper-elevated text-sm leading-relaxed shadow-sm">
                      {entry.content}
                    </div>
                  ) : (
                    <div className="w-full max-w-xl">
                      <div className="inline-flex items-start gap-2.5 px-4 py-3 rounded-2xl rounded-tl-sm bg-paper-elevated border border-rule text-sm text-ink leading-relaxed shadow-sm">
                        <p className="flex-1">{entry.content}</p>
                        <button
                          type="button"
                          onClick={() => speakReply(entry.content, language, true || ttsEnabled)}
                          className="p-1 rounded-lg text-ink-muted hover:text-vermilion hover:bg-paper-subtle transition-colors shrink-0 mt-0.5"
                          title="Replay spoken response"
                          aria-label="Replay spoken response"
                        >
                          <Volume2 className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Interactive Clarification Chips ("Do you mean Coca-Cola?", Price chips, Variant chips) */}
                      {entry.clarification?.candidates && entry.clarification.candidates.length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-2">
                          {entry.clarification.candidates.map((cand) => (
                            <button
                              key={cand.id}
                              type="button"
                              onClick={() => selectClarificationCandidate(cand)}
                              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-vermilion hover:bg-vermilion-soft/40 transition-colors shadow-sm"
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

                      {/* > 30 Days Memory Boundary Link to Reports */}
                      {entry.clarification?.kind === "memory_boundary" && (
                        <div className="mt-2.5">
                          <Link
                            href="/reports"
                            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium bg-paper-elevated border border-rule-strong text-ink hover:border-ink transition-colors"
                          >
                            Open Permanent Reports & Ledger
                            <ArrowRight className="w-3.5 h-3.5" />
                          </Link>
                        </div>
                      )}

                      {/* Tactile Paper-Slip Receipt Card */}
                      {entry.receipt && (
                        <ReceiptSlipCard receipt={entry.receipt} onUndo={undoReceipt} />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Bottom Sculptural Living Mic Dock */}
        <LivingMicDock />
      </div>
    </AppShell>
  );
}
