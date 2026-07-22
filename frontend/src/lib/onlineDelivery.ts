type DeliveryNotificationOrder = {
  id: string;
  status: string;
  provider: string;
};

export function unseenNewDeliveryOrders<T extends DeliveryNotificationOrder>(
  orders: T[],
  knownIds: Set<string>,
  initialized: boolean,
): T[] {
  if (!initialized) return [];
  return orders.filter((order) => order.status === "new" && !knownIds.has(order.id));
}
