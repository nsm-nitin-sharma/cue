"use client";

import React, { useState } from "react";
import { Search, Plus, Tag, ArrowDownUp } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusPill, Amount } from "@/components/ui/LedgerPrimitives";
import { useCueWorkspace } from "@/store/CueWorkspaceContext";
import { formatShortOp } from "@/lib/format";
import type { BaseUnit } from "@/types/cue";

export default function InventoryPage() {
  const { products, movements, addManualProduct } = useCueWorkspace();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"stock" | "movements">("stock");
  const [showAdd, setShowAdd] = useState(false);

  const [name, setName] = useState("");
  const [category, setCategory] = useState("Beverages");
  const [baseUnit, setBaseUnit] = useState<BaseUnit>("piece");
  const [costPrice, setCostPrice] = useState("20");
  const [sellingPrice, setSellingPrice] = useState("25");
  const [stock, setStock] = useState("10");
  const [aliases, setAliases] = useState("");

  const filteredProducts = products.filter(
    (p) =>
      p.name.toLowerCase().includes(query.toLowerCase()) ||
      p.aliases.some((a) => a.toLowerCase().includes(query.toLowerCase())) ||
      p.category.toLowerCase().includes(query.toLowerCase())
  );

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    addManualProduct({
      skuCode: `SKU-${Math.floor(100 + Math.random() * 899)}`,
      name: name.trim(),
      category,
      baseUnit,
      costPrice: Number(costPrice) || 0,
      sellingPrice: Number(sellingPrice) || 0,
      stock: Number(stock) || 0,
      lowStockThreshold: 5,
      aliases: aliases
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
    });
    setName("");
    setAliases("");
    setShowAdd(false);
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto p-6 sm:p-8 paper-grain">
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
                Catalog &amp; Stock Ledger
              </p>
              <h1 className="text-2xl font-semibold tracking-tight text-ink mt-0.5">
                Inventory &amp; Verified Aliases
              </h1>
              <p className="text-xs text-ink-secondary mt-1">
                Verified spoken aliases (like &ldquo;coke&rdquo; → Coca-Cola) and immutable stock movements.
              </p>
            </div>

            <div className="flex items-center gap-2.5">
              <div className="flex items-center bg-paper-elevated p-1 rounded-xl border border-rule">
                <button
                  type="button"
                  onClick={() => setTab("stock")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    tab === "stock" ? "bg-ink text-paper-elevated" : "text-ink-secondary hover:text-ink"
                  }`}
                >
                  Current Stock ({products.length})
                </button>
                <button
                  type="button"
                  onClick={() => setTab("movements")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
                    tab === "movements" ? "bg-ink text-paper-elevated" : "text-ink-secondary hover:text-ink"
                  }`}
                >
                  <ArrowDownUp className="w-3.5 h-3.5" />
                  Movements ({movements.length})
                </button>
              </div>

              <button
                type="button"
                onClick={() => setShowAdd((v) => !v)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium bg-vermilion hover:bg-vermilion-hover text-white transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Product
              </button>
            </div>
          </div>

          {showAdd && (
            <form
              onSubmit={handleCreate}
              className="bg-paper-elevated border border-rule-strong rounded-2xl p-5 shadow-slip grid grid-cols-1 sm:grid-cols-6 gap-3 animate-slip-in"
            >
              <input
                type="text"
                required
                placeholder="Product Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="sm:col-span-2 px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              />
              <input
                type="text"
                placeholder="Category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              />
              <select
                value={baseUnit}
                onChange={(e) => setBaseUnit(e.target.value as BaseUnit)}
                className="px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              >
                <option value="piece">piece</option>
                <option value="packet">packet</option>
                <option value="kg">kg</option>
                <option value="litre">litre</option>
                <option value="box">box</option>
              </select>
              <input
                type="number"
                placeholder="Cost ₹"
                value={costPrice}
                onChange={(e) => setCostPrice(e.target.value)}
                className="px-3 py-2 text-sm font-mono rounded-xl bg-paper border border-rule"
              />
              <input
                type="number"
                placeholder="Sell ₹"
                value={sellingPrice}
                onChange={(e) => setSellingPrice(e.target.value)}
                className="px-3 py-2 text-sm font-mono rounded-xl bg-paper border border-rule"
              />
              <input
                type="number"
                placeholder="Opening Qty"
                value={stock}
                onChange={(e) => setStock(e.target.value)}
                className="px-3 py-2 text-sm font-mono rounded-xl bg-paper border border-rule"
              />
              <input
                type="text"
                placeholder="Aliases (comma separated)"
                value={aliases}
                onChange={(e) => setAliases(e.target.value)}
                className="sm:col-span-4 px-3 py-2 text-sm rounded-xl bg-paper border border-rule"
              />
              <button
                type="submit"
                className="px-4 py-2 rounded-xl text-xs font-medium bg-ink text-paper-elevated hover:bg-ink/90"
              >
                Save Item
              </button>
            </form>
          )}

          {tab === "stock" ? (
            <div className="bg-paper-elevated border border-rule rounded-2xl shadow-slip overflow-hidden">
              <div className="p-4 border-b border-rule flex items-center gap-3">
                <Search className="w-4 h-4 text-ink-muted" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by product, alias, or category..."
                  className="flex-1 text-sm bg-transparent focus:outline-none placeholder:text-ink-muted"
                />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-rule bg-paper/70 text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                      <th className="py-3 px-4">Product</th>
                      <th className="py-3 px-4">Verified Aliases</th>
                      <th className="py-3 px-4 text-right">Cost</th>
                      <th className="py-3 px-4 text-right">Selling</th>
                      <th className="py-3 px-4 text-right">In Stock</th>
                      <th className="py-3 px-4 text-right">Health</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule text-sm">
                    {filteredProducts.map((p) => {
                      const low = p.stock <= p.lowStockThreshold;
                      return (
                        <tr key={p.id} className="hover:bg-paper/60 transition-colors">
                          <td className="py-3.5 px-4">
                            <p className="font-medium text-ink">{p.name}</p>
                            <p className="text-[11px] font-mono text-ink-muted">
                              {p.skuCode} · {p.category}
                            </p>
                          </td>
                          <td className="py-3.5 px-4">
                            <div className="flex flex-wrap gap-1.5">
                              {p.aliases.map((al) => (
                                <span
                                  key={al}
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-paper-subtle text-ink-secondary border border-rule"
                                >
                                  <Tag className="w-2.5 h-2.5 text-ink-muted" />
                                  {al}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3.5 px-4 text-right">
                            <Amount value={p.costPrice} className="text-ink-secondary text-xs" />
                          </td>
                          <td className="py-3.5 px-4 text-right">
                            <Amount value={p.sellingPrice} className="text-ink text-xs font-medium" />
                          </td>
                          <td className="py-3.5 px-4 text-right font-mono tabular-nums font-semibold text-ink">
                            {p.stock}{" "}
                            <span className="text-[11px] font-normal text-ink-muted">{p.baseUnit}</span>
                          </td>
                          <td className="py-3.5 px-4 text-right">
                            <StatusPill tone={low ? "crimson" : "sage"}>
                              {low ? "Low Stock" : "Healthy"}
                            </StatusPill>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="bg-paper-elevated border border-rule rounded-2xl shadow-slip overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-rule bg-paper/70 text-[11px] font-mono uppercase tracking-wider text-ink-muted">
                      <th className="py-3 px-4">Date</th>
                      <th className="py-3 px-4">Product</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4 text-right">Delta</th>
                      <th className="py-3 px-4">Notes</th>
                      <th className="py-3 px-4 text-right">Op ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule text-sm">
                    {movements.map((m) => (
                      <tr key={m.id} className="hover:bg-paper/60 transition-colors">
                        <td className="py-3 px-4 font-mono text-xs text-ink-secondary">
                          {m.transactionDate}
                        </td>
                        <td className="py-3 px-4 font-medium text-ink">{m.productName}</td>
                        <td className="py-3 px-4">
                          <StatusPill
                            tone={
                              m.movementType === "receive"
                                ? "sage"
                                : m.movementType === "damage" || m.movementType === "expiry"
                                  ? "crimson"
                                  : m.movementType === "reversal"
                                    ? "ochre"
                                    : "neutral"
                            }
                          >
                            {m.movementType}
                          </StatusPill>
                        </td>
                        <td
                          className={`py-3 px-4 text-right font-mono tabular-nums font-semibold ${
                            m.quantityDelta >= 0 ? "text-sage" : "text-crimson"
                          }`}
                        >
                          {m.quantityDelta >= 0 ? `+${m.quantityDelta}` : m.quantityDelta} {m.unit}
                        </td>
                        <td className="py-3 px-4 text-xs text-ink-secondary">{m.notes}</td>
                        <td className="py-3 px-4 text-right font-mono text-[11px] text-ink-muted">
                          {formatShortOp(m.operationId)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
