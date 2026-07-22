export type RazorpayProviderStatus = "live" | "partial" | "not_configured" | "unavailable";

export type RazorpayProviderPayment = {
  id: string;
  local_order_id?: string | null;
  gateway_order_id?: string | null;
  amount: string;
  currency: string;
  status: string;
  method: string;
  amount_refunded: string;
  created_at?: number | null;
};

export type RazorpayProviderRefund = {
  id: string;
  payment_id?: string | null;
  local_order_id?: string | null;
  amount: string;
  currency: string;
  status: string;
  created_at?: number | null;
};

export type RazorpayProviderPayout = {
  id: string;
  local_payroll_id?: string | null;
  amount: string;
  currency: string;
  status: string;
  mode: string;
  purpose: string;
  utr?: string | null;
  created_at?: number | null;
};

type ProviderSection<TItem, TAmounts extends Record<string, string>> = {
  status: Exclude<RazorpayProviderStatus, "partial">;
  error?: string;
  scanned: number;
  matched: number;
  truncated: boolean;
  counts: Record<string, number>;
  amounts: TAmounts;
  items: TItem[];
};

export type RazorpayProviderSnapshot = {
  source: "razorpay_api";
  status: RazorpayProviderStatus;
  modes: {
    payments: "live" | "test" | "unknown" | "not_configured";
    payouts: "live" | "test" | "unknown" | "not_configured";
  };
  fetched_at: string;
  window: {
    days: number;
    from: number;
    to: number;
    max_records_per_resource: number;
  };
  payments: ProviderSection<RazorpayProviderPayment, {
    captured: string;
    authorized: string;
    failed: string;
  }>;
  refunds: ProviderSection<RazorpayProviderRefund, {
    pending: string;
    processed: string;
    failed: string;
  }>;
  payouts: ProviderSection<RazorpayProviderPayout, {
    processed: string;
    in_flight: string;
    failed: string;
  }>;
  totals: {
    captured: string;
    refunded: string;
    payouts: string;
    net_flow: string | null;
    complete: boolean;
  };
};

type MetricSnapshot = {
  readonly status: RazorpayProviderStatus;
  readonly payments: {
    readonly status: string;
    readonly amounts: { readonly captured: string };
  };
  readonly refunds: {
    readonly status: string;
    readonly amounts: { readonly processed: string };
  };
  readonly payouts: {
    readonly status: string;
    readonly amounts: { readonly processed: string };
  };
};

type LocalGatewayMetrics = {
  netCollections: number;
  payouts: number;
};

export type ResolvedRazorpayMetrics = {
  netCollections: number;
  grossCollections: number | null;
  refunds: number | null;
  payouts: number;
  netFlow: number;
  collectionSource: "provider" | "local";
  payoutSource: "provider" | "local";
  status: RazorpayProviderStatus | "local";
};

export function isRazorpayProviderSnapshot(value: unknown): value is RazorpayProviderSnapshot {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RazorpayProviderSnapshot>;
  return candidate.source === "razorpay_api"
    && typeof candidate.status === "string"
    && Boolean(candidate.payments && typeof candidate.payments === "object")
    && Boolean(candidate.refunds && typeof candidate.refunds === "object")
    && Boolean(candidate.payouts && typeof candidate.payouts === "object")
    && Boolean(candidate.totals && typeof candidate.totals === "object")
    && Boolean(candidate.window && typeof candidate.window === "object")
    && Boolean(candidate.modes && typeof candidate.modes === "object");
}

function amountNumber(value: string | number | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function resolveRazorpayDashboardMetrics(
  snapshot: MetricSnapshot | null,
  local: LocalGatewayMetrics,
): ResolvedRazorpayMetrics {
  const providerCollectionsLive = snapshot?.payments?.status === "live" && snapshot?.refunds?.status === "live";
  const providerPayoutsLive = snapshot?.payouts?.status === "live";
  const grossCollections = providerCollectionsLive
    ? amountNumber(snapshot?.payments?.amounts?.captured)
    : null;
  const refunds = providerCollectionsLive
    ? amountNumber(snapshot?.refunds?.amounts?.processed)
    : null;
  const netCollections = grossCollections !== null && refunds !== null
    ? grossCollections - refunds
    : local.netCollections;
  const payouts = providerPayoutsLive
    ? amountNumber(snapshot?.payouts?.amounts?.processed)
    : local.payouts;

  return {
    netCollections,
    grossCollections,
    refunds,
    payouts,
    netFlow: netCollections - payouts,
    collectionSource: providerCollectionsLive ? "provider" : "local",
    payoutSource: providerPayoutsLive ? "provider" : "local",
    status: snapshot?.status ?? "local",
  };
}
