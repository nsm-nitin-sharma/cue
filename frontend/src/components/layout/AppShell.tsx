"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Mic,
  Package,
  ReceiptIndianRupee,
  Users,
  Wallet,
  BarChart3,
  Wifi,
  WifiOff,
  Volume2,
  VolumeX,
  CalendarDays,
  ShieldCheck,
  Menu,
  X,
  Crown,
  LogIn,
  AlertTriangle,
} from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatINR } from "@/lib/format";
import { StatusPill, ConfirmDrawer } from "@/components/ui/LedgerPrimitives";
import { NewEntityPopup } from "@/features/voice/NewEntityPopup";
import type { LanguageMode } from "@/types/cue";

const NAV_ITEMS = [
  { href: "/", label: "Voice Desk", icon: Mic },
  { href: "/inventory", label: "Stock & Aliases", icon: Package },
  { href: "/sales", label: "Sales Ledger", icon: ReceiptIndianRupee },
  { href: "/customers", label: "Udhaar Khata", icon: Users },
  { href: "/expenses", label: "Expenses", icon: Wallet },
  { href: "/reports", label: "Replay & Reports", icon: BarChart3 },
];

export function AppShell({
  children,
  showPulseRail = false,
}: {
  children: React.ReactNode;
  showPulseRail?: boolean;
}) {
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
    store.tier === "free" ? "Free Pilot" : store.tier === "growth" ? "Growth" : "Pro";

  return (
    <div className="min-h-screen flex bg-paper text-ink">
      {/* Mobile Sidebar Backdrop */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink/25 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      {/* Left Rail: Store Identity, Navigation & 30-Day Daily Chat Strip */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[268px] bg-paper-elevated border-r border-rule flex flex-col transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand & Store Header */}
        <div className="px-5 py-4 border-b border-rule flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-vermilion text-white flex items-center justify-center font-semibold text-sm tracking-tight shrink-0">
              C
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-sm tracking-tight text-ink">Cue</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-paper-subtle text-ink-secondary border border-rule">
                  {tierLabel}
                </span>
              </div>
              <p className="text-[11px] text-ink-muted truncate">{store.name}</p>
            </div>
          </div>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="lg:hidden p-1 rounded-lg text-ink-muted hover:text-ink"
            aria-label="Close menu"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="px-3 py-3 space-y-0.5 border-b border-rule">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileNavOpen(false)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] transition-colors ${
                  active
                    ? "bg-paper-subtle text-ink font-semibold border border-rule"
                    : "text-ink-secondary hover:bg-paper hover:text-ink"
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? "text-vermilion" : "text-ink-muted"}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* 30-Day Daily Ledger Chat History */}
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <div className="px-2 mb-2 flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted flex items-center gap-1">
              <CalendarDays className="w-3 h-3" />
              Daily Chats (30d Window)
            </span>
          </div>
          <div className="space-y-1">
            {conversations.map((conv) => {
              const selected = conv.date === activeDate && pathname === "/";
              return (
                <Link
                  key={conv.date}
                  href="/"
                  onClick={() => {
                    setActiveDate(conv.date);
                    setMobileNavOpen(false);
                  }}
                  className={`block px-3 py-2 rounded-xl transition-colors border ${
                    selected
                      ? "bg-vermilion-soft/55 border-vermilion/25 text-ink"
                      : "border-transparent hover:bg-paper text-ink-secondary"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-ink">{conv.label}</span>
                    <span className="text-[10px] font-mono text-ink-muted">{conv.date.slice(5)}</span>
                  </div>
                  <p className="text-[11px] text-ink-muted truncate mt-0.5">{conv.summary}</p>
                </Link>
              );
            })}
          </div>
        </div>

        {/* Subscription Usage & Account Footer */}
        <div className="p-3 border-t border-rule space-y-2 bg-paper/60">
          <div className="px-2 py-1.5">
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-ink-secondary">Voice Turns</span>
              <span className="font-mono tabular-nums text-ink">
                {store.monthlyVoiceUsed}/{store.monthlyVoiceLimit}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-paper-wash overflow-hidden">
              <div
                className="h-full bg-vermilion rounded-full transition-all"
                style={{
                  width: `${Math.min(100, Math.round((store.monthlyVoiceUsed / store.monthlyVoiceLimit) * 100))}%`,
                }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1.5">
            <Link
              href="/onboarding"
              className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium bg-paper-elevated border border-rule text-ink-secondary hover:text-ink transition-colors"
            >
              <Crown className="w-3 h-3 text-ochre" />
              Plans
            </Link>
            <Link
              href="/login"
              className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium bg-paper-elevated border border-rule text-ink-secondary hover:text-ink transition-colors"
            >
              <LogIn className="w-3 h-3" />
              Account
            </Link>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Quiet Context Top Bar */}
        <header className="h-14 px-4 sm:px-6 border-b border-rule bg-paper-elevated/80 backdrop-blur-sm flex items-center justify-between gap-3 sticky top-0 z-30">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileNavOpen(true)}
              className="lg:hidden p-1.5 rounded-xl border border-rule text-ink-secondary hover:text-ink"
              aria-label="Open menu"
            >
              <Menu className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-ink-muted hidden sm:inline">IST · Asia/Kolkata</span>
              <span className="text-rule-strong hidden sm:inline">|</span>
              <span className="inline-flex items-center gap-1 text-[11px] text-sage font-medium">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span className="hidden md:inline">AI Parser Only · Append-Only Ledger</span>
                <span className="md:hidden">Protected Ledger</span>
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Language Switcher */}
            <div className="hidden sm:flex items-center bg-paper-subtle p-0.5 rounded-xl border border-rule">
              {(
                [
                  { code: "hinglish", label: "Hinglish" },
                  { code: "hi", label: "हिन्दी" },
                  { code: "en", label: "English" },
                ] as { code: LanguageMode; label: string }[]
              ).map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => setLanguage(lang.code)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${
                    language === lang.code
                      ? "bg-paper-elevated text-ink shadow-sm"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>

            {/* TTS Voice Toggle */}
            <button
              type="button"
              onClick={() => setTtsEnabled(!ttsEnabled)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium border transition-colors ${
                ttsEnabled
                  ? "bg-paper-elevated border-rule text-ink"
                  : "bg-paper-subtle border-rule text-ink-muted"
              }`}
              title="Toggle spoken responses"
            >
              {ttsEnabled ? <Volume2 className="w-3.5 h-3.5 text-vermilion" /> : <VolumeX className="w-3.5 h-3.5" />}
              <span className="hidden md:inline">{ttsEnabled ? "Voice On" : "Muted"}</span>
            </button>

            {/* Offline Queue Simulator Toggle */}
            <button
              type="button"
              onClick={() => setIsOffline(!isOffline)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium border transition-colors ${
                isOffline
                  ? "bg-ochre-soft border-ochre/30 text-ochre"
                  : "bg-sage-soft border-sage/20 text-sage"
              }`}
              title="Toggle offline mode to test IndexedDB FIFO queueing"
            >
              {isOffline ? <WifiOff className="w-3.5 h-3.5" /> : <Wifi className="w-3.5 h-3.5" />}
              <span>{isOffline ? `Offline (${offlineQueue.length})` : "Online"}</span>
            </button>
          </div>
        </header>

        <div className="flex-1 flex min-h-0">
          {/* Center Workspace */}
          <main className="flex-1 flex flex-col min-w-0">{children}</main>

          {/* Right Live Register Pulse Strip (Desktop Voice Desk) */}
          {showPulseRail && (
            <aside className="hidden xl:flex w-[288px] border-l border-rule bg-paper-elevated/60 flex-col p-5 space-y-6">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                    Today&apos;s Register
                  </span>
                  <StatusPill tone="sage" dot>
                    Live
                  </StatusPill>
                </div>

                <div className="p-4 rounded-2xl bg-paper-elevated border border-rule space-y-3">
                  <div>
                    <p className="text-[11px] text-ink-muted">Today&apos;s Total Sales</p>
                    <p className="text-2xl font-mono font-semibold tabular-nums text-ink mt-0.5">
                      {formatINR(todayStats.salesTotal)}
                    </p>
                  </div>
                  <div className="pt-2.5 border-t border-rule grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <p className="text-[11px] text-ink-muted">Cash</p>
                      <p className="font-mono font-medium tabular-nums text-sage">
                        {formatINR(todayStats.cashTotal)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] text-ink-muted">Udhaar</p>
                      <p className="font-mono font-medium tabular-nums text-ochre">
                        {formatINR(todayStats.udhaarTotal)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="p-3 rounded-xl bg-paper-elevated border border-rule">
                  <p className="text-[11px] text-ink-muted">Movements</p>
                  <p className="text-lg font-mono font-semibold tabular-nums text-ink mt-0.5">
                    {todayStats.movementsCount}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-paper-elevated border border-rule">
                  <p className="text-[11px] text-ink-muted">Pending Khata</p>
                  <p className="text-lg font-mono font-semibold tabular-nums text-ochre mt-0.5">
                    {formatINR(todayStats.outstandingTotal)}
                  </p>
                </div>
              </div>

              {/* Low Stock Watchlist */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-ink-muted flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-ochre" />
                    Low Stock Watch
                  </span>
                  <Link href="/inventory" className="text-[11px] text-vermilion hover:underline">
                    View all
                  </Link>
                </div>
                <div className="space-y-1.5">
                  {todayStats.lowStockProducts.map((p) => (
                    <div
                      key={p.id}
                      className="px-3 py-2 rounded-xl bg-paper-elevated border border-rule flex items-center justify-between text-xs"
                    >
                      <span className="text-ink truncate pr-2">{p.name}</span>
                      <span className="font-mono font-medium tabular-nums text-crimson shrink-0">
                        {p.stock} {p.baseUnit}
                      </span>
                    </div>
                  ))}
                  {todayStats.lowStockProducts.length === 0 && (
                    <p className="text-xs text-ink-muted">All stock levels healthy.</p>
                  )}
                </div>
              </div>

              {/* Hardcore Security Callout */}
              <div className="mt-auto p-3.5 rounded-xl bg-paper border border-rule text-[11px] text-ink-secondary space-y-1">
                <p className="font-medium text-ink flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-sage" />
                  Enterprise Guardrails
                </p>
                <p className="leading-relaxed text-ink-muted">
                  Negative stock blocked · ≥ ₹5,000 requires confirmation · 30-day rolling memory window.
                </p>
              </div>
            </aside>
          )}
        </div>
      </div>

      {/* Global Interactive Pop-Ups (Confirmable via Voice OR Tap) */}
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
