// ─────────────────────────────────────────────────────────
// Korvexa Auth — Role hierarchy, permission matrix, nav access
// ─────────────────────────────────────────────────────────

export type AppRole =
  | "super_admin"
  | "platform_owner"
  | "platform_admin"
  | "tenant_owner"
  | "tenant_admin"
  | "manager"
  | "store_manager"
  | "cashier"
  | "waiter"
  | "kitchen_staff"
  | "accountant";

export const ROLE_LEVELS: Record<AppRole, number> = {
  super_admin: 9,
  platform_owner: 8,
  platform_admin: 7,
  tenant_owner: 6,
  tenant_admin: 6,
  manager: 5,
  store_manager: 5,
  cashier: 4,
  waiter: 3,
  kitchen_staff: 2,
  accountant: 1,
};

export const ROLE_LABELS: Record<AppRole, string> = {
  super_admin: "Super Admin",
  platform_owner: "Platform Owner",
  platform_admin: "Platform Admin",
  tenant_owner: "Tenant Owner",
  tenant_admin: "Tenant Admin",
  manager: "Manager",
  store_manager: "Store Manager",
  cashier: "Cashier",
  waiter: "Waiter",
  kitchen_staff: "Kitchen Staff",
  accountant: "Accountant",
};

export const ROLE_COLORS: Record<AppRole, { color: string; bg: string }> = {
  super_admin:    { color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  platform_owner: { color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  platform_admin: { color: "#f97316", bg: "rgba(249,115,22,0.12)" },
  tenant_owner:   { color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  tenant_admin:   { color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  manager:        { color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  store_manager:  { color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  cashier:        { color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  waiter:         { color: "#2dd4bf", bg: "rgba(45,212,191,0.12)" },
  kitchen_staff:  { color: "#fb923c", bg: "rgba(251,146,60,0.12)" },
  accountant:     { color: "#94a3b8", bg: "rgba(148,163,184,0.12)" },
};

export type NavSection =
  | "Dashboard" | "POS Billing" | "Orders" | "Online Delivery" | "KDS" | "Table Management"
  | "Menu" | "Inventory" | "Staff" | "Reports" | "Settings"
  | "Razorpay Dashboard" | "Admin Panel" | "Platform";

const NAV_ACCESS: Record<NavSection, AppRole[]> = {
  "Platform":          ["super_admin", "platform_owner", "platform_admin"],
  "Admin Panel":       ["super_admin", "platform_owner", "platform_admin", "tenant_owner", "tenant_admin", "manager", "store_manager"],
  "Dashboard":         ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","cashier","waiter","accountant"],
  "POS Billing":       ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","cashier","waiter"],
  "Orders":            ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","cashier","waiter","accountant"],
  "Online Delivery":   ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","cashier","waiter"],
  "KDS":               ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","kitchen_staff","waiter"],
  "Table Management":  ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","cashier","waiter"],
  "Menu":              ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager"],
  "Inventory":         ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","accountant"],
  "Staff":             ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","accountant"],
  "Reports":           ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","accountant"],
  "Razorpay Dashboard": ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager","accountant"],
  "Settings":          ["super_admin","platform_owner","platform_admin","tenant_owner","tenant_admin","manager","store_manager"],
};

export function canAccessNav(role: AppRole | null, section: NavSection): boolean {
  if (!role) return false;
  const allowed = NAV_ACCESS[section] ?? [];
  return allowed.includes(role);
}

// Decode role from JWT payload (base64)
export function getRoleFromToken(token: string): AppRole | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const rawRole: string = payload.role ?? payload.roles?.[0] ?? "";
    return normalizeRole(rawRole);
  } catch {
    return null;
  }
}

export function normalizeRole(role: string): AppRole | null {
  const map: Record<string, AppRole> = {
    super_admin: "super_admin",
    platform_owner: "platform_owner",
    platform_admin: "platform_admin",
    tenant_owner: "tenant_owner",
    tenant_admin: "tenant_admin",
    manager: "manager",
    store_manager: "store_manager",
    cashier: "cashier",
    waiter: "waiter",
    kitchen_staff: "kitchen_staff",
    accountant: "accountant",
  };
  return map[role] ?? null;
}

export function getTenantIdFromToken(token: string): string | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.tenant_id ?? null;
  } catch { return null; }
}

export function isAtLeast(role: AppRole | null, minRole: AppRole): boolean {
  if (!role) return false;
  return ROLE_LEVELS[role] >= ROLE_LEVELS[minRole];
}

export function isSuperAdmin(role: AppRole | null): boolean {
  return role === "super_admin" || role === "platform_owner" || role === "platform_admin";
}

export function isTenantAdmin(role: AppRole | null): boolean {
  return role === "tenant_owner" || role === "tenant_admin" || isSuperAdmin(role);
}
