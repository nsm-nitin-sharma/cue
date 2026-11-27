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

  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

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
