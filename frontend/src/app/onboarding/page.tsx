"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ArrowRight, Store } from "lucide-react";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import type { SubscriptionTierCode } from "@/types/cue";

const PLANS: {
  code: SubscriptionTierCode;
  name: string;
  tag: string;
  priceLabel: string;
  description: string;
  features: string[];
}[] = [
  {
    code: "free",
    name: "Free Pilot",
    tag: "Start Testing Today",
    priceLabel: "₹0 · Active Free Tier",
    description: "Built for solo shopkeepers to test voice-first khata & stock tracking immediately.",
    features: [
      "250 voice transactions / month",
      "1 store · 1 owner seat",
      "30-day rolling daily chat memory",
      "Hindi, Hinglish & English voice desk",
      "Offline IndexedDB queue & audit trail",
    ],
  },
  {
    code: "growth",
    name: "Growth",
    tag: "Busy Kirana & Retail",
    priceLabel: "Pricing Coming Soon",
    description: "Higher daily voice volume, staff seats, and full Business Day Replay automation.",
    features: [
      "2,500 voice transactions / month",
      "1 store · up to 3 staff seats",
      "30-day memory + full historical ledger",
      "Custom unit conversions (peti, darjan, kg)",
      "Priority cloud transcription & backups",
    ],
  },
  {
    code: "pro",
    name: "Pro",
    tag: "Multi-Store & Wholesalers",
    priceLabel: "Custom Enterprise",
    description: "Designed for wholesalers, multi-branch shops, and predictive restocking insights.",
    features: [
      "15,000 voice transactions / month",
      "Up to 5 stores · unlimited staff roles",
      "Future BI: low-stock & anomaly alerts",
      "Regional Indian language pack readiness",
      "Dedicated onboarding & export APIs",
    ],
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { store, setStoreTier, updateStoreProfile } = useCueWorkspace();
  const [selectedTier, setSelectedTier] = useState<SubscriptionTierCode>(store.tier);
  const [storeName, setStoreName] = useState(store.name);
  const [ownerName, setOwnerName] = useState(store.ownerName);
  const [city, setCity] = useState(store.city);

  const handleActivate = (e: React.FormEvent) => {
    e.preventDefault();
    setStoreTier(selectedTier);
    updateStoreProfile({ name: storeName, ownerName, city });
    router.push("/");
  };

  return (
    <div className="min-h-screen bg-paper py-8 px-4 sm:px-8">
      <div className="max-w-5xl mx-auto space-y-8">
        <header className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-vermilion text-white flex items-center justify-center font-semibold text-sm">
              C
            </div>
            <span className="font-semibold text-base tracking-tight text-ink">Cue</span>
          </Link>
          <Link
            href="/"
            className="text-xs font-medium text-ink-secondary hover:text-ink inline-flex items-center gap-1"
          >
            Back to Voice Desk
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </header>

        <div className="max-w-2xl">
          <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
            Subscription & Store Onboarding
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-ink mt-1">
            Choose your tier & launch your store
          </h1>
          <p className="text-sm text-ink-secondary mt-2 leading-relaxed">
            Start immediately on the <span className="font-medium text-ink">Free Pilot</span> tier
            with zero credit card, or preview Growth &amp; Pro capacity tiers before launching in your store.
          </p>
        </div>

        {/* 3 Subscription Tiers */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map((plan) => {
            const active = selectedTier === plan.code;
            return (
              <button
                key={plan.code}
                type="button"
                onClick={() => setSelectedTier(plan.code)}
                className={`text-left p-6 rounded-3xl border transition-all flex flex-col justify-between ${
                  active
                    ? "bg-paper-elevated border-vermilion shadow-dock ring-2 ring-vermilion/15"
                    : "bg-paper-elevated/80 border-rule hover:border-rule-strong"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                      {plan.tag}
                    </span>
                    {active && (
                      <span className="w-5 h-5 rounded-full bg-vermilion text-white flex items-center justify-center">
                        <Check className="w-3 h-3" />
                      </span>
                    )}
                  </div>
                  <h2 className="text-xl font-semibold text-ink mt-2">{plan.name}</h2>
                  <p className="text-xs font-mono text-vermilion mt-1">{plan.priceLabel}</p>
                  <p className="text-xs text-ink-secondary mt-3 leading-relaxed">
                    {plan.description}
                  </p>

                  <ul className="mt-5 pt-4 border-t border-rule space-y-2">
                    {plan.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-2 text-xs text-ink-secondary">
                        <Check className="w-3.5 h-3.5 text-sage shrink-0 mt-0.5" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </button>
            );
          })}
        </div>

        {/* Store Profile Form */}
        <form
          onSubmit={handleActivate}
          className="bg-paper-elevated border border-rule-strong rounded-3xl p-6 sm:p-7 shadow-slip"
        >
          <div className="flex items-center gap-2.5 mb-5">
            <div className="w-8 h-8 rounded-xl bg-paper-subtle border border-rule flex items-center justify-center text-ink">
              <Store className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-ink">Store Details</h3>
              <p className="text-xs text-ink-muted">
                Used to isolate your business ledger, timezone (IST), and product catalog.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">
                Store / Dukaan Name
              </label>
              <input
                type="text"
                required
                value={storeName}
                onChange={(e) => setStoreName(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">
                Owner Name
              </label>
              <input
                type="text"
                required
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">
                City / Market
              </label>
              <input
                type="text"
                required
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-paper border border-rule focus:outline-none focus:border-ink"
              />
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-ink-muted">
              Selected tier:{" "}
              <span className="font-mono font-semibold text-ink uppercase">{selectedTier}</span> ·
              Ready for immediate store testing
            </p>
            <button
              type="submit"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-vermilion hover:bg-vermilion-hover text-white transition-colors"
            >
              Activate &amp; Open Voice Desk
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
