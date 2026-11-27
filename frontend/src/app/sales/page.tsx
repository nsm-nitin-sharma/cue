"use client";

import React, { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Amount, StatusPill } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatShortOp, getTodayIST, isDateInPeriod, type TimePeriodFilter } from "@/lib/format";

const SALES_FILTERS: { code: TimePeriodFilter; label: string }[] = [
  { code: "today", label: "Today" },
  { code: "month", label: "This Month" },
  { code: "prev_month", label: "Previous Month" },
  { code: "year", label: "This Year" },
  { code: "all", label: "All Time" },
];

export default function SalesPage() {
  const { sales, products, undoReceipt } = useCueWorkspace();
  const [period, setPeriod] = useState<TimePeriodFilter>("today");
  const todayYmd = useMemo(() => getTodayIST(), []);

  const costByProductId = useMemo(() => {
    const map = new Map<string, number>();
    products.forEach((p) => map.set(p.id, p.costPrice));
    return map;
  }, [products]);

  const filteredSales = useMemo(
    () => sales.filter((s) => isDateInPeriod(s.transactionDate, period, todayYmd)),
    [period, sales, todayYmd]
  );

  const summary = useMemo(() => {
    const active = filteredSales.filter((s) => s.status === "active");
    const totalBilled = active.reduce((acc, s) => acc + s.totalAmount, 0);
    const revenueCollected = active.reduce((acc, s) => acc + s.paidAmount, 0);
    const udhaarPending = Math.max(0, totalBilled - revenueCollected);
    const profit = active.reduce((acc, s) => {
      const sProfit = s.items.reduce((pAcc, it) => {
        const cost = costByProductId.get(it.productId);
        if (cost === undefined) return pAcc;
        return pAcc + (it.unitPrice - cost) * it.quantity;
      }, 0);
      return acc + sProfit;
    }, 0);
    return { count: active.length, totalBilled, revenueCollected, udhaarPending, profit };
  }, [costByProductId, filteredSales]);

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Revenue, Profit &amp; Credit Billing
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Sales Ledger
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Collected revenue (Cash &amp; Online), pending Udhaar, and profit margin per bill.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <div className="px-3.5 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Sales ({summary.count})</p>
                <Amount value={summary.totalBilled} className="text-sm font-semibold text-ink" />
              </div>
              <div className="px-3.5 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Revenue</p>
                <Amount value={summary.revenueCollected} className="text-sm font-semibold text-sage" />
              </div>
              <div className="px-3.5 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Profit</p>
                <Amount value={summary.profit} className="text-sm font-semibold text-sage" />
              </div>
              <div className="px-3.5 py-2 rounded-2xl bg-paper-elevated border border-rule">
                <p className="text-[10px] font-mono uppercase text-ink-muted">Udhaar</p>
                <Amount value={summary.udhaarPending} className="text-sm font-semibold text-ochre" />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 bg-paper-elevated p-1 rounded-xl border border-rule w-fit">
            {SALES_FILTERS.map((f) => (
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

          <div className="bg-paper-elevated border border-rule rounded-2xl shadow-slip overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-rule bg-paper/70 text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                    <th className="py-3 px-4">Biz Date</th>
                    <th className="py-3 px-4">Customer</th>
                    <th className="py-3 px-4">Items</th>
                    <th className="py-3 px-4">Payment</th>
                    <th className="py-3 px-4 text-right">Total</th>
                    <th className="py-3 px-4 text-right">Profit</th>
                    <th className="py-3 px-4 text-right">Status</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule text-sm">
                  {filteredSales.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-10 px-4 text-center text-xs text-ink-muted">
                        No sales recorded for this period yet.
                      </td>
                    </tr>
                  )}
                  {filteredSales.map((s) => {
                    const rowProfit = s.items.reduce((pAcc, it) => {
                      const cost = costByProductId.get(it.productId);
                      return cost === undefined ? pAcc : pAcc + (it.unitPrice - cost) * it.quantity;
                    }, 0);
                    return (
                      <tr key={s.id} className="hover:bg-paper/60 transition-colors">
                        <td className="py-3.5 px-4">
                          <p className="font-mono text-xs text-ink">{s.transactionDate}</p>
                          <p className="font-mono text-[10px] text-ink-muted">{formatShortOp(s.operationId)}</p>
                        </td>
                        <td className="py-3.5 px-4 font-medium text-ink">{s.customerName}</td>
                        <td className="py-3.5 px-4 text-xs text-ink-secondary">
                          {s.items.length > 0
                            ? s.items.map((it) => `${it.quantity} ${it.unit} ${it.productName}`).join(", ")
                            : "Direct credit entry"}
                        </td>
                        <td className="py-3.5 px-4">
                          <StatusPill tone={s.paymentStatus === "paid" ? "sage" : "ochre"}>
                            {s.paymentStatus === "credit"
                              ? "Udhaar"
                              : s.notes?.includes("[ONLINE]")
                                ? "Online"
                                : "Cash"}
                          </StatusPill>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <Amount value={s.totalAmount} className="font-semibold text-ink" />
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <Amount
                            value={rowProfit}
                            className={`text-xs font-medium ${rowProfit >= 0 ? "text-sage" : "text-crimson"}`}
                          />
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <StatusPill
                            tone={
                              s.status === "active"
                                ? "sage"
                                : s.status === "corrected"
                                  ? "ochre"
                                  : "neutral"
                            }
                          >
                            {s.status}
                          </StatusPill>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          {s.status !== "voided" && (
                            <button
                              type="button"
                              onClick={() => undoReceipt(s.operationId)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-rule text-xs text-ink-secondary hover:text-ink hover:bg-paper-subtle"
                            >
                              <RotateCcw className="w-3 h-3" />
                              Reverse
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
