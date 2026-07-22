import { describe, expect, it } from "vitest";
import { visibleKdsOrders } from "./kds";

describe("visibleKdsOrders", () => {
  it("does not create clickable demo tickets when backend has no KDS orders", () => {
    expect(visibleKdsOrders([])).toEqual([]);
  });

  it("keeps active KDS orders and only keeps served orders from today", () => {
    const today = new Date().toISOString();
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const orders = [
      { id: "new-1", kds_status: "new", created_at: yesterday },
      { id: "ready-1", kds_status: "ready", created_at: yesterday },
      { id: "served-today", kds_status: "served", created_at: today },
      { id: "served-old", kds_status: "served", created_at: yesterday },
      { id: "pending-1", kds_status: "pending", created_at: today },
    ];

    expect(visibleKdsOrders(orders).map((order) => order.id)).toEqual(["new-1", "ready-1", "served-today"]);
  });
});
