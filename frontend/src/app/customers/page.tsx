"use client";

import React, { useState } from "react";
import { IndianRupee, Check } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatTimeIST } from "@/lib/format";
import type { Customer } from "@/types/cue";

export default function CustomersPage() {
  const { customers, sales, recordManualCustomerPayment, todayStats } = useCueWorkspace();
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
            {customers.length === 0 && (
              <div className="md:col-span-2 bg-paper-elevated border border-rule rounded-2xl p-8 text-center text-xs text-ink-muted">
                No customers in Khata yet. Say &ldquo;Nitin purchased 10 bottles of Coke but he did not paid&rdquo; to track Udhaar automatically.
              </div>
            )}
            {customers.map((c) => {
              const customerUdhaar = sales.filter(
                (s) => s.customerId === c.id && s.status !== "voided" && s.paymentStatus !== "paid"
              );
              return (
                <div
                  key={c.id}
                  className="bg-paper-elevated border border-rule rounded-2xl p-5 shadow-slip flex flex-col justify-between gap-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-semibold text-ink">{c.name}</h3>
                        {c.areaNote && (
                          <span className="text-[11px] px-2 py-0.5 rounded-md bg-paper-subtle text-ink-secondary border border-rule">
                            {c.areaNote}
                          </span>
                        )}
                      </div>
                      {c.phone && <p className="text-xs font-mono text-ink-muted mt-1">{c.phone}</p>}
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

                  {customerUdhaar.length > 0 && (
                    <div className="pt-3 border-t border-rule space-y-1.5">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-ink-muted">
                        Udhaar History (When &amp; What)
                      </p>
                      <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                        {customerUdhaar.map((u) => (
                          <div
                            key={u.id}
                            className="flex items-center justify-between gap-2 text-xs py-1 px-2 rounded-lg bg-paper border border-rule/70"
                          >
                            <div className="min-w-0">
                              <p className="text-ink truncate">
                                {u.items.length > 0
                                  ? u.items.map((it) => `${it.quantity} ${it.unit} ${it.productName}`).join(", ")
                                  : "Direct Khata Udhaar"}
                              </p>
                              <p className="text-[10px] font-mono text-ink-muted">
                                {u.transactionDate} · {formatTimeIST(u.createdAt)}
                              </p>
                            </div>
                            <Amount value={u.totalAmount - u.paidAmount} className="font-mono font-medium text-ochre shrink-0" />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
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
                  <option value="upi">Online</option>
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
