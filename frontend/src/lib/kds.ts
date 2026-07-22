export type KdsOrderLike = {
  id: string;
  kds_status: string;
  created_at?: string;
};

const ACTIVE_KDS_STATUSES = new Set(["new", "accepted", "preparing", "ready"]);

function isToday(value?: string) {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return date.toDateString() === new Date().toDateString();
}

export function visibleKdsOrders<T extends KdsOrderLike>(orders: T[]): T[] {
  return orders.filter((order) => {
    if (ACTIVE_KDS_STATUSES.has(order.kds_status)) return true;
    return order.kds_status === "served" && isToday(order.created_at);
  });
}
