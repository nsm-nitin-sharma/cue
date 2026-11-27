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
  ChevronDown,
  LogIn,
  LogOut,
  Mic,
  Store,
  Trash2,
  UserCheck,
} from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatINR } from "@/lib/format";
import { StatusPill, ConfirmDrawer } from "@/components/ui/LedgerPrimitives";
import { NewEntityPopup } from "@/features/voice/NewEntityPopup";
import type { LanguageMode } from "@/types/cue";

const NAV_TABS = [
  { href: "/", label: "Voice" },
  { href: "/inventory", label: "Inventory" },
  { href: "/sales", label: "Sales" },
  { href: "/customers", label: "Khata" },
  { href: "/expenses", label: "Expenses" },
  { href: "/reports", label: "Reports" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
    isLiveBackend,
    authUser,
    needsOnboarding,
    isDemoMode,
    signOut,
    deleteAccount,
    enableDemoPreview,
  } = useCueWorkspace();

  const tierLabel =
    store.tier === "free" ? "Free" : store.tier === "growth" ? "Growth" : "Pro";

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-paper text-ink relative">
      {/* Precision Institutional Top Bar */}
      <header className="sticky top-0 z-30 h-14 px-4 sm:px-8 flex items-center justify-between gap-4 bg-paper-elevated/95 backdrop-blur-md border-b border-rule">
        {/* Left: Monogram + Business + Active Day */}
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/" className="flex items-center gap-2 shrink-0 group">
            <span className="w-6 h-6 rounded-md bg-ink text-white flex items-center justify-center text-[11px] font-mono font-semibold tracking-tight group-hover:bg-vermilion transition-colors">
              C
            </span>
            <span className="text-sm font-semibold tracking-tight text-ink">Cue</span>
          </Link>

          <span className="text-rule-strong hidden sm:inline">/</span>

          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="hidden sm:inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs text-ink-secondary hover:text-ink bg-paper border border-rule hover:border-rule-strong transition-colors"
            title="Open 30-day ledger history"
          >
            <CalendarDays className="w-3.5 h-3.5 text-ink-muted" />
            <span className="font-medium text-ink">{activeConversation.label}</span>
            <span className="font-mono text-[11px] text-ink-muted">{activeConversation.date}</span>
          </button>
        </div>

        {/* Center: Crisp Architectural Segmented Nav */}
        <nav className="hidden md:flex items-center p-0.5 rounded-lg bg-paper-subtle border border-rule">
          {NAV_TABS.map((tab) => {
            const active = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  active
                    ? "bg-paper-elevated text-ink shadow-sm border border-rule/80"
                    : "text-ink-secondary hover:text-ink border border-transparent"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        {/* Right: Distinct Status, Sales Ticker, Store Menu & Settings */}
        <div className="flex items-center gap-2">
          {(isOffline || offlineQueue.length > 0) && (
            <button
              type="button"
              onClick={() => setRegisterOpen(true)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-ochre-soft text-ochre border border-ochre/25 transition-colors hover:border-ochre/50"
            >
              <WifiOff className="w-3 h-3" />
              <span>{offlineQueue.length} queued</span>
            </button>
          )}

          {/* 1. Separate Status Pill */}
          <span
            className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-paper border border-rule text-ink-secondary"
            title={isLiveBackend ? "Connected to Live Cloud Store" : "Local Mode — Sign in for Live AI"}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isLiveBackend ? "bg-sage animate-pulse" : "bg-ochre"}`} />
            <span>{isLiveBackend ? "Live" : isDemoMode ? "Demo" : "Local"}</span>
          </span>

          {/* 2. Separate Today Sales Pill */}
          <Link
            href="/sales"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-paper border border-rule hover:border-rule-strong transition-colors"
            title="View Sales Ledger"
          >
            <span className="hidden lg:inline text-[10px] font-mono uppercase tracking-wider text-ink-muted">
              Today
            </span>
            <span className="font-mono tabular-nums font-semibold text-ink">
              {formatINR(todayStats.salesTotal)}
            </span>
            {todayStats.lowStockProducts.length > 0 && (
              <span className="hidden md:inline text-[11px] text-ochre font-mono">
                · {todayStats.lowStockProducts.length} low
              </span>
            )}
          </Link>

          {/* 3. Store & Account Popover Pill */}
          {authUser ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setAccountMenuOpen((v) => !v)}
                className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs bg-paper border border-rule hover:border-rule-strong transition-colors"
                aria-expanded={accountMenuOpen}
                aria-haspopup="menu"
              >
                <span className="w-4 h-4 rounded bg-ink text-paper-elevated flex items-center justify-center shrink-0">
                  <Store className="w-2.5 h-2.5" />
                </span>
                <span className="hidden sm:inline max-w-[140px] truncate font-medium text-ink">
                  {store.name && store.name !== "My Store" ? store.name : "My Store"}
                </span>
                <ChevronDown className={`w-3.5 h-3.5 text-ink-muted transition-transform duration-200 ${accountMenuOpen ? "rotate-180" : ""}`} />
              </button>

              {accountMenuOpen && (
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setAccountMenuOpen(false)}
                />
              )}
              <div
                role="menu"
                aria-hidden={!accountMenuOpen}
                className={`absolute right-0 mt-2 w-64 rounded-xl bg-paper-elevated border border-rule-strong shadow-dock z-50 overflow-hidden transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)] origin-top-right ${
                  accountMenuOpen
                    ? "opacity-100 scale-100 translate-y-0 pointer-events-auto"
                    : "opacity-0 scale-95 -translate-y-1 pointer-events-none"
                }`}
              >
                <div className="p-3.5 border-b border-rule bg-paper/60">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-ink truncate">
                      {store.name || "My Store"}
                    </p>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-paper-subtle border border-rule text-ink-secondary shrink-0">
                      {tierLabel}
                    </span>
                  </div>
                  {store.city && (
                    <p className="text-[11px] text-ink-muted mt-0.5 truncate">{store.city}</p>
                  )}
                </div>

                <div className="p-3.5 border-b border-rule space-y-1">
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                    <UserCheck className="w-3 h-3 text-sage shrink-0" />
                    <span>Signed in as</span>
                  </div>
                  <p className="text-xs font-medium text-ink truncate">{authUser.name}</p>
                  {authUser.email && authUser.email !== authUser.name && (
                    <p className="text-[11px] font-mono text-ink-muted truncate">{authUser.email}</p>
                  )}
                </div>

                <div className="p-1.5 space-y-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setAccountMenuOpen(false);
                      setRegisterOpen(true);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-ink-secondary hover:text-ink hover:bg-paper transition-colors text-left"
                  >
                    <SlidersHorizontal className="w-3.5 h-3.5" />
                    Store &amp; System Controls
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAccountMenuOpen(false);
                      signOut();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-medium text-crimson hover:bg-paper transition-colors text-left"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    Sign Out
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium bg-ink text-paper-elevated hover:bg-vermilion transition-colors"
            >
              <LogIn className="w-3.5 h-3.5" />
              <span>Sign In</span>
            </Link>
          )}

          {/* 4. Separate Settings Button */}
          <button
            type="button"
            onClick={() => setRegisterOpen(true)}
            className="p-1.5 rounded-md bg-paper border border-rule hover:border-rule-strong text-ink-secondary hover:text-ink transition-colors"
            title="Store Settings & Controls"
            aria-label="Open settings"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {authUser && needsOnboarding && pathname !== "/onboarding" && (
        <div className="px-4 sm:px-8 py-2 bg-ochre-soft border-b border-ochre/25 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="text-ink inline-flex items-center gap-1.5">
            <Store className="w-3.5 h-3.5 text-ochre" />
            Signed in as <strong>{authUser.email}</strong> — complete your store profile to enable live cloud sync.
          </span>
          <Link
            href="/onboarding"
            className="px-3 py-1 rounded-md bg-ink text-paper-elevated font-medium hover:bg-vermilion transition-colors"
          >
            Set Up Store
          </Link>
        </div>
      )}

      {!authUser && !isDemoMode && (
        <div className="px-4 sm:px-8 py-1.5 bg-paper-subtle border-b border-rule flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-secondary">
          <span>Clean workspace ready. Sign in to connect your live AI store, or load sample kirana items to explore.</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={enableDemoPreview}
              className="px-2.5 py-0.5 rounded border border-rule bg-paper-elevated hover:border-rule-strong text-ink font-medium"
            >
              Load Sample Items
            </button>
            <Link href="/login" className="text-vermilion font-medium hover:underline">
              Sign In →
            </Link>
          </div>
        </div>
      )}

      {/* Mobile Compact Route Strip */}
      <div className="md:hidden flex items-center gap-1 px-4 py-2 overflow-x-auto no-scrollbar border-b border-rule bg-paper-elevated">
        {NAV_TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`shrink-0 px-2.5 py-1 rounded-md text-xs font-medium ${
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
          className="shrink-0 ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-vermilion bg-vermilion-soft"
        >
          <CalendarDays className="w-3 h-3" />
          {activeConversation.label}
        </button>
      </div>

      {/* Main Stage with minimal premium route transition */}
      <main className="flex-1 flex flex-col min-h-0">
        <div key={pathname} className="flex-1 flex flex-col min-h-0 animate-page-enter">
          {children}
        </div>
      </main>

      {/* Persistent Mini Voice Trigger on Secondary Views */}
      {pathname !== "/" && (
        <Link
          href="/"
          className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-ink hover:bg-vermilion text-white shadow-orb transition-colors"
          title="Return to Voice Console"
        >
          <Mic className="w-4 h-4" />
          <span className="text-xs font-medium tracking-tight">Voice Console</span>
        </Link>
      )}

      {/* Slide-Over Drawer 1: 30-Day Daily Ledger History (Smooth Open & Close) */}
      <div
        aria-hidden={!historyOpen}
        className={`fixed inset-0 z-50 flex justify-start transition-opacity duration-300 ease-out ${
          historyOpen
            ? "opacity-100 pointer-events-auto bg-ink/25 backdrop-blur-[2px]"
            : "opacity-0 pointer-events-none bg-ink/0"
        }`}
      >
        <div
          className={`w-full max-w-sm bg-paper-elevated h-full border-r border-rule shadow-dock flex flex-col transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
            historyOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="px-5 py-4 border-b border-rule flex items-center justify-between">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
                30-Day Rolling Context Window
              </p>
              <h2 className="text-sm font-semibold text-ink mt-0.5">Daily Ledger Sessions</h2>
            </div>
            <button
              onClick={() => setHistoryOpen(false)}
              className="p-1.5 rounded-md text-ink-muted hover:text-ink hover:bg-paper-subtle transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3.5 space-y-1.5">
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
                  className={`block p-3 rounded-lg border transition-colors ${
                    selected
                      ? "bg-vermilion-soft/70 border-vermilion/30"
                      : "bg-paper border-rule hover:border-rule-strong"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-ink">{conv.label}</span>
                    <span className="text-[11px] font-mono text-ink-muted">{conv.date}</span>
                  </div>
                  <p className="text-xs text-ink-secondary mt-1 line-clamp-2">{conv.summary}</p>
                </Link>
              );
            })}
          </div>

          <div className="p-4 border-t border-rule bg-paper text-[11px] text-ink-muted leading-relaxed">
            One continuous session per business day. Records older than 30 days remain permanently in{" "}
            <Link href="/reports" onClick={() => setHistoryOpen(false)} className="text-ink underline">
              Reports
            </Link>
            .
          </div>
        </div>
        <div className="flex-1" onClick={() => setHistoryOpen(false)} />
      </div>

      {/* Slide-Over Drawer 2: Register Summary, Guardrails & Controls (Smooth Open & Close) */}
      <div
        aria-hidden={!registerOpen}
        className={`fixed inset-0 z-50 flex justify-end transition-opacity duration-300 ease-out ${
          registerOpen
            ? "opacity-100 pointer-events-auto bg-ink/25 backdrop-blur-[2px]"
            : "opacity-0 pointer-events-none bg-ink/0"
        }`}
      >
        <div className="flex-1" onClick={() => setRegisterOpen(false)} />
        <div
          className={`w-full max-w-sm bg-paper-elevated h-full border-l border-rule shadow-dock flex flex-col transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
            registerOpen ? "translate-x-0" : "translate-x-full"
          }`}
        >
            <div className="px-5 py-4 border-b border-rule flex items-center justify-between">
              <div>
                <p className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
                  {store.name} · {tierLabel}
                </p>
                <h2 className="text-sm font-semibold text-ink mt-0.5">Register &amp; System Controls</h2>
              </div>
              <button
                onClick={() => setRegisterOpen(false)}
                className="p-1.5 rounded-md text-ink-muted hover:text-ink hover:bg-paper-subtle"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* Today Snapshot */}
              <div className="p-4 rounded-xl bg-paper border border-rule space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-ink-secondary">Today&apos;s Revenue</span>
                  <StatusPill tone="sage" dot>IST Active</StatusPill>
                </div>
                <p className="text-2xl font-mono font-semibold tabular-nums text-ink">
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

              {/* Controls */}
              <div className="space-y-2.5">
                <p className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
                  Voice &amp; Network Policy
                </p>

                <div className="flex items-center justify-between p-3 rounded-lg bg-paper border border-rule">
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
                        className={`px-2 py-1 rounded text-[11px] font-medium ${
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
                  className="w-full flex items-center justify-between p-3 rounded-lg bg-paper border border-rule text-xs"
                >
                  <span className="font-medium text-ink">Spoken Confirmation (TTS)</span>
                  <span className="inline-flex items-center gap-1.5 text-ink-secondary">
                    {ttsEnabled ? <Volume2 className="w-3.5 h-3.5 text-vermilion" /> : <VolumeX className="w-3.5 h-3.5" />}
                    {ttsEnabled ? "Enabled" : "Muted"}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsOffline(!isOffline)}
                  className="w-full flex items-center justify-between p-3 rounded-lg bg-paper border border-rule text-xs"
                >
                  <span className="font-medium text-ink">Sync Mode</span>
                  <span className={`inline-flex items-center gap-1.5 font-medium ${isOffline ? "text-ochre" : "text-sage"}`}>
                    {isOffline ? <WifiOff className="w-3.5 h-3.5" /> : <Wifi className="w-3.5 h-3.5" />}
                    {isOffline ? `Offline (${offlineQueue.length} queued)` : "Online"}
                  </span>
                </button>
              </div>

              {/* Low Stock Watch */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-ink-muted flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-ochre" />
                    Low Stock Thresholds
                  </span>
                  <Link
                    href="/inventory"
                    onClick={() => setRegisterOpen(false)}
                    className="text-xs text-vermilion hover:underline font-medium"
                  >
                    Open Stock
                  </Link>
                </div>
                <div className="space-y-1.5">
                  {todayStats.lowStockProducts.map((p) => (
                    <div
                      key={p.id}
                      className="px-3 py-2 rounded-lg bg-paper border border-rule flex items-center justify-between text-xs"
                    >
                      <span className="text-ink">{p.name}</span>
                      <span className="font-mono text-crimson font-medium">
                        {p.stock} {p.baseUnit}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Quota & Security Policy */}
              <div className="p-3.5 rounded-xl bg-paper border border-rule space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ink-secondary">Monthly Voice Quota</span>
                  <span className="font-mono text-ink">
                    {store.monthlyVoiceUsed}/{store.monthlyVoiceLimit}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-paper-wash overflow-hidden">
                  <div
                    className="h-full bg-ink rounded-full"
                    style={{
                      width: `${Math.min(100, Math.round((store.monthlyVoiceUsed / store.monthlyVoiceLimit) * 100))}%`,
                    }}
                  />
                </div>
                <p className="text-[11px] text-ink-muted flex items-center gap-1.5 pt-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-sage shrink-0" />
                  Parser-only AI · Negative stock blocked · ≥ ₹5,000 gated
                </p>
              </div>

              {authUser && (
                <div className="p-3.5 rounded-xl bg-paper border border-crimson/25 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-crimson">Delete Account &amp; Reset</span>
                    {!confirmDeleteOpen && (
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmDeleteOpen(true);
                          setDeleteError(null);
                          setDeleteText("");
                        }}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium text-crimson border border-crimson/30 hover:bg-crimson hover:text-white transition-colors"
                      >
                        <Trash2 className="w-3 h-3" />
                        Delete
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-muted leading-relaxed">
                    Permanently deletes your account and store ledger so you can create a fresh account.
                  </p>
                  {confirmDeleteOpen && (
                    <div className="space-y-2 pt-1">
                      <input
                        type="text"
                        value={deleteText}
                        onChange={(e) => setDeleteText(e.target.value)}
                        placeholder='Type DELETE to confirm'
                        className="w-full px-3 py-1.5 text-xs rounded-lg bg-paper-elevated border border-rule font-mono focus:outline-none focus:border-crimson"
                      />
                      {deleteError && <p className="text-[11px] text-crimson">{deleteError}</p>}
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          disabled={deletingAccount || deleteText.trim().toUpperCase() !== "DELETE"}
                          onClick={async () => {
                            setDeletingAccount(true);
                            setDeleteError(null);
                            try {
                              await deleteAccount();
                              setRegisterOpen(false);
                              window.location.href = "/login";
                            } catch (err) {
                              setDeleteError(err instanceof Error ? err.message : "Failed to delete account");
                            } finally {
                              setDeletingAccount(false);
                            }
                          }}
                          className="flex-1 py-1.5 rounded-lg text-xs font-medium bg-crimson text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
                        >
                          {deletingAccount ? "Deleting..." : "Confirm Delete"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteOpen(false)}
                          className="px-3 py-1.5 rounded-lg text-xs text-ink-secondary border border-rule hover:border-rule-strong"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-rule grid grid-cols-2 gap-2">
              <Link
                href="/onboarding"
                onClick={() => setRegisterOpen(false)}
                className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium bg-paper border border-rule hover:border-rule-strong"
              >
                <Crown className="w-3.5 h-3.5 text-ochre" />
                Plans ({tierLabel})
              </Link>
              {authUser ? (
                <button
                  type="button"
                  onClick={() => {
                    setRegisterOpen(false);
                    signOut();
                  }}
                  className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium bg-ink text-paper-elevated hover:bg-crimson transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Sign Out
                </button>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setRegisterOpen(false)}
                  className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium bg-ink text-paper-elevated"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  Sign In
                </Link>
              )}
            </div>
          </div>
        </div>

      {/* Interactive Modals */}
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
