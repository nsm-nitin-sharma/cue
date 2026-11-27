"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarDays,
  Wifi,
  WifiOff,
  Volume2,
  VolumeX,
  SlidersHorizontal,
  X,
  ShieldCheck,
  AlertTriangle,
  Crown,
  LogIn,
  Mic,
} from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatINR } from "@/lib/format";
import { StatusPill, ConfirmDrawer } from "@/components/ui/LedgerPrimitives";
import { NewEntityPopup } from "@/features/voice/NewEntityPopup";
import type { LanguageMode } from "@/types/cue";

const NAV_TABS = [
  { href: "/", label: "Voice" },
  { href: "/inventory", label: "Stock" },
  { href: "/sales", label: "Sales" },
  { href: "/customers", label: "Khata" },
  { href: "/expenses", label: "Expenses" },
  { href: "/reports", label: "Reports" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);

  const {
    store,
    language,
    setLanguage,
    ttsEnabled,
    setTtsEnabled,
    isOffline,
    setIsOffline,
    conversations,
    activeDate,
    setActiveDate,
    activeConversation,
    offlineQueue,
    todayStats,
    newProductDraft,
    setNewProductDraft,
    confirmNewProductFromModal,
    dismissNewProductModal,
    pendingConfirmation,
    confirmPendingHighValue,
    cancelPendingHighValue,
  } = useCueWorkspace();

  const tierLabel =
    store.tier === "free" ? "Free" : store.tier === "growth" ? "Growth" : "Pro";

  return (
    <div className="min-h-screen flex flex-col bg-paper text-ink relative">
      {/* Ultra-Minimal Floating Top Bar */}
      <header className="sticky top-0 z-30 h-16 px-4 sm:px-8 flex items-center justify-between gap-4 bg-paper/85 backdrop-blur-md border-b border-rule/70">
        {/* Left: Wordmark + 30-Day Calendar Selector */}
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/" className="flex items-center gap-2 shrink-0 group">
            <span className="w-2.5 h-2.5 rounded-full bg-vermilion group-hover:scale-125 transition-transform" />
            <span className="text-[15px] font-semibold tracking-tight text-ink">Cue</span>
          </Link>

          <span className="text-rule-strong hidden sm:inline">/</span>

          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs text-ink-secondary hover:text-ink bg-paper-elevated border border-rule hover:border-rule-strong transition-colors"
            title="Open 30-day daily ledger history"
          >
            <CalendarDays className="w-3.5 h-3.5 text-vermilion" />
            <span className="font-medium text-ink">{activeConversation.label}</span>
            <span className="font-mono text-[11px] text-ink-muted">{activeConversation.date.slice(5)}</span>
          </button>
        </div>

        {/* Center: Clean Floating Navigation Dock */}
        <nav className="hidden md:flex items-center p-1 rounded-full bg-paper-elevated border border-rule shadow-sm">
          {NAV_TABS.map((tab) => {
            const active = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all ${
                  active
                    ? "bg-ink text-paper-elevated shadow-sm"
                    : "text-ink-secondary hover:text-ink"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        {/* Right: Quiet Today Ticker + Register / Controls Drawer Trigger */}
        <div className="flex items-center gap-2">
          {(isOffline || offlineQueue.length > 0) && (
            <button
              type="button"
              onClick={() => setRegisterOpen(true)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-medium bg-ochre-soft text-ochre border border-ochre/25"
            >
              <WifiOff className="w-3 h-3" />
              <span>{offlineQueue.length} queued</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setRegisterOpen(true)}
            className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full text-xs bg-paper-elevated border border-rule hover:border-rule-strong transition-colors shadow-sm"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-sage" />
            <span className="font-mono tabular-nums font-medium text-ink">
              {formatINR(todayStats.salesTotal)}
            </span>
            {todayStats.lowStockProducts.length > 0 && (
              <span className="hidden sm:inline text-[11px] text-ochre font-mono">
                · {todayStats.lowStockProducts.length} low
              </span>
            )}
            <SlidersHorizontal className="w-3.5 h-3.5 text-ink-muted" />
          </button>
        </div>
      </header>

      {/* Mobile Compact Route Strip */}
      <div className="md:hidden flex items-center gap-1 px-4 py-2 overflow-x-auto no-scrollbar border-b border-rule bg-paper-elevated/60">
        {NAV_TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`shrink-0 px-3 py-1 rounded-full text-xs font-medium ${
                active ? "bg-ink text-paper-elevated" : "text-ink-secondary"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          className="shrink-0 ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs text-vermilion bg-vermilion-soft"
        >
          <CalendarDays className="w-3 h-3" />
          {activeConversation.label}
        </button>
      </div>

      {/* Main Open Stage */}
      <main className="flex-1 flex flex-col min-h-0">{children}</main>

      {/* Persistent Mini Voice Orb on Secondary Ledger Screens */}
      {pathname !== "/" && (
        <Link
          href="/"
          className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2.5 pl-3.5 pr-4 py-3 rounded-full bg-vermilion hover:bg-vermilion-hover text-white shadow-orb transition-transform hover:scale-[1.03]"
          title="Return to Voice Desk"
        >
          <Mic className="w-4 h-4" />
          <span className="text-xs font-medium tracking-wide">Speak to Cue</span>
        </Link>
      )}

      {/* Slide-Over Drawer 1: 30-Day Daily Chat History */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex justify-start bg-ink/20 backdrop-blur-[2px]">
          <div className="w-full max-w-sm bg-paper-elevated h-full border-r border-rule shadow-dock flex flex-col animate-slip-in">
            <div className="px-6 py-5 border-b border-rule flex items-center justify-between">
              <div>
                <p className="text-[10px] font-mono uppercase tracking-wider text-vermilion">
                  Rolling 30-Day Memory
                </p>
                <h2 className="text-base font-semibold text-ink mt-0.5">Daily Ledger Chats</h2>
              </div>
              <button
                onClick={() => setHistoryOpen(false)}
                className="p-1.5 rounded-full text-ink-muted hover:text-ink hover:bg-paper-subtle"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {conversations.map((conv) => {
                const selected = conv.date === activeDate;
                return (
                  <Link
                    key={conv.date}
                    href="/"
                    onClick={() => {
                      setActiveDate(conv.date);
                      setHistoryOpen(false);
                    }}
                    className={`block p-3.5 rounded-2xl border transition-colors ${
                      selected
                        ? "bg-vermilion-soft/50 border-vermilion/30"
                        : "bg-paper border-rule hover:border-rule-strong"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-ink">{conv.label}</span>
                      <span className="text-[11px] font-mono text-ink-muted">{conv.date}</span>
                    </div>
                    <p className="text-xs text-ink-secondary mt-1 line-clamp-2">{conv.summary}</p>
                  </Link>
                );
              })}
            </div>

            <div className="p-4 border-t border-rule bg-paper text-[11px] text-ink-muted leading-relaxed">
              One continuous chat per business day. Older than 30 days? Permanent records stay safely in{" "}
              <Link href="/reports" onClick={() => setHistoryOpen(false)} className="text-ink underline">
                Reports
              </Link>
              .
            </div>
          </div>
          <div className="flex-1" onClick={() => setHistoryOpen(false)} />
        </div>
      )}

      {/* Slide-Over Drawer 2: Today's Register, Controls, Account & Guardrails */}
      {registerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-ink/20 backdrop-blur-[2px]">
          <div className="flex-1" onClick={() => setRegisterOpen(false)} />
          <div className="w-full max-w-sm bg-paper-elevated h-full border-l border-rule shadow-dock flex flex-col animate-slip-in">
            <div className="px-6 py-5 border-b border-rule flex items-center justify-between">
              <div>
                <p className="text-[10px] font-mono uppercase tracking-wider text-sage">
                  {store.name} · {tierLabel}
                </p>
                <h2 className="text-base font-semibold text-ink mt-0.5">Today&apos;s Register &amp; Controls</h2>
              </div>
              <button
                onClick={() => setRegisterOpen(false)}
                className="p-1.5 rounded-full text-ink-muted hover:text-ink hover:bg-paper-subtle"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Today Snapshot */}
              <div className="p-4 rounded-2xl bg-paper border border-rule space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-ink-secondary">Today&apos;s Sales</span>
                  <StatusPill tone="sage" dot>IST Live</StatusPill>
                </div>
                <p className="text-3xl font-mono font-semibold tabular-nums text-ink">
                  {formatINR(todayStats.salesTotal)}
                </p>
                <div className="grid grid-cols-3 gap-2 pt-3 border-t border-rule text-xs">
                  <div>
                    <p className="text-[10px] text-ink-muted">Cash</p>
                    <p className="font-mono font-medium text-sage">{formatINR(todayStats.cashTotal)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-ink-muted">Udhaar</p>
                    <p className="font-mono font-medium text-ochre">{formatINR(todayStats.udhaarTotal)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-ink-muted">Khata Due</p>
                    <p className="font-mono font-medium text-ink">{formatINR(todayStats.outstandingTotal)}</p>
                  </div>
                </div>
              </div>

              {/* Voice & Connectivity Controls */}
              <div className="space-y-3">
                <p className="text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                  Voice &amp; Sync Preferences
                </p>

                <div className="flex items-center justify-between p-3 rounded-2xl bg-paper border border-rule">
                  <span className="text-xs font-medium text-ink">Language</span>
                  <div className="flex items-center gap-1">
                    {(
                      [
                        { code: "hinglish", label: "Hinglish" },
                        { code: "hi", label: "हिन्दी" },
                        { code: "en", label: "English" },
                      ] as { code: LanguageMode; label: string }[]
                    ).map((l) => (
                      <button
                        key={l.code}
                        type="button"
                        onClick={() => setLanguage(l.code)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-medium ${
                          language === l.code ? "bg-ink text-paper-elevated" : "text-ink-muted hover:text-ink"
                        }`}
                      >
                        {l.label}
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setTtsEnabled(!ttsEnabled)}
                  className="w-full flex items-center justify-between p-3 rounded-2xl bg-paper border border-rule text-xs"
                >
                  <span className="font-medium text-ink">Spoken Voice Replies (TTS)</span>
                  <span className="inline-flex items-center gap-1.5 text-ink-secondary">
                    {ttsEnabled ? <Volume2 className="w-3.5 h-3.5 text-vermilion" /> : <VolumeX className="w-3.5 h-3.5" />}
                    {ttsEnabled ? "On" : "Muted"}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsOffline(!isOffline)}
                  className="w-full flex items-center justify-between p-3 rounded-2xl bg-paper border border-rule text-xs"
                >
                  <span className="font-medium text-ink">Connectivity Simulator</span>
                  <span className={`inline-flex items-center gap-1.5 font-medium ${isOffline ? "text-ochre" : "text-sage"}`}>
                    {isOffline ? <WifiOff className="w-3.5 h-3.5" /> : <Wifi className="w-3.5 h-3.5" />}
                    {isOffline ? `Offline (${offlineQueue.length} queued)` : "Online"}
                  </span>
                </button>
              </div>

              {/* Low Stock Watch */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-ink-muted flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-ochre" />
                    Low Stock Watch
                  </span>
                  <Link
                    href="/inventory"
                    onClick={() => setRegisterOpen(false)}
                    className="text-xs text-vermilion hover:underline"
                  >
                    Manage
                  </Link>
                </div>
                <div className="space-y-1.5">
                  {todayStats.lowStockProducts.map((p) => (
                    <div
                      key={p.id}
                      className="px-3 py-2 rounded-xl bg-paper border border-rule flex items-center justify-between text-xs"
                    >
                      <span className="text-ink">{p.name}</span>
                      <span className="font-mono text-crimson font-medium">
                        {p.stock} {p.baseUnit}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Subscription Usage & Guardrails */}
              <div className="p-4 rounded-2xl bg-paper border border-rule space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-secondary">Monthly Voice Quota</span>
                  <span className="font-mono text-ink">
                    {store.monthlyVoiceUsed}/{store.monthlyVoiceLimit}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-paper-wash overflow-hidden">
                  <div
                    className="h-full bg-vermilion rounded-full"
                    style={{
                      width: `${Math.min(100, Math.round((store.monthlyVoiceUsed / store.monthlyVoiceLimit) * 100))}%`,
                    }}
                  />
                </div>
                <p className="text-[11px] text-ink-muted flex items-center gap-1.5 pt-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-sage shrink-0" />
                  AI acts strictly as parser · ≥ ₹5,000 confirmed
                </p>
              </div>
            </div>

            <div className="p-4 border-t border-rule grid grid-cols-2 gap-2">
              <Link
                href="/onboarding"
                onClick={() => setRegisterOpen(false)}
                className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-xs font-medium bg-paper border border-rule hover:border-rule-strong"
              >
                <Crown className="w-3.5 h-3.5 text-ochre" />
                Plans ({tierLabel})
              </Link>
              <Link
                href="/login"
                onClick={() => setRegisterOpen(false)}
                className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-xs font-medium bg-ink text-paper-elevated"
              >
                <LogIn className="w-3.5 h-3.5" />
                Account
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Modals (Voice OR Tap Confirmable) */}
      <NewEntityPopup
        draft={newProductDraft}
        onChange={setNewProductDraft}
        onConfirm={confirmNewProductFromModal}
        onCancel={dismissNewProductModal}
      />

      <ConfirmDrawer
        confirmation={pendingConfirmation}
        onConfirm={confirmPendingHighValue}
        onCancel={cancelPendingHighValue}
      />
    </div>
  );
}
