export function formatINR(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: value % 1 === 0 ? 0 : 2,
  }).format(value);
}

export function formatQty(qty: number, unit: string): string {
  const num = Number.isInteger(qty) ? String(qty) : qty.toFixed(2).replace(/\.?0+$/, "");
  const plural = qty === 1 ? unit : unit === "box" ? "boxes" : `${unit}s`;
  return `${num} ${plural}`;
}

export function formatShortOp(opId: string): string {
  return `#${opId.slice(0, 6).toUpperCase()}`;
}

export function getTodayIST(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function formatTimeIST(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    }).format(new Date(iso));
  } catch {
    return "";
  }
}

export function makeOperationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `op-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export function formatPaymentMethod(method?: string | null): string {
  const m = (method ?? "cash").toLowerCase();
  if (m === "upi" || m === "online") return "Online";
  if (m === "bank") return "Bank";
  if (m === "credit") return "Udhaar";
  return "Cash";
}

export type TimePeriodFilter = "today" | "week" | "month" | "prev_month" | "year" | "all";

export function isDateInPeriod(ymd: string, period: TimePeriodFilter, todayYmd: string): boolean {
  if (period === "all") return true;
  if (period === "today") return ymd === todayYmd;
  const [ty, tm] = todayYmd.split("-").map(Number);
  const [y, m] = ymd.split("-").map(Number);
  if (period === "year") return y === ty;
  if (period === "month") return y === ty && m === tm;
  if (period === "prev_month") {
    const prevM = tm === 1 ? 12 : tm - 1;
    const prevY = tm === 1 ? ty - 1 : ty;
    return y === prevY && m === prevM;
  }
  if (period === "week") {
    const tMs = Date.parse(`${todayYmd}T00:00:00Z`);
    const dMs = Date.parse(`${ymd}T00:00:00Z`);
    const diffDays = (tMs - dMs) / 86_400_000;
    return diffDays >= 0 && diffDays < 7;
  }
  return true;
}
