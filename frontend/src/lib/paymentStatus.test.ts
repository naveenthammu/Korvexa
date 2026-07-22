import { describe, expect, it } from "vitest";
import {
  canRefundOrder,
  canSubmitPayrollPayout,
  didRefundStateAdvance,
  gatewayPaymentDisplayStatus,
  gatewayPayoutDisplayStatus,
  refundablePayments,
} from "./paymentStatus";

describe("gateway payment display status", () => {
  it("shows captured only for captured-like statuses", () => {
    expect(gatewayPaymentDisplayStatus({ status: "captured", gateway_payment_id: "pay_123" })).toBe("Captured");
    expect(gatewayPaymentDisplayStatus({ status: "processed", gateway_payment_id: "pay_123" })).toBe("Captured");
  });

  it("shows failed webhook attempts as failed even when Razorpay provides a payment id", () => {
    expect(gatewayPaymentDisplayStatus({ status: "failed", gateway_payment_id: "pay_failed" })).toBe("Failed");
  });

  it("shows created and pending checkout attempts as pending", () => {
    expect(gatewayPaymentDisplayStatus({ status: "created", gateway_payment_id: null })).toBe("Pending");
    expect(gatewayPaymentDisplayStatus({ status: "pending", gateway_payment_id: null })).toBe("Pending");
  });
});

describe("gateway payout display status", () => {
  it("shows processed payout states as captured", () => {
    expect(gatewayPayoutDisplayStatus({ payout_status: "processed", status: "paid" })).toBe("Captured");
    expect(gatewayPayoutDisplayStatus({ payout_status: "settled", status: "paid" })).toBe("Captured");
  });

  it("shows failed payout states as failed even when payroll was previously paid", () => {
    expect(gatewayPayoutDisplayStatus({ payout_status: "failed", status: "paid" })).toBe("Failed");
    expect(gatewayPayoutDisplayStatus({ payout_status: "reversed", status: "paid" })).toBe("Failed");
  });

  it("shows queued and processing payouts as pending", () => {
    expect(gatewayPayoutDisplayStatus({ payout_status: "processing", status: "paid" })).toBe("Pending");
    expect(gatewayPayoutDisplayStatus({ payout_status: "queued", status: "paid" })).toBe("Pending");
  });
});

describe("payroll payout submission", () => {
  it("allows fresh and failed payroll payouts", () => {
    expect(canSubmitPayrollPayout({ status: "pending", payout_status: null })).toBe(true);
    expect(canSubmitPayrollPayout({ status: "pending", payout_status: "failed" })).toBe(true);
  });

  it("blocks duplicate processing and settled payouts", () => {
    expect(canSubmitPayrollPayout({ status: "processing", payout_status: "processing" })).toBe(false);
    expect(canSubmitPayrollPayout({ status: "paid", payout_status: "processed" })).toBe(false);
  });
});

describe("order refunds", () => {
  const payments = [
    { id: "captured", amount: "100.00", status: "captured" },
    { id: "failed", amount: "50.00", status: "failed" },
  ];

  it("only exposes captured payments for refund", () => {
    expect(refundablePayments({ payments })).toEqual([payments[0]]);
  });

  it("allows refunds only for settled orders without an active refund", () => {
    expect(canRefundOrder({ payment_status: "paid", payments })).toBe(true);
    expect(canRefundOrder({ payment_status: "partial", payments })).toBe(true);
    expect(canRefundOrder({ payment_status: "refund_pending", payments })).toBe(false);
    expect(canRefundOrder({ payment_status: "refunded", payments })).toBe(false);
  });

  it("recognizes a persisted refund after a lost success response", () => {
    expect(didRefundStateAdvance("paid", "refunded")).toBe(true);
    expect(didRefundStateAdvance("paid", "refund_pending")).toBe(true);
    expect(didRefundStateAdvance("paid", "partially_refunded")).toBe(true);
    expect(didRefundStateAdvance("paid", "paid")).toBe(false);
  });
});
