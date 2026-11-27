"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  clearOfflineQueue,
  enqueueOfflineCommand,
  listOfflineCommands,
  removeOfflineCommand,
} from "@/lib/offlineQueue";
import { formatINR, formatQty, formatTimeIST, getTodayIST, makeOperationId } from "@/lib/format";
import { speakReply, stopSpeaking } from "@/lib/tts";
import { supabase } from "@/lib/supabase";
import {
  addManualProductRemote,
  archiveProductRemote,
  clearUnusedCatalogRemote,
  confirmTier3Remote,
  createProductFromPopupRemote,
  deleteAccountRemote,
  fetchWorkspaceBootstrap,
  sendTextCommandRemote,
  sendVoiceAudioTurn,
  syncOfflineBatchRemote,
} from "@/lib/api";
import type {
  BaseUnit,
  ChatEntry,
  ClarificationCandidate,
  Customer,
  DayConversation,
  Expense,
  InventoryMovement,
  LanguageMode,
  NewProductDraft,
  PendingConfirmation,
  Product,
  QueuedVoiceCommand,
  ReceiptSlip,
  Sale,
  StoreProfile,
  SubscriptionTierCode,
  VoicePhase,
  VoiceTurnResult,
} from "@/types/cue";

interface PendingSlotDraft {
  kind: "receive" | "sale" | "expense" | "payment" | "expiry";
  productId?: string;
  productName?: string;
  customerId?: string;
  customerName?: string;
  quantity?: number;
  unit?: BaseUnit;
  unitPrice?: number;
  amount?: number;
  paymentStatus?: "paid" | "credit";
  paymentMethod?: "cash" | "upi" | "bank";
  category?: string;
  description?: string;
  transactionDate: string;
  missingField: "purchase_price" | "selling_price" | "payment_method" | "quantity" | "amount";
  aliasToVerify?: { spoken: string; targetProductId: string; targetProductName: string };
  lastReceiveBatchQty?: number;
}

type PendingFlowState =
  | { type: "verify_alias"; spoken: string; candidate: Product; draft: Omit<PendingSlotDraft, "missingField"> }
  | { type: "disambiguate_product"; candidates: Product[]; draft: Omit<PendingSlotDraft, "missingField"> }
  | { type: "disambiguate_customer"; candidates: Customer[]; draft: Omit<PendingSlotDraft, "missingField"> }
  | { type: "missing_slot"; draft: PendingSlotDraft }
  | null;

interface CueWorkspaceContextValue {
  store: StoreProfile;
  setStoreTier: (tier: SubscriptionTierCode) => void;
  updateStoreProfile: (patch: Partial<StoreProfile>) => void;
  language: LanguageMode;
  setLanguage: (lang: LanguageMode) => void;
  ttsEnabled: boolean;
  setTtsEnabled: (enabled: boolean) => void;
  isOffline: boolean;
  setIsOffline: (offline: boolean) => void;
  voicePhase: VoicePhase;
  setVoicePhase: (phase: VoicePhase) => void;
  statusMessage: string;
  products: Product[];
  movements: InventoryMovement[];
  customers: Customer[];
  sales: Sale[];
  expenses: Expense[];
  conversations: DayConversation[];
  activeDate: string;
  setActiveDate: (date: string) => void;
  activeConversation: DayConversation;
  offlineQueue: QueuedVoiceCommand[];
  newProductDraft: NewProductDraft | null;
  setNewProductDraft: React.Dispatch<React.SetStateAction<NewProductDraft | null>>;
  confirmNewProductFromModal: (draft: NewProductDraft) => void;
  dismissNewProductModal: () => void;
  pendingConfirmation: PendingConfirmation | null;
  confirmPendingHighValue: () => void;
  cancelPendingHighValue: () => void;
  isLiveBackend: boolean;
  authUser: { id: string; email: string; name: string } | null;
  needsOnboarding: boolean;
  isDemoMode: boolean;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  refreshWorkspace: () => Promise<void>;
  archiveProduct: (productId: string) => Promise<void>;
  clearUnusedCatalog: () => Promise<number>;
  enableDemoPreview: () => void;
  submitAudioTurn: (audioBlob: Blob, fallbackTranscript?: string) => Promise<void>;
  submitCommand: (rawText: string, opts?: { fromOfflineSync?: boolean; operationId?: string }) => Promise<void>;
  selectClarificationCandidate: (candidate: ClarificationCandidate) => void;
  undoReceipt: (operationId: string) => void;
  syncOfflineQueue: () => Promise<void>;
  addManualProduct: (p: Omit<Product, "id">) => void;
  addManualExpense: (e: Omit<Expense, "id" | "operationId" | "createdAt" | "status">) => void;
  recordManualCustomerPayment: (customerId: string, amount: number, method: "cash" | "upi" | "bank") => void;
  todayStats: {
    salesTotal: number;
    cashTotal: number;
    udhaarTotal: number;
    expensesTotal: number;
    movementsCount: number;
    outstandingTotal: number;
    lowStockProducts: Product[];
  };
}

const CueWorkspaceContext = createContext<CueWorkspaceContextValue | null>(null);

const INITIAL_PRODUCTS: Product[] = [
  {
    id: "prod-pepsi-500",
    skuCode: "BEV-001",
    name: "Pepsi 500ml",
    category: "Beverages",
    baseUnit: "piece",
    costPrice: 16,
    sellingPrice: 20,
    stock: 24,
    lowStockThreshold: 10,
    aliases: ["pepsi 500ml", "chhoti pepsi", "chotti pepsi"],
  },
  {
    id: "prod-pepsi-2l",
    skuCode: "BEV-002",
    name: "Pepsi 2L",
    category: "Beverages",
    baseUnit: "piece",
    costPrice: 72,
    sellingPrice: 90,
    stock: 8,
    lowStockThreshold: 6,
    aliases: ["pepsi 2l", "badi pepsi"],
  },
  {
    id: "prod-coca-750",
    skuCode: "BEV-003",
    name: "Coca-Cola 750ml",
    category: "Beverages",
    baseUnit: "piece",
    costPrice: 32,
    sellingPrice: 40,
    stock: 18,
    lowStockThreshold: 8,
    // Note: "coke" is intentionally absent initially so "Do you mean Coca-Cola 750ml?" triggers live!
    aliases: ["coca cola", "coca-cola 750ml"],
  },
  {
    id: "prod-maggi-70",
    skuCode: "SNK-001",
    name: "Maggi Masala 70g",
    category: "Instant Food",
    baseUnit: "packet",
    costPrice: 11,
    sellingPrice: 14,
    stock: 36,
    lowStockThreshold: 15,
    aliases: ["maggi", "maggi packet", "maggi masala"],
  },
  {
    id: "prod-salt-1kg",
    skuCode: "GRC-001",
    name: "Tata Salt 1kg",
    category: "Staples",
    baseUnit: "packet",
    costPrice: 22,
    sellingPrice: 28,
    stock: 14,
    lowStockThreshold: 10,
    aliases: ["tata salt", "namak", "salt"],
  },
  {
    id: "prod-oil-1l",
    skuCode: "OIL-001",
    name: "Fortune Sunflower Oil 1L",
    category: "Oils & Ghee",
    baseUnit: "litre",
    costPrice: 132,
    sellingPrice: 155,
    stock: 5,
    lowStockThreshold: 6,
    aliases: ["fortune oil", "tel", "sunflower oil"],
  },
  {
    id: "prod-milk-1l",
    skuCode: "DRY-001",
    name: "Amul Gold Milk 1L",
    category: "Dairy",
    baseUnit: "packet",
    costPrice: 60,
    sellingPrice: 66,
    stock: 4,
    lowStockThreshold: 8,
    aliases: ["amul milk", "doodh", "milk"],
  },
  {
    id: "prod-parleg-100",
    skuCode: "SNK-002",
    name: "Parle-G Gold 100g",
    category: "Biscuits",
    baseUnit: "packet",
    costPrice: 8,
    sellingPrice: 10,
    stock: 42,
    lowStockThreshold: 15,
    aliases: ["parle g", "parle-g", "biscuit"],
  },
];

const INITIAL_CUSTOMERS: Customer[] = [
  {
    id: "cust-ramesh-g",
    name: "Ramesh Gupta",
    phone: "+91 98110 44210",
    areaNote: "Sector 4",
    outstandingBalance: 1200,
  },
  {
    id: "cust-ramesh-y",
    name: "Ramesh Yadav",
    phone: "+91 98712 90344",
    areaNote: "Station Road",
    outstandingBalance: 650,
  },
  {
    id: "cust-sunita",
    name: "Sunita Devi",
    phone: "+91 99104 77812",
    areaNote: "Gandhi Nagar",
    outstandingBalance: 350,
  },
  {
    id: "cust-vikram",
    name: "Vikram Traders",
    phone: "+91 98188 11209",
    areaNote: "Mandi Chowk",
    outstandingBalance: 0,
  },
];

function shiftDate(baseYmd: string, deltaDays: number): string {
  const [y, m, d] = baseYmd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + deltaDays));
  return dt.toISOString().slice(0, 10);
}

function formatDayBadge(ymd: string, todayYmd: string): string {
  if (ymd === todayYmd) return "Today";
  if (ymd === shiftDate(todayYmd, -1)) return "Yesterday";
  const [y, m, d] = ymd.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

function parseIndianNumber(text: string): number | null {
  const lower = text.toLowerCase();
  const hindiMap: Record<string, number> = {
    ek: 1,
    do: 2,
    teen: 3,
    char: 4,
    chaar: 4,
    paanch: 5,
    panch: 5,
    chhe: 6,
    che: 6,
    saat: 7,
    aath: 8,
    nau: 9,
    das: 10,
    gyarah: 11,
    barah: 12,
    pandrah: 15,
    bees: 20,
    pachees: 25,
    tees: 30,
    chalis: 40,
    pachas: 50,
    sau: 100,
    pav: 0.25,
    aadha: 0.5,
    adha: 0.5,
    dedh: 1.5,
    dhai: 2.5,
  };

  const numMatch = lower.match(/(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)/i);
  if (numMatch) {
    return Number(numMatch[1]);
  }
  for (const [word, val] of Object.entries(hindiMap)) {
    const regex = new RegExp(`\\b${word}\\b`, "i");
    if (regex.test(lower)) return val;
  }
  return null;
}

function extractRupeeHint(text: string): number | null {
  const rateMatch = text.match(/(?:₹|rs\.?\s*|rupaye\s*|rate\s*(?:par|pe|hai)?\s*)(\d+(?:\.\d+)?)/i);
  if (rateMatch) return Number(rateMatch[1]);
  const atPrice = text.match(/(\d+(?:\.\d+)?)\s*(?:rs|rupaye|rupees|mein|par|pe|each|per)/i);
  if (atPrice) return Number(atPrice[1]);
  return null;
}

export function CueWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const todayYmd = useMemo(() => getTodayIST(), []);
  const yesterdayYmd = useMemo(() => shiftDate(todayYmd, -1), [todayYmd]);
  const dayMinus3Ymd = useMemo(() => shiftDate(todayYmd, -3), [todayYmd]);
  const dayMinus9Ymd = useMemo(() => shiftDate(todayYmd, -9), [todayYmd]);
  const dayMinus23Ymd = useMemo(() => shiftDate(todayYmd, -23), [todayYmd]);

  const [store, setStore] = useState<StoreProfile>({
    name: "My Store",
    ownerName: "",
    city: "",
    timezone: "Asia/Kolkata",
    tier: "free",
    monthlyVoiceUsed: 0,
    monthlyVoiceLimit: 250,
  });

  const [language, setLanguage] = useState<LanguageMode>("hinglish");
  const [ttsEnabled, setTtsEnabled] = useState<boolean>(true);
  const [isOffline, setIsOffline] = useState<boolean>(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [statusMessage, setStatusMessage] = useState<string>("Ready to listen");

  const [products, setProducts] = useState<Product[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [movements, setMovements] = useState<InventoryMovement[]>([]);
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);

  const [conversations, setConversations] = useState<DayConversation[]>([
    {
      date: todayYmd,
      label: "Today",
      summary: "Ready for voice or text commands",
      entries: [],
    },
  ]);

  const [activeDate, setActiveDate] = useState<string>(todayYmd);
  const [offlineQueue, setOfflineQueue] = useState<QueuedVoiceCommand[]>([]);
  const [newProductDraft, setNewProductDraft] = useState<NewProductDraft | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [pendingFlow, setPendingFlow] = useState<PendingFlowState>(null);
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);
  const [authUser, setAuthUser] = useState<{ id: string; email: string; name: string } | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState<boolean>(false);
  const [isDemoMode, setIsDemoMode] = useState<boolean>(false);

  // Track last entity / operation in active day context for anaphora & corrections
  const [lastContext, setLastContext] = useState<{
    productId?: string;
    productName?: string;
    lastReceiveQty?: number;
    lastSaleId?: string;
    lastOperationId?: string;
  }>({});

  useEffect(() => {
    listOfflineCommands().then(setOfflineQueue);
  }, []);

  const refreshLiveWorkspace = useCallback(async () => {
    if (!supabase) return;
    const { data: sessionData } = await supabase.auth.getSession();
    if (!sessionData.session) {
      setAuthUser(null);
      setNeedsOnboarding(false);
      setIsLiveBackend(false);
      return;
    }
    const u = sessionData.session.user;
    const displayName = String(
      u.user_metadata?.full_name || u.user_metadata?.name || u.email || "Owner"
    );
    setAuthUser({ id: u.id, email: u.email ?? "", name: displayName });
    try {
      const boot = (await fetchWorkspaceBootstrap()) as Record<string, unknown>;
      setNeedsOnboarding(false);
      setIsDemoMode(false);
      const biz = boot.business as Record<string, unknown> | undefined;
      const sub = boot.subscription as Record<string, unknown> | undefined;
      if (biz) {
        const plan = (sub?.subscription_plans as Record<string, unknown> | undefined) ?? {};
        const limits = (plan.limits as Record<string, unknown> | undefined) ?? {};
        const code = (plan.code as SubscriptionTierCode | undefined) ?? "free";
        setStore({
          name: String(biz.name ?? "Store"),
          ownerName: displayName,
          city: String(biz.city ?? ""),
          timezone: String(biz.timezone ?? "Asia/Kolkata"),
          tier: code,
          monthlyVoiceUsed: Number(sub?.monthly_voice_used ?? 0),
          monthlyVoiceLimit: Number(limits.monthly_voice_turns ?? 250),
        });
      }
      const rawProds = (boot.products as Record<string, unknown>[]) ?? [];
      setProducts(
        rawProds.map((p) => {
          const inv = p.inventory as Record<string, unknown>[] | Record<string, unknown> | null;
          const stockVal = Array.isArray(inv)
            ? Number(inv[0]?.current_quantity ?? 0)
            : Number((inv as Record<string, unknown> | null)?.current_quantity ?? 0);
          const alList = (p.product_aliases as { alias_text: string }[] | undefined) ?? [];
          return {
            id: String(p.id),
            skuCode: String(p.sku_code ?? ""),
            name: String(p.name),
            category: String(p.category ?? "General"),
            baseUnit: (p.base_unit as BaseUnit) ?? "piece",
            costPrice: Number(p.default_cost_price ?? 0),
            sellingPrice: Number(p.default_selling_price ?? 0),
            stock: stockVal,
            lowStockThreshold: Number(p.low_stock_threshold ?? 5),
            aliases: alList.map((a) => a.alias_text),
          };
        })
      );
      const rawCusts = (boot.customers as Record<string, unknown>[]) ?? [];
      setCustomers(
        rawCusts.map((c) => ({
          id: String(c.id),
          name: String(c.name),
          phone: String(c.phone ?? ""),
          areaNote: String(c.area_note ?? ""),
          outstandingBalance: Number(c.outstanding_balance ?? 0),
        }))
      );
      const rawMovs = (boot.movements as Record<string, unknown>[]) ?? [];
      setMovements(
        rawMovs.map((m) => {
          const pRel = m.products as { name?: string } | null;
          return {
            id: String(m.id),
            productId: String(m.product_id),
            productName: String(pRel?.name ?? "Item"),
            movementType: (m.movement_type as InventoryMovement["movementType"]) ?? "receive",
            quantityDelta: Number(m.quantity_delta ?? 0),
            unit: (m.unit as BaseUnit) ?? "piece",
            unitCost: m.unit_cost !== null && m.unit_cost !== undefined ? Number(m.unit_cost) : undefined,
            transactionDate: String(m.transaction_date),
            notes: String(m.notes ?? ""),
            operationId: String(m.operation_id),
            createdAt: String(m.created_at),
          };
        })
      );
      const rawSales = (boot.sales as Record<string, unknown>[]) ?? [];
      setSales(
        rawSales.map((s) => {
          const cRel = s.customers as { name?: string } | null;
          const itemsRaw = (s.sale_items as Record<string, unknown>[] | undefined) ?? [];
          return {
            id: String(s.id),
            customerId: s.customer_id ? String(s.customer_id) : undefined,
            customerName: String(cRel?.name ?? "Walk-in Customer"),
            items: itemsRaw.map((it) => {
              const pRel = it.products as { name?: string } | null;
              return {
                productId: String(it.product_id),
                productName: String(pRel?.name ?? "Item"),
                quantity: Number(it.quantity ?? 0),
                unit: (it.unit as BaseUnit) ?? "piece",
                unitPrice: Number(it.unit_price ?? 0),
                lineTotal: Number(it.line_total ?? 0),
              };
            }),
            totalAmount: Number(s.total_amount ?? 0),
            paidAmount: Number(s.paid_amount ?? 0),
            paymentStatus: (s.payment_status as Sale["paymentStatus"]) ?? "paid",
            transactionDate: String(s.transaction_date),
            status: (s.status as Sale["status"]) ?? "active",
            operationId: String(s.operation_id),
            createdAt: String(s.created_at),
          };
        })
      );
      const rawExps = (boot.expenses as Record<string, unknown>[]) ?? [];
      setExpenses(
        rawExps.map((ex) => ({
          id: String(ex.id),
          category: String(ex.category ?? "General"),
          description: String(ex.description ?? ""),
          amount: Number(ex.amount ?? 0),
          paymentMethod: (ex.payment_method as Expense["paymentMethod"]) ?? "cash",
          transactionDate: String(ex.transaction_date),
          status: (ex.status as Expense["status"]) ?? "active",
          operationId: String(ex.operation_id),
          createdAt: String(ex.created_at),
        }))
      );
      const rawConvs = (boot.conversations as Record<string, unknown>[]) ?? [];
      const rawMsgs = (boot.messages as Record<string, unknown>[]) ?? [];
      if (rawConvs.length > 0) {
        setConversations(
          rawConvs.map((conv) => {
            const cDate = String(conv.conversation_date);
            const entries: ChatEntry[] = rawMsgs
              .filter((m) => String(m.conversation_date) === cDate)
              .map((m) => {
                const ui = (m.ui_payload as VoiceTurnResult | null) ?? null;
                return {
                  id: String(m.id),
                  role: (m.role as "user" | "assistant") ?? "assistant",
                  content: String(m.content),
                  timestamp: formatTimeIST(String(m.created_at)),
                  language: (m.language as LanguageMode) ?? "hinglish",
                  operationId: m.linked_operation_id ? String(m.linked_operation_id) : undefined,
                  receipt: ui?.receipts?.[0],
                  receipts: ui?.receipts,
                  clarification: ui?.clarification ?? undefined,
                };
              });
            return {
              date: cDate,
              label: formatDayBadge(cDate, todayYmd),
              summary: String(conv.daily_summary ?? "Daily ledger chat"),
              entries,
            };
          })
        );
      } else {
        setConversations([
          {
            date: todayYmd,
            label: "Today",
            summary: "Ready for voice or text commands",
            entries: [],
          },
        ]);
      }
      setIsLiveBackend(true);
      setStatusMessage("Live");
    } catch (err) {
      const msg = err instanceof Error ? err.message.toLowerCase() : "";
      if (msg.includes("no store") || msg.includes("404") || msg.includes("onboard")) {
        setNeedsOnboarding(true);
      }
      setIsLiveBackend(false);
    }
  }, [todayYmd]);

  useEffect(() => {
    refreshLiveWorkspace();
    if (!supabase) return;
    const { data: sub } = supabase.auth.onAuthStateChange(() => {
      refreshLiveWorkspace();
    });
    return () => sub.subscription.unsubscribe();
  }, [refreshLiveWorkspace]);

  const activeConversation = useMemo(
    () =>
      conversations.find((c) => c.date === activeDate) ?? {
        date: activeDate,
        label: formatDayBadge(activeDate, todayYmd),
        summary: "No entries yet",
        entries: [],
      },
    [conversations, activeDate, todayYmd]
  );

  const appendEntriesToDate = useCallback(
    (date: string, newEntries: ChatEntry[], summaryHint?: string) => {
      setConversations((prev) => {
        const exists = prev.some((c) => c.date === date);
        if (!exists) {
          return [
            {
              date,
              label: formatDayBadge(date, todayYmd),
              summary: summaryHint ?? "Active conversation",
              entries: newEntries,
            },
            ...prev,
          ];
        }
        return prev.map((c) =>
          c.date === date
            ? {
                ...c,
                summary: summaryHint ?? c.summary,
                entries: [...c.entries, ...newEntries],
              }
            : c
        );
      });
    },
    [todayYmd]
  );

  const commitStockReceive = useCallback(
    (params: {
      product: Product;
      quantity: number;
      unitCost: number;
      transactionDate: string;
      operationId: string;
      notes?: string;
      userText?: string;
      verifiedAlias?: string;
    }) => {
      const { product, quantity, unitCost, transactionDate, operationId, notes, verifiedAlias } = params;
      const beforeStock = product.stock;
      const afterStock = beforeStock + quantity;
      const totalCost = Number((quantity * unitCost).toFixed(2));

      setProducts((prev) =>
        prev.map((p) =>
          p.id === product.id
            ? {
                ...p,
                stock: afterStock,
                costPrice: unitCost > 0 ? unitCost : p.costPrice,
                aliases:
                  verifiedAlias && !p.aliases.includes(verifiedAlias.toLowerCase())
                    ? [...p.aliases, verifiedAlias.toLowerCase()]
                    : p.aliases,
              }
            : p
        )
      );

      const nowIso = new Date().toISOString();
      setMovements((prev) => [
        {
          id: `mov-${operationId}`,
          productId: product.id,
          productName: product.name,
          movementType: "receive",
          quantityDelta: quantity,
          unit: product.baseUnit,
          unitCost,
          transactionDate,
          notes: notes ?? "Voice stock receive",
          operationId,
          createdAt: nowIso,
        },
        ...prev,
      ]);

      setLastContext({
        productId: product.id,
        productName: product.name,
        lastReceiveQty: quantity,
        lastOperationId: operationId,
      });

      const aliasLine = verifiedAlias
        ? [{ label: "Verified Alias Saved", value: `"${verifiedAlias}" → ${product.name}`, tone: "sage" as const }]
        : [];

      const reply = `${formatQty(quantity, product.baseUnit)} ${product.name} ${formatINR(unitCost)}/unit par receive hui hain (Total ${formatINR(totalCost)}). Closing stock: ${afterStock}. Aur kuch?`;

      const slip: ReceiptSlip = {
        id: `slip-${operationId}`,
        operationId,
        kind: "receive",
        title: `Stock Added · ${product.name}`,
        subtitle: verifiedAlias ? `Alias "${verifiedAlias}" verified & saved` : "Verified Inventory Receipt",
        transactionDate,
        amountINR: totalCost,
        lines: [
          ...aliasLine,
          { label: "Received", value: `+${formatQty(quantity, product.baseUnit)} @ ${formatINR(unitCost)}`, tone: "sage" },
          { label: "Stock Level", value: `${beforeStock} → ${afterStock}`, tone: "neutral" },
        ],
        status: "saved",
        reversible: true,
        auditTrail: [{ timestamp: formatTimeIST(nowIso), action: "created", summary: `+${quantity} @ ${formatINR(unitCost)}` }],
      };

      appendEntriesToDate(todayYmd, [
        {
          id: `ast-${operationId}`,
          role: "assistant",
          content: reply,
          timestamp: formatTimeIST(nowIso),
          language,
          operationId,
          receipt: slip,
        },
      ]);

      setStore((s) => ({ ...s, monthlyVoiceUsed: s.monthlyVoiceUsed + 1 }));
      setVoicePhase("saved");
      setStatusMessage("Saved to Ledger");
      speakReply(reply, language, ttsEnabled);
    },
    [appendEntriesToDate, language, todayYmd, ttsEnabled]
  );

  const commitSale = useCallback(
    (params: {
      product: Product;
      quantity: number;
      unitPrice: number;
      paymentStatus: "paid" | "credit";
      customer?: Customer;
      transactionDate: string;
      operationId: string;
    }) => {
      const { product, quantity, unitPrice, paymentStatus, customer, transactionDate, operationId } = params;
      const beforeStock = product.stock;
      const afterStock = beforeStock - quantity;
      const totalAmount = Number((quantity * unitPrice).toFixed(2));
      const paidAmount = paymentStatus === "paid" ? totalAmount : 0;
      const nowIso = new Date().toISOString();
      const saleId = `sale-${operationId}`;

      setProducts((prev) =>
        prev.map((p) => (p.id === product.id ? { ...p, stock: afterStock } : p))
      );

      if (paymentStatus === "credit" && customer) {
        setCustomers((prev) =>
          prev.map((c) =>
            c.id === customer.id
              ? { ...c, outstandingBalance: c.outstandingBalance + totalAmount }
              : c
          )
        );
      }

      setMovements((prev) => [
        {
          id: `mov-${operationId}`,
          productId: product.id,
          productName: product.name,
          movementType: "sale",
          quantityDelta: -quantity,
          unit: product.baseUnit,
          transactionDate,
          notes: paymentStatus === "credit" ? `Udhaar sale to ${customer?.name}` : "Cash sale",
          operationId,
          createdAt: nowIso,
        },
        ...prev,
      ]);

      setSales((prev) => [
        {
          id: saleId,
          customerId: customer?.id,
          customerName: customer?.name ?? "Walk-in Customer",
          items: [
            {
              productId: product.id,
              productName: product.name,
              quantity,
              unit: product.baseUnit,
              unitPrice,
              lineTotal: totalAmount,
            },
          ],
          totalAmount,
          paidAmount,
          paymentStatus,
          transactionDate,
          status: "active",
          operationId,
          createdAt: nowIso,
        },
        ...prev,
      ]);

      setLastContext({
        productId: product.id,
        productName: product.name,
        lastSaleId: saleId,
        lastOperationId: operationId,
      });

      const reply =
        paymentStatus === "credit" && customer
          ? `${customer.name} ke naam ${formatQty(quantity, product.baseUnit)} ${product.name} (${formatINR(totalAmount)}) udhaar record ho gaya.`
          : `${formatQty(quantity, product.baseUnit)} ${product.name} ki sale (${formatINR(totalAmount)} cash) save ho gayi.`;

      const slip: ReceiptSlip = {
        id: `slip-${operationId}`,
        operationId,
        kind: "sale",
        title: paymentStatus === "credit" ? `Udhaar Sale · ${customer?.name}` : `Cash Sale · ${product.name}`,
        subtitle: paymentStatus === "credit" ? "Added to Customer Credit Ledger" : "Walk-in Paid Sale",
        transactionDate,
        amountINR: totalAmount,
        lines: [
          { label: product.name, value: `-${formatQty(quantity, product.baseUnit)} @ ${formatINR(unitPrice)}`, tone: "sage" },
          { label: "Stock Level", value: `${beforeStock} → ${afterStock}`, tone: "neutral" },
          ...(paymentStatus === "credit" && customer
            ? [{ label: "Customer Balance", value: formatINR(customer.outstandingBalance + totalAmount), tone: "ochre" as const }]
            : []),
        ],
        status: "saved",
        reversible: true,
        auditTrail: [{ timestamp: formatTimeIST(nowIso), action: "created", summary: `Sale ${quantity} × ${formatINR(unitPrice)}` }],
      };

      appendEntriesToDate(todayYmd, [
        {
          id: `ast-${operationId}`,
          role: "assistant",
          content: reply,
          timestamp: formatTimeIST(nowIso),
          language,
          operationId,
          receipt: slip,
        },
      ]);

      setStore((s) => ({ ...s, monthlyVoiceUsed: s.monthlyVoiceUsed + 1 }));
      setVoicePhase("saved");
      setStatusMessage("Saved to Ledger");
      speakReply(reply, language, ttsEnabled);
    },
    [appendEntriesToDate, language, todayYmd, ttsEnabled]
  );

  const commitDamageOrExpiry = useCallback(
    (params: {
      product: Product;
      quantity: number;
      kind: "damage" | "expiry";
      transactionDate: string;
      linkedNote?: string;
      operationId: string;
      netContextQty?: number;
    }) => {
      const { product, quantity, kind, transactionDate, linkedNote, operationId, netContextQty } = params;
      if (quantity > product.stock) {
        const msg = `Stock mein sirf ${product.stock} ${product.name} available hain, ${quantity} deduct nahi kar sakte. Kripya sahi quantity batayein.`;
        appendEntriesToDate(todayYmd, [
          {
            id: `clar-${operationId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(new Date().toISOString()),
            language,
            clarification: { kind: "negative_stock", prompt: msg },
          },
        ]);
        setVoicePhase("clarifying");
        setStatusMessage("Stock Limit Clarification");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      const beforeStock = product.stock;
      const afterStock = beforeStock - quantity;
      const nowIso = new Date().toISOString();

      setProducts((prev) =>
        prev.map((p) => (p.id === product.id ? { ...p, stock: afterStock } : p))
      );

      setMovements((prev) => [
        {
          id: `mov-${operationId}`,
          productId: product.id,
          productName: product.name,
          movementType: kind,
          quantityDelta: -quantity,
          unit: product.baseUnit,
          transactionDate,
          notes: linkedNote ?? (kind === "expiry" ? "Expired stock deducted" : "Damaged stock deducted"),
          operationId,
          createdAt: nowIso,
        },
        ...prev,
      ]);

      const reply =
        netContextQty !== undefined
          ? `${netContextQty} received aur ${quantity} damaged. Net stock mein ${netContextQty - quantity} ${product.baseUnit}s add hui hain.`
          : `${quantity} ${product.name} ${kind === "expiry" ? "expired" : "damaged"} mark kar diya gaya hai. Remaining stock: ${afterStock}.`;

      const slip: ReceiptSlip = {
        id: `slip-${operationId}`,
        operationId,
        kind,
        title: `${kind === "expiry" ? "Expiry Deduction" : "Damage Deduction"} · ${product.name}`,
        subtitle: linkedNote ?? "Linked Inventory Adjustment",
        transactionDate,
        lines: [
          { label: kind === "expiry" ? "Expired" : "Damaged", value: `-${formatQty(quantity, product.baseUnit)}`, tone: "crimson" },
          ...(netContextQty !== undefined
            ? [{ label: "Net Batch Added", value: `+${netContextQty - quantity} ${product.baseUnit}s`, tone: "sage" as const }]
            : []),
          { label: "Stock Level", value: `${beforeStock} → ${afterStock}`, tone: "neutral" },
        ],
        status: "saved",
        reversible: true,
      };

      appendEntriesToDate(todayYmd, [
        {
          id: `ast-${operationId}`,
          role: "assistant",
          content: reply,
          timestamp: formatTimeIST(nowIso),
          language,
          operationId,
          receipt: slip,
        },
      ]);

      setStore((s) => ({ ...s, monthlyVoiceUsed: s.monthlyVoiceUsed + 1 }));
      setVoicePhase("saved");
      setStatusMessage("Ledger Updated");
      speakReply(reply, language, ttsEnabled);
    },
    [appendEntriesToDate, language, todayYmd, ttsEnabled]
  );

  const commitExpense = useCallback(
    (params: {
      category: string;
      description: string;
      amount: number;
      paymentMethod: "cash" | "upi" | "bank";
      transactionDate: string;
      operationId: string;
    }) => {
      const { category, description, amount, paymentMethod, transactionDate, operationId } = params;
      const nowIso = new Date().toISOString();

      setExpenses((prev) => [
        {
          id: `exp-${operationId}`,
          category,
          description,
          amount,
          paymentMethod,
          transactionDate,
          status: "active",
          operationId,
          createdAt: nowIso,
        },
        ...prev,
      ]);

      const reply = `${formatINR(amount)} ka ${category} expense (${paymentMethod.toUpperCase()}) record ho gaya hai.`;
      appendEntriesToDate(todayYmd, [
        {
          id: `ast-${operationId}`,
          role: "assistant",
          content: reply,
          timestamp: formatTimeIST(nowIso),
          language,
          operationId,
          receipt: {
            id: `slip-${operationId}`,
            operationId,
            kind: "expense",
            title: `Expense · ${category}`,
            subtitle: description,
            transactionDate,
            amountINR: amount,
            lines: [
              { label: "Paid Via", value: paymentMethod.toUpperCase(), tone: "neutral" },
              { label: "Amount", value: formatINR(amount), tone: "ochre" },
            ],
            status: "saved",
            reversible: true,
          },
        },
      ]);

      setStore((s) => ({ ...s, monthlyVoiceUsed: s.monthlyVoiceUsed + 1 }));
      setVoicePhase("saved");
      setStatusMessage("Expense Saved");
      speakReply(reply, language, ttsEnabled);
    },
    [appendEntriesToDate, language, todayYmd, ttsEnabled]
  );

  const requestHighValueConfirm = useCallback(
    (conf: PendingConfirmation) => {
      setPendingConfirmation(conf);
      setVoicePhase("confirming");
      setStatusMessage("Confirmation Required (>= ₹5,000)");
      const msg = `${conf.title}: ${formatINR(conf.amountINR ?? 0)} ek high-value transaction hai. Confirm karne ke liye "Yes" bolein ya Confirm dabayein.`;
      appendEntriesToDate(todayYmd, [
        {
          id: `conf-${conf.operationId}`,
          role: "assistant",
          content: msg,
          timestamp: formatTimeIST(new Date().toISOString()),
          language,
        },
      ]);
      speakReply(msg, language, ttsEnabled);
    },
    [appendEntriesToDate, language, todayYmd, ttsEnabled]
  );

  const resolveMissingSlotAndExecute = useCallback(
    (draft: PendingSlotDraft) => {
      const opId = makeOperationId();
      if (draft.kind === "receive" && draft.productId) {
        const prod = products.find((p) => p.id === draft.productId);
        if (!prod || !draft.quantity) return;
        if (draft.unitPrice === undefined) {
          const msg = `${draft.quantity} ${prod.name} kis purchase price par aayi hain? (Last rate ${formatINR(prod.costPrice)}/${prod.baseUnit} tha)`;
          setPendingFlow({ type: "missing_slot", draft: { ...draft, missingField: "purchase_price" } });
          appendEntriesToDate(todayYmd, [
            {
              id: `slot-${opId}`,
              role: "assistant",
              content: msg,
              timestamp: formatTimeIST(new Date().toISOString()),
              language,
              clarification: {
                kind: "missing_slot",
                prompt: msg,
                candidates: [
                  { id: "p-last", label: `Same ₹${prod.costPrice}/${prod.baseUnit}`, value: String(prod.costPrice) },
                  { id: "p-30", label: "₹30 / unit", value: "30" },
                  { id: "p-free", label: "Free Bonus (₹0)", value: "0" },
                ],
              },
            },
          ]);
          setVoicePhase("clarifying");
          setStatusMessage("Purchase Price Needed");
          speakReply(msg, language, ttsEnabled);
          return;
        }
        const totalVal = draft.quantity * draft.unitPrice;
        if (totalVal >= 5000) {
          requestHighValueConfirm({
            operationId: opId,
            token: `tok-${opId}`,
            title: `High-Value Stock Receive · ${prod.name}`,
            description: `${formatQty(draft.quantity, prod.baseUnit)} @ ${formatINR(draft.unitPrice)}`,
            amountINR: totalVal,
            impactSummary: `Inventory +${draft.quantity}, Total Value ${formatINR(totalVal)}`,
            payload: { kind: "receive", productId: prod.id, quantity: draft.quantity, unitCost: draft.unitPrice, transactionDate: draft.transactionDate },
          });
          return;
        }
        commitStockReceive({
          product: prod,
          quantity: draft.quantity,
          unitCost: draft.unitPrice,
          transactionDate: draft.transactionDate,
          operationId: opId,
        });
      } else if (draft.kind === "sale" && draft.productId) {
        const prod = products.find((p) => p.id === draft.productId);
        if (!prod || !draft.quantity) return;
        if (draft.quantity > prod.stock) {
          const msg = `Negative stock allowed nahi hai. ${prod.name} ka current stock sirf ${prod.stock} ${prod.baseUnit}s hai — ${draft.quantity} nahi bech sakte.`;
          appendEntriesToDate(todayYmd, [
            {
              id: `neg-${opId}`,
              role: "assistant",
              content: msg,
              timestamp: formatTimeIST(new Date().toISOString()),
              language,
              clarification: { kind: "negative_stock", prompt: msg },
            },
          ]);
          setVoicePhase("clarifying");
          setStatusMessage("Negative Stock Blocked");
          speakReply(msg, language, ttsEnabled);
          return;
        }
        const price = draft.unitPrice ?? prod.sellingPrice;
        const total = draft.quantity * price;
        const cust = draft.customerId ? customers.find((c) => c.id === draft.customerId) : undefined;
        if (total >= 5000) {
          requestHighValueConfirm({
            operationId: opId,
            token: `tok-${opId}`,
            title: `High-Value ${draft.paymentStatus === "credit" ? "Udhaar" : "Cash"} Sale`,
            description: `${cust ? cust.name + " · " : ""}${formatQty(draft.quantity, prod.baseUnit)} ${prod.name}`,
            amountINR: total,
            impactSummary: `Stock -${draft.quantity}, Amount ${formatINR(total)}`,
            payload: { kind: "sale", productId: prod.id, quantity: draft.quantity, unitPrice: price, paymentStatus: draft.paymentStatus ?? "paid", customerId: cust?.id, transactionDate: draft.transactionDate },
          });
          return;
        }
        commitSale({
          product: prod,
          quantity: draft.quantity,
          unitPrice: price,
          paymentStatus: draft.paymentStatus ?? "paid",
          customer: cust,
          transactionDate: draft.transactionDate,
          operationId: opId,
        });
      }
    },
    [appendEntriesToDate, commitSale, commitStockReceive, customers, language, products, requestHighValueConfirm, todayYmd, ttsEnabled]
  );

  const confirmNewProductFromModal = useCallback(
    async (draft: NewProductDraft) => {
      const opId = makeOperationId();
      const costPrice = Number(draft.costPrice) || 0;
      const sellingPrice = Number(draft.sellingPrice) || costPrice;
      const lowStockThreshold = Number(draft.lowStockThreshold) || 5;

      if (isLiveBackend) {
        try {
          const remote = await createProductFromPopupRemote({
            operation_id: opId,
            name: draft.name.trim(),
            category: draft.category || "General",
            base_unit: draft.baseUnit,
            quantity: draft.quantity,
            cost_price: costPrice,
            selling_price: sellingPrice,
            low_stock_threshold: lowStockThreshold,
            action_kind: draft.actionKind,
          });
          setNewProductDraft(null);
          setPendingFlow(null);
          appendEntriesToDate(todayYmd, [
            {
              id: `ast-${remote.operation_id}`,
              role: "assistant",
              content: remote.reply,
              timestamp: formatTimeIST(new Date().toISOString()),
              language: remote.language,
              operationId: remote.operation_id,
              receipt: remote.receipts?.[0],
            },
          ]);
          speakReply(remote.reply, remote.language, ttsEnabled);
          await refreshLiveWorkspace();
          return;
        } catch {
          // Fallback to local update if unreachable
        }
      }

      const newProd: Product = {
        id: `prod-${opId.slice(0, 8)}`,
        skuCode: `NEW-${Math.floor(100 + Math.random() * 899)}`,
        name: draft.name.trim(),
        category: draft.category || "General",
        baseUnit: draft.baseUnit,
        costPrice,
        sellingPrice,
        stock: 0,
        lowStockThreshold,
        aliases: [draft.name.trim().toLowerCase()],
      };

      setProducts((prev) => [newProd, ...prev]);
      setNewProductDraft(null);
      setPendingFlow(null);

      commitStockReceive({
        product: newProd,
        quantity: draft.quantity,
        unitCost: costPrice,
        transactionDate: todayYmd,
        operationId: opId,
        notes: "New product created & stocked",
      });
    },
    [appendEntriesToDate, commitStockReceive, isLiveBackend, refreshLiveWorkspace, todayYmd, ttsEnabled]
  );

  const dismissNewProductModal = useCallback(() => {
    setNewProductDraft(null);
    setVoicePhase("idle");
    setStatusMessage("Cancelled");
  }, []);

  const confirmPendingHighValue = useCallback(async () => {
    if (!pendingConfirmation) return;
    const { payload, operationId, token } = pendingConfirmation;
    setPendingConfirmation(null);

    if (isLiveBackend && token && !token.startsWith("tok-")) {
      try {
        const remote = await confirmTier3Remote(operationId, token, true);
        appendEntriesToDate(todayYmd, [
          {
            id: `ast-${remote.operation_id}`,
            role: "assistant",
            content: remote.reply,
            timestamp: formatTimeIST(new Date().toISOString()),
            language: remote.language,
            operationId: remote.operation_id,
            receipt: remote.receipts?.[0],
          },
        ]);
        setVoicePhase("saved");
        setStatusMessage("Confirmed & Saved");
        speakReply(remote.reply, remote.language, ttsEnabled);
        await refreshLiveWorkspace();
        return;
      } catch {
        // Fallback if local token
      }
    }

    if (payload.kind === "receive") {
      const prod = products.find((p) => p.id === payload.productId);
      if (prod) {
        commitStockReceive({
          product: prod,
          quantity: Number(payload.quantity),
          unitCost: Number(payload.unitCost),
          transactionDate: String(payload.transactionDate),
          operationId,
        });
      }
    } else if (payload.kind === "sale") {
      const prod = products.find((p) => p.id === payload.productId);
      const cust = payload.customerId ? customers.find((c) => c.id === payload.customerId) : undefined;
      if (prod) {
        commitSale({
          product: prod,
          quantity: Number(payload.quantity),
          unitPrice: Number(payload.unitPrice),
          paymentStatus: (payload.paymentStatus as "paid" | "credit") ?? "paid",
          customer: cust,
          transactionDate: String(payload.transactionDate),
          operationId,
        });
      }
    } else if (payload.kind === "direct_udhaar") {
      const cust = customers.find((c) => c.id === payload.customerId);
      const amount = Number(payload.amount);
      if (cust) {
        const nowIso = new Date().toISOString();
        const saleId = `sale-${operationId}`;
        setCustomers((prev) =>
          prev.map((c) => (c.id === cust.id ? { ...c, outstandingBalance: c.outstandingBalance + amount } : c))
        );
        setSales((prev) => [
          {
            id: saleId,
            customerId: cust.id,
            customerName: cust.name,
            items: [],
            totalAmount: amount,
            paidAmount: 0,
            paymentStatus: "credit",
            transactionDate: todayYmd,
            status: "active",
            operationId,
            createdAt: nowIso,
          },
          ...prev,
        ]);
        const reply = `${cust.name} ke khate mein ${formatINR(amount)} udhaar confirm aur save ho gaya.`;
        appendEntriesToDate(todayYmd, [
          {
            id: `ast-${operationId}`,
            role: "assistant",
            content: reply,
            timestamp: formatTimeIST(nowIso),
            language,
            operationId,
            receipt: {
              id: `slip-${operationId}`,
              operationId,
              kind: "sale",
              title: `Confirmed Udhaar · ${cust.name}`,
              subtitle: "Tier-3 High-Value Confirmation Passed",
              transactionDate: todayYmd,
              amountINR: amount,
              lines: [
                { label: "Udhaar Added", value: formatINR(amount), tone: "ochre" },
                { label: "New Balance", value: formatINR(cust.outstandingBalance + amount), tone: "neutral" },
              ],
              status: "saved",
              reversible: true,
            },
          },
        ]);
        setVoicePhase("saved");
        setStatusMessage("Confirmed & Saved");
        speakReply(reply, language, ttsEnabled);
      }
    }
  }, [appendEntriesToDate, commitSale, commitStockReceive, customers, isLiveBackend, language, pendingConfirmation, products, refreshLiveWorkspace, todayYmd, ttsEnabled]);

  const cancelPendingHighValue = useCallback(() => {
    setPendingConfirmation(null);
    setVoicePhase("idle");
    setStatusMessage("Action Cancelled");
    const msg = "High-value transaction cancel kar diya gaya hai. Koi record change nahi hua.";
    appendEntriesToDate(todayYmd, [
      {
        id: `cancel-${Date.now()}`,
        role: "assistant",
        content: msg,
        timestamp: formatTimeIST(new Date().toISOString()),
        language,
      },
    ]);
  }, [appendEntriesToDate, language, todayYmd]);

  const undoReceipt = useCallback(
    (operationId: string) => {
      const mov = movements.find((m) => m.operationId === operationId);
      const nowIso = new Date().toISOString();
      if (mov) {
        setProducts((prev) =>
          prev.map((p) =>
            p.id === mov.productId ? { ...p, stock: Math.max(0, p.stock - mov.quantityDelta) } : p
          )
        );
        setMovements((prev) => [
          {
            id: `rev-${Date.now()}`,
            productId: mov.productId,
            productName: mov.productName,
            movementType: "reversal",
            quantityDelta: -mov.quantityDelta,
            unit: mov.unit,
            transactionDate: todayYmd,
            notes: `Reversal of ${operationId.slice(0, 6)}`,
            operationId: `rev-${operationId}`,
            createdAt: nowIso,
          },
          ...prev,
        ]);
      }

      const linkedSale = sales.find((s) => s.operationId === operationId);
      if (linkedSale) {
        setSales((prev) =>
          prev.map((s) => (s.operationId === operationId ? { ...s, status: "voided" } : s))
        );
        if (linkedSale.paymentStatus === "credit" && linkedSale.customerId) {
          setCustomers((prev) =>
            prev.map((c) =>
              c.id === linkedSale.customerId
                ? { ...c, outstandingBalance: Math.max(0, c.outstandingBalance - linkedSale.totalAmount) }
                : c
            )
          );
        }
      }

      setConversations((prev) =>
        prev.map((c) => ({
          ...c,
          entries: c.entries.map((e) =>
            e.receipt?.operationId === operationId
              ? {
                  ...e,
                  receipt: {
                    ...e.receipt,
                    status: "undone",
                    reversible: false,
                    auditTrail: [
                      ...(e.receipt.auditTrail ?? []),
                      { timestamp: formatTimeIST(nowIso), action: "undone", summary: "Compensating reversal committed" },
                    ],
                  },
                }
              : e
          ),
        }))
      );

      const msg = `Operation reverse ho gaya hai aur immutable audit log mein mark kar diya gaya.`;
      appendEntriesToDate(todayYmd, [
        {
          id: `undo-${Date.now()}`,
          role: "assistant",
          content: msg,
          timestamp: formatTimeIST(nowIso),
          language,
        },
      ]);
      speakReply(msg, language, ttsEnabled);
    },
    [appendEntriesToDate, language, movements, sales, todayYmd, ttsEnabled]
  );

  const applyRemoteTurnResult = useCallback(
    async (res: VoiceTurnResult, opts?: { includeUserTranscript?: boolean }) => {
      const nowIso = new Date().toISOString();
      const entriesToAdd: ChatEntry[] = [];
      if (opts?.includeUserTranscript && res.transcript) {
        entriesToAdd.push({
          id: `usr-${res.operation_id}`,
          role: "user",
          content: res.transcript,
          timestamp: formatTimeIST(nowIso),
          language: res.language,
          operationId: res.operation_id,
        });
      }
      entriesToAdd.push({
        id: `ast-${res.operation_id}`,
        role: "assistant",
        content: res.reply,
        timestamp: formatTimeIST(nowIso),
        language: res.language,
        operationId: res.operation_id,
        receipt: res.receipts?.[0],
        receipts: res.receipts,
        clarification: res.clarification ?? undefined,
      });
      appendEntriesToDate(todayYmd, entriesToAdd);

      if (res.new_product_draft) {
        setNewProductDraft(res.new_product_draft);
      }
      if (res.confirmation) {
        setPendingConfirmation(res.confirmation);
      }

      setVoicePhase(
        res.status === "policy_blocked"
          ? "blocked"
          : res.status === "needs_clarification" || res.status === "memory_boundary" || res.status === "new_product_popup"
            ? "clarifying"
            : res.status === "needs_confirmation"
              ? "confirming"
              : res.status === "retry_audio"
                ? "error"
                : "saved"
      );
      setStatusMessage(
        res.status === "executed" || res.status === "query_answered"
          ? "Synced with Ledger"
          : res.status === "policy_blocked"
            ? "Blocked by Policy"
            : "Clarification Needed"
      );
      speakReply(res.reply, res.language, ttsEnabled);
      await refreshLiveWorkspace();
    },
    [appendEntriesToDate, refreshLiveWorkspace, todayYmd, ttsEnabled]
  );

  const submitCommand = useCallback(
    async (rawText: string, opts?: { fromOfflineSync?: boolean; operationId?: string }) => {
      const text = rawText.trim();
      if (!text) return;
      stopSpeaking();
      const opId = opts?.operationId ?? makeOperationId();
      const nowIso = new Date().toISOString();
      const lower = text.toLowerCase();

      if (!opts?.fromOfflineSync) {
        setActiveDate(todayYmd);
        appendEntriesToDate(todayYmd, [
          {
            id: `usr-${opId}`,
            role: "user",
            content: text,
            timestamp: formatTimeIST(nowIso),
            language,
            operationId: opId,
          },
        ]);
      }

      if (isLiveBackend && !isOffline && !opts?.fromOfflineSync) {
        try {
          setVoicePhase("validating");
          setStatusMessage("Processing via Gemini + Supabase");
          const remoteRes = await sendTextCommandRemote(text, opId, language);
          await applyRemoteTurnResult(remoteRes, { includeUserTranscript: false });
          return;
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : "Backend processing error";
          appendEntriesToDate(todayYmd, [
            {
              id: `err-${opId}`,
              role: "assistant",
              content: `Server error: ${errMsg}`,
              timestamp: formatTimeIST(nowIso),
              language,
            },
          ]);
          setVoicePhase("error");
          setStatusMessage("Backend Error");
          return;
        }
      }

      // Offline queueing into real IndexedDB
      if (isOffline && !opts?.fromOfflineSync) {
        const queued: QueuedVoiceCommand = {
          id: opId,
          operationId: opId,
          transcript: text,
          conversationDate: todayYmd,
          language,
          queuedAt: nowIso,
          status: "pending",
        };
        await enqueueOfflineCommand(queued);
        setOfflineQueue((prev) => [...prev, queued]);
        setVoicePhase("pending_sync");
        setStatusMessage("Queued Offline (IndexedDB)");

        const msg = "Internet offline hai — command safely queue kar di gayi hai. Connection aate hi FIFO order mein sync ho jayegi.";
        appendEntriesToDate(todayYmd, [
          {
            id: `q-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
            operationId: opId,
            receipt: {
              id: `slip-q-${opId}`,
              operationId: opId,
              kind: "query",
              title: "Queued Offline · Pending Sync",
              subtitle: "Stored safely in browser IndexedDB",
              transactionDate: todayYmd,
              lines: [{ label: "Transcript", value: text.slice(0, 48), tone: "ochre" }],
              status: "pending_sync",
            },
          },
        ]);
        return;
      }

      setVoicePhase("validating");
      setStatusMessage("Policy & Context Check");

      // 1. Handle active modal / confirmation via voice
      if (newProductDraft && /^(yes|haan|ha|add|kar do|confirm|ok|theek)/i.test(lower)) {
        confirmNewProductFromModal(newProductDraft);
        return;
      }
      if (newProductDraft && /^(no|nahi|cancel|mat)/i.test(lower)) {
        dismissNewProductModal();
        return;
      }
      if (pendingConfirmation && /^(yes|haan|ha|confirm|ok)/i.test(lower)) {
        confirmPendingHighValue();
        return;
      }
      if (pendingConfirmation && /^(no|nahi|cancel)/i.test(lower)) {
        cancelPendingHighValue();
        return;
      }

      // 2. Handle active pending flow (alias confirmation, missing slot, disambiguation)
      if (pendingFlow) {
        if (pendingFlow.type === "verify_alias") {
          if (/^(yes|haan|ha|ji|bilkul|yahi|correct)/i.test(lower)) {
            const { spoken, candidate, draft } = pendingFlow;
            setProducts((prev) =>
              prev.map((p) =>
                p.id === candidate.id && !p.aliases.includes(spoken.toLowerCase())
                  ? { ...p, aliases: [...p.aliases, spoken.toLowerCase()] }
                  : p
              )
            );
            setPendingFlow(null);
            resolveMissingSlotAndExecute({
              ...draft,
              productId: candidate.id,
              productName: candidate.name,
              unit: candidate.baseUnit,
              missingField: "purchase_price",
              aliasToVerify: {
                spoken,
                targetProductId: candidate.id,
                targetProductName: candidate.name,
              },
            });
            return;
          }
          if (/^(no|nahi|na|galat)/i.test(lower)) {
            setPendingFlow(null);
            const msg = "Theek hai, kaunsa product tha? Kripya sahi naam ya size batayein.";
            appendEntriesToDate(todayYmd, [
              { id: `no-${opId}`, role: "assistant", content: msg, timestamp: formatTimeIST(nowIso), language },
            ]);
            setVoicePhase("clarifying");
            setStatusMessage("Awaiting Clarification");
            speakReply(msg, language, ttsEnabled);
            return;
          }
        }

        if (pendingFlow.type === "disambiguate_product") {
          const matchedCand = pendingFlow.candidates.find((c) => {
            const cLower = c.name.toLowerCase();
            const normalizedInput = lower.replace(/\s+/g, "");
            const normalizedName = cLower.replace(/\s+/g, "");
            return (
              normalizedName.includes(normalizedInput) ||
              c.aliases.some((a) => lower.includes(a) || a.replace(/\s+/g, "").includes(normalizedInput)) ||
              (/(500|chhoti|chotti|small)/i.test(lower) && cLower.includes("500")) ||
              (/(2l|2 l|badi|baddi|large|1l|1 l)/i.test(lower) && cLower.includes("2l"))
            );
          });
          if (matchedCand) {
            const draft = pendingFlow.draft;
            setPendingFlow(null);
            resolveMissingSlotAndExecute({
              ...draft,
              productId: matchedCand.id,
              productName: matchedCand.name,
              unit: matchedCand.baseUnit,
              missingField: draft.kind === "receive" ? "purchase_price" : "selling_price",
            });
            return;
          }
        }

        if (pendingFlow.type === "disambiguate_customer") {
          const matchedCust = pendingFlow.candidates.find(
            (c) =>
              c.name
                .toLowerCase()
                .split(" ")
                .some((part) => part.length > 2 && lower.includes(part)) ||
              (c.areaNote && lower.includes(c.areaNote.toLowerCase())) ||
              c.phone.slice(-4).includes(lower)
          );
          if (matchedCust) {
            const amt = pendingFlow.draft.amount ?? 0;
            setPendingFlow(null);
            if (amt >= 5000) {
              requestHighValueConfirm({
                operationId: opId,
                token: `tok-${opId}`,
                title: `High-Value Udhaar · ${matchedCust.name}`,
                description: `${matchedCust.areaNote ?? ""} · ${matchedCust.phone}`,
                amountINR: amt,
                impactSummary: `Outstanding balance ${formatINR(matchedCust.outstandingBalance)} → ${formatINR(matchedCust.outstandingBalance + amt)}`,
                payload: { kind: "direct_udhaar", customerId: matchedCust.id, amount: amt },
              });
              return;
            }
          }
        }

        if (pendingFlow.type === "missing_slot") {
          let val = parseIndianNumber(text);
          if (val === null && pendingFlow.draft.productId && /(same|wahi|purana|purane|pichla|pichle|last)/i.test(lower)) {
            const p = products.find((item) => item.id === pendingFlow.draft.productId);
            if (p) val = pendingFlow.draft.missingField === "purchase_price" ? p.costPrice : p.sellingPrice;
          } else if (val === null && /(free|bonus|muft)/i.test(lower)) {
            val = 0;
          }
          if (val !== null) {
            const nextDraft = { ...pendingFlow.draft };
            if (nextDraft.missingField === "purchase_price" || nextDraft.missingField === "selling_price") {
              nextDraft.unitPrice = val;
            } else if (nextDraft.missingField === "quantity") {
              nextDraft.quantity = val;
            }
            setPendingFlow(null);
            if (nextDraft.kind === "expiry" && nextDraft.productId) {
              const prod = products.find((p) => p.id === nextDraft.productId);
              if (prod && nextDraft.quantity) {
                commitDamageOrExpiry({
                  product: prod,
                  quantity: nextDraft.quantity,
                  kind: "expiry",
                  transactionDate: nextDraft.transactionDate,
                  linkedNote: `Linked to ${nextDraft.transactionDate} batch`,
                  operationId: opId,
                });
                return;
              }
            }
            resolveMissingSlotAndExecute(nextDraft);
            return;
          }
        }
      }

      // 3. Hardcore Security: Block destructive intents immediately
      if (/(delete all|sab delete|saara data|drop table|wipe|truncate|clear database|sab hatao)/i.test(lower)) {
        const msg = "Security Policy: Destructive ya bulk-delete commands voice/AI se allowed nahi hain. Koi data modify nahi hua.";
        appendEntriesToDate(todayYmd, [
          {
            id: `blk-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
            operationId: opId,
            receipt: {
              id: `slip-blk-${opId}`,
              operationId: opId,
              kind: "blocked",
              title: "Action Blocked · Security Policy",
              subtitle: "AI has zero destructive permissions",
              transactionDate: todayYmd,
              lines: [
                { label: "Rule", value: "POLICY_BLOCKED (Append-only ledger)", tone: "crimson" },
              ],
              status: "blocked",
            },
          },
        ]);
        setVoicePhase("blocked");
        setStatusMessage("Blocked by Policy");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      // 4. > 30 Days Memory Boundary Guard
      if (/(do mahine|2 mahine|2 months|teen mahine|3 months|60 days|90 days|pichle saal|last year)/i.test(lower)) {
        const msg =
          "Conversational chat memory sirf pichle 30 dinon (1 mahine) tak ki available hai, isliye main 2 mahine purani chat context ko yaad nahi kar sakta. Lekin aapka poora permanent record Reports & Ledger sections mein safe hai.";
        appendEntriesToDate(todayYmd, [
          {
            id: `mem-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
            clarification: { kind: "memory_boundary", prompt: msg },
          },
        ]);
        setVoicePhase("clarifying");
        setStatusMessage("30-Day Memory Window");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      // 5. Correction ("Actually 7 the" or "20 pepsi nahi 10 hi biki")
      if (/(actually|nahi|galti se|ki jagah|\bhi\b.*(?:biki|aayi|the|chahiye))/i.test(lower) && lastContext.lastSaleId) {
        const postNeg = lower.split(/\bnahi\b|\bki jagah\b|\binstead\b/).pop() ?? text;
        const newQty = parseIndianNumber(postNeg) ?? parseIndianNumber(text);
        const targetSale = sales.find((s) => s.id === lastContext.lastSaleId);
        if (newQty !== null && targetSale && targetSale.items.length > 0) {
          const item = targetSale.items[0];
          const diff = item.quantity - newQty; // positive means return to stock
          const updatedTotal = newQty * item.unitPrice;

          setProducts((prev) =>
            prev.map((p) => (p.id === item.productId ? { ...p, stock: p.stock + diff } : p))
          );
          setSales((prev) =>
            prev.map((s) =>
              s.id === targetSale.id
                ? {
                    ...s,
                    totalAmount: updatedTotal,
                    paidAmount: s.paymentStatus === "paid" ? updatedTotal : s.paidAmount,
                    status: "corrected",
                    items: [{ ...item, quantity: newQty, lineTotal: updatedTotal }],
                  }
                : s
            )
          );
          setMovements((prev) => [
            {
              id: `mov-corr-${opId}`,
              productId: item.productId,
              productName: item.productName,
              movementType: "reversal",
              quantityDelta: diff,
              unit: item.unit,
              transactionDate: todayYmd,
              notes: `Corrected sale ${item.quantity} → ${newQty}`,
              operationId: opId,
              createdAt: nowIso,
            },
            ...prev,
          ]);

          const reply = `Original transaction correct ho gaya: ${item.quantity} se ${newQty} ${item.unit}s (${formatINR(updatedTotal)}). Audit trail mein correction save hai.`;
          appendEntriesToDate(todayYmd, [
            {
              id: `corr-${opId}`,
              role: "assistant",
              content: reply,
              timestamp: formatTimeIST(nowIso),
              language,
              operationId: opId,
              receipt: {
                id: `slip-corr-${opId}`,
                operationId: opId,
                kind: "correction",
                title: `Corrected · ${item.productName}`,
                subtitle: "Original sale updated + reversal logged",
                transactionDate: todayYmd,
                amountINR: updatedTotal,
                lines: [
                  { label: "Quantity", value: `${item.quantity} → ${newQty} ${item.unit}s`, tone: "ochre" },
                  { label: "Stock Adjustment", value: `${diff >= 0 ? "+" : ""}${diff} ${item.unit}s`, tone: "sage" },
                ],
                status: "corrected",
                auditTrail: [{ timestamp: formatTimeIST(nowIso), action: "corrected", summary: `${item.quantity} → ${newQty}` }],
              },
            },
          ]);
          setVoicePhase("saved");
          setStatusMessage("Corrected with Audit Trail");
          speakReply(reply, language, ttsEnabled);
          return;
        }
      }

      // 6. Anaphora follow-up ("Unmein se 3 damaged hain")
      if (/(unmein se|usme se|inmein se|isme se)/i.test(lower) && /(damaged|kharab|toot|expired)/i.test(lower)) {
        const qty = parseIndianNumber(text);
        const prod = products.find((p) => p.id === lastContext.productId);
        if (prod && qty !== null) {
          commitDamageOrExpiry({
            product: prod,
            quantity: qty,
            kind: lower.includes("expired") ? "expiry" : "damage",
            transactionDate: todayYmd,
            operationId: opId,
            netContextQty: lastContext.lastReceiveQty,
          });
          return;
        }
      }

      // 7. Cross-day 30-day memory ("Kal jo Pepsi aayi thi, wo expired thi")
      if (/kal\b|yesterday/i.test(lower) && /expired|kharab|damaged/i.test(lower) && /pepsi/i.test(lower)) {
        const yestMov = movements.find(
          (m) => m.transactionDate === yesterdayYmd && m.productId === "prod-pepsi-500" && m.movementType === "receive"
        );
        const prod = products.find((p) => p.id === "prod-pepsi-500");
        const qty = parseIndianNumber(text);
        if (yestMov && prod) {
          if (qty === null) {
            const msg = `Kal (${yesterdayYmd}) supplier se ${yestMov.quantityDelta} ${prod.name} bottles aayi thin. Kya saari ${yestMov.quantityDelta} expired hain ya kuch?`;
            setPendingFlow({
              type: "missing_slot",
              draft: {
                kind: "expiry",
                productId: prod.id,
                productName: prod.name,
                unit: prod.baseUnit,
                transactionDate: yesterdayYmd,
                missingField: "quantity",
                lastReceiveBatchQty: yestMov.quantityDelta,
              },
            });
            // Handle quick chips inside missing_slot cleanly
            appendEntriesToDate(todayYmd, [
              {
                id: `yest-${opId}`,
                role: "assistant",
                content: msg,
                timestamp: formatTimeIST(nowIso),
                language,
                clarification: {
                  kind: "missing_slot",
                  prompt: msg,
                  candidates: [
                    { id: "exp-all", label: `Saari ${yestMov.quantityDelta} expired`, value: `exp:${yestMov.quantityDelta}` },
                    { id: "exp-5", label: "5 bottles expired", value: "exp:5" },
                    { id: "exp-3", label: "3 bottles expired", value: "exp:3" },
                  ],
                },
              },
            ]);
            setVoicePhase("clarifying");
            setStatusMessage("30-Day Memory Matched");
            speakReply(msg, language, ttsEnabled);
            return;
          }
          commitDamageOrExpiry({
            product: prod,
            quantity: qty,
            kind: "expiry",
            transactionDate: yesterdayYmd,
            linkedNote: `Linked to ${yesterdayYmd} batch (${yestMov.quantityDelta} received)`,
            operationId: opId,
          });
          return;
        }
      }

      // 8. Business Day Replay (multi-item narration)
      if (/(replay|poora din|din bhar)/i.test(lower) || (lower.includes("maggi") && lower.includes("bijli"))) {
        const maggi = products.find((p) => p.id === "prod-maggi-70");
        const ramesh = customers.find((c) => c.id === "cust-ramesh-g");
        if (maggi && ramesh) {
          setProducts((prev) => prev.map((p) => (p.id === maggi.id ? { ...p, stock: Math.max(0, p.stock - 10) } : p)));
          setCustomers((prev) => prev.map((c) => (c.id === ramesh.id ? { ...c, outstandingBalance: c.outstandingBalance + 500 } : c)));
          setExpenses((prev) => [
            {
              id: `exp-rep-${opId}`,
              category: "Utilities",
              description: "Bijli bill (Business Day Replay)",
              amount: 1200,
              paymentMethod: "upi",
              transactionDate: todayYmd,
              status: "active",
              operationId: opId,
              createdAt: nowIso,
            },
            ...prev,
          ]);
          const reply = "Business Day Replay complete: 10 Maggi cash sale (₹140), kal ka Ramesh Gupta ₹500 udhaar, aur ₹1,200 bijli bill record ho gaya.";
          appendEntriesToDate(todayYmd, [
            {
              id: `rep-${opId}`,
              role: "assistant",
              content: reply,
              timestamp: formatTimeIST(nowIso),
              language,
              operationId: opId,
              receipt: {
                id: `slip-rep-${opId}`,
                operationId: opId,
                kind: "replay",
                title: "Business Day Replay · 3 Operations",
                subtitle: "Relative dates resolved in Asia/Kolkata",
                transactionDate: todayYmd,
                lines: [
                  { label: "Today · Sale", value: "10 Maggi · ₹140 cash", tone: "sage" },
                  { label: `Yesterday · Udhaar`, value: "Ramesh Gupta · ₹500", tone: "ochre" },
                  { label: "Today · Expense", value: "Bijli bill · ₹1,200 UPI", tone: "crimson" },
                ],
                status: "saved",
              },
            },
          ]);
          setVoicePhase("saved");
          setStatusMessage("Day Replay Committed");
          speakReply(reply, language, ttsEnabled);
          return;
        }
      }

      // 9. Queries ("Aaj kitni sale hui?", "payment pending")
      if (/(kitni sale|aaj ki sale|today.*sale)/i.test(lower)) {
        const todaysSales = sales.filter((s) => s.transactionDate === todayYmd && s.status !== "voided");
        const total = todaysSales.reduce((acc, s) => acc + s.totalAmount, 0);
        const reply = `Aaj abhi tak ${todaysSales.length} sales hui hain, total ${formatINR(total)}.`;
        appendEntriesToDate(todayYmd, [
          {
            id: `qry-${opId}`,
            role: "assistant",
            content: reply,
            timestamp: formatTimeIST(nowIso),
            language,
            receipt: {
              id: `slip-qry-${opId}`,
              operationId: opId,
              kind: "query",
              title: "Today's Sales Summary",
              subtitle: `${todayYmd} · Read-Only Query`,
              transactionDate: todayYmd,
              amountINR: total,
              lines: [
                { label: "Total Bills", value: String(todaysSales.length), tone: "neutral" },
                { label: "Total Revenue", value: formatINR(total), tone: "sage" },
              ],
              status: "saved",
            },
          },
        ]);
        setVoicePhase("saved");
        setStatusMessage("Query Answered");
        speakReply(reply, language, ttsEnabled);
        return;
      }

      if (/(pending|udhaar|kitna payment)/i.test(lower) && !/(diya|de diya|udhaar par)/i.test(lower)) {
        const pendingCusts = customers.filter((c) => c.outstandingBalance > 0);
        const totalOut = pendingCusts.reduce((a, b) => a + b.outstandingBalance, 0);
        const reply = `${pendingCusts.length} customers ka total ${formatINR(totalOut)} payment pending hai: ${pendingCusts.map((c) => `${c.name} (${formatINR(c.outstandingBalance)})`).join(", ")}.`;
        appendEntriesToDate(todayYmd, [
          {
            id: `qry-${opId}`,
            role: "assistant",
            content: reply,
            timestamp: formatTimeIST(nowIso),
            language,
            receipt: {
              id: `slip-pend-${opId}`,
              operationId: opId,
              kind: "query",
              title: "Pending Udhaar Summary",
              subtitle: `${pendingCusts.length} active balances`,
              transactionDate: todayYmd,
              amountINR: totalOut,
              lines: pendingCusts.map((c) => ({
                label: c.name,
                value: formatINR(c.outstandingBalance),
                tone: "ochre" as const,
              })),
              status: "saved",
            },
          },
        ]);
        setVoicePhase("saved");
        setStatusMessage("Ledger Retrieved");
        speakReply(reply, language, ttsEnabled);
        return;
      }

      // 10. Unverified Alias ("Coke" -> "Do you mean Coca-Cola 750ml?")
      if (/\bcoke\b/i.test(lower)) {
        const coca = products.find((p) => p.id === "prod-coca-750");
        const qty = parseIndianNumber(text) ?? 5;
        const priceHint = extractRupeeHint(text);
        if (coca && !coca.aliases.includes("coke")) {
          const msg = `Do you mean ${coca.name}?`;
          setPendingFlow({
            type: "verify_alias",
            spoken: "coke",
            candidate: coca,
            draft: {
              kind: "receive",
              quantity: qty,
              unitPrice: priceHint ?? undefined,
              transactionDate: todayYmd,
            },
          });
          appendEntriesToDate(todayYmd, [
            {
              id: `alias-${opId}`,
              role: "assistant",
              content: msg,
              timestamp: formatTimeIST(nowIso),
              language,
              clarification: {
                kind: "verify_alias",
                prompt: msg,
                candidates: [
                  { id: "yes", label: `Yes, ${coca.name} (Remember alias)`, value: "verify:yes" },
                  { id: "no", label: "No, different product", value: "verify:no" },
                ],
              },
            },
          ]);
          setVoicePhase("clarifying");
          setStatusMessage("Do you mean Coca-Cola?");
          speakReply(msg, language, ttsEnabled);
          return;
        }
      }

      // 11. Brand-New Product ("Nescafe Gold" or unknown item) -> Voice + Pop-up
      if (/nescafe|bournvita|horlicks|new product/i.test(lower)) {
        const qty = parseIndianNumber(text) ?? 5;
        const nameMatch = text.match(/(?:nescafe gold|nescafe|bournvita|horlicks)/i);
        const itemName = nameMatch ? nameMatch[0].replace(/\b\w/g, (c) => c.toUpperCase()) : "Nescafe Gold 50g";
        const msg = `${itemName} inventory mein nahi mila — kya naya product add karun?`;
        setNewProductDraft({
          name: itemName,
          category: "Beverages",
          baseUnit: "piece",
          quantity: qty,
          costPrice: "145",
          sellingPrice: "175",
          lowStockThreshold: "5",
          actionKind: "receive",
        });
        appendEntriesToDate(todayYmd, [
          {
            id: `newp-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
          },
        ]);
        setVoicePhase("clarifying");
        setStatusMessage("New Product Pop-up Open");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      // 12. Duplicate Customer + High-Value >= ₹5,000 ("Ramesh ko ₹6,500 udhaar diya")
      if (/ramesh/i.test(lower) && /(udhaar|diya|credit)/i.test(lower)) {
        const amt = parseIndianNumber(text) ?? 6500;
        const rameshes = customers.filter((c) => c.name.toLowerCase().includes("ramesh"));
        const msg = `Database mein ${rameshes.length} Ramesh hain. Kaunse Ramesh ko ${formatINR(amt)} udhaar dena hai?`;
        setPendingFlow({
          type: "disambiguate_customer",
          candidates: rameshes,
          draft: { kind: "sale", amount: amt, paymentStatus: "credit", transactionDate: todayYmd },
        });
        appendEntriesToDate(todayYmd, [
          {
            id: `cust-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
            clarification: {
              kind: "disambiguate_customer",
              prompt: msg,
              candidates: rameshes.map((c) => ({
                id: c.id,
                label: c.name,
                meta: `${c.areaNote ?? ""} · Bal ${formatINR(c.outstandingBalance)}`,
                value: `cust:${c.id}:${amt}`,
              })),
            },
          },
        ]);
        setVoicePhase("clarifying");
        setStatusMessage("Select Customer");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      // 13. Ambiguous Pepsi ("Aaj supplier se 20 Pepsi bottles aayi hain")
      if (/pepsi|pespsi/i.test(lower) && !/500|2l|2 l|chhoti|chotti|badi|baddi/i.test(lower)) {
        const qty = parseIndianNumber(text) ?? 20;
        const isSale = /(bik|bech|sale)/i.test(lower);
        const matches = products.filter((p) => p.name.toLowerCase().includes("pepsi"));
        const msg = `Pepsi mein ${matches.length} variants hain. Kya aapka matlab ${matches.map((m) => m.name).join(" ya ")} se hai?`;
        setPendingFlow({
          type: "disambiguate_product",
          candidates: matches,
          draft: {
            kind: isSale ? "sale" : "receive",
            quantity: qty,
            unitPrice: extractRupeeHint(text) ?? (isSale ? undefined : 16),
            paymentStatus: "paid",
            transactionDate: todayYmd,
          },
        });
        appendEntriesToDate(todayYmd, [
          {
            id: `amb-${opId}`,
            role: "assistant",
            content: msg,
            timestamp: formatTimeIST(nowIso),
            language,
            clarification: {
              kind: "disambiguate_product",
              prompt: msg,
              candidates: matches.map((m) => ({
                id: m.id,
                label: m.name,
                meta: `Stock: ${m.stock} · ${formatINR(m.sellingPrice)}`,
                value: `prod:${m.id}`,
              })),
            },
          },
        ]);
        setVoicePhase("clarifying");
        setStatusMessage("Clarify Pepsi Variant");
        speakReply(msg, language, ttsEnabled);
        return;
      }

      // 14. Direct Product Match (Receive or Sale)
      const matchedProd = products.find(
        (p) =>
          lower.includes(p.name.toLowerCase()) ||
          p.aliases.some((a) => lower.includes(a))
      );

      if (matchedProd) {
        const qty = parseIndianNumber(text) ?? 1;
        const isReceive = /(aayi|aaya|receive|stock add|kharida)/i.test(lower);
        if (isReceive) {
          resolveMissingSlotAndExecute({
            kind: "receive",
            productId: matchedProd.id,
            productName: matchedProd.name,
            quantity: qty,
            unit: matchedProd.baseUnit,
            unitPrice: extractRupeeHint(text) ?? undefined,
            transactionDate: todayYmd,
            missingField: "purchase_price",
          });
          return;
        }
        resolveMissingSlotAndExecute({
          kind: "sale",
          productId: matchedProd.id,
          productName: matchedProd.name,
          quantity: qty,
          unit: matchedProd.baseUnit,
          unitPrice: extractRupeeHint(text) ?? matchedProd.sellingPrice,
          paymentStatus: /(udhaar|credit)/i.test(lower) ? "credit" : "paid",
          transactionDate: todayYmd,
          missingField: "selling_price",
        });
        return;
      }

      // 15. Direct Expense ("Bijli bill 1200 diya")
      if (/(bill|expense|kharcha|bhada|rent|kiraya)/i.test(lower)) {
        const amt = parseIndianNumber(text);
        if (amt !== null) {
          commitExpense({
            category: lower.includes("bijli") ? "Utilities" : "Shop Expense",
            description: text,
            amount: amt,
            paymentMethod: lower.includes("upi") ? "upi" : "cash",
            transactionDate: todayYmd,
            operationId: opId,
          });
          return;
        }
      }

      // Fallback helpful prompt
      const fallback = "Kripya product ka naam aur quantity saaf bolein — jaise '20 Pepsi 500ml aayi' ya '10 Maggi bik gayi'.";
      appendEntriesToDate(todayYmd, [
        { id: `fb-${opId}`, role: "assistant", content: fallback, timestamp: formatTimeIST(nowIso), language },
      ]);
      setVoicePhase("clarifying");
      setStatusMessage("Clarification Needed");
      speakReply(fallback, language, ttsEnabled);
    },
    [
      appendEntriesToDate,
      cancelPendingHighValue,
      commitDamageOrExpiry,
      commitExpense,
      confirmNewProductFromModal,
      confirmPendingHighValue,
      customers,
      dismissNewProductModal,
      isOffline,
      language,
      lastContext,
      movements,
      newProductDraft,
      pendingConfirmation,
      pendingFlow,
      products,
      resolveMissingSlotAndExecute,
      sales,
      todayYmd,
      ttsEnabled,
      yesterdayYmd,
    ]
  );

  const selectClarificationCandidate = useCallback(
    (candidate: ClarificationCandidate) => {
      if (candidate.value === "verify:yes") {
        submitCommand("Yes");
        return;
      }
      if (candidate.value === "verify:no") {
        submitCommand("No");
        return;
      }
      if (candidate.value.startsWith("exp:")) {
        const qty = Number(candidate.value.split(":")[1]);
        const prod = products.find((p) => p.id === "prod-pepsi-500");
        if (prod) {
          setPendingFlow(null);
          commitDamageOrExpiry({
            product: prod,
            quantity: qty,
            kind: "expiry",
            transactionDate: yesterdayYmd,
            linkedNote: `Linked to ${yesterdayYmd} batch`,
            operationId: makeOperationId(),
          });
        }
        return;
      }
      if (candidate.value.startsWith("prod:") && pendingFlow?.type === "disambiguate_product") {
        const prodId = candidate.value.replace("prod:", "");
        const prod = products.find((p) => p.id === prodId);
        const draft = pendingFlow.draft;
        setPendingFlow(null);
        if (prod) {
          resolveMissingSlotAndExecute({
            ...draft,
            productId: prod.id,
            productName: prod.name,
            unit: prod.baseUnit,
            missingField: draft.kind === "receive" ? "purchase_price" : "selling_price",
          });
        }
        return;
      }
      if (candidate.value.startsWith("cust:")) {
        const [, custId, amtStr] = candidate.value.split(":");
        const cust = customers.find((c) => c.id === custId);
        const amt = Number(amtStr);
        setPendingFlow(null);
        if (cust) {
          const opId = makeOperationId();
          if (amt >= 5000) {
            requestHighValueConfirm({
              operationId: opId,
              token: `tok-${opId}`,
              title: `High-Value Udhaar · ${cust.name}`,
              description: `${cust.areaNote ?? ""} · ${cust.phone}`,
              amountINR: amt,
              impactSummary: `Outstanding balance ${formatINR(cust.outstandingBalance)} → ${formatINR(cust.outstandingBalance + amt)}`,
              payload: { kind: "direct_udhaar", customerId: cust.id, amount: amt },
            });
          }
        }
        return;
      }
      submitCommand(candidate.value);
    },
    [
      commitDamageOrExpiry,
      customers,
      pendingFlow,
      products,
      requestHighValueConfirm,
      resolveMissingSlotAndExecute,
      submitCommand,
      yesterdayYmd,
    ]
  );

  const syncOfflineQueue = useCallback(async () => {
    const items = await listOfflineCommands();
    if (items.length === 0) return;
    setStatusMessage(`Syncing ${items.length} queued items...`);
    if (isLiveBackend) {
      try {
        await syncOfflineBatchRemote(
          items.map((it) => ({
            operation_id: it.operationId,
            text: it.transcript,
            language: it.language,
            conversation_date: it.conversationDate,
          }))
        );
        await clearOfflineQueue();
        setOfflineQueue([]);
        setVoicePhase("saved");
        setStatusMessage("Offline Queue Synced (FIFO)");
        await refreshLiveWorkspace();
        return;
      } catch {
        // Retry locally if unreachable
      }
    }
    for (const item of items) {
      await submitCommand(item.transcript, { fromOfflineSync: true, operationId: item.operationId });
      await removeOfflineCommand(item.id);
    }
    await clearOfflineQueue();
    setOfflineQueue([]);
    setVoicePhase("saved");
    setStatusMessage("Offline Queue Synced (FIFO)");
  }, [isLiveBackend, refreshLiveWorkspace, submitCommand]);

  useEffect(() => {
    if (!isOffline && offlineQueue.length > 0) {
      syncOfflineQueue();
    }
  }, [isOffline, offlineQueue.length, syncOfflineQueue]);

  const setStoreTier = useCallback((tier: SubscriptionTierCode) => {
    const limits: Record<SubscriptionTierCode, number> = {
      free: 250,
      growth: 2500,
      pro: 15000,
    };
    setStore((prev) => ({ ...prev, tier, monthlyVoiceLimit: limits[tier] }));
  }, []);

  const updateStoreProfile = useCallback((patch: Partial<StoreProfile>) => {
    setStore((prev) => ({ ...prev, ...patch }));
  }, []);

  const addManualProduct = useCallback(
    (p: Omit<Product, "id">) => {
      if (isLiveBackend) {
        addManualProductRemote({
          name: p.name,
          category: p.category,
          base_unit: p.baseUnit,
          cost_price: p.costPrice,
          selling_price: p.sellingPrice,
          stock: p.stock,
          low_stock_threshold: p.lowStockThreshold,
          aliases: p.aliases,
        })
          .then(() => refreshLiveWorkspace())
          .catch(() => setProducts((prev) => [{ ...p, id: `prod-${Date.now()}` }, ...prev]));
        return;
      }
      setProducts((prev) => [{ ...p, id: `prod-${Date.now()}` }, ...prev]);
    },
    [isLiveBackend, refreshLiveWorkspace]
  );

  const archiveProduct = useCallback(
    async (productId: string) => {
      if (isLiveBackend) {
        await archiveProductRemote(productId);
        await refreshLiveWorkspace();
        return;
      }
      setProducts((prev) => prev.filter((p) => p.id !== productId));
    },
    [isLiveBackend, refreshLiveWorkspace]
  );

  const clearUnusedCatalog = useCallback(async (): Promise<number> => {
    if (isLiveBackend) {
      const res = await clearUnusedCatalogRemote();
      await refreshLiveWorkspace();
      return res.archived_count ?? 0;
    }
    const usedIds = new Set(movements.map((m) => m.productId));
    const unused = products.filter((p) => !usedIds.has(p.id));
    setProducts((prev) => prev.filter((p) => usedIds.has(p.id)));
    return unused.length;
  }, [isLiveBackend, movements, products, refreshLiveWorkspace]);

  const enableDemoPreview = useCallback(() => {
    setIsDemoMode(true);
    setStore({
      name: "Sharma Kirana & General Store",
      ownerName: "Demo Owner",
      city: "Jaipur, RJ",
      timezone: "Asia/Kolkata",
      tier: "free",
      monthlyVoiceUsed: 12,
      monthlyVoiceLimit: 250,
    });
    setProducts(INITIAL_PRODUCTS);
    setCustomers(INITIAL_CUSTOMERS);
  }, []);

  const signOut = useCallback(async () => {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setAuthUser(null);
    setNeedsOnboarding(false);
    setIsLiveBackend(false);
    setIsDemoMode(false);
    setStore({
      name: "My Store",
      ownerName: "",
      city: "",
      timezone: "Asia/Kolkata",
      tier: "free",
      monthlyVoiceUsed: 0,
      monthlyVoiceLimit: 250,
    });
    setProducts([]);
    setCustomers([]);
    setMovements([]);
    setSales([]);
    setExpenses([]);
    setConversations([
      {
        date: todayYmd,
        label: "Today",
        summary: "Ready for voice or text commands",
        entries: [],
      },
    ]);
  }, [todayYmd]);

  const deleteAccount = useCallback(async () => {
    await deleteAccountRemote();
    await signOut();
  }, [signOut]);

  const addManualExpense = useCallback(
    (e: Omit<Expense, "id" | "operationId" | "createdAt" | "status">) => {
      const opId = makeOperationId();
      setExpenses((prev) => [
        { ...e, id: `exp-${opId}`, operationId: opId, status: "active", createdAt: new Date().toISOString() },
        ...prev,
      ]);
    },
    []
  );

  const recordManualCustomerPayment = useCallback(
    (customerId: string, amount: number, method: "cash" | "upi" | "bank") => {
      setCustomers((prev) =>
        prev.map((c) =>
          c.id === customerId ? { ...c, outstandingBalance: Math.max(0, c.outstandingBalance - amount) } : c
        )
      );
      const cust = customers.find((c) => c.id === customerId);
      if (cust) {
        appendEntriesToDate(todayYmd, [
          {
            id: `pay-${Date.now()}`,
            role: "assistant",
            content: `${cust.name} se ${formatINR(amount)} (${method.toUpperCase()}) payment receive ho gaya.`,
            timestamp: formatTimeIST(new Date().toISOString()),
            language,
          },
        ]);
      }
    },
    [appendEntriesToDate, customers, language, todayYmd]
  );

  const todayStats = useMemo(() => {
    const todaysSales = sales.filter((s) => s.transactionDate === todayYmd && s.status !== "voided");
    const salesTotal = todaysSales.reduce((a, s) => a + s.totalAmount, 0);
    const cashTotal = todaysSales.reduce((a, s) => a + s.paidAmount, 0);
    const udhaarTotal = salesTotal - cashTotal;
    const expensesTotal = expenses
      .filter((e) => e.transactionDate === todayYmd && e.status === "active")
      .reduce((a, e) => a + e.amount, 0);
    const movementsCount = movements.filter((m) => m.transactionDate === todayYmd).length;
    const outstandingTotal = customers.reduce((a, c) => a + c.outstandingBalance, 0);
    const lowStockProducts = products.filter((p) => p.stock <= p.lowStockThreshold);

    return {
      salesTotal,
      cashTotal,
      udhaarTotal,
      expensesTotal,
      movementsCount,
      outstandingTotal,
      lowStockProducts,
    };
  }, [customers, expenses, movements, products, sales, todayYmd]);

  const submitAudioTurn = useCallback(
    async (audioBlob: Blob, fallbackTranscript?: string) => {
      stopSpeaking();
      const opId = makeOperationId();
      if (isLiveBackend && !isOffline && audioBlob.size > 400) {
        try {
          setVoicePhase("transcribing");
          setStatusMessage("Processing audio...");
          const res = await sendVoiceAudioTurn(audioBlob, opId, language);
          await applyRemoteTurnResult(res, { includeUserTranscript: true });
          return;
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : "Audio transcription failed";
          appendEntriesToDate(todayYmd, [
            {
              id: `aerr-${opId}`,
              role: "assistant",
              content: `Audio error: ${errMsg}`,
              timestamp: formatTimeIST(new Date().toISOString()),
              language,
            },
          ]);
          setVoicePhase("error");
          setStatusMessage("Audio Retry Needed");
          return;
        }
      }
      if (fallbackTranscript && fallbackTranscript.trim()) {
        await submitCommand(fallbackTranscript, { operationId: opId });
      } else {
        setVoicePhase("idle");
        setStatusMessage("Ready to listen");
      }
    },
    [applyRemoteTurnResult, isLiveBackend, isOffline, language, submitCommand]
  );

  return (
    <CueWorkspaceContext.Provider
      value={{
        store,
        setStoreTier,
        updateStoreProfile,
        language,
        setLanguage,
        ttsEnabled,
        setTtsEnabled,
        isOffline,
        setIsOffline,
        voicePhase,
        setVoicePhase,
        statusMessage,
        products,
        movements,
        customers,
        sales,
        expenses,
        conversations,
        activeDate,
        setActiveDate,
        activeConversation,
        offlineQueue,
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
        refreshWorkspace: refreshLiveWorkspace,
        archiveProduct,
        clearUnusedCatalog,
        enableDemoPreview,
        submitAudioTurn,
        submitCommand,
        selectClarificationCandidate,
        undoReceipt,
        syncOfflineQueue,
        addManualProduct,
        addManualExpense,
        recordManualCustomerPayment,
        todayStats,
      }}
    >
      {children}
    </CueWorkspaceContext.Provider>
  );
}

export function useCueWorkspace() {
  const ctx = useContext(CueWorkspaceContext);
  if (!ctx) throw new Error("useCueWorkspace must be used inside CueWorkspaceProvider");
  return ctx;
}
