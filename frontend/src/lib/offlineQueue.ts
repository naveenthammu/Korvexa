export type OfflineActionType = "create_order" | "payment" | "kds_update" | "inventory_adjustment";

export interface OfflineQueueItem {
  id: string;
  type: OfflineActionType;
  payload: unknown;
  synced: boolean;
  createdAt: string;
}

const KEY = "korvexa.offlineQueue";

export function getQueueItems(): OfflineQueueItem[] {
  const stored = localStorage.getItem(KEY);
  if (!stored) {
    return [];
  }
  try {
    return JSON.parse(stored) as OfflineQueueItem[];
  } catch {
    return [];
  }
}

export function addQueueItem(input: Omit<OfflineQueueItem, "id" | "synced" | "createdAt">): OfflineQueueItem {
  const item: OfflineQueueItem = {
    id: crypto.randomUUID(),
    synced: false,
    createdAt: new Date().toISOString(),
    ...input,
  };
  localStorage.setItem(KEY, JSON.stringify([...getQueueItems(), item]));
  return item;
}

export function markQueueItemSynced(id: string): void {
  localStorage.setItem(
    KEY,
    JSON.stringify(getQueueItems().map((item) => (item.id === id ? { ...item, synced: true } : item))),
  );
}
