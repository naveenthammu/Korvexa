export type GatewayPaymentStatus = "Captured" | "Failed" | "Pending";
export type GatewayPayoutStatus = "Captured" | "Failed" | "Pending";

export function gatewayPaymentDisplayStatus(payment: { status?: string | null; gateway_payment_id?: string | null }): GatewayPaymentStatus {
  const status = (payment.status || "").toLowerCase();
  if (["captured", "completed", "paid", "processed", "processing"].includes(status)) return "Captured";
  if (["failed", "cancelled", "canceled", "refunded"].includes(status)) return "Failed";
  if (payment.gateway_payment_id && !status) return "Captured";
  return "Pending";
}

export function gatewayPayoutDisplayStatus(payout: { payout_status?: string | null; status?: string | null }): GatewayPayoutStatus {
  const payoutStatus = (payout.payout_status || "").toLowerCase();
  const payrollStatus = (payout.status || "").toLowerCase();
  if (["failed", "reversed", "rejected", "cancelled", "canceled"].includes(payoutStatus)) return "Failed";
  if (["processed", "completed", "settled"].includes(payoutStatus)) return "Captured";
  if (["queued", "pending", "processing"].includes(payoutStatus)) return "Pending";
  if (["failed", "cancelled", "canceled"].includes(payrollStatus)) return "Failed";
  if (payrollStatus === "paid" && !payoutStatus) return "Captured";
  return "Pending";
}

export function canSubmitPayrollPayout(payroll: { status?: string | null; payout_status?: string | null }): boolean {
  const payrollStatus = (payroll.status || "").toLowerCase();
  const payoutStatus = (payroll.payout_status || "").toLowerCase();
  if (payrollStatus !== "pending") return false;
  return !["queued", "pending", "processing"].includes(payoutStatus);
}

type RefundablePayment = {
  id: string;
  amount: string;
  status?: string | null;
  method?: string;
  provider?: string | null;
  gateway_payment_id?: string | null;
};

export function refundablePayments(order: { payments?: RefundablePayment[] | null }): RefundablePayment[] {
  return (order.payments || []).filter((payment) => {
    const status = (payment.status || "captured").toLowerCase();
    return ["captured", "completed", "paid"].includes(status) && Number(payment.amount) > 0;
  });
}

export function canRefundOrder(order: { payment_status?: string | null; payments?: RefundablePayment[] | null }): boolean {
  const paymentStatus = (order.payment_status || "").toLowerCase();
  return ["paid", "partial"].includes(paymentStatus) && refundablePayments(order).length > 0;
}

export function didRefundStateAdvance(previousStatus?: string | null, currentStatus?: string | null): boolean {
  const previous = (previousStatus || "").trim().toLowerCase();
  const current = (currentStatus || "").trim().toLowerCase();
  return previous !== current && ["partially_refunded", "refund_pending", "refunded"].includes(current);
}
