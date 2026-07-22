import { describe, expect, it } from "vitest";

import { unseenNewDeliveryOrders } from "./onlineDelivery";

describe("online delivery notifications", () => {
  const orders = [
    { id: "new-swiggy", status: "new", provider: "swiggy" },
    { id: "accepted-zomato", status: "accepted", provider: "zomato" },
  ];

  it("does not notify during the initial snapshot", () => {
    expect(unseenNewDeliveryOrders(orders, new Set(), false)).toEqual([]);
  });

  it("returns only unseen orders that still need attention", () => {
    expect(unseenNewDeliveryOrders(orders, new Set(["accepted-zomato"]), true)).toEqual([orders[0]]);
  });
});
