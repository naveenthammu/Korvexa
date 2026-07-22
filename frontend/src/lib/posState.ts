export type OrderType = "dine_in" | "takeaway" | "delivery";
export type OrderStatus = "held" | "active" | "completed" | "void";
export type KdsStatus = "pending" | "new" | "preparing" | "ready" | "delivered";
export type TableStatus = "available" | "occupied" | "reserved" | "cleaning";
export type PaymentMethod = "cash" | "card" | "upi";

export interface CartAddon {
  name: string;
  price: number;
}

export interface CartVariant {
  name: string;
  priceDelta: number;
}

export interface CartItem {
  productId: string;
  name: string;
  quantity: number;
  price: number;
  taxRate: number;
  variant?: CartVariant;
  addons?: CartAddon[];
}

export interface PaymentInput {
  method: PaymentMethod;
  amount: number;
  reference?: string;
}

export interface PosOrder {
  id: string;
  tableId?: string;
  orderType: OrderType;
  status: OrderStatus;
  kdsStatus: KdsStatus;
  items: CartItem[];
  subtotal: number;
  tax: number;
  discountAmount: number;
  total: number;
  paymentStatus: "unpaid" | "partial" | "paid" | "refunded";
  payments: PaymentInput[];
  createdAt: string;
}

export interface TableState {
  id: string;
  name: string;
  status: TableStatus;
}

export interface BuildOrderInput {
  tableId?: string;
  orderType: OrderType;
  discountAmount: number;
  items: CartItem[];
}

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function itemUnitPrice(item: CartItem): number {
  const variantDelta = item.variant?.priceDelta ?? 0;
  const addonsTotal = (item.addons ?? []).reduce((sum, addon) => sum + addon.price, 0);
  return item.price + variantDelta + addonsTotal;
}

export function buildOrderFromCart(input: BuildOrderInput): PosOrder {
  const subtotal = roundMoney(
    input.items.reduce((sum, item) => sum + itemUnitPrice(item) * item.quantity, 0),
  );
  const tax = roundMoney(
    input.items.reduce((sum, item) => sum + itemUnitPrice(item) * item.quantity * (item.taxRate / 100), 0),
  );
  const total = roundMoney(subtotal + tax - input.discountAmount);

  return {
    id: crypto.randomUUID(),
    tableId: input.tableId,
    orderType: input.orderType,
    status: "held",
    kdsStatus: "pending",
    items: input.items,
    subtotal,
    tax,
    discountAmount: input.discountAmount,
    total,
    paymentStatus: "unpaid",
    payments: [],
    createdAt: new Date().toISOString(),
  };
}

export function payOrder(order: PosOrder, payments: PaymentInput[]): PosOrder {
  const amountPaid = roundMoney(payments.reduce((sum, payment) => sum + payment.amount, 0));
  return {
    ...order,
    payments,
    paymentStatus: amountPaid >= order.total ? "paid" : amountPaid > 0 ? "partial" : "unpaid",
    status: amountPaid >= order.total ? "completed" : order.status,
  };
}

export function changeKdsStatus(order: PosOrder, kdsStatus: KdsStatus): PosOrder {
  return {
    ...order,
    kdsStatus,
    status: kdsStatus === "pending" ? order.status : "active",
  };
}

export function setTableStatus(table: TableState, status: TableStatus): TableState {
  return { ...table, status };
}

export { addQueueItem, getQueueItems, markQueueItemSynced } from "./offlineQueue";
