"use client";

import React, { useState } from "react";
import { IndianRupee, Check } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import type { Customer } from "@/types/cue";

export default function CustomersPage() {
  const { customers, recordManualCustomerPayment, todayStats } = useCueWorkspace();
  const [activeCustomer, setActiveCustomer] = useState<Customer | null>(null);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState<"cash" | "upi" | "bank">("cash");

  const handleCollect = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeCustomer) return;
    const amt = Number(payAmount);
    if (amt <= 0) return;
    recordManualCustomerPayment(activeCustomer.id, amt, payMethod);
    setActiveCustomer(null);
    setPayAmount("");
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Customer Credit Ledger
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Udhaar Khata
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Track pending customer balances and disambiguate duplicate names safely.
              </p>
            </div>

            <div className="px-4 py-2.5 rounded-2xl bg-paper-elevated border border-rule">
              <p className="text-[10px] font-mono uppercase text-ink-muted">Total Receivable</p>
              <Amount value={todayStats.outstandingTotal} className="text-lg font-semibold text-ochre" />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {customers.map((c) => (
              <div
                key={c.id}
                className="bg-paper-elevated border border-rule rounded-2xl p-5 shadow-slip flex items-center justify-between gap-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-ink">{c.name}</h3>
                    {c.areaNote && (
                      <span className="text-[11px] px-2 py-0.5 rounded-md bg-paper-subtle text-ink-secondary border border-rule">
                        {c.areaNote}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-ink-muted mt-1">{c.phone}</p>
                  <div className="mt-3">
                    <StatusPill tone={c.outstandingBalance > 0 ? "ochre" : "sage"}>
                      {c.outstandingBalance > 0 ? "Payment Pending" : "Settled"}
                    </StatusPill>
                  </div>
                </div>

                <div className="text-right space-y-2.5">
                  <div>
                    <p className="text-[10px] font-mono uppercase text-ink-muted">Balance</p>
                    <Amount
                      value={c.outstandingBalance}
                      className={`text-xl font-semibold ${
                        c.outstandingBalance > 0 ? "text-ochre" : "text-sage"
                      }`}
                    />
                  </div>
                  {c.outstandingBalance > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveCustomer(c);
                        setPayAmount(String(c.outstandingBalance));
                      }}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-ink text-paper-elevated hover:bg-ink/90 transition-colors"
                    >
                      <IndianRupee className="w-3 h-3" />
                      Collect
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {activeCustomer && (
            <form
              onSubmit={handleCollect}
              className="bg-paper-elevated border border-rule-strong rounded-2xl p-5 shadow-dock flex flex-wrap items-end gap-3 animate-slip-in"
            >
              <div className="flex-1 min-w-[180px]">
                <p className="text-xs font-semibold text-ink">
                  Record Payment · {activeCustomer.name}
                </p>
                <p className="text-[11px] text-ink-muted">
                  Current outstanding: <Amount value={activeCustomer.outstandingBalance} />
                </p>
              </div>
              <div>
                <label className="block text-[11px] text-ink-muted mb-1">Amount (₹)</label>
                <input
                  type="number"
                  required
                  min={1}
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  className="w-32 px-3 py-2 text-sm font-mono rounded-xl bg-paper border border-rule"
                />
              </div>
              <div>
                <label className="block text-[11px] text-ink-muted mb-1">Method</label>
                <select
                  value={payMethod}
                  onChange={(e) => setPayMethod(e.target.value as "cash" | "upi" | "bank")}
                  className="px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
                >
                  <option value="cash">Cash</option>
                  <option value="upi">UPI</option>
                  <option value="bank">Bank</option>
                </select>
              </div>
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium bg-sage text-white"
              >
                <Check className="w-3.5 h-3.5" />
                Save Payment
              </button>
              <button
                type="button"
                onClick={() => setActiveCustomer(null)}
                className="px-3 py-2 rounded-xl text-xs text-ink-secondary border border-rule"
              >
                Cancel
              </button>
            </form>
          )}
        </div>
      </div>
    </AppShell>
  );
}
