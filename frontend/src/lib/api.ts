import { supabase } from "@/lib/supabase";
import type { BaseUnit, LanguageMode, SubscriptionTierCode, VoiceTurnResult } from "@/types/cue";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function getAuthHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const headers: Record<string, string> = {
    ...authHeaders,
    ...((init.headers as Record<string, string>) ?? {}),
  };

  if (!(init.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  let resp: Response | null = null;
  let lastNetworkErr: unknown = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      resp = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers,
      });
      lastNetworkErr = null;
      break;
    } catch (err) {
      lastNetworkErr = err;
      // Retry once after transient keep-alive/socket reset on local server
      if (attempt === 0) {
        await new Promise((r) => setTimeout(r, 350));
        continue;
      }
    }
  }
  if (!resp) {
    throw lastNetworkErr instanceof Error ? lastNetworkErr : new Error("Failed to fetch");
  }

  if (!resp.ok) {
    const errBody = await resp.json().catch(() => ({}));
    throw new Error(errBody.detail || `API request failed (${resp.status})`);
  }
  return (await resp.json()) as T;
}

export async function checkBackendHealth(): Promise<{
  status: string;
  stt_provider: string;
  llm_provider: string;
  database_schema_ready: boolean;
}> {
  return apiFetch("/health");
}

export async function onboardStoreRemote(payload: {
  name: string;
  city: string;
  plan_code: SubscriptionTierCode;
  seed_sample_catalog: boolean;
}) {
  return apiFetch<{ business_id: string; plan_code?: string }>("/onboarding/store", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchWorkspaceBootstrap() {
  return apiFetch<Record<string, unknown>>("/workspace/bootstrap");
}

export async function sendVoiceAudioTurn(
  audioBlob: Blob,
  operationId: string,
  language: LanguageMode
): Promise<VoiceTurnResult> {
  const form = new FormData();
  const ext = audioBlob.type.includes("mp4") ? "m4a" : audioBlob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audioBlob, `recording.${ext}`);
  form.append("operation_id", operationId);
  form.append("language", language);

  return apiFetch<VoiceTurnResult>("/voice/turn", {
    method: "POST",
    body: form,
  });
}

export async function sendTextCommandRemote(
  text: string,
  operationId: string,
  language: LanguageMode
): Promise<VoiceTurnResult> {
  return apiFetch<VoiceTurnResult>("/voice/text", {
    method: "POST",
    body: JSON.stringify({ text, operation_id: operationId, language }),
  });
}

export async function confirmTier3Remote(
  operationId: string,
  confirmationToken: string,
  accept = true
): Promise<VoiceTurnResult> {
  return apiFetch<VoiceTurnResult>("/voice/confirm", {
    method: "POST",
    body: JSON.stringify({
      operation_id: operationId,
      confirmation_token: confirmationToken,
      accept,
    }),
  });
}

export async function createProductFromPopupRemote(payload: {
  operation_id: string;
  name: string;
  category: string;
  base_unit: BaseUnit;
  quantity: number;
  cost_price: number;
  selling_price: number;
  low_stock_threshold: number;
  action_kind: "receive" | "sale";
}): Promise<VoiceTurnResult> {
  return apiFetch<VoiceTurnResult>("/voice/create-entity", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function syncOfflineBatchRemote(
  items: { operation_id: string; text: string; language: LanguageMode; conversation_date?: string }[]
) {
  return apiFetch<{ synced_count: number; results: VoiceTurnResult[] }>("/voice/sync-batch", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function archiveProductRemote(productId: string) {
  return apiFetch<{ status: string; product_id: string }>(
    `/inventory/products/${encodeURIComponent(productId)}/archive`,
    { method: "POST" }
  );
}

export async function clearUnusedCatalogRemote() {
  return apiFetch<{ status: string; archived_count: number }>("/inventory/clear-unused", {
    method: "POST",
  });
}

export async function addManualProductRemote(payload: {
  name: string;
  category: string;
  base_unit: BaseUnit;
  cost_price: number;
  selling_price: number;
  stock: number;
  low_stock_threshold: number;
  aliases: string[];
}) {
  return apiFetch<{ product: Record<string, unknown> }>("/inventory/products", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAccountRemote() {
  return apiFetch<{ status: string; user_id: string }>("/account", {
    method: "DELETE",
  });
}

export async function addManualExpenseRemote(payload: {
  category: string;
  description: string;
  amount: number;
  payment_method: "cash" | "upi" | "bank" | "credit";
  transaction_date?: string;
}) {
  return apiFetch<Record<string, unknown>>("/expenses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function recordCustomerPaymentRemote(payload: {
  customer_id: string;
  amount: number;
  payment_method: "cash" | "upi" | "bank";
}) {
  return apiFetch<Record<string, unknown>>("/customers/payments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function recordSupplierPaymentRemote(payload: {
  customer_id: string;
  amount: number;
  payment_method: "cash" | "upi" | "bank";
}) {
  return apiFetch<Record<string, unknown>>("/suppliers/payments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function reverseOperationRemote(operationId: string) {
  return apiFetch<{ status: string; reversed: boolean; summary: string }>(
    `/operations/${encodeURIComponent(operationId)}/reverse`,
    { method: "POST" }
  );
}

export async function updateProductRemote(
  productId: string,
  payload: {
    name?: string;
    category?: string;
    base_unit?: BaseUnit;
    cost_price?: number;
    selling_price?: number;
    stock?: number;
    low_stock_threshold?: number;
    aliases?: string[];
  }
) {
  return apiFetch<{ product: Record<string, unknown> }>(
    `/inventory/products/${encodeURIComponent(productId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
}

export async function updateCustomerRemote(
  customerId: string,
  payload: { name?: string; phone?: string; area_note?: string }
) {
  return apiFetch<Record<string, unknown>>(`/customers/${encodeURIComponent(customerId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function updateExpenseRemote(
  expenseId: string,
  payload: {
    category?: string;
    description?: string;
    amount?: number;
    payment_method?: "cash" | "upi" | "bank" | "credit";
    transaction_date?: string;
  }
) {
  return apiFetch<Record<string, unknown>>(`/expenses/${encodeURIComponent(expenseId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
