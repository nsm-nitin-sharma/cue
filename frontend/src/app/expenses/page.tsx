"use client";

import React, { useState } from "react";
import { Plus } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { getTodayIST } from "@/lib/format";

export default function ExpensesPage() {
  const { expenses, addManualExpense, todayStats } = useCueWorkspace();
  const [showAdd, setShowAdd] = useState(false);
  const [category, setCategory] = useState("Utilities");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "upi" | "bank">("cash");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const amt = Number(amount);
    if (!description.trim() || amt <= 0) return;
    addManualExpense({
      category,
      description: description.trim(),
      amount: amt,
      paymentMethod: method,
      transactionDate: getTodayIST(),
    });
    setDescription("");
    setAmount("");
    setShowAdd(false);
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto p-6 sm:p-8 paper-grain">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Daily Shop Outflows
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Expenses Ledger
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Utilities, transport, staff wages, and shop maintenance costs.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="px-4 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Today&apos;s Outflow</p>
                <Amount value={todayStats.expensesTotal} className="text-sm font-semibold text-crimson" />
              </div>
              <button
                type="button"
                onClick={() => setShowAdd((v) => !v)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl text-xs font-medium bg-vermilion hover:bg-vermilion-hover text-white transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Expense
              </button>
            </div>
          </div>

          {showAdd && (
            <form
              onSubmit={handleSubmit}
              className="bg-paper-elevated border border-rule-strong rounded-2xl p-5 shadow-slip grid grid-cols-1 sm:grid-cols-5 gap-3 animate-slip-in"
            >
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              >
                <option value="Utilities">Utilities</option>
                <option value="Transport / Tempo">Transport / Tempo</option>
                <option value="Staff Tea / Snacks">Staff Tea / Snacks</option>
                <option value="Maintenance">Maintenance</option>
                <option value="Rent">Rent</option>
              </select>
              <input
                type="text"
                required
                placeholder="Description (e.g. Bijli bill)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="sm:col-span-2 px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              />
              <input
                type="number"
                required
                min={1}
                placeholder="Amount ₹"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="px-3 py-2 text-sm font-mono rounded-xl bg-paper border border-rule"
              />
              <div className="flex gap-2">
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value as "cash" | "upi" | "bank")}
                  className="px-2.5 py-2 text-sm rounded-xl bg-paper border border-rule"
                >
                  <option value="cash">Cash</option>
                  <option value="upi">UPI</option>
                  <option value="bank">Bank</option>
                </select>
                <button
                  type="submit"
                  className="flex-1 px-3 py-2 rounded-xl text-xs font-medium bg-ink text-paper-elevated"
                >
                  Save
                </button>
              </div>
            </form>
          )}

          <div className="bg-paper-elevated border border-rule rounded-2xl shadow-slip overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-rule bg-paper/70 text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4">Method</th>
                  <th className="py-3 px-4 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule text-sm">
                {expenses.map((ex) => (
                  <tr key={ex.id} className="hover:bg-paper/60 transition-colors">
                    <td className="py-3.5 px-4 font-mono text-xs text-ink-secondary">
                      {ex.transactionDate}
                    </td>
                    <td className="py-3.5 px-4 font-medium text-ink">{ex.category}</td>
                    <td className="py-3.5 px-4 text-xs text-ink-secondary">{ex.description}</td>
                    <td className="py-3.5 px-4">
                      <StatusPill tone="neutral">{ex.paymentMethod.toUpperCase()}</StatusPill>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <Amount value={ex.amount} className="font-semibold text-ink" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
