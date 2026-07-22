import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2, Users, Shield, Settings, Plus, Edit2,
  Trash2, ToggleLeft, ToggleRight, X, Check, Mail,
  Phone, MapPin, Store, UserPlus, Key, Lock, Unlock,
} from "lucide-react";
import type { AppRole } from "../lib/auth";
import { ROLE_LABELS, ROLE_COLORS } from "../lib/auth";
import { Button } from "../components/ui/button";


interface Branch { id: string; name: string; address?: string; phone?: string; status: string; }
interface AppUser  { id: string; name: string; email: string; phone?: string; role: AppRole; branch_id?: string; status: string; locked?: boolean; permissions?: string[]; }
interface TaxSettings {
  receipt_name: string;
  gst_number: string;
  food_gst_rate: number;
  beverage_gst_rate: number;
  upi_id: string;
  upi_qr_url: string;
  receipt_footer: string;
}
interface SecurityPolicy {
  password_min_length: number;
  session_timeout_minutes: number;
  multi_device_login: boolean;
  two_factor_auth: boolean;
  login_attempts_threshold: number;
}

interface Props {
  token: string;
  branches: Branch[];
  users: AppUser[];
  userRole: AppRole;
  activeTab?: AdminTab;
  onTabChange?: (tab: AdminTab) => void;
  onRefresh: () => void;
  showToast: (msg: string, type?: "success"|"error"|"info"|"warning") => void;
  apiRequest: (url: string, opts?: any) => Promise<any>;
}

export type AdminTab = "stores" | "users" | "roles" | "security" | "taxes";

const ALL_ROLES = [
  "manager","cashier","waiter","kitchen_staff","accountant"
] as const;
type ManagedRole = typeof ALL_ROLES[number];

const USER_PERMISSION_OPTIONS = [
  { key: "branch:manage", label: "Stores & Branches" },
  { key: "user:manage", label: "Users & Roles" },
  { key: "employee:view", label: "View Staff" },
  { key: "employee:manage", label: "Attendance, Payroll & Staff" },
  { key: "menu:view", label: "View Menu" },
  { key: "menu:manage", label: "Menu, Items & Discounts" },
  { key: "inventory:view", label: "View Inventory" },
  { key: "inventory:manage", label: "Stock, Purchase Orders & Suppliers" },
  { key: "table:view", label: "View Tables" },
  { key: "table:manage", label: "Tables, Merge & Cleaning" },
  { key: "order:view", label: "View Orders" },
  { key: "order:manage", label: "Orders, KDS & Discount Approval" },
  { key: "kds:view", label: "View KDS" },
  { key: "kds:manage", label: "Accept & Update KDS" },
  { key: "payment:manage", label: "Payments, Refunds & Cashout" },
  { key: "report:view", label: "Sales, Staff & Inventory Reports" },
  { key: "settings:manage", label: "GST, Receipt & App Settings" },
  { key: "audit:view", label: "Audit Logs" },
  { key: "customer:view", label: "View Customers" },
  { key: "customer:manage", label: "Manage Customers" },
  { key: "discount:manage", label: "Discount Approval" },
  { key: "refund:manage", label: "Refund Approval" },
  { key: "void:manage", label: "Void Orders" },
  { key: "shift:view", label: "View Shifts" },
  { key: "shift:manage", label: "Manage Shifts" },
  { key: "drawer:manage", label: "Cash Drawer" },
];

const DEFAULT_ROLE_PERMISSIONS: Record<ManagedRole, string[]> = {
  manager: ["branch:manage", "menu:manage", "order:manage", "payment:manage", "table:manage", "inventory:manage", "inventory:view", "kds:view", "kds:manage", "report:view", "user:manage", "employee:view", "employee:manage", "audit:view", "customer:manage", "discount:manage", "refund:manage", "void:manage", "shift:manage", "drawer:manage"],
  cashier: ["order:manage", "payment:manage", "table:view", "report:view", "shift:manage", "drawer:manage", "customer:view"],
  waiter: ["order:manage", "table:manage", "customer:manage", "kds:view", "kds:manage"],
  kitchen_staff: ["kds:manage", "kds:view", "order:view", "menu:view", "inventory:view"],
  accountant: ["report:view", "employee:view", "employee:manage"],
};

function unwrapApiData<T>(response: any): T {
  return (response?.data ?? response) as T;
}

function readableApiError(error: unknown, fallback: string) {
  if (!(error instanceof Error) || !error.message) return fallback;
  try {
    const parsed = JSON.parse(error.message);
    if (typeof parsed.message === "string" && parsed.message.trim()) return parsed.message;
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail;
    if (Array.isArray(parsed.message) && parsed.message[0]?.msg) return parsed.message[0].msg;
    if (Array.isArray(parsed.errors) && typeof parsed.errors[0]?.detail === "string" && parsed.errors[0].detail.trim()) return parsed.errors[0].detail;
  } catch {
    if (error.message.trim()) return error.message;
  }
  return fallback;
}

function getUserIdFromToken(token: string): string | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}

export default function AdminPage({
  token,
  branches,
  users,
  userRole,
  activeTab,
  onTabChange,
  onRefresh,
  showToast,
  apiRequest,
}: Props) {
  const [internalTab, setInternalTab] = useState<AdminTab>("stores");
  const tab = activeTab ?? internalTab;
  const setTab = (nextTab: AdminTab) => {
    if (activeTab === undefined) setInternalTab(nextTab);
    onTabChange?.(nextTab);
  };
  const manageableUserRoles = ALL_ROLES.filter((role) => userRole !== "manager" || role !== "manager");
  const currentUserId = getUserIdFromToken(token);

  const [showPasswordResetWizard, setShowPasswordResetWizard] = useState(false);
  const [passwordResetWizard, setPasswordResetWizard] = useState({ userId: "", userName: "", newPassword: "" });

  // Store CRUD
  const [showStoreModal, setShowStoreModal] = useState(false);
  const [editingStore, setEditingStore] = useState<Branch | null>(null);
  const [storeName, setStoreName]       = useState("");
  const [storeAddr, setStoreAddr]       = useState("");
  const [storePhone, setStorePhone]     = useState("");

  // User CRUD
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser]   = useState<AppUser | null>(null);
  const [userName, setUserName]         = useState("");
  const [userEmail, setUserEmail]       = useState("");
  const [userPhone, setUserPhone]       = useState("");
  const [userBranch, setUserBranch]     = useState("");
  const [userRoleSel, setUserRoleSel]   = useState<AppRole>("cashier");
  const [userPassword, setUserPassword] = useState("");
  const [userPermissions, setUserPermissions] = useState<string[]>([]);

  // Security
  const [pwMinLen, setPwMinLen]       = useState(8);
  const [sessionMin, setSessionMin]   = useState(30);
  const [multiDevice, setMultiDevice] = useState(true);
  const [twoFactor, setTwoFactor]     = useState(false);
  const [lockLimit, setLockLimit]     = useState(5);

  // GST / receipt
  const [taxBranchId, setTaxBranchId] = useState("");
  const [taxLoading, setTaxLoading] = useState(false);
  const [taxSaving, setTaxSaving] = useState(false);
  const [receiptName, setReceiptName] = useState("");
  const [gstNumber, setGstNumber] = useState("");
  const [foodGstRate, setFoodGstRate] = useState(5);
  const [beverageGstRate, setBeverageGstRate] = useState(18);
  const [upiId, setUpiId] = useState("");
  const [upiQrUrl, setUpiQrUrl] = useState("");
  const [receiptFooter, setReceiptFooter] = useState("Thank you! Visit again.");
  const [applyTaxToMenu, setApplyTaxToMenu] = useState(true);

  // Role Permissions
  const [rolePermissions, setRolePermissions] = useState<Record<ManagedRole, string[]>>(DEFAULT_ROLE_PERMISSIONS);
  const [userPermissionDrafts, setUserPermissionDrafts] = useState<Record<string, string[]>>({});
  const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean, title: string, message: string, onConfirm: () => void }>({ isOpen: false, title: "", message: "", onConfirm: () => {} });

  function togglePermission(role: ManagedRole, perm: string) {
    setRolePermissions(prev => {
      const current = prev[role] || [];
      if (current.includes(perm)) {
        return { ...prev, [role]: current.filter(p => p !== perm) };
      } else {
        return { ...prev, [role]: [...current, perm] };
      }
    });
  }

  async function handleSavePermissions() {
    try {
      const res = await apiRequest("/api/v1/admin/permissions", { method: "PATCH", token, body: JSON.stringify(rolePermissions) });
      const data = unwrapApiData<{ role_permissions?: Partial<Record<ManagedRole, string[]>> }>(res);
      if (data.role_permissions) setRolePermissions({ ...DEFAULT_ROLE_PERMISSIONS, ...data.role_permissions });
      showToast("Permissions updated successfully", "success");
    } catch (error) {
      showToast(readableApiError(error, "Failed to save permissions"), "error");
    }
  }

  useEffect(() => {
    if (tab !== "roles") return;
    let cancelled = false;
    async function loadRolePermissions() {
      try {
        const res = await apiRequest("/api/v1/admin/permissions", { token });
        const data = unwrapApiData<{ role_permissions?: Partial<Record<ManagedRole, string[]>> }>(res);
        if (!cancelled && data.role_permissions) {
          setRolePermissions({ ...DEFAULT_ROLE_PERMISSIONS, ...data.role_permissions });
        }
      } catch (error) {
        if (!cancelled) showToast(readableApiError(error, "Failed to load permissions"), "error");
      }
    }
    loadRolePermissions();
    return () => { cancelled = true; };
  }, [tab, token, apiRequest, showToast]);

  useEffect(() => {
    if (tab !== "security") return;
    let cancelled = false;
    async function loadSecurityPolicy() {
      try {
        const res = await apiRequest("/api/v1/admin/security-settings", { token });
        const data = unwrapApiData<SecurityPolicy>(res);
        if (cancelled) return;
        setPwMinLen(Number(data.password_min_length ?? 8));
        setSessionMin(Number(data.session_timeout_minutes ?? 30));
        setMultiDevice(Boolean(data.multi_device_login));
        setTwoFactor(Boolean(data.two_factor_auth));
        setLockLimit(Number(data.login_attempts_threshold ?? 5));
      } catch (error) {
        if (!cancelled) showToast(readableApiError(error, "Failed to load security settings"), "error");
      }
    }
    loadSecurityPolicy();
    return () => { cancelled = true; };
  }, [tab, token, apiRequest, showToast]);

  useEffect(() => {
    setUserPermissionDrafts((prev) => {
      const next: Record<string, string[]> = {};
      users.forEach((user) => {
        next[user.id] = user.permissions || prev[user.id] || [];
      });
      return next;
    });
  }, [users]);

  function toggleUserPermission(userId: string, permission: string) {
    setUserPermissionDrafts((prev) => {
      const current = prev[userId] || [];
      return {
        ...prev,
        [userId]: current.includes(permission)
          ? current.filter((item) => item !== permission)
          : [...current, permission],
      };
    });
  }

  async function handleSaveUserPermissions(user: AppUser) {
    try {
      await apiRequest(`/api/v1/users/${user.id}`, { method: "PATCH", token, body: JSON.stringify({ permissions: userPermissionDrafts[user.id] || [] }) });
      showToast(`Permissions updated for ${user.name}`, "success");
      onRefresh();
    } catch {
      showToast("Failed to update user permissions", "error");
    }
  }

  useEffect(() => {
    if (!taxBranchId && branches[0]?.id) setTaxBranchId(branches[0].id);
  }, [branches, taxBranchId]);

  useEffect(() => {
    if (tab !== "taxes" || !taxBranchId) return;
    let cancelled = false;
    async function loadTaxSettings() {
      setTaxLoading(true);
      try {
        const res = await apiRequest(`/api/v1/settings/tax?branch_id=${taxBranchId}`, { token });
        const data = (res.data ?? res) as TaxSettings;
        if (cancelled) return;
        setReceiptName(data.receipt_name || branches.find((b) => b.id === taxBranchId)?.name || "");
        setGstNumber(data.gst_number || "");
        setFoodGstRate(Number(data.food_gst_rate ?? 5));
        setBeverageGstRate(Number(data.beverage_gst_rate ?? 18));
        setUpiId(data.upi_id || "");
        setUpiQrUrl(data.upi_qr_url || "");
        setReceiptFooter(data.receipt_footer || "Thank you! Visit again.");
      } catch {
        if (!cancelled) showToast("Failed to load GST settings", "error");
      } finally {
        if (!cancelled) setTaxLoading(false);
      }
    }
    loadTaxSettings();
    return () => { cancelled = true; };
  }, [tab, taxBranchId, token, apiRequest, branches, showToast]);

  async function handleDeleteStore(b: Branch) {
    setConfirmModal({
      isOpen: true,
      title: "Delete Store",
      message: `Are you sure you want to delete store ${b.name}? This will remove it from active store lists.`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/branches/${b.id}`, { method: "DELETE", token });
          showToast(`Store ${b.name} deleted successfully!`, "success");
          onRefresh();
        } catch {
          showToast("Failed to delete store (cannot delete your only store)", "error");
        }
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  }

  async function handleSaveStore(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (editingStore) {
        await apiRequest(`/api/v1/branches/${editingStore.id}`, { method: "PATCH", token, body: JSON.stringify({ name: storeName, address: storeAddr, phone: storePhone }) });
        showToast("Store updated!", "success");
      } else {
        await apiRequest("/api/v1/branches", { method: "POST", token, body: JSON.stringify({ name: storeName, address: storeAddr, phone: storePhone }) });
        showToast("Store created!", "success");
      }
      setShowStoreModal(false); onRefresh();
    } catch { showToast("Failed to save store", "error"); }
  }

  async function handleToggleStore(b: Branch) {
    try {
      await apiRequest(`/api/v1/branches/${b.id}`, { method: "PATCH", token, body: JSON.stringify({ status: b.status === "active" ? "inactive" : "active" }) });
      showToast(`Store ${b.status === "active" ? "disabled" : "enabled"}`, "success");
      onRefresh();
    } catch { showToast("Failed to update store", "error"); }
  }

  async function handleSaveUser(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (editingUser) {
        await apiRequest(`/api/v1/users/${editingUser.id}`, { method: "PATCH", token, body: JSON.stringify({ name: userName, phone: userPhone, role: userRoleSel, branch_id: userBranch || null, permissions: userPermissions }) });
        showToast("User updated!", "success");
      } else {
        await apiRequest("/api/v1/users", { method: "POST", token, body: JSON.stringify({ name: userName, email: userEmail, phone: userPhone, password: userPassword, role: userRoleSel, branch_id: userBranch || null, permissions: userPermissions }) });
        showToast("User created!", "success");
      }
      setShowUserModal(false); onRefresh();
    } catch (error) {
      showToast(readableApiError(error, "Failed to save user"), "error");
    }
  }

  async function handleToggleUser(u: AppUser) {
    try {
      const unlock = Boolean(u.locked);
      await apiRequest(`/api/v1/admin/users/${u.id}/${unlock ? "unlock" : "lock"}`, { method: "POST", token });
      showToast(`User ${u.name} ${unlock ? "unlocked" : "locked"}`, "success");
      onRefresh();
    } catch { showToast("Failed to update user", "error"); }
  }

  async function handleSetUserStatus(u: AppUser, status: "active" | "inactive") {
    try {
      await apiRequest(`/api/v1/users/${u.id}`, { method: "PATCH", token, body: JSON.stringify({ status }) });
      showToast(`User ${u.name} ${status === "active" ? "enabled" : "disabled"}`, "success");
      onRefresh();
    } catch (error) {
      showToast(readableApiError(error, "Failed to update user status"), "error");
    }
  }

  async function handleResetPassword(u: AppUser) {
    setPasswordResetWizard({ userId: u.id, userName: u.name, newPassword: "" });
    setShowPasswordResetWizard(true);
  }

  async function handleSavePasswordResetWizard(e: React.FormEvent) {
    e.preventDefault();
    if (!passwordResetWizard.newPassword) return;
    try {
      await apiRequest(`/api/v1/users/${passwordResetWizard.userId}/reset-password`, { method: "POST", token, body: JSON.stringify({ new_password: passwordResetWizard.newPassword }) });
      showToast(`Password reset successfully for ${passwordResetWizard.userName}!`, "success");
      setShowPasswordResetWizard(false);
    } catch (error) {
      showToast(readableApiError(error, "Failed to reset password"), "error");
    }
  }

  async function handleDeleteUser(u: AppUser) {
    setConfirmModal({
      isOpen: true,
      title: "Delete User",
      message: `Are you sure you want to permanently delete user ${u.name}?`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/users/${u.id}`, { method: "DELETE", token });
          showToast(`User ${u.name} deleted successfully!`, "success");
          onRefresh();
        } catch { showToast("Failed to delete user", "error"); }
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  }

  function handleGrantAll(role: ManagedRole) {
    setRolePermissions((prev) => ({
      ...prev,
      [role]: USER_PERMISSION_OPTIONS.map((permission) => permission.key)
    }));
  }

  async function handleSaveSecurity(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/v1/admin/security-settings", { method: "PATCH", token, body: JSON.stringify({ password_min_length: pwMinLen, session_timeout_minutes: sessionMin, multi_device_login: multiDevice, two_factor_auth: twoFactor, login_attempts_threshold: lockLimit }) });
      const data = unwrapApiData<SecurityPolicy>(res);
      setPwMinLen(Number(data.password_min_length ?? pwMinLen));
      setSessionMin(Number(data.session_timeout_minutes ?? sessionMin));
      setMultiDevice(Boolean(data.multi_device_login));
      setTwoFactor(Boolean(data.two_factor_auth));
      setLockLimit(Number(data.login_attempts_threshold ?? lockLimit));
      showToast("Security policy saved!", "success");
    } catch (error) { showToast(readableApiError(error, "Failed to save security settings"), "error"); }
  }

  async function handleSaveTaxSettings(e: React.FormEvent) {
    e.preventDefault();
    if (!taxBranchId) {
      showToast("Select a store first", "warning");
      return;
    }
    setTaxSaving(true);
    try {
      const res = await apiRequest(`/api/v1/settings/tax?branch_id=${taxBranchId}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({
          receipt_name: receiptName,
          gst_number: gstNumber,
          food_gst_rate: foodGstRate,
          beverage_gst_rate: beverageGstRate,
          upi_id: upiId,
          upi_qr_url: upiQrUrl,
          receipt_footer: receiptFooter,
          apply_to_menu: applyTaxToMenu,
        }),
      });
      const updatedProducts = res.data?.updated_products ?? res.updated_products ?? 0;
      showToast(applyTaxToMenu ? `GST settings saved. ${updatedProducts} menu items updated.` : "GST settings saved.", "success");
      onRefresh();
    } catch {
      showToast("Failed to save GST settings", "error");
    } finally {
      setTaxSaving(false);
    }
  }

  function openCreateStore() { setEditingStore(null); setStoreName(""); setStoreAddr(""); setStorePhone(""); setShowStoreModal(true); }
  function openEditStore(b: Branch) { setEditingStore(b); setStoreName(b.name); setStoreAddr(b.address || ""); setStorePhone(b.phone || ""); setShowStoreModal(true); }
  function openCreateUser() { setEditingUser(null); setUserName(""); setUserEmail(""); setUserPhone(""); setUserRoleSel(manageableUserRoles[0] || "cashier"); setUserBranch(branches[0]?.id || ""); setUserPassword(""); setUserPermissions([]); setShowUserModal(true); }
  function openEditUser(u: AppUser) { setEditingUser(u); setUserName(u.name); setUserEmail(u.email); setUserPhone(u.phone || ""); setUserRoleSel(u.role); setUserBranch(u.branch_id || ""); setUserPassword(""); setUserPermissions(userPermissionDrafts[u.id] || u.permissions || []); setShowUserModal(true); }

  const tabs: { key: AdminTab; label: string; icon: typeof Building2 }[] = [
    { key: "stores", label: "Stores", icon: Building2 },
    { key: "users",  label: "Users",  icon: Users },
    { key: "roles",  label: "Roles & Permissions", icon: Shield },
    { key: "taxes",  label: "GST & Taxes", icon: Settings },
    { key: "security", label: "Security Policy", icon: Settings },
  ];

  const userPermissionsPanel = (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h2>User Permissions</h2>
            <p>Grant or remove feature access for individual users</p>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Shield size={20} color="var(--accent)" />
          </div>
      </div>
      <div className="table-responsive">
<table className="data-table">
        <thead><tr><th>User</th><th>Role</th><th>Permissions</th><th>Actions</th></tr></thead>
        <tbody>
          {users.length === 0 ? (
            <tr><td colSpan={4} style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>No users found</td></tr>
          ) : users.map((u) => {
            const rc = ROLE_COLORS[u.role] || { color: "var(--text-muted)", bg: "var(--surface-soft)" };
            const grants = userPermissionDrafts[u.id] || [];
            return (
              <tr key={u.id}>
                <td>
                  <strong style={{ display: "block" }}>{u.name}</strong>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{u.email}</span>
                </td>
                <td><span className="role-badge" style={{ background: rc.bg, color: rc.color }}>{ROLE_LABELS[u.role] || u.role}</span></td>
                <td>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                    {USER_PERMISSION_OPTIONS.map((permission) => {
                      const checked = grants.includes(permission.key);
                      return (
                        <label key={`${u.id}-${permission.key}`} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, background: checked ? "var(--success-soft)" : "var(--surface-soft)", border: `1px solid ${checked ? "var(--success)" : "var(--border)"}`, color: checked ? "var(--success)" : "var(--text-soft)", fontSize: "0.78rem", fontWeight: 700 }}>
                          <input type="checkbox" checked={checked} onChange={() => toggleUserPermission(u.id, permission.key)} />
                          {permission.label}
                        </label>
                      );
                    })}
                  </div>
                </td>
                <td><Button variant="default" onClick={() => handleSaveUserPermissions(u)}>Save User</Button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
</div>
    </div>
  );

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <div className="tab-nav">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
              <Icon size={14} style={{ marginRight: 6 }} />{t.label}
            </button>
          );
        })}
      </div>

      {/* ── STORES TAB ─────────────────────────────────────── */}
      {tab === "stores" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <div>
                <h2>Store Management</h2>
                <p>Create and manage branches within your tenant</p>
              </div>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{branches.length} stores</span>
                <Button variant="default" onClick={openCreateStore}><Plus size={16} /> New Store</Button>
              </div>
            </div>
            <div className="table-responsive">
<table className="data-table">
              <thead><tr><th>Store Name</th><th>Address</th><th>Phone</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {branches.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>No stores found</td></tr>
                ) : branches.map((b) => (
                  <tr key={b.id}>
                    <td><strong>{b.name}</strong></td>
                    <td style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{b.address || "—"}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{b.phone || "—"}</td>
                    <td><span className={`pill ${b.status === "active" ? "success" : "danger"}`}>{b.status}</span></td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <Button variant="secondary" onClick={() => openEditStore(b)}><Edit2 size={16} /> Edit</Button>
                        <Button variant={b.status === "active" ? "ghost" : "default"} style={{ color: b.status === "active" ? "var(--danger)" : undefined }} onClick={() => handleToggleStore(b)}>
                          {b.status === "active" ? <><ToggleLeft size={16}/> Disable</> : <><ToggleRight size={16}/> Enable</>}
                        </Button>
                        <Button variant="ghost" style={{ color: "var(--danger)" }} onClick={() => handleDeleteStore(b)}>
                          <Trash2 size={16}/> Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
</div>
          </div>
        </div>
      )}

      {/* ── USERS TAB ──────────────────────────────────────── */}
      {tab === "users" && (
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <div>
              <h2>User Management</h2>
              <p>All users across your tenant's stores</p>
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{users.length} users</span>
              <Button variant="default" onClick={openCreateUser}><UserPlus size={16} /> New User</Button>
            </div>
          </div>
          <div className="table-responsive">
<table className="data-table">
            <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Store</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {users.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>No users found</td></tr>
              ) : users.map((u) => {
                const rc = ROLE_COLORS[u.role] || { color: "var(--text-muted)", bg: "var(--surface-soft)" };
                const store = branches.find(b => b.id === u.branch_id);
                const isCurrentUser = currentUserId === u.id;
                return (
                  <tr key={u.id}>
                    <td><strong>{u.name}</strong></td>
                    <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>{u.email}</td>
                    <td>
                      <span className="role-badge" style={{ background: rc.bg, color: rc.color }}>
                        {ROLE_LABELS[u.role] || u.role}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.82rem" }}>{store?.name || "—"}</td>
                    <td><span className={`pill ${u.locked ? "danger" : u.status === "active" ? "success" : "danger"}`}>{u.locked ? "locked" : u.status}</span></td>
                    <td>
                      <div style={{ display: "flex", gap: 5 }}>
                        <Button variant="secondary" onClick={() => openEditUser(u)}><Edit2 size={16}/> Edit</Button>
                        <Button variant="secondary" onClick={() => handleResetPassword(u)}><Key size={16}/> Reset PW</Button>
                        {isCurrentUser ? (
                          <span style={{ alignSelf: "center", color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: 700 }}>Current user</span>
                        ) : (
                          <>
                            <Button variant={u.locked ? "default" : "ghost"} style={{ color: u.locked ? undefined : "var(--amber)" }} onClick={() => handleToggleUser(u)}>
                              {u.locked ? <><Unlock size={16}/> Unlock</> : <><Lock size={16}/> Lock</>}
                            </Button>
                            <Button
                              variant={u.status === "active" ? "ghost" : "default"}
                              style={{ color: u.status === "active" ? "var(--danger)" : undefined }}
                              onClick={() => handleSetUserStatus(u, u.status === "active" ? "inactive" : "active")}
                            >
                              {u.status === "active" ? <><ToggleLeft size={16}/> Disable</> : <><ToggleRight size={16}/> Enable</>}
                            </Button>
                            <Button variant="ghost" style={{ color: "var(--danger)" }} onClick={() => handleDeleteUser(u)}>
                              <Trash2 size={16}/> Delete
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
</div>
        </div>
      )}

      {/* ── ROLES TAB ──────────────────────────────────────── */}
      {tab === "roles" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h2>Role Permissions</h2>
            <p>Feature access by role level</p>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Button variant="default" onClick={handleSavePermissions}>Save Permissions</Button>
          </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="permission-matrix">
              <thead>
                <tr>
                  <th style={{ minWidth: 220 }}>Permission</th>
                  {ALL_ROLES.map((r) => {
                    const rc = ROLE_COLORS[r];
                    return (
                      <th key={r}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center" }}>
                          <span className="role-badge" style={{ background: rc.bg, color: rc.color }}>{ROLE_LABELS[r]}</span>
                          <button onClick={() => handleGrantAll(r)} style={{ fontSize: "0.68rem", background: "none", border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", padding: "2px 6px" }}>Grant All</button>
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {USER_PERMISSION_OPTIONS.map((permission) => (
                  <tr key={permission.key}>
                    <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{permission.label}</td>
                    {ALL_ROLES.map((r) => {
                      const has = (rolePermissions[r] || []).includes(permission.key);
                      return (
                        <td key={r} style={{ textAlign: "center" }}>
                          <button
                            onClick={() => togglePermission(r, permission.key)}
                            style={{
                              background: "transparent", border: "none", cursor: "pointer",
                              padding: "4px", borderRadius: "4px",
                              backgroundColor: has ? "var(--success-soft)" : "transparent"
                            }}
                          >
                            {has
                              ? <Check size={16} color="var(--success)" />
                              : <X size={14} color="var(--border)" />}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {userPermissionsPanel}
        </div>
      )}

      {/* ── SECURITY TAB ───────────────────────────────────── */}
      {tab === "security" && (
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h2>Security Policy</h2>
            <p>Manage lockout, session, and authentication rules</p>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Settings size={20} color="var(--accent)" />
          </div>
          </div>
          <form onSubmit={handleSaveSecurity} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="form-grid">
              <div className="form-group">
                <label>Min Password Length</label>
                <input type="number" value={pwMinLen} onChange={(e) => setPwMinLen(parseInt(e.target.value))} min="8" max="32" required />
              </div>
              <div className="form-group">
                <label>Session Timeout (min)</label>
                <input type="number" value={sessionMin} onChange={(e) => setSessionMin(parseInt(e.target.value))} min="5" max="1440" required />
              </div>
              <div className="form-group">
                <label>Failed Login Limit</label>
                <input type="number" value={lockLimit} onChange={(e) => setLockLimit(parseInt(e.target.value))} min="3" max="20" required />
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {[
                { key: "multiDevice" as const, val: multiDevice, setter: setMultiDevice, label: "Allow Multi-Device Login", desc: "Users can sign in from multiple devices simultaneously" },
                { key: "twoFactor" as const, val: twoFactor, setter: setTwoFactor, label: "Enforce Two-Factor Authentication", desc: "Require OTP/TOTP on every login" },
              ].map(({ key, val, setter, label, desc }) => (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 16, background: "var(--surface-soft)", border: "1px solid var(--border)", borderRadius: 12 }}>
                  <div>
                    <strong style={{ display: "block", fontSize: "0.875rem" }}>{label}</strong>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{desc}</span>
                  </div>
                  <div className={`toggle-switch ${val ? "active" : ""}`} onClick={() => setter(!val)}>
                    <motion.div className="toggle-thumb" animate={{ x: val ? 20 : 0 }} />
                  </div>
                </div>
              ))}
            </div>
            <Button type="submit" variant="default" style={{ alignSelf: "flex-start" }}>
              Save Security Settings
            </Button>
          </form>
        </div>
      )}

      {tab === "taxes" && (
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h2>Tax, GST &amp; Receipt Settings</h2>
            <p>Configure bill header, GST rates, UPI, and receipt print details</p>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Settings size={20} color="var(--accent)" />
          </div>
          </div>
          <form onSubmit={handleSaveTaxSettings} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="form-grid">
              <div className="form-group">
                <label htmlFor="tax-store">Store</label>
                <select id="tax-store" value={taxBranchId} onChange={(e) => setTaxBranchId(e.target.value)} disabled={taxLoading || taxSaving}>
                  {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="receipt-name">Hotel / Receipt Name</label>
                <input id="receipt-name" type="text" value={receiptName} onChange={(e) => setReceiptName(e.target.value)} placeholder="Green Bistro" required />
              </div>
              <div className="form-group">
                <label htmlFor="gst-number">GST Number</label>
                <input id="gst-number" type="text" value={gstNumber} onChange={(e) => setGstNumber(e.target.value)} placeholder="29ABCDE1234F1Z5" />
              </div>
              <div className="form-group">
                <label htmlFor="gst-food">Default Food GST (%)</label>
                <input id="gst-food" type="number" value={foodGstRate} onChange={(e) => setFoodGstRate(parseFloat(e.target.value || "0"))} min="0" max="30" step="0.01" required />
              </div>
              <div className="form-group">
                <label htmlFor="gst-beverage">Default Beverage GST (%)</label>
                <input id="gst-beverage" type="number" value={beverageGstRate} onChange={(e) => setBeverageGstRate(parseFloat(e.target.value || "0"))} min="0" max="30" step="0.01" required />
              </div>
              <div className="form-group">
                <label htmlFor="upi-id">UPI ID</label>
                <input id="upi-id" type="text" value={upiId} onChange={(e) => setUpiId(e.target.value)} placeholder="greenbistro@upi" />
              </div>
              <div className="form-group">
                <label htmlFor="upi-qr-url">UPI QR Image URL</label>
                <input id="upi-qr-url" type="url" value={upiQrUrl} onChange={(e) => setUpiQrUrl(e.target.value)} placeholder="https://.../upi-qr.png" />
              </div>
              <div className="form-group">
                <label htmlFor="receipt-footer">Receipt Footer</label>
                <input id="receipt-footer" type="text" value={receiptFooter} onChange={(e) => setReceiptFooter(e.target.value)} placeholder="Thank you! Visit again." />
              </div>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-soft)", fontSize: "0.86rem", fontWeight: 700 }}>
              <input type="checkbox" checked={applyTaxToMenu} onChange={(e) => setApplyTaxToMenu(e.target.checked)} />
              Apply food GST rate to existing menu items
            </label>
            <Button type="submit" variant="default" style={{ alignSelf: "flex-start" }} disabled={taxLoading || taxSaving || !taxBranchId}>
              {taxSaving ? "Saving..." : "Save Tax Settings"}
            </Button>
          </form>
        </div>
      )}

      {/* ── STORE MODAL ────────────────────────────────────── */}
      {confirmModal.isOpen && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-head">
              <h3>{confirmModal.title}</h3>
              <button onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}>&times;</button>
            </div>
            <p style={{ marginTop: '1rem', color: 'var(--text-soft)' }}>{confirmModal.message}</p>
            <div className="modal-footer" style={{ marginTop: '1.5rem', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <Button variant="secondary" onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}>Cancel</Button>
              <Button variant="default" style={{ background: 'var(--danger)' }} onClick={confirmModal.onConfirm}>Confirm</Button>
            </div>
          </div>
        </div>
      )}

      <AnimatePresence>
        {showStoreModal && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box narrow" initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}>
              <div className="modal-head">
                <div><h2>{editingStore ? "Edit Store" : "Create New Store"}</h2><p>Add a branch to your tenant</p></div>
                <button className="modal-close" onClick={() => setShowStoreModal(false)}><X size={14} /></button>
              </div>
              <form onSubmit={handleSaveStore} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div className="form-group"><label>Store Name *</label><input value={storeName} onChange={e=>setStoreName(e.target.value)} placeholder="e.g. Hyderabad Branch" required /></div>
                <div className="form-group"><label>Address</label><input value={storeAddr} onChange={e=>setStoreAddr(e.target.value)} placeholder="Street, City" /></div>
                <div className="form-group"><label>Phone</label><input value={storePhone} onChange={e=>setStorePhone(e.target.value)} placeholder="+91 98765 43210" /></div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowStoreModal(false)}>Cancel</Button>
                  <Button variant="default" type="submit">{editingStore ? "Update Store" : "Create Store"}</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── USER MODAL ─────────────────────────────────────── */}
      <AnimatePresence>
        {showUserModal && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}>
              <div className="modal-head">
                <div><h2>{editingUser ? "Edit User" : "Create New User"}</h2><p>Add or update a staff member</p></div>
                <button className="modal-close" onClick={() => setShowUserModal(false)}><X size={14} /></button>
              </div>
              <form onSubmit={handleSaveUser}>
                <div className="form-grid-2">
                  <div className="form-group"><label>Full Name *</label><input value={userName} onChange={e=>setUserName(e.target.value)} required /></div>
                  <div className="form-group"><label>Phone</label><input value={userPhone} onChange={e=>setUserPhone(e.target.value)} placeholder="+91..." /></div>
                  <div className="form-group span-2"><label>Email *</label><input type="email" value={userEmail} onChange={e=>setUserEmail(e.target.value)} required disabled={!!editingUser} /></div>
                  {!editingUser && <div className="form-group span-2"><label>Password *</label><input type="password" value={userPassword} onChange={e=>setUserPassword(e.target.value)} required={!editingUser} /></div>}
                  <div className="form-group">
                    <label>Role *</label>
                    <select value={userRoleSel} onChange={e=>setUserRoleSel(e.target.value as AppRole)}>
                      {manageableUserRoles.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Assigned Store</label>
                    <select value={userBranch} onChange={e=>setUserBranch(e.target.value)}>
                      <option value="">— All Stores —</option>
                      {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </select>
                  </div>
                  <div className="form-group span-2">
                    <label>Individual Access Grants</label>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
                      {USER_PERMISSION_OPTIONS.map((permission) => {
                        const checked = userPermissions.includes(permission.key);
                        return (
                          <label key={permission.key} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, background: checked ? "var(--success-soft)" : "var(--surface-soft)", border: `1px solid ${checked ? "var(--success)" : "var(--border)"}`, color: checked ? "var(--success)" : "var(--text-soft)", fontSize: "0.78rem", fontWeight: 700 }}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => setUserPermissions((prev) => event.target.checked ? [...prev, permission.key] : prev.filter((key) => key !== permission.key))}
                            />
                            {permission.label}
                          </label>
                        );
                      })}
                    </div>
                  </div>                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowUserModal(false)}>Cancel</Button>
                  <Button variant="default" type="submit">{editingUser ? "Update User" : "Create User"}</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Password Reset Wizard */}
      {showPasswordResetWizard && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-head">
              <h3>Reset Password for {passwordResetWizard.userName}</h3>
              <button className="modal-close" type="button" onClick={() => setShowPasswordResetWizard(false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleSavePasswordResetWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>New Password</label>
                <input type="password" value={passwordResetWizard.newPassword} onChange={(e) => setPasswordResetWizard({ ...passwordResetWizard, newPassword: e.target.value })} required className="input-field" style={{ width: '100%', padding: '10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)' }} />
              </div>
              <div className="modal-footer" style={{ marginTop: 16, display: "flex", gap: 12, justifyContent: "flex-end" }}>
                <Button variant="ghost" type="button" onClick={() => setShowPasswordResetWizard(false)}>Cancel</Button>
                <Button variant="default" type="submit">Reset Password</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
