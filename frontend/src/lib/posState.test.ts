import { describe, expect, it, beforeEach } from "vitest";
import {
  addQueueItem,
  buildOrderFromCart,
  changeKdsStatus,
  getQueueItems,
  payOrder,
  setTableStatus,
} from "./posState";

beforeEach(() => {
  localStorage.clear();
});

describe("POS state helpers", () => {
  it("calculates tax, discounts, and mixed payment balance", () => {
    const order = buildOrderFromCart({
      tableId: "table-1",
      orderType: "dine_in",
      discountAmount: 10,
      items: [
        {
          productId: "paneer",
          name: "Paneer Tikka Bowl",
          quantity: 2,
          price: 240,
          taxRate: 5,
          variant: { name: "Large", priceDelta: 40 },
          addons: [{ name: "Extra Chutney", price: 20 }],
        },
      ],
    });

    expect(order.subtotal).toBe(600);
    expect(order.tax).toBe(30);
    expect(order.total).toBe(620);
    expect(order.status).toBe("held");

    const paid = payOrder(order, [
      { method: "cash", amount: 300 },
      { method: "upi", amount: 320 },
    ]);

    expect(paid.paymentStatus).toBe("paid");
    expect(paid.status).toBe("completed");
  });

  it("updates table and kitchen statuses for touch workflows", () => {
    const table = setTableStatus({ id: "t1", name: "T1", status: "available" }, "occupied");
    expect(table.status).toBe("occupied");

    const order = buildOrderFromCart({
      tableId: "t1",
      orderType: "dine_in",
      discountAmount: 0,
      items: [{ productId: "tea", name: "Tea", quantity: 1, price: 40, taxRate: 5 }],
    });

    expect(changeKdsStatus(order, "preparing").kdsStatus).toBe("preparing");
    expect(changeKdsStatus(order, "ready").kdsStatus).toBe("ready");
  });

  it("persists offline queue items for later sync", () => {
    addQueueItem({ type: "create_order", payload: { tableId: "t1" } });
    addQueueItem({ type: "payment", payload: { orderId: "o1" } });

    const queue = getQueueItems();
    expect(queue).toHaveLength(2);
    expect(queue[0].synced).toBe(false);
    expect(queue[1].type).toBe("payment");
  });
});
