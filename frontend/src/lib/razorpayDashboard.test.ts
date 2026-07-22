import { describe, expect, it } from "vitest";
import {
  isRazorpayProviderSnapshot,
  resolveRazorpayDashboardMetrics,
} from "./razorpayDashboard";

const completeSnapshot = {
  status: "live",
  payments: {
    status: "live",
    amounts: { captured: "100.00" },
  },
  refunds: {
    status: "live",
    amounts: { processed: "20.00" },
  },
  payouts: {
    status: "live",
    amounts: { processed: "30.00" },
  },
} as const;

describe("Razorpay dashboard metric source selection", () => {
  it("uses complete provider values for net collection, payouts, and flow", () => {
    expect(resolveRazorpayDashboardMetrics(completeSnapshot, {
      netCollections: 70,
      payouts: 10,
    })).toEqual({
      netCollections: 80,
      grossCollections: 100,
      refunds: 20,
      payouts: 30,
      netFlow: 50,
      collectionSource: "provider",
      payoutSource: "provider",
      status: "live",
    });
  });

  it("keeps local net collections when either provider payment or refund data is unavailable", () => {
    const partialSnapshot = {
      ...completeSnapshot,
      status: "partial",
      refunds: {
        status: "unavailable",
        amounts: { processed: "0.00" },
      },
    } as const;

    expect(resolveRazorpayDashboardMetrics(partialSnapshot, {
      netCollections: 70,
      payouts: 10,
    })).toMatchObject({
      netCollections: 70,
      grossCollections: null,
      refunds: null,
      payouts: 30,
      netFlow: 40,
      collectionSource: "local",
      payoutSource: "provider",
      status: "partial",
    });
  });

  it("uses local values and a local status before the first provider sync", () => {
    expect(resolveRazorpayDashboardMetrics(null, {
      netCollections: 70,
      payouts: 10,
    })).toEqual({
      netCollections: 70,
      grossCollections: null,
      refunds: null,
      payouts: 10,
      netFlow: 60,
      collectionSource: "local",
      payoutSource: "local",
      status: "local",
    });
  });
});

describe("Razorpay provider response validation", () => {
  it("rejects incomplete success payloads before the dashboard reads them", () => {
    expect(isRazorpayProviderSnapshot({ items: [] })).toBe(false);
    expect(isRazorpayProviderSnapshot(null)).toBe(false);
  });
});
