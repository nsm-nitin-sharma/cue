"use client";

import React, { useMemo, useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatPaymentMethod, getTodayIST, isDateInPeriod, type TimePeriodFilter } from "@/lib/format";
import type { Expense } from "@/types/cue";

const EXPENSE_FILTERS: { code: TimePeriodFilter; label: string }[] = [
  { code: "today", label: "Today" },
  { code: "week", label: "Weekly" },
  { code: "month", label: "Monthly" },
  { code: "prev_month", label: "Previous Month" },
  { code: "year", label: "Yearly" },
  { code: "all", label: "All Time" },
];

export default function ExpensesPage() {
  const { expenses, addManualExpense, updateExpense } = useCueWorkspace();
  const [period, setPeriod] = useState<TimePeriodFilter>("today");
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [category, setCategory] = useState("Daily Expense");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "upi" | "bank">("cash");
  const todayYmd = useMemo(() => getTodayIST(), []);

  const filteredExpenses = useMemo(
    () =>
      expenses.filter(
        (ex) => ex.status === "active" && isDateInPeriod(ex.transactionDate, period, todayYmd)
      ),
    [expenses, period, todayYmd]
  );

  const periodTotal = useMemo(
    () => filteredExpenses.reduce((acc, ex) => acc + ex.amount, 0),
    [filteredExpenses]
  );

  const openEdit = (ex: Expense) => {
    setEditingId(ex.id);
    setCategory(ex.category);
    setDescription(ex.description);
    setAmount(String(ex.amount));
    setMethod(ex.paymentMethod);
    setShowAdd(true);
  };

  const resetForm = () => {
    setEditingId(null);
    setCategory("Daily Expense");
    setDescription("");
    setAmount("");
    setMethod("cash");
    setShowAdd(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = Number(amount);
    if (!description.trim() || amt <= 0) return;
    if (editingId) {
      await updateExpense(editingId, {
        category,
        description: description.trim(),
        amount: amt,
        paymentMethod: method,
      });
    } else {
      addManualExpense({
        category,
        description: description.trim(),
        amount: amt,
        paymentMethod: method,
        transactionDate: todayYmd,
      });
    }
    resetForm();
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Shop Outflows
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Expenses Ledger
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Daily, weekly, monthly, and yearly shop expenses via Cash or Online.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="px-4 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">
                  {EXPENSE_FILTERS.find((f) => f.code === period)?.label} Outflow
                </p>
                <Amount value={periodTotal} className="text-sm font-semibold text-crimson" />
              </div>
              <button
                type="button"
                onClick={() => setShowAdd((v) => !v)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-xs font-medium bg-ink hover:bg-vermilion text-white transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Expense
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 bg-paper-elevated p-1 rounded-xl border border-rule w-fit">
            {EXPENSE_FILTERS.map((f) => (
              <button
                key={f.code}
                type="button"
                onClick={() => setPeriod(f.code)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  period === f.code
                    ? "bg-ink text-paper-elevated"
                    : "text-ink-secondary hover:text-ink"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {showAdd && (
            <form
              onSubmit={handleSubmit}
              className="bg-paper-elevated border border-rule-strong rounded-2xl p-5 shadow-slip grid grid-cols-1 sm:grid-cols-5 gap-3 animate-panel-expand"
            >
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              >
                <option value="Daily Expense">Daily Expense</option>
                <option value="Weekly Expense">Weekly Expense</option>
                <option value="Monthly Expense">Monthly Expense</option>
                <option value="Yearly Expense">Yearly Expense</option>
                <option value="Utilities">Utilities</option>
                <option value="Transport / Tempo">Transport / Tempo</option>
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
                  <option value="upi">Online</option>
                  <option value="bank">Bank</option>
                </select>
                <button
                  type="submit"
                  className="flex-1 px-3 py-2 rounded-xl text-xs font-medium bg-ink hover:bg-vermilion text-paper-elevated transition-colors"
                >
                  {editingId ? "Update" : "Save"}
                </button>
                {editingId && (
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-2.5 py-2 rounded-xl text-xs text-ink-secondary border border-rule"
                  >
                    Cancel
                  </button>
                )}
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
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule text-sm">
                {filteredExpenses.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-10 px-4 text-center text-xs text-ink-muted">
                      No expenses recorded for this period yet.
                    </td>
                  </tr>
                )}
                {filteredExpenses.map((ex) => (
                  <tr key={ex.id} className="hover:bg-paper/60 transition-colors">
                    <td className="py-3.5 px-4 font-mono text-xs text-ink-secondary">
                      {ex.transactionDate}
                    </td>
                    <td className="py-3.5 px-4 font-medium text-ink">{ex.category}</td>
                    <td className="py-3.5 px-4 text-xs text-ink-secondary">{ex.description}</td>
                    <td className="py-3.5 px-4">
                      <StatusPill tone="neutral">{formatPaymentMethod(ex.paymentMethod)}</StatusPill>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <Amount value={ex.amount} className="font-semibold text-ink" />
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        type="button"
                        onClick={() => openEdit(ex)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] text-ink-muted hover:text-ink hover:bg-paper border border-transparent hover:border-rule transition-colors"
                        title="Edit expense"
                      >
                        <Pencil className="w-3 h-3" />
                        Edit
                      </button>
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
