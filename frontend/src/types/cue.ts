export type LanguageMode = "hinglish" | "hi" | "en";

export type VoicePhase =
  | "idle"
  | "listening"
  | "transcribing"
  | "validating"
  | "clarifying"
  | "confirming"
  | "saved"
  | "pending_sync"
  | "error"
  | "blocked";

export type SubscriptionTierCode = "free" | "growth" | "pro";

export type BaseUnit = "piece" | "packet" | "kg" | "litre" | "box";

export interface Product {
  id: string;
  skuCode: string;
  name: string;
  category: string;
  baseUnit: BaseUnit;
  costPrice: number;
  sellingPrice: number;
  stock: number;
  lowStockThreshold: number;
  aliases: string[];
}

export interface InventoryMovement {
  id: string;
  productId: string;
  productName: string;
  movementType: "receive" | "sale" | "damage" | "expiry" | "adjustment" | "reversal";
  quantityDelta: number;
  unit: BaseUnit;
  unitCost?: number;
  transactionDate: string; // YYYY-MM-DD (Asia/Kolkata)
  notes: string;
  operationId: string;
  createdAt: string;
}

export interface Customer {
  id: string;
  name: string;
  phone: string;
  areaNote?: string;
  outstandingBalance: number;
}

export interface SaleItem {
  productId: string;
  productName: string;
  quantity: number;
  unit: BaseUnit;
  unitPrice: number;
  lineTotal: number;
}

export interface Sale {
  id: string;
  customerId?: string;
  customerName: string;
  items: SaleItem[];
  totalAmount: number;
  paidAmount: number;
  paymentStatus: "paid" | "partial" | "credit";
  transactionDate: string;
  status: "active" | "corrected" | "voided";
  operationId: string;
  createdAt: string;
}

export interface Expense {
  id: string;
  category: string;
  description: string;
  amount: number;
  paymentMethod: "cash" | "upi" | "bank";
  transactionDate: string;
  status: "active" | "corrected" | "voided";
  operationId: string;
  createdAt: string;
}

export interface AuditEntry {
  timestamp: string;
  action: string;
  summary: string;
}

export interface ReceiptSlip {
  id: string;
  operationId: string;
  kind:
    | "receive"
    | "sale"
    | "damage"
    | "expiry"
    | "expense"
    | "payment"
    | "correction"
    | "replay"
    | "query"
    | "blocked";
  title: string;
  subtitle: string;
  transactionDate: string;
  amountINR?: number;
  lines: { label: string; value: string; tone?: "sage" | "crimson" | "ochre" | "neutral" }[];
  status: "saved" | "corrected" | "undone" | "pending_sync" | "blocked";
  reversible?: boolean;
  auditTrail?: AuditEntry[];
}

export interface ClarificationCandidate {
  id: string;
  label: string;
  meta?: string;
  value: string;
}

export interface NewProductDraft {
  name: string;
  category: string;
  baseUnit: BaseUnit;
  quantity: number;
  costPrice: string;
  sellingPrice: string;
  lowStockThreshold: string;
  actionKind: "receive" | "sale";
}

export interface PendingConfirmation {
  operationId: string;
  token: string;
  title: string;
  description: string;
  amountINR?: number;
  impactSummary: string;
  payload: Record<string, unknown>;
}

export interface ChatEntry {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  language: LanguageMode;
  operationId?: string;
  receipt?: ReceiptSlip;
  clarification?: {
    kind:
      | "disambiguate_product"
      | "disambiguate_customer"
      | "verify_alias"
      | "missing_slot"
      | "negative_stock"
      | "memory_boundary";
    prompt: string;
    candidates?: ClarificationCandidate[];
    resolved?: boolean;
  };
}

export interface DayConversation {
  date: string; // YYYY-MM-DD
  label: string;
  summary: string;
  entries: ChatEntry[];
}

export interface QueuedVoiceCommand {
  id: string;
  operationId: string;
  transcript: string;
  conversationDate: string;
  language: LanguageMode;
  queuedAt: string;
  status: "pending" | "syncing" | "synced" | "failed";
}

export interface StoreProfile {
  name: string;
  ownerName: string;
  city: string;
  timezone: string;
  tier: SubscriptionTierCode;
  monthlyVoiceUsed: number;
  monthlyVoiceLimit: number;
}

export interface VoiceTurnResult {
  operation_id: string;
  status:
    | "executed"
    | "needs_clarification"
    | "needs_confirmation"
    | "new_product_popup"
    | "policy_blocked"
    | "memory_boundary"
    | "retry_audio"
    | "query_answered";
  transcript: string;
  reply: string;
  language: LanguageMode;
  receipts: ReceiptSlip[];
  clarification?: {
    kind:
      | "disambiguate_product"
      | "disambiguate_customer"
      | "verify_alias"
      | "missing_slot"
      | "negative_stock"
      | "memory_boundary";
    prompt: string;
    candidates?: ClarificationCandidate[];
  } | null;
  confirmation?: PendingConfirmation | null;
  new_product_draft?: NewProductDraft | null;
}
