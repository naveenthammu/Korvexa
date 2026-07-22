import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  Banknote,
  ChefHat,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  Eye,
  EyeOff,
  Info,
  LayoutDashboard,
  Lock,
  LogOut,
  Mail,
  MailCheck,
  Moon,
  Package,
  Percent,
  Plus,
  Printer,
  Receipt,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Smartphone,
  Sun,
  Table2,
  TrendingDown,
  TrendingUp,
  Truck,
  Users,
  Utensils,
  WifiOff,
  X,
  Clock,
  Calendar,
  ArrowUpRight,
  Warehouse,
  Store,
  DollarSign,
  Edit2,
  Trash2,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { useAppStore } from "./lib/appStore";
import {
  ACCESS_TOKEN_KEY,
  API_BASE,
  AUTH_SESSION_EXPIRED_EVENT,
  AUTH_TOKEN_REFRESHED_EVENT,
  apiRequest,
  clearStoredAuthTokens,
  printReceipt,
  storeAuthTokens,
} from "./lib/api";
import { canAccessNav, getRoleFromToken } from "./lib/auth";
import { visibleKdsOrders } from "./lib/kds";
import { unseenNewDeliveryOrders } from "./lib/onlineDelivery";
import type { AppRole, NavSection } from "./lib/auth";
import {
  canRefundOrder,
  canSubmitPayrollPayout,
  didRefundStateAdvance,
  gatewayPaymentDisplayStatus,
  gatewayPayoutDisplayStatus,
  refundablePayments,
} from "./lib/paymentStatus";
import {
  isRazorpayProviderSnapshot,
  resolveRazorpayDashboardMetrics,
  type RazorpayProviderSnapshot,
} from "./lib/razorpayDashboard";
import { qrOrderUrl } from "./lib/qr";
import {
  childPathForSection,
  isPublicAuthPath,
  pathForSection,
  resolveAppRoute,
  type AppRouteSection,
} from "./lib/uiRoutes";
import AdminPage, { type AdminTab } from "./pages/AdminPage";
import "./styles.css";

// ─────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────
type Category = { id: string; name: string; };
  type Product = {
  id: string;
  category_id?: string;
  name: string;
  price: string;
  tax_rate: string;
  available: boolean;
  variants: any[];
  addons: any[];
};

type TableState = {
  id: string;
  name: string;
  capacity: number;
  status: "available" | "occupied" | "reserved" | "cleaning" | "out_of_service";
  floor_area: string;
  merged_with?: string | null;
  order_id?: string | null;
};

type BranchState = {
  id: string;
  name: string;
  address?: string;
  phone?: string;
  status: string;
};

type AppUser = { id: string; name: string; email: string; phone?: string; role: AppRole; branch_id?: string; status: string; locked?: boolean; permissions?: string[]; };

type OrderItem = {
  product_id: string;
  name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  variant_name?: string | null;
  addons?: any[];
};

type BackendOrder = {
  id: string;
  table_id?: string | null;
  order_type: string;
  status: string;
  kds_status: string;
  subtotal: string;
  tax_amount: string;
  discount_amount: string;
  total: string;
  payment_status: string;
  items: OrderItem[];
  payments?: Array<{
    id: string;
    method: string;
    amount: string;
    status?: string | null;
    reference?: string | null;
    provider?: string | null;
    gateway_order_id?: string | null;
    gateway_payment_id?: string | null;
  }>;
  created_at?: string;
};

type OnlineDeliveryOrder = {
  id: string;
  branch_id: string;
  order_id?: string | null;
  provider: "swiggy" | "zomato" | "own" | "other";
  external_order_id: string;
  status: "new" | "needs_mapping" | "accepted" | "rejected" | "cancelled" | "ready" | "picked_up" | "delivered";
  customer_name: string;
  customer_phone?: string | null;
  delivery_address: string;
  rider_name?: string | null;
  rider_phone?: string | null;
  payment_mode: string;
  payment_status: string;
  subtotal: string;
  total: string;
  commission_amount: string;
  items: Array<{ product_id: string; name: string; quantity: number; unit_price?: string; line_total?: string; notes?: string | null; unmapped?: boolean }>;
  notes?: string | null;
  created_at?: string;
};

type DashboardMetrics = {
  today_sales: string;
  today_collection?: string;
  revenue: string;
  last_month_sales?: string;
  today_orders?: number;
  total_orders?: number;
  completed_orders?: number;
  pending_orders?: number;
  active_orders: number;
  active_tables: number;
  available_tables?: number;
  occupied_tables?: number;
  reserved_tables?: number;
  cleaning_tables?: number;
  low_stock_alerts: number;
  total_stock_items?: number;
  attendance_today?: number;
  purchase_orders_today?: number;
  purchase_orders_month?: number;
  pending_discount_requests?: number;
  pending_payroll_count?: number;
  top_selling_products: Array<{ name: string; quantity: number }>;
  active_staff?: number;
  active_staff_details?: Array<{ id: string; employee_id: string; name: string; role: string; check_in: string; check_in_time: string }>;
  pending_payments?: number;
    notifications?: any[];
  sales_charts?: {
    daily: number[];
    daily_labels?: string[];
    monthly: number[];
    last_month_sales?: number;
  };
  weekly_attendance?: {
    labels: string[];
    users: Array<{
      id: string;
      name: string;
      role: string;
      days: Array<"present" | "active" | "absent">;
      present_days: number;
      active_today: boolean;
    }>;
  };
  monthly_attendance?: {
    month: string;
    users: Array<{
      id: string;
      name: string;
      role: string;
      present_days: number;
      absent_days: number;
      total_days: number;
      attendance_percent: number;
      active_today: boolean;
    }>;
  };
  today_order_types?: Record<"dine_in" | "takeaway" | "delivery", { orders: number; sales: string }>;
  order_status_counts?: Record<string, number>;
  payment_method_totals?: Record<string, string>;
  payment_gateway_totals?: Record<string, string>;
  payout_method_totals?: Record<string, string>;
  payout_gateway_totals?: Record<string, string>;
};

type InventoryItem = {
  id: string;
  name: string;
  unit: string;
  quantity: string;
  low_stock_threshold: string;
  low_stock: boolean;
};

type PurchaseOrder = {
  id: string;
  po_number: string;
  supplier_id?: string | null;
  status: string;
  total_amount: string;
  items: Array<{ name: string; quantity: string; cost_price: string }>;
};

type Employee = {
  id: string;
  user_id?: string | null;
  employee_id: string;
  name: string;
  email: string;
  phone: string;
  role: string;
  joining_date: string;
  active: boolean;
};

type AttendanceLog = {
  id: string;
  name: string;
  employee_id: string;
  check_in: string;
  check_out?: string | null;
  shift_type: string;
  overtime_minutes: number;
  overtime_status?: "none" | "pending" | "approved" | "rejected";
};

type CurrentAttendanceRow = {
  id: string;
  employee_id: string;
  name: string;
  role: string;
  attendance_id?: string | null;
  check_in?: string | null;
  check_out?: string | null;
  status: "not_started" | "clocked_in" | "clocked_out";
};

type PayrollLog = {
  id: string;
  name: string;
  employee_id: string;
  employee_record_id?: string;
  period: string;
  day_salary?: string;
  base_salary: string;
  net_salary: string;
  incentives?: string;
  present_days?: number;
  approved_leave_days?: number;
  payable_days?: number;
  absent_days?: number;
  status: string;
  payment_mode?: PayrollPaymentMode;
  payment_reference?: string | null;
  payout_provider?: string | null;
  payout_id?: string | null;
  payout_status?: string | null;
};

type PayrollPaymentMode = "cash" | "bank" | "upi" | "payroll";

type IncentiveLog = {
  id: string;
  name: string;
  employee_id: string;
  employee_record_id: string;
  sales_amount: string;
  incentive_amount: string;
  date: string;
};

type LeaveRequest = {
  id: string;
  employee_id: string;
  name: string;
  type: "sick" | "vacation" | "unpaid" | "other";
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  applied_on: string;
};

type ToastItem = {
  id: string;
  message: string;
  type: "success" | "error" | "info" | "warning";
};

type SystemStatus = {
  api: "connected" | "disconnected" | "checking";
  db: "connected" | "disconnected" | "checking";
};

type IntegrationServiceStatus = {
  configured: boolean;
  missing: string[];
  provider?: string;
  webhook_url?: string;
};

type IntegrationStatus = {
  password_reset_mail: IntegrationServiceStatus;
  razorpay: IntegrationServiceStatus;
  razorpayx: IntegrationServiceStatus;
  swiggy: IntegrationServiceStatus;
  zomato: IntegrationServiceStatus;
};

type DiscountRequest = {
  id: string;
  order_id: string;
  requested_by_id: string;
  requested_by_name?: string;
  amount_or_percentage: number;
  is_percentage: boolean;
  bill_total?: string;
  discount_amount?: string;
  proposed_total?: string;
  status?: string;
  created_at: string;
};

type ProductWizardDraft = {
  category_id?: string;
  name: string;
  price: string;
  tax_rate: string;
  sku: string;
  description: string;
  image_url: string;
  available: boolean;
};

type SettingsGST = {
  receipt_name: string;
  gst_number: string;
  food_gst_rate: number;
  beverage_gst_rate: number;
  upi_id: string;
  upi_qr_url: string;
  receipt_footer: string;
};

type LoginSession = {
  id: string;
  user_id: string;
  user_agent: string;
  created_at: string;
  revoked: boolean;
};

// ─────────────────────────────────────────────────────────
// Nav config
// ─────────────────────────────────────────────────────────
const nav: Array<{ label: AppRouteSection; icon: typeof LayoutDashboard }> = [
  { label: "Dashboard",        icon: LayoutDashboard },
  { label: "POS Billing",      icon: Receipt },
  { label: "Orders",           icon: ClipboardList },
  { label: "Online Delivery",  icon: Truck },
  { label: "KDS",              icon: ChefHat },
  { label: "Table Management", icon: Table2 },
  { label: "Menu",             icon: Utensils },
  { label: "Inventory",        icon: Package },
  { label: "Staff",            icon: Users },
  { label: "Reports",          icon: BarChart3 },
  { label: "Razorpay Dashboard", icon: CreditCard },
  { label: "Settings",         icon: Settings },
  { label: "Admin Panel",      icon: ShieldCheck },
  { label: "Platform",         icon: Warehouse },
];

function statusLabel(status: string) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableApiError(error: unknown, fallback: string) {
  if (!(error instanceof Error) || !error.message) return fallback;

  try {
    const payload = JSON.parse(error.message) as {
      message?: unknown;
      detail?: unknown;
      errors?: Array<{ detail?: unknown; message?: unknown }>;
    };
    const detail = payload.errors?.[0]?.detail ?? payload.errors?.[0]?.message ?? payload.message ?? payload.detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (Array.isArray(detail)) {
      const message = detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) return String((item as { msg: unknown }).msg);
          return "";
        })
        .filter(Boolean)
        .join(", ");
      if (message) return message;
    }
  } catch {
    // Plain text error messages are handled below.
  }

  return error.message.length <= 220 ? error.message : fallback;
}

function moneyNumber(value?: string | number | null) {
  const amount = typeof value === "number" ? value : parseFloat(value || "0");
  return Number.isFinite(amount) ? amount : 0;
}

function formatMoney(value: string | number | null | undefined) {
  return `Rs. ${moneyNumber(value).toFixed(2)}`;
}

function getInitials(name: string) {
  return name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
}

function elapsed(createdAt?: string): string {
  if (!createdAt) return "—";
  const diff = Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

// ─────────────────────────────────────────────────────────
// Page transition variants
// ─────────────────────────────────────────────────────────
const pageVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.18 } },
};

// ─────────────────────────────────────────────────────────
// Toast Component
// ─────────────────────────────────────────────────────────
function ToastContainer({ toasts, dismiss }: { toasts: ToastItem[]; dismiss: (id: string) => void }) {
  const icons = { success: CheckCircle2, error: AlertTriangle, info: Info, warning: AlertTriangle };
  const colors = { success: "#4ade80", error: "#f87171", info: "#38bdf8", warning: "#fbbf24" };
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 10 }}>
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = icons[t.type];
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 60, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 60, scale: 0.9 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "13px 18px", borderRadius: 12, maxWidth: 360,
                background: "rgba(15,23,42,0.95)",
                border: `1px solid ${colors[t.type]}30`,
                boxShadow: `0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)`,
                backdropFilter: "blur(16px)", color: "#f1f5f9", fontSize: "0.875rem", fontWeight: 500,
              }}
            >
              <Icon size={18} color={colors[t.type]} />
              <span style={{ flex: 1 }}>{t.message}</span>
              <button onClick={() => dismiss(t.id)} style={{ background: "transparent", border: 0, color: "var(--text-muted)", cursor: "pointer", padding: 2 }}>
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Live Clock
// ─────────────────────────────────────────────────────────
function LiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 14px", borderRadius: 8, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text-soft)", fontSize: "0.8rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
      <Clock size={14} />
      <span>{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
      <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{now.toLocaleDateString([], { day: "2-digit", month: "short" })}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// KDS Elapsed Timer per ticket
// ─────────────────────────────────────────────────────────
function ElapsedTimer({ createdAt }: { createdAt?: string }) {
  const [, forceUpdate] = useState(0);
  useEffect(() => {
    const t = setInterval(() => forceUpdate((n) => n + 1), 10000);
    return () => clearInterval(t);
  }, []);
  const minutes = createdAt ? Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000) : 0;
  const isUrgent = minutes >= 20;
  return (
    <span style={{ fontSize: "0.72rem", fontWeight: 600, color: isUrgent ? "var(--danger)" : "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
      <Clock size={11} />
      {createdAt ? `${minutes}m ago` : "Just now"}
      {isUrgent && " ⚠"}
    </span>
  );
}

// ─────────────────────────────────────────────────────────
// Stock Progress Bar
// ─────────────────────────────────────────────────────────
function StockBar({ current, max, unit }: { current: number; max: number; unit: string }) {
  const pct = Math.min((current / max) * 100, 100);
  const color = pct < 30 ? "var(--danger)" : pct < 60 ? "var(--amber)" : "var(--success)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ color, fontWeight: 700, fontSize: "0.875rem" }}>{current} {unit}</span>
        <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: 5, borderRadius: 999, background: "var(--border)", overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          style={{ height: "100%", background: color, borderRadius: 999 }}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Toggle Switch
// ─────────────────────────────────────────────────────────
function ToggleSwitch({ checked, onChange, id }: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <label htmlFor={id} style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
      <div
        onClick={() => onChange(!checked)}
        style={{
          width: 44, height: 24, borderRadius: 999, position: "relative", cursor: "pointer",
          background: checked ? "var(--accent)" : "var(--border)",
          transition: "background 0.2s ease",
          boxShadow: checked ? "0 0 12px var(--accent-glow)" : "none",
        }}
      >
        <motion.div
          animate={{ x: checked ? 22 : 2 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          style={{ width: 20, height: 20, borderRadius: "50%", background: "#fff", position: "absolute", top: 2, boxShadow: "0 1px 4px rgba(0,0,0,0.3)" }}
        />
      </div>
    </label>
  );
}

// ─────────────────────────────────────────────────────────
// Avatar Circle
// ─────────────────────────────────────────────────────────
const AVATAR_COLORS = ["#0d9488","#0e7490","#7c3aed","#db2777","#d97706","#16a34a","#2563eb","#dc2626"];
function AvatarCircle({ name, size = 36 }: { name: string; size?: number }) {
  const color = AVATAR_COLORS[name.charCodeAt(0) % AVATAR_COLORS.length];
  return (
    <div style={{ width: size, height: size, minWidth: size, borderRadius: "50%", background: color + "22", border: `2px solid ${color}40`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.35, fontWeight: 700, color, letterSpacing: -0.5 }}>
      {getInitials(name)}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Status Badge
// ─────────────────────────────────────────────────────────
function StatusBadge({ value, map }: { value: string; map: Record<string, { label: string; color: string; bg: string }> }) {
  const cfg = map[value] || { label: value, color: "var(--text-muted)", bg: "var(--surface-soft)" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "3px 10px", borderRadius: 999, fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", background: cfg.bg, color: cfg.color }}>
      {cfg.label}
    </span>
  );
}

const kdsStatusMap: Record<string, any> = {
  new: { label: "New", color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  accepted: { label: "Accepted", color: "#2dd4bf", bg: "rgba(45,212,191,0.12)" },
  preparing: { label: "Preparing", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  ready: { label: "Ready", color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  served: { label: "Served", color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
};
const payStatusMap: Record<string, any> = {
  paid: { label: "Paid", color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  unpaid: { label: "Unpaid", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
  partial: { label: "Partial", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  partially_refunded: { label: "Partially Refunded", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  refund_pending: { label: "Refund Pending", color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  refunded: { label: "Refunded", color: "#94a3b8", bg: "rgba(148,163,184,0.12)" },
};
const orderStatusMap: Record<string, any> = {
  active: { label: "Active", color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  held: { label: "On Hold", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  completed: { label: "Completed", color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  cancelled: { label: "Cancelled", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
  void: { label: "Void", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
};

const DEFAULT_TABLE_FLOORS = ["Ground Floor", "First Floor", "Rooftop", "VIP Area"];
const payrollPaymentLabels: Record<PayrollPaymentMode, string> = {
  cash: "Cash",
  bank: "Bank Transfer",
  upi: "UPI",
  payroll: "Payroll Account",
};

type RazorpayCheckoutResponse = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};

type RazorpayCheckoutOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpayCheckoutResponse) => void;
  prefill?: { email?: string };
  theme?: { color?: string };
  modal?: { ondismiss?: () => void };
};

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayCheckoutOptions) => { open: () => void };
  }
}

// ─────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────
function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const resolvedRoute = useMemo(() => resolveAppRoute(location.pathname), [location.pathname]);
  const activeNav = resolvedRoute?.section || "Dashboard";
  const { theme, toggleTheme } = useAppStore();
  const [token, setToken] = useState(localStorage.getItem(ACCESS_TOKEN_KEY) || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotMessage, setForgotMessage] = useState("");
  const [forgotError, setForgotError] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [resetConfirm, setResetConfirm] = useState("");
  const [resetLoading, setResetLoading] = useState(false);
  const setActiveNav = useCallback((section: AppRouteSection) => {
    navigate(pathForSection(section));
  }, [navigate]);
  const setActiveChildRoute = useCallback((section: AppRouteSection, child: string) => {
    const path = childPathForSection(section, child);
    if (path) navigate(path);
  }, [navigate]);

  const [branch, setBranch] = useState<BranchState | null>(null);
  const [branches, setBranches] = useState<BranchState[]>([]);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tables, setTables] = useState<TableState[]>([]);
  const [orders, setOrders] = useState<BackendOrder[]>([]);
  const [onlineDeliveryOrders, setOnlineDeliveryOrders] = useState<OnlineDeliveryOrder[]>([]);
  const [onlineDeliveryTab, setOnlineDeliveryTab] = useState<"new" | "needs_mapping" | "accepted" | "ready" | "picked_up" | "delivered" | "all">("new");
  const [deliveryDraft, setDeliveryDraft] = useState({
    provider: "swiggy" as OnlineDeliveryOrder["provider"],
    external_order_id: "",
    customer_name: "Online Customer",
    customer_phone: "",
    delivery_address: "",
    payment_mode: "prepaid",
    payment_status: "paid",
    commission_amount: "0.00",
    product_id: "",
    quantity: 1,
    notes: "",
  });

  // Inventory
  const [inventoryItems, setInventoryItems] = useState<InventoryItem[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);

  // HR
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [attendance, setAttendance] = useState<AttendanceLog[]>([]);
  const [currentAttendance, setCurrentAttendance] = useState<CurrentAttendanceRow[]>([]);
  const [payrolls, setPayrolls] = useState<PayrollLog[]>([]);
  const [incentives, setIncentives] = useState<IncentiveLog[]>([]);
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequest[]>([]);
  const [leaveFilter, setLeaveFilter] = useState("all");
  const [showLeaveWizard, setShowLeaveWizard] = useState(false);
  const [leaveWizard, setLeaveWizard] = useState({ employee_id: "", type: "sick" as "sick" | "vacation" | "unpaid" | "other", start_date: "", end_date: "", reason: "" });
  const [showEditLeaveWizard, setShowEditLeaveWizard] = useState(false);
  const [editLeaveWizard, setEditLeaveWizard] = useState({ id: "", type: "sick" as "sick" | "vacation" | "unpaid" | "other", start_date: "", end_date: "", reason: "", status: "pending" as "pending" | "approved" | "rejected" });

  const [loginSessions, setLoginSessions] = useState<LoginSession[]>([]);
  const [discountRequests, setDiscountRequests] = useState<DiscountRequest[]>([]);
  const [staffTab, setStaffTab] = useState<"directory" | "attendance" | "payroll" | "incentives" | "leaves">("directory");
  const [attendanceFilters, setAttendanceFilters] = useState({ search: "", date: "", overtime: "" });
  const [taxSettings, setTaxSettings] = useState<SettingsGST>({
    receipt_name: "",
    gst_number: "",
    food_gst_rate: 5,
    beverage_gst_rate: 18,
    upi_id: "",
    upi_qr_url: "",
    receipt_footer: "Thank you! Visit again.",
  });
  const [showProductWizard, setShowProductWizard] = useState(false);
  const [productWizard, setProductWizard] = useState<ProductWizardDraft>({
    category_id: "",
    name: "",
    price: "",
    tax_rate: "5",
    sku: "",
    description: "",
    image_url: "",
    available: true,
  });

  const [showEmployeeWizard, setShowEmployeeWizard] = useState(false);
  const [employeeWizard, setEmployeeWizard] = useState({ id: "", name: "", employee_id: "", email: "", phone: "", role: "waiter", base_salary: "500", password: "" });

  const [showIncentiveWizard, setShowIncentiveWizard] = useState(false);
  const [incentiveWizard, setIncentiveWizard] = useState({ employee_id: "", amount: "", id: "" });

  const [showAttendanceWizard, setShowAttendanceWizard] = useState(false);
  const [attendanceWizard, setAttendanceWizard] = useState({ employee_id: "", type: "in", hours: 9 });

  const [showOvertimeWizard, setShowOvertimeWizard] = useState(false);
  const [overtimeWizard, setOvertimeWizard] = useState({ attendance_id: "", minutes: 30 });

  const [showEditAttendanceWizard, setShowEditAttendanceWizard] = useState(false);
  const [editAttendanceWizard, setEditAttendanceWizard] = useState({ id: "", date: "", checkIn: "", checkOut: "" });

  const [showTableWizard, setShowTableWizard] = useState(false);
  const [tableWizard, setTableWizard] = useState({ name: "", capacity: 4, floor_area: "Ground Floor" });
  const [showEditTableWizard, setShowEditTableWizard] = useState(false);
  const [editTableWizard, setEditTableWizard] = useState({
    id: "",
    name: "",
    capacity: 4,
    floor_area: "Ground Floor",
    status: "available" as TableState["status"],
  });

  const [showPayrollWizard, setShowPayrollWizard] = useState(false);
  const [payrollWizard, setPayrollWizard] = useState({ employee_id: "", id: "", daily_wage: 400, days_present: 30, base: 12000, incentives: 0 });
  const [showPayoutWizard, setShowPayoutWizard] = useState(false);
  const [payoutWizard, setPayoutWizard] = useState({
    payroll_id: "",
    name: "",
    net_salary: "0.00",
    payment_mode: "cash" as PayrollPaymentMode,
    payment_reference: "",
    use_gateway: false,
    recipient_upi: "",
  });

  // Security
  const [security, setSecurity] = useState({ password_min_length: 8, session_timeout_minutes: 30, multi_device_login: true, two_factor_auth: false, login_attempts_threshold: 5 });
  const [settingsTab, setSettingsTab] = useState<"security" | "profile" | "integrations" | "appearance">("security");

  // Monitoring
  const [inactiveAlerts, setInactiveAlerts] = useState<any[]>([]);
  const [platformMetrics, setPlatformMetrics] = useState<any>(null);
  const [tenantMetrics, setTenantMetrics] = useState<any>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ api: "checking", db: "checking" });
  const [integrationStatus, setIntegrationStatus] = useState<IntegrationStatus | null>(null);
  const [resetMailTesting, setResetMailTesting] = useState(false);

  const [metrics, setMetrics] = useState<DashboardMetrics>({
    today_sales: "0.00", today_collection: "0.00", revenue: "0.00", last_month_sales: "0.00",
    today_orders: 0, total_orders: 0, completed_orders: 0, pending_orders: 0, active_orders: 0, active_tables: 0,
    available_tables: 0, occupied_tables: 0, reserved_tables: 0, cleaning_tables: 0,
    low_stock_alerts: 0, total_stock_items: 0, attendance_today: 0, purchase_orders_today: 0, purchase_orders_month: 0,
    pending_discount_requests: 0, pending_payroll_count: 0, top_selling_products: [], active_staff: 0, pending_payments: 0,
    active_staff_details: [],
    sales_charts: { daily: [], daily_labels: [], monthly: [], last_month_sales: 0 },
    weekly_attendance: { labels: [], users: [] },
    monthly_attendance: { month: "", users: [] },
    today_order_types: {
      dine_in: { orders: 0, sales: "0.00" },
      takeaway: { orders: 0, sales: "0.00" },
      delivery: { orders: 0, sales: "0.00" },
    },
    order_status_counts: {},
    payment_method_totals: {},
    payment_gateway_totals: {},
    payout_method_totals: {},
    payout_gateway_totals: {},
  });
  const [razorpayRefreshing, setRazorpayRefreshing] = useState(false);
  const [razorpayLastRefresh, setRazorpayLastRefresh] = useState("");
  const [razorpayProviderSnapshot, setRazorpayProviderSnapshot] = useState<RazorpayProviderSnapshot | null>(null);
  const [razorpayProviderError, setRazorpayProviderError] = useState("");

  // Table management
  const [selectedFloor, setSelectedFloor] = useState("Ground Floor");
  const [tableFloors, setTableFloors] = useState<string[]>(DEFAULT_TABLE_FLOORS);
  const [newFloorName, setNewFloorName] = useState("");
  const [editingFloor, setEditingFloor] = useState("");
  const [editFloorName, setEditFloorName] = useState("");
  const [mergeT1, setMergeT1] = useState("");
  const [mergeT2, setMergeT2] = useState("");

  const floorOptions = useMemo(() => {
    const seen = new Set<string>();
    const floors: string[] = [];
    const addFloor = (value?: string) => {
      const floor = (value || "").trim().replace(/\s+/g, " ");
      const key = floor.toLowerCase();
      if (floor && !seen.has(key)) {
        seen.add(key);
        floors.push(floor);
      }
    };
    DEFAULT_TABLE_FLOORS.forEach(addFloor);
    tableFloors.forEach(addFloor);
    tables.forEach((table) => addFloor(table.floor_area));
    addFloor(selectedFloor);
    return floors;
  }, [selectedFloor, tableFloors, tables]);

  // POS
  const [orderType, setOrderType] = useState<"dine_in" | "takeaway" | "delivery">("dine_in");
  const [selectedTable, setSelectedTable] = useState("");
  const [cart, setCart] = useState<Array<{ product: Product; quantity: number }>>([]);
  const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean, title: string, message: string, onConfirm: () => void }>({ isOpen: false, title: "", message: "", onConfirm: () => {} });
  const [discountModal, setDiscountModal] = useState<{ isOpen: boolean, amount: string, type: "percentage" | "fixed" }>({ isOpen: false, amount: "", type: "percentage" });
  const [search, setSearch] = useState("");
  const [posCategory, setPosCategory] = useState("All");
  const [ordersTab, setOrdersTab] = useState<"dine_in" | "takeaway" | "delivery">("dine_in");
  const [orderFilters, setOrderFilters] = useState({
    orderId: "",
    type: "",
    tableNo: "",
    items: "",
    total: "",
    kds: "",
    payment: "",
    status: "",
  });
  const [refundWizard, setRefundWizard] = useState<{
    order: BackendOrder | null;
    payment_id: string;
    amount: string;
    reason: string;
  }>({ order: null, payment_id: "", amount: "", reason: "" });
  const [refundSubmitting, setRefundSubmitting] = useState(false);

  // Toast system
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastTimer = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const discountRequestIds = useRef<Set<string>>(new Set());
  const discountRequestsLoaded = useRef(false);
  const deliveryOrderIds = useRef<Set<string>>(new Set());
  const deliveryOrdersLoaded = useRef(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const showToast = useCallback((message: string, type: ToastItem["type"] = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, message, type }]);
    toastTimer.current[id] = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      delete toastTimer.current[id];
    }, 3500);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    if (toastTimer.current[id]) { clearTimeout(toastTimer.current[id]); delete toastTimer.current[id]; }
  }, []);

  useEffect(() => {
    checkSystemStatus();
    const interval = window.setInterval(checkSystemStatus, 30000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleTokenRefreshed = (event: Event) => {
      setToken((event as CustomEvent<string>).detail);
    };
    const handleSessionExpired = () => {
      clearStoredAuthTokens();
      setToken("");
      setBranch(null);
      navigate("/login", { replace: true });
    };
    window.addEventListener(AUTH_TOKEN_REFRESHED_EVENT, handleTokenRefreshed);
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => {
      window.removeEventListener(AUTH_TOKEN_REFRESHED_EVENT, handleTokenRefreshed);
      window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    };
  }, [navigate]);

  useEffect(() => {
    const pathname = location.pathname.toLowerCase().replace(/\/+$/, "") || "/";
    if (pathname === "/") {
      navigate(token ? "/dashboard" : "/login", { replace: true });
      return;
    }
    if (pathname === "/login" && token) {
      navigate("/dashboard", { replace: true });
      return;
    }
    if (!resolvedRoute && !isPublicAuthPath(pathname)) {
      navigate(token ? "/dashboard" : "/login", { replace: true });
      return;
    }
    if (resolvedRoute && resolvedRoute.canonicalPath !== pathname) {
      navigate(`${resolvedRoute.canonicalPath}${location.search}`, { replace: true });
    }
  }, [location.pathname, location.search, navigate, resolvedRoute, token]);

  useEffect(() => {
    const pathname = location.pathname.toLowerCase().replace(/\/+$/, "");
    const tokenFromUrl = pathname === "/reset-password"
      ? new URLSearchParams(location.search).get("token")
      : null;
    if (pathname === "/forgot-password") {
      setResetToken("");
      setForgotError("");
      setForgotMessage("");
      setShowPasswordReset(true);
      return;
    }
    if (pathname === "/reset-password") {
      setShowPasswordReset(true);
      if (!tokenFromUrl) {
        setForgotError("Reset link is missing its token.");
        return;
      }
      if (token) {
        clearStoredAuthTokens();
        setToken("");
        setBranch(null);
      }
      setResetToken(tokenFromUrl);
      return;
    }
    setShowPasswordReset(false);
    setResetToken("");
    setForgotError("");
    setForgotMessage("");
  }, [location.pathname, location.search, token]);

  useEffect(() => {
    if (activeNav === "Online Delivery") {
      setOnlineDeliveryTab((resolvedRoute?.child as typeof onlineDeliveryTab) || "new");
    }
    if (activeNav === "Staff") {
      setStaffTab((resolvedRoute?.child as typeof staffTab) || "directory");
    }
    if (activeNav === "Settings") {
      setSettingsTab((resolvedRoute?.child as typeof settingsTab) || "security");
    }
  }, [activeNav, resolvedRoute?.child]);

  useEffect(() => { if (token) initData(); }, [token]);

  useEffect(() => {
    if (!token || !branch?.id || activeNav !== "Orders") return;
    const interval = window.setInterval(() => {
      refreshOrders(branch.id);
      refreshMetrics(branch.id);
    }, 5000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id, activeNav]);

  useEffect(() => {
    if (!token || !branch?.id || activeNav !== "KDS") return;
    refreshKdsOrders(branch.id);
    const interval = window.setInterval(() => refreshKdsOrders(branch.id), 5000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id, activeNav]);

  useEffect(() => {
    if (!token || !branch?.id || activeNav !== "Online Delivery") return;
    const refreshDelivery = () => {
      refreshOrders(branch.id);
      refreshIntegrationStatus(branch.id);
    };
    refreshDelivery();
    const interval = window.setInterval(refreshDelivery, 5000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id, activeNav]);

  useEffect(() => {
    if (!token || !["Razorpay Dashboard", "Settings"].includes(activeNav)) return;
    refreshIntegrationStatus(branch?.id);
  }, [token, activeNav, branch?.id]);

  useEffect(() => {
    setRazorpayProviderSnapshot(null);
    setRazorpayProviderError("");
    setRazorpayLastRefresh("");
  }, [branch?.id]);

  useEffect(() => {
    if (!token || !branch?.id || activeNav !== "Dashboard") return;
    const refreshDashboard = () => refreshMetrics(branch.id);
    refreshDashboard();
    const interval = window.setInterval(refreshDashboard, 5000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id, activeNav]);

  useEffect(() => {
    if (!token || !branch?.id) return;
    deliveryOrderIds.current = new Set();
    deliveryOrdersLoaded.current = false;
    discountRequestIds.current = new Set();
    discountRequestsLoaded.current = false;
    const refreshAlerts = () => {
      refreshOnlineDelivery(branch.id, false);
      refreshDiscountRequests(branch.id);
    };
    refreshAlerts();
    const interval = window.setInterval(refreshAlerts, 5000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id]);

  // ── Auth ───────────────────────────────────────────────
  useEffect(() => {
    if (!token || !branch?.id || activeNav !== "Razorpay Dashboard") return;
    refreshRazorpayDashboard();
    const interval = window.setInterval(() => refreshRazorpayDashboard(), 30000);
    return () => window.clearInterval(interval);
  }, [token, branch?.id, activeNav]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setAuthError("");
    setAuthLoading(true);
    try {
      const res = await apiRequest<{ success: boolean; data: any; message: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (res.success) {
        storeAuthTokens(res.data.access_token, res.data.refresh_token);
        setToken(res.data.access_token);
        if (isPublicAuthPath(location.pathname)) {
          navigate("/dashboard", { replace: true });
        }
      } else {
        setAuthError(res.message || "Invalid credentials");
      }
    } catch {
      setAuthError("Invalid credentials. Please try again.");
    } finally {
      setAuthLoading(false);
    }
  }

  function openPasswordReset() {
    setForgotEmail(email);
    setForgotMessage("");
    setForgotError("");
    setShowPasswordReset(true);
    navigate("/forgot-password");
  }

  function closePasswordReset() {
    setShowPasswordReset(false);
    setForgotMessage("");
    setForgotError("");
    setResetPassword("");
    setResetConfirm("");
    if (isPublicAuthPath(location.pathname) && location.pathname !== "/login") {
      navigate("/login", { replace: true });
    }
  }

  async function handleForgotPassword(e: React.FormEvent) {
    e.preventDefault();
    const targetEmail = forgotEmail.trim();
    if (!targetEmail) {
      setForgotError("Enter your account email.");
      return;
    }
    setForgotLoading(true);
    setForgotError("");
    setForgotMessage("");
    try {
      const res = await apiRequest<{ success: boolean; data?: { email_delivery?: string }; message: string }>("/api/v1/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email: targetEmail }),
      });
      if (res.data?.email_delivery === "sent") {
        setForgotMessage("Password reset link sent. Check your email.");
      } else if (res.data?.email_delivery === "failed") {
        setForgotError("Reset mail failed. Check Gmail app password and SMTP settings.");
      } else if (res.data?.email_delivery === "not_configured") {
        setForgotError("Reset mail is not configured on the backend.");
      } else {
        setForgotMessage("If this email exists, a reset link will be sent.");
      }
    } catch {
      setForgotError("Unable to send reset link right now.");
    } finally {
      setForgotLoading(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (resetPassword.length < 8) {
      setForgotError("Password must be at least 8 characters.");
      return;
    }
    if (resetPassword !== resetConfirm) {
      setForgotError("Passwords do not match.");
      return;
    }
    setResetLoading(true);
    setForgotError("");
    setForgotMessage("");
    try {
      await apiRequest<{ success: boolean; data: any; message: string }>("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({ token: resetToken, new_password: resetPassword }),
      });
      setForgotMessage("Password updated. Sign in with your new password.");
      setResetToken("");
      setResetPassword("");
      setResetConfirm("");
      navigate("/login", { replace: true });
    } catch {
      setForgotError("Reset link is invalid or expired.");
    } finally {
      setResetLoading(false);
    }
  }

  function handleLogout() {
    clearStoredAuthTokens();
    setToken("");
    setBranch(null);
    navigate("/login", { replace: true });
  }

  // ── Data loading ───────────────────────────────────────
  async function checkSystemStatus() {
    try {
      const res = await apiRequest<{ success: boolean; data: { status: string; database: string } }>("/api/v1/ready");
      setSystemStatus({
        api: res.success ? "connected" : "disconnected",
        db: res.data?.database === "ok" ? "connected" : "disconnected",
      });
    } catch {
      setSystemStatus({ api: "disconnected", db: "disconnected" });
    }
  }

  async function refreshIntegrationStatus(branchId = branch?.id) {
    if (!token) return;
    try {
      const suffix = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : "";
      const res = await apiRequest<{ success: boolean; data: IntegrationStatus }>(`/api/v1/integrations/status${suffix}`, { token });
      if (res.success) setIntegrationStatus(res.data);
    } catch {
      setIntegrationStatus(null);
    }
  }

  async function testPasswordResetMail() {
    if (!token || resetMailTesting) return;
    setResetMailTesting(true);
    try {
      const response = await apiRequest<{
        success: boolean;
        data: { email_delivery: string; recipient: string };
      }>("/api/v1/integrations/password-reset-mail/test", {
        method: "POST",
        token,
      });
      showToast(`Test email sent to ${response.data.recipient}`, "success");
    } catch (error) {
      showToast(readableApiError(error, "Password reset mail test failed"), "error");
    } finally {
      setResetMailTesting(false);
    }
  }

  async function initData() {
    try {
      const branchRes = await apiRequest<{ success: boolean; data: { items: BranchState[] } }>("/api/v1/branches", { token });
      const selectedBranch = branchRes.data.items[0];
      setBranches(branchRes.data.items);
      if (!selectedBranch) return;
      setBranch(selectedBranch);

      const [productsRes, catRes, tablesRes, floorsRes, empRes, attRes, currentAttRes, payRes, incRes, ordersRes, usersRes, invRes, poRes, sessionsRes, discountsRes, leaveRes, onlineDeliveryRes, taxRes] = await Promise.allSettled([
        apiRequest<{ success: boolean; data: { items: any[] } }>(`/api/v1/products?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: Category[] } }>(`/api/v1/categories?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: TableState[] } }>(`/api/v1/tables?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: string[] } }>(`/api/v1/table-floors?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: Employee[] } }>(`/api/v1/employees?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: AttendanceLog[] } }>(`/api/v1/reports/attendance?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: CurrentAttendanceRow[] } }>(`/api/v1/reports/attendance/current?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: PayrollLog[] } }>(`/api/v1/reports/payroll?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: IncentiveLog[] } }>(`/api/v1/reports/incentives?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: BackendOrder[] } }>(`/api/v1/orders?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: AppUser[] } }>("/api/v1/users", { token }),
        apiRequest<{ success: boolean; data: { items: InventoryItem[] } }>(`/api/v1/inventory/items?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: PurchaseOrder[] } }>(`/api/v1/inventory/purchase-orders?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: LoginSession[] } }>(`/api/v1/staff/login-sessions?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: DiscountRequest[] } }>(`/api/v1/discounts/requests/pending?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: LeaveRequest[] } }>(`/api/v1/leaves?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: OnlineDeliveryOrder[] } }>(`/api/v1/online-delivery/orders?branch_id=${selectedBranch.id}`, { token }),
        apiRequest<{ success: boolean; data: SettingsGST }>(`/api/v1/settings/tax?branch_id=${selectedBranch.id}`, { token }),
      ]);

      if (productsRes.status === "fulfilled") setProducts(productsRes.value.data.items);
        if (catRes.status === 'fulfilled') setCategories(catRes.value.data.items);
      if (tablesRes.status === "fulfilled") { setTables(tablesRes.value.data.items); if (tablesRes.value.data.items.length > 0) setSelectedTable(tablesRes.value.data.items[0].id); }
      if (floorsRes.status === "fulfilled") setTableFloors(floorsRes.value.data.items);
      if (empRes.status === "fulfilled") setEmployees(empRes.value.data.items);
      if (attRes.status === "fulfilled") setAttendance(attRes.value.data.items);
      if (currentAttRes.status === "fulfilled") setCurrentAttendance(currentAttRes.value.data.items);
      if (payRes.status === "fulfilled") setPayrolls(payRes.value.data.items);
      if (incRes.status === "fulfilled") setIncentives(incRes.value.data.items);
      if (ordersRes.status === "fulfilled") setOrders(ordersRes.value.data.items);
      if (usersRes.status === "fulfilled") setUsers(usersRes.value.data.items);
      if (invRes.status === "fulfilled") setInventoryItems(invRes.value.data.items);
      if (poRes.status === "fulfilled") setPurchaseOrders(poRes.value.data.items);
      if (sessionsRes.status === "fulfilled") setLoginSessions(sessionsRes.value.data.items);
      if (discountsRes.status === "fulfilled") setDiscountRequests(discountsRes.value.data.items);
      if (leaveRes.status === "fulfilled") setLeaveRequests(leaveRes.value.data.items);
      if (onlineDeliveryRes.status === "fulfilled") setOnlineDeliveryOrders(onlineDeliveryRes.value.data.items);
      if (taxRes.status === "fulfilled") setTaxSettings(taxRes.value.data);

      // Non-critical
      const currentRole = getRoleFromToken(token);
      const nonCriticalCalls: Promise<any>[] = [
        apiRequest<{ success: boolean; data: any }>("/api/v1/admin/security-settings", { token }),
        apiRequest<{ success: boolean; data: { alerts: any[] } }>("/api/v1/admin/inactive-monitoring", { token }),
        apiRequest<{ success: boolean; data: any }>("/api/v1/reports/tenant-analytics", { token }),
      ];
      if (currentRole === "super_admin" || currentRole === "platform_admin") {
        nonCriticalCalls.push(apiRequest<{ success: boolean; data: any }>("/api/v1/reports/platform-dashboard", { token }));
      }
      Promise.allSettled(nonCriticalCalls).then(([sec, alert, tan, plat]) => {
        if (sec.status === "fulfilled") setSecurity(sec.value.data);
        if (alert.status === "fulfilled") setInactiveAlerts(alert.value.data.alerts);
        if (tan.status === "fulfilled") setTenantMetrics(tan.value.data);
        if (plat?.status === "fulfilled") setPlatformMetrics(plat.value.data);
      });

      refreshMetrics(selectedBranch.id);
    } catch (err) {
      console.error(err);
    }
  }

  async function refreshMetrics(branchId: string) {
    try {
      const res = await apiRequest<{ success: boolean; data: DashboardMetrics }>(`/api/v1/reports/manager-dashboard?branch_id=${branchId}`, { token });
      if (res.success) setMetrics(res.data);
    } catch (e) { console.error(e); }
  }

  
  function exportToExcel(data: any[], filename: string) {
    if (!data || data.length === 0) return showToast("No data to export", "warning");
    const headers = Object.keys(data[0]).join(",");
    const rows = data.map(obj => Object.values(obj).map(v => `"${String(v || "").replace(/"/g, '""')}"`).join(","));
    const csvContent = [headers, ...rows].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}.csv`;
    link.click();
    showToast(`Exported ${filename}.csv successfully`, "success");
  }

  async function refreshDiscountRequests(branchId: string) {
    try {
      const res = await apiRequest<{ success: boolean; data: { items: DiscountRequest[] } }>(`/api/v1/discounts/requests/pending?branch_id=${branchId}`, { token });
      if (res.success) {
        const nextItems = res.data.items;
        const nextIds = new Set(nextItems.map((item) => item.id));
        if (discountRequestsLoaded.current) {
          const newRequests = nextItems.filter((item) => !discountRequestIds.current.has(item.id));
          if (newRequests.length > 0) {
            showToast(
              `${newRequests.length} new discount approval request${newRequests.length === 1 ? "" : "s"}`,
              "warning",
            );
          }
        }
        discountRequestIds.current = nextIds;
        discountRequestsLoaded.current = true;
        setDiscountRequests(nextItems);
      }
    } catch (e) { console.error(e); }
  }

  async function refreshOrders(branchId: string) {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      const res = await apiRequest<{ success: boolean; data: { items: BackendOrder[] } }>(`/api/v1/orders?branch_id=${branchId}`, { token });
      if (res.success) setOrders(res.data.items);
    } catch (e) {
      console.error(e);
    } finally {
      setIsRefreshing(false);
    }
  }

  async function refreshKdsOrders(branchId: string) {
    try {
      const res = await apiRequest<{ success: boolean; data: { items: BackendOrder[] } }>(`/api/v1/kds/orders?branch_id=${branchId}`, { token });
      if (res.success) setOrders((current) => {
        const kdsIds = new Set(res.data.items.map((order) => order.id));
        const nonKdsOrders = current.filter((order) => !kdsIds.has(order.id) && !["new", "accepted", "preparing", "ready", "served"].includes(order.kds_status));
        return [...res.data.items, ...nonKdsOrders];
      });
    } catch (e) {
      console.error(e);
    }
  }

  async function refreshOnlineDelivery(branchId: string, showError = true) {
    try {
      const res = await apiRequest<{ success: boolean; data: { items: OnlineDeliveryOrder[] } }>(`/api/v1/online-delivery/orders?branch_id=${branchId}`, { token });
      if (res.success) {
        const nextItems = res.data.items;
        const newOrders = unseenNewDeliveryOrders(nextItems, deliveryOrderIds.current, deliveryOrdersLoaded.current);
        if (newOrders.length > 0) {
          const providers = [...new Set(newOrders.map((order) => statusLabel(order.provider)))].join(" / ");
          showToast(
            `${newOrders.length} new ${providers} delivery order${newOrders.length === 1 ? "" : "s"}`,
            "warning",
          );
        }
        deliveryOrderIds.current = new Set(nextItems.map((order) => order.id));
        deliveryOrdersLoaded.current = true;
        setOnlineDeliveryOrders(nextItems);
      }
    } catch (error) {
      if (showError) showToast(readableApiError(error, "Failed to refresh online delivery"), "error");
    }
  }

  // ── Cart / Orders ──────────────────────────────────────
  const totals = useMemo(() => {
    let subtotal = 0, tax = 0;
    cart.forEach((item) => {
      const price = parseFloat(item.product.price);
      subtotal += price * item.quantity;
      tax += price * item.quantity * (parseFloat(item.product.tax_rate) / 100);
    });
    const discount = cart.length > 2 ? 10 : 0;
    return { subtotal, tax, discount, total: subtotal + tax - discount };
  }, [cart]);

  async function refreshRazorpayDashboard(showSuccess = false) {
    if (!branch?.id) return;
    setRazorpayRefreshing(true);
    try {
      const [providerRes, metricsRes, ordersRes, payrollRes] = await Promise.allSettled([
        apiRequest<{ success: boolean; data: RazorpayProviderSnapshot }>(
          `/api/v1/integrations/razorpay/dashboard?branch_id=${branch.id}`,
          { token },
        ),
        apiRequest<{ success: boolean; data: DashboardMetrics }>(`/api/v1/reports/manager-dashboard?branch_id=${branch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: BackendOrder[] } }>(`/api/v1/orders?branch_id=${branch.id}`, { token }),
        apiRequest<{ success: boolean; data: { items: PayrollLog[] } }>(`/api/v1/reports/payroll?branch_id=${branch.id}`, { token }),
      ]);

      const loaded: string[] = [];
      const failed: string[] = [];

      if (
        providerRes.status === "fulfilled"
        && providerRes.value.success
        && isRazorpayProviderSnapshot(providerRes.value.data)
      ) {
        setRazorpayProviderSnapshot(providerRes.value.data);
        setRazorpayProviderError("");
        loaded.push("provider");
      } else {
        setRazorpayProviderSnapshot(null);
        setRazorpayProviderError(
          providerRes.status === "rejected"
            ? readableApiError(providerRes.reason, "Provider sync failed")
            : "Provider sync failed",
        );
        failed.push("provider");
      }
      if (metricsRes.status === "fulfilled" && metricsRes.value.success) {
        setMetrics(metricsRes.value.data);
        loaded.push("metrics");
      } else {
        failed.push("metrics");
      }
      if (ordersRes.status === "fulfilled" && ordersRes.value.success) {
        setOrders(ordersRes.value.data.items);
        loaded.push("orders");
      } else {
        failed.push("orders");
      }
      if (payrollRes.status === "fulfilled" && payrollRes.value.success) {
        setPayrolls(payrollRes.value.data.items);
        loaded.push("payouts");
      } else {
        failed.push("payouts");
      }

      if (loaded.length === 0) {
        const firstError = [providerRes, metricsRes, ordersRes, payrollRes].find((result) => result.status === "rejected");
        throw firstError?.status === "rejected" ? firstError.reason : new Error("No Razorpay dashboard data was returned");
      }

      setRazorpayLastRefresh(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
      if (showSuccess) {
        showToast(failed.length ? `Dashboard refreshed. ${failed.join(", ")} unavailable.` : "Razorpay dashboard refreshed", failed.length ? "warning" : "success");
      }
    } catch (error) {
      showToast(readableApiError(error, "Failed to refresh Razorpay dashboard"), "error");
    } finally {
      setRazorpayRefreshing(false);
    }
  }

  function addProductToCart(product: Product) {
    setCart((items) => {
      const ex = items.find((i) => i.product.id === product.id);
      if (ex) return items.map((i) => i.product.id === product.id ? { ...i, quantity: i.quantity + 1 } : i);
      return [...items, { product, quantity: 1 }];
    });
  }

  async function handleCreateOnlineDeliveryOrder(e: React.FormEvent) {
    e.preventDefault();
    if (!branch) return;
    if (!deliveryDraft.product_id) {
      showToast("Select a menu item", "warning");
      return;
    }
    try {
      await apiRequest("/api/v1/online-delivery/orders", {
        method: "POST",
        token,
        body: JSON.stringify({
          branch_id: branch.id,
          provider: deliveryDraft.provider,
          external_order_id: deliveryDraft.external_order_id.trim() || `${deliveryDraft.provider.toUpperCase()}-${Date.now()}`,
          customer_name: deliveryDraft.customer_name.trim() || "Online Customer",
          customer_phone: deliveryDraft.customer_phone.trim() || undefined,
          delivery_address: deliveryDraft.delivery_address.trim(),
          payment_mode: deliveryDraft.payment_mode,
          payment_status: deliveryDraft.payment_status,
          commission_amount: deliveryDraft.commission_amount || "0.00",
          notes: deliveryDraft.notes.trim() || undefined,
          items: [{ product_id: deliveryDraft.product_id, quantity: deliveryDraft.quantity, notes: deliveryDraft.notes.trim() || undefined }],
        }),
      });
      setDeliveryDraft((prev) => ({ ...prev, external_order_id: "", customer_name: "Online Customer", customer_phone: "", delivery_address: "", notes: "" }));
      await refreshOnlineDelivery(branch.id);
      showToast("Online delivery order added", "success");
    } catch (error) {
      showToast(readableApiError(error, "Failed to add online delivery order"), "error");
    }
  }

  async function handleAcceptOnlineDelivery(deliveryId: string) {
    if (!branch) return;
    try {
      await apiRequest(`/api/v1/online-delivery/orders/${deliveryId}/accept`, { method: "POST", token });
      await Promise.all([refreshOnlineDelivery(branch.id), refreshOrders(branch.id)]);
      showToast("Delivery order accepted and sent to KDS", "success");
    } catch (error) {
      showToast(readableApiError(error, "Failed to accept delivery order"), "error");
    }
  }

  async function handleUpdateOnlineDelivery(deliveryId: string, status: OnlineDeliveryOrder["status"]) {
    if (!branch) return;
    try {
      await apiRequest(`/api/v1/online-delivery/orders/${deliveryId}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({ status }),
      });
      await Promise.all([refreshOnlineDelivery(branch.id), refreshOrders(branch.id)]);
      showToast(`Delivery order marked ${statusLabel(status)}`, "success");
    } catch (error) {
      showToast(readableApiError(error, "Failed to update delivery order"), "error");
    }
  }

  async function handleCreateOrder(statusStr: "held" | "active" = "held") {
    if (!branch || cart.length === 0) return;
    try {
      const orderPayload = { branch_id: branch.id, table_id: selectedTable || null, order_type: orderType, discount_amount: totals.discount.toFixed(2), items: cart.map((c) => ({ product_id: c.product.id, quantity: c.quantity })) };
      const res = await apiRequest<any>("/api/v1/orders", { method: "POST", token, body: JSON.stringify(orderPayload) });
      if (res.success) {
        const orderId = res.data.id;
        if (statusStr === "active") await apiRequest(`/api/v1/orders/${orderId}/send-to-kitchen`, { method: "POST", token });
        setCart([]);
        refreshMetrics(branch.id);
        initData();
        showToast(`Order ${statusStr === "active" ? "sent to kitchen" : "placed on hold"} successfully!`, "success");
      }
    } catch { showToast("Error creating order", "error"); }
  }

  async function handleRequestDiscountApproval() {
    if (!branch || cart.length === 0) {
      showToast("Add items before requesting a discount", "warning");
      return;
    }
    setDiscountModal({ isOpen: true, amount: "", type: "percentage" });
  }

  async function submitDiscountRequest() {
    const numericValue = parseFloat(discountModal.amount);
    if (Number.isNaN(numericValue) || numericValue <= 0) {
      showToast("Enter a valid discount value", "error");
      return;
    }
    try {
      const isPercentage = discountModal.type === "percentage";
      const orderPayload = {
        branch_id: branch?.id,
        table_id: selectedTable || null,
        order_type: orderType,
        discount_amount: "0.00",
        items: cart.map((c) => ({ product_id: c.product.id, quantity: c.quantity })),
      };
      const orderRes = await apiRequest<{ success: boolean; data: BackendOrder }>("/api/v1/orders", {
        method: "POST",
        token,
        body: JSON.stringify(orderPayload),
      });
      if (!orderRes.success) throw new Error("Order creation failed");
      await apiRequest("/api/v1/discounts/request", {
        method: "POST",
        token,
        body: JSON.stringify({
          order_id: orderRes.data.id,
          amount_or_percentage: numericValue.toFixed(2),
          is_percentage: isPercentage,
        }),
      });
      if (orderType === "dine_in") {
        await apiRequest(`/api/v1/orders/${orderRes.data.id}/send-to-kitchen`, { method: "POST", token });
      }
      setCart([]);
      initData();
      showToast("Discount request sent to manager", "success");
      setDiscountModal(prev => ({ ...prev, isOpen: false }));
    } catch { showToast("Failed to request discount", "error"); }
  }

  async function loadRazorpayCheckout() {
    if (window.Razorpay) return;
    await new Promise<void>((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
      if (existing) {
        existing.addEventListener("load", () => resolve(), { once: true });
        existing.addEventListener("error", () => reject(new Error("Razorpay checkout failed to load")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Razorpay checkout failed to load"));
      document.body.appendChild(script);
    });
  }

  async function handleGatewayOrderPayment(orderId: string) {
    await loadRazorpayCheckout();
    const gateway = await apiRequest<{
      success: boolean;
      data: { key_id: string; gateway_order_id: string; amount_paise: number; amount: string; currency: string };
    }>(`/api/v1/orders/${orderId}/payments/gateway`, { method: "POST", token });
    const RazorpayCheckout = window.Razorpay;
    if (!RazorpayCheckout) throw new Error("Razorpay checkout is unavailable");
    await new Promise<void>((resolve, reject) => {
      const checkout = new RazorpayCheckout({
        key: gateway.data.key_id,
        amount: gateway.data.amount_paise,
        currency: gateway.data.currency,
        name: "Korvexa POS",
        description: `Bill payment #${orderId.slice(0, 8)}`,
        order_id: gateway.data.gateway_order_id,
        prefill: { email },
        theme: { color: "#0d9488" },
        handler: async (response) => {
          try {
            await apiRequest(`/api/v1/orders/${orderId}/payments/gateway/verify`, {
              method: "POST",
              token,
              body: JSON.stringify({
                gateway_order_id: response.razorpay_order_id,
                gateway_payment_id: response.razorpay_payment_id,
                gateway_signature: response.razorpay_signature,
              }),
            });
            resolve();
          } catch (error) {
            reject(error);
          }
        },
        modal: { ondismiss: () => reject(new Error("Payment cancelled")) },
      });
      checkout.open();
    });
  }

  async function handlePayment(method: "cash" | "card" | "upi") {
    if (!branch || cart.length === 0) return;
    try {
      const orderPayload = { branch_id: branch.id, table_id: selectedTable || null, order_type: orderType, discount_amount: totals.discount.toFixed(2), items: cart.map((c) => ({ product_id: c.product.id, quantity: c.quantity })) };
      const orderRes = await apiRequest<{ success: boolean; data: BackendOrder }>("/api/v1/orders", { method: "POST", token, body: JSON.stringify(orderPayload) });
      if (orderRes.success) {
        const orderId = orderRes.data.id;
        await apiRequest(`/api/v1/orders/${orderId}/payments`, { method: "POST", token, body: JSON.stringify({ payments: [{ method, amount: totals.total.toFixed(2) }] }) });
        setCart([]);
        refreshMetrics(branch.id);
        initData();
        showToast(`Payment of ₹${totals.total.toFixed(2)} via ${method.toUpperCase()} successful!`, "success");
      }
    } catch { showToast("Payment failed", "error"); }
  }

  async function handleGatewayCartPayment() {
    if (!branch || cart.length === 0) return;
    try {
      const orderPayload = { branch_id: branch.id, table_id: selectedTable || null, order_type: orderType, discount_amount: totals.discount.toFixed(2), items: cart.map((c) => ({ product_id: c.product.id, quantity: c.quantity })) };
      const orderRes = await apiRequest<{ success: boolean; data: BackendOrder }>("/api/v1/orders", { method: "POST", token, body: JSON.stringify(orderPayload) });
      if (!orderRes.success) throw new Error("Order creation failed");
      await handleGatewayOrderPayment(orderRes.data.id);
      setCart([]);
      refreshMetrics(branch.id);
      initData();
      showToast(`Gateway payment of ₹${totals.total.toFixed(2)} captured`, "success");
    } catch (error) {
      const message = error instanceof Error && error.message === "Payment cancelled" ? "Payment cancelled" : readableApiError(error, "Gateway payment failed");
      showToast(message, "error");
    }
  }

  async function handleClockIn(employeeId: string) {
    try {
      await apiRequest("/api/v1/attendance/check-in", { method: "POST", token, body: JSON.stringify({ employee_id: employeeId, shift_type: "Morning" }) });
      await initData(); showToast("Clocked in and payroll updated", "success");
    } catch { showToast("Already clocked in or error occurred.", "warning"); }
  }

  async function handleClockOut(employeeId: string) {
    try {
      await apiRequest("/api/v1/attendance/check-out", { method: "POST", token, body: JSON.stringify({ employee_id: employeeId }) });
      await initData(); showToast("Clocked out and payroll updated", "success");
    } catch { showToast("Not clocked in or error occurred.", "warning"); }
  }

  async function handleDeleteTable(tableId: string) {
    const table = tables.find((item) => item.id === tableId);
    if (!table) return;
    if (table.status === "occupied" || table.order_id || table.merged_with) {
      showToast("Clear orders and unmerge before deleting this table", "warning");
      return;
    }
    setConfirmModal({
      isOpen: true,
      title: "Delete Table",
      message: `Delete ${table.name}? This cannot be undone.`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/tables/${tableId}`, { method: "DELETE", token });
          initData(); showToast("Table deleted successfully", "success");
        } catch { showToast("Failed to delete table", "error"); }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }

  async function handleTableStatus(tableId: string, status: TableState["status"]) {
    try {
      await apiRequest(`/api/v1/tables/${tableId}`, { method: "PATCH", token, body: JSON.stringify({ status }) });
      initData();
      showToast(`Table marked ${statusLabel(status)}`, "success");
    } catch { showToast("Failed to update table", "error"); }
  }

  async function handleReserveTable(tableId: string) {
    try {
      await apiRequest("/api/v1/tables/reserve", {
        method: "POST",
        token,
        body: JSON.stringify({ table_id: tableId, customer_name: "Walk-in", customer_phone: "" }),
      });
      initData();
      showToast("Table reserved", "success");
    } catch { showToast("Failed to reserve table", "error"); }
  }

  function handleEditTable(table: TableState) {
    setEditTableWizard({
      id: table.id,
      name: table.name,
      capacity: table.capacity,
      floor_area: table.floor_area,
      status: table.status,
    });
    setShowEditTableWizard(true);
  }

  function handleOpenTableQr(table: TableState) {
    if (!branch) {
      showToast("Select a branch before opening QR", "warning");
      return;
    }
    const qrUrl = qrOrderUrl({
      branchId: branch.id,
      tableId: table.id,
      currentOrigin: window.location.origin,
      publicAppUrl: import.meta.env.VITE_PUBLIC_APP_URL || import.meta.env.VITE_APP_PUBLIC_URL,
    });
    const qrImage = `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(qrUrl)}`;
    const win = window.open("", "_blank", "width=420,height=620");
    if (!win) {
      navigator.clipboard?.writeText(qrUrl);
      showToast("QR link copied", "success");
      return;
    }
    win.document.write(`
      <!doctype html>
      <html>
        <head>
          <title>${table.name} QR Order</title>
          <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 28px; text-align: center; color: #111827; }
            .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; }
            h1 { margin: 0 0 6px; font-size: 24px; }
            p { margin: 0 0 18px; color: #6b7280; }
            img { width: 240px; height: 240px; }
            code { display: block; margin-top: 16px; word-break: break-all; font-size: 12px; color: #374151; }
            button { margin-top: 18px; padding: 10px 16px; border: 0; border-radius: 8px; background: #0d9488; color: white; font-weight: 700; }
          </style>
        </head>
        <body>
          <div class="card">
            <h1>${branch.name}</h1>
            <p>${table.name} - scan to order and pay</p>
            <img src="${qrImage}" alt="QR order code" />
            <code>${qrUrl}</code>
            <button onclick="window.print()">Print QR</button>
          </div>
        </body>
      </html>
    `);
    win.document.close();
  }

  async function handleSaveEditTableWizard(e: React.FormEvent) {
    e.preventDefault();
    const floorArea = editTableWizard.floor_area.trim().replace(/\s+/g, " ");
    if (!editTableWizard.id || !editTableWizard.name.trim() || !floorArea) return;
    try {
      await apiRequest(`/api/v1/tables/${editTableWizard.id}`, {
        method: "PATCH",
        token,
        body: JSON.stringify({
          name: editTableWizard.name.trim(),
          capacity: editTableWizard.capacity,
          floor_area: floorArea,
          status: editTableWizard.status,
        }),
      });
      setSelectedFloor(floorArea);
      setShowEditTableWizard(false);
      initData();
      showToast("Table updated", "success");
    } catch {
      showToast("Failed to update table", "error");
    }
  }

  async function handleToggleProduct(productId: string, currentStatus: boolean) {
    try {
      await apiRequest(`/api/v1/products/${productId}`, { method: "PATCH", token, body: JSON.stringify({ available: !currentStatus }) });
      initData(); showToast("Product availability updated", "success");
    } catch { showToast("Failed to update product", "error"); }
  }

  function handleDeleteProduct(productId: string) {
    const product = products.find((item) => item.id === productId);
    setConfirmModal({
      isOpen: true,
      title: "Delete Menu Item",
      message: `Delete ${product?.name || "this item"} from the menu? Past orders will stay unchanged.`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/products/${productId}`, { method: "DELETE", token });
          setProducts((current) => current.filter((item) => item.id !== productId));
          await initData();
          showToast("Menu item deleted", "success");
        } catch (error) {
          const message = error instanceof Error && error.message ? error.message : "Failed to delete menu item";
          showToast(message, "error");
        }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }

  async function handleDeleteInventoryItem(itemId: string) {
    try {
      await apiRequest(`/api/v1/inventory/items/${itemId}`, { method: "DELETE", token });
      setInventoryItems((current) => current.filter((item) => item.id !== itemId));
      await initData();
      showToast("Inventory item deleted successfully", "success");
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : "Failed to delete inventory item";
      showToast(message, "error");
    }
  }

  async function handleDisableEmployee(employeeId: string) {
    try {
      await apiRequest(`/api/v1/employees/${employeeId}`, { method: "DELETE", token });
      initData(); showToast("Employee removed", "success");
    } catch { showToast("Failed to remove employee", "error"); }
  }

  async function handleToggleEmployeeActive(employeeId: string, currentActive: boolean) {
    try {
      await apiRequest(`/api/v1/employees/${employeeId}`, { method: "PATCH", token, body: JSON.stringify({ active: !currentActive }) });
      initData(); showToast(currentActive ? "Employee Disabled" : "Employee Enabled", "success");
    } catch { showToast("Failed to update employee status", "error"); }
  }

  async function handleEditAttendance(attendanceId: string, currentIn: string, currentOut: string) {
    const checkIn = currentIn ? new Date(currentIn).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', hour12: false}) : "";
    const checkOut = currentOut ? new Date(currentOut).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', hour12: false}) : "";
    const date = currentIn ? attendanceDateKey(currentIn) : attendanceDateKey(new Date());
    setEditAttendanceWizard({ id: attendanceId, date, checkIn, checkOut });
    setShowEditAttendanceWizard(true);
  }

  async function handleSaveEditAttendanceWizard(e: React.FormEvent) {
    e.preventDefault();
    if (!editAttendanceWizard.checkIn) {
        setShowEditAttendanceWizard(false);
        return;
    }
    const logDate = editAttendanceWizard.date || attendanceDateKey(new Date());
    const checkInDate = new Date(`${logDate}T${editAttendanceWizard.checkIn}:00`);
    let checkOutDate = null;

    if (editAttendanceWizard.checkOut) {
      checkOutDate = new Date(`${logDate}T${editAttendanceWizard.checkOut}:00`);
    } else {
      checkOutDate = new Date(checkInDate.getTime() + 9 * 60 * 60 * 1000);
    }

    try {
      await apiRequest(`/api/v1/attendance/${editAttendanceWizard.id}`, {
        method: "PATCH", token,
        body: JSON.stringify({
          check_in: checkInDate.toISOString(),
          check_out: checkOutDate.toISOString()
        })
      });
      initData(); showToast("Log updated", "success");
    } catch { showToast("Failed to update log", "error"); }
    setShowEditAttendanceWizard(false);
  }

  async function handleApproveOvertime(attendanceId: string, approved: boolean) {
    try {
      await apiRequest(`/api/v1/attendance/${attendanceId}`, { method: "PATCH", token, body: JSON.stringify({ overtime_status: approved ? "approved" : "rejected" }) });
      initData(); showToast(approved ? "Overtime Approved" : "Overtime Rejected", "success");
    } catch { showToast("Failed to update overtime status", "error"); }
  }

  async function handleRequestOvertime(attendanceId?: string) {
    if (!attendanceId) {
      showToast("Clock in first or select today's log before requesting OT", "warning");
      return;
    }
    setOvertimeWizard({ attendance_id: attendanceId, minutes: 30 });
    setShowOvertimeWizard(true);
  }

  async function handleSaveOvertimeWizard(e: React.FormEvent) {
    e.preventDefault();
    const minutes = overtimeWizard.minutes;
    if (!minutes || minutes < 1) {
      setShowOvertimeWizard(false);
      return;
    }
    try {
      await apiRequest(`/api/v1/attendance/${overtimeWizard.attendance_id}`, { method: "PATCH", token, body: JSON.stringify({ overtime_minutes: minutes, overtime_status: "pending" }) });
      initData(); showToast("Overtime request submitted", "success");
    } catch { showToast("Failed to submit overtime request", "error"); }
    setShowOvertimeWizard(false);
  }

  async function handleDeleteAttendance(attendanceId: string) {
    setConfirmModal({
      isOpen: true,
      title: "Delete Log",
      message: "Are you sure you want to delete this log?",
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/attendance/${attendanceId}`, { method: "DELETE", token });
          initData(); showToast("Log deleted", "success");
        } catch { showToast("Failed to delete log", "error"); }
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  }

  async function handleCleanupAttendance() {
    setConfirmModal({
      isOpen: true,
      title: "Cleanup Old Logs",
      message: "Delete all logs older than 2 months?",
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/attendance/cleanup`, { method: "DELETE", token });
          initData(); showToast("Old logs cleaned up", "success");
        } catch { showToast("Failed to cleanup logs", "error"); }
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  }


  function openPayoutWizard(payroll: PayrollLog) {
    setPayoutWizard({
      payroll_id: payroll.id,
      name: payroll.name,
      net_salary: payroll.net_salary,
      payment_mode: "cash",
      payment_reference: "",
      use_gateway: false,
      recipient_upi: "",
    });
    setShowPayoutWizard(true);
  }

  async function handlePayPayroll(e: React.FormEvent) {
    e.preventDefault();
    if (payoutWizard.payment_mode === "upi" && payoutWizard.use_gateway && !payoutWizard.recipient_upi.trim()) {
      showToast("Enter recipient UPI ID", "warning");
      return;
    }
    if (payoutWizard.payment_mode === "upi" && !payoutWizard.use_gateway && !payoutWizard.payment_reference.trim()) {
      showToast("Enter UPI transaction reference", "warning");
      return;
    }
    try {
      await apiRequest(`/api/v1/payroll/${payoutWizard.payroll_id}/pay`, {
        method: "POST",
        token,
        body: JSON.stringify({
          payment_mode: payoutWizard.payment_mode,
          payment_reference: payoutWizard.payment_reference.trim() || undefined,
          gateway_provider: payoutWizard.use_gateway ? "razorpayx" : undefined,
          recipient_upi: payoutWizard.use_gateway ? payoutWizard.recipient_upi.trim() : undefined,
          recipient_name: payoutWizard.name,
        }),
      });
      setShowPayoutWizard(false);
      initData();
      showToast(
        payoutWizard.use_gateway
          ? "RazorpayX payout submitted. Waiting for settlement."
          : `Payroll marked as paid via ${payrollPaymentLabels[payoutWizard.payment_mode]}`,
        "success",
      );
    } catch (error) { showToast(readableApiError(error, "Failed to process payroll"), "error"); }
  }

  function handleDeletePayroll(payrollId: string, name: string) {
    setConfirmModal({
      isOpen: true,
      title: "Delete Payroll",
      message: `Delete payroll for ${name}?`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/payroll/${payrollId}`, { method: "DELETE", token });
          initData();
          showToast("Payroll deleted", "success");
        } catch { showToast("Failed to delete payroll", "error"); }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }

  async function handleAddTable() {
    setTableWizard({ name: "", capacity: 4, floor_area: selectedFloor });
    setShowTableWizard(true);
  }

  async function handleSaveTableWizard(e: React.FormEvent) {
    e.preventDefault();
    const floorArea = tableWizard.floor_area.trim().replace(/\s+/g, " ");
    if (!branch?.id) {
      showToast("Select a branch before adding tables", "warning");
      return;
    }
    if (!tableWizard.name.trim() || !floorArea) {
      setShowTableWizard(false);
      return;
    }
    try {
      await apiRequest("/api/v1/tables", {
        method: "POST",
        token,
        body: JSON.stringify({
          branch_id: branch.id,
          name: tableWizard.name.trim(),
          capacity: tableWizard.capacity,
          status: "available",
          floor_area: floorArea,
        }),
      });
      setSelectedFloor(floorArea);
      initData(); showToast(`Table added to ${floorArea}`, "success");
    } catch { showToast("Error adding table", "error"); }
    setShowTableWizard(false);
  }

  async function handleCreateFloor(e: React.FormEvent) {
    e.preventDefault();
    const floorName = newFloorName.trim().replace(/\s+/g, " ");
    if (!branch?.id || !floorName) return;
    try {
      const response = await apiRequest<{ success: boolean; data: { items: string[]; name: string } }>("/api/v1/table-floors", {
        method: "POST",
        token,
        body: JSON.stringify({ branch_id: branch.id, name: floorName }),
      });
      setTableFloors(response.data.items);
      setSelectedFloor(response.data.name);
      setNewFloorName("");
      showToast(`${response.data.name} added`, "success");
    } catch {
      showToast("Error adding floor", "error");
    }
  }

  function handleStartEditFloor() {
    setEditingFloor(selectedFloor);
    setEditFloorName(selectedFloor);
  }

  async function handleSaveFloorRename(e: React.FormEvent) {
    e.preventDefault();
    const nextName = editFloorName.trim().replace(/\s+/g, " ");
    if (!branch?.id || !editingFloor || !nextName) return;
    try {
      const response = await apiRequest<{ success: boolean; data: { items: string[]; name: string } }>("/api/v1/table-floors", {
        method: "PATCH",
        token,
        body: JSON.stringify({ branch_id: branch.id, current_name: editingFloor, name: nextName }),
      });
      setTableFloors(response.data.items);
      setSelectedFloor(response.data.name);
      setEditingFloor("");
      setEditFloorName("");
      initData();
      showToast("Floor updated", "success");
    } catch {
      showToast("Error updating floor", "error");
    }
  }

  function handleDeleteFloor() {
    if (!branch?.id) return;
    const tableCount = tables.filter((table) => table.floor_area === selectedFloor).length;
    if (tableCount > 0) {
      showToast("Move or delete tables before deleting this floor", "warning");
      return;
    }
    setConfirmModal({
      isOpen: true,
      title: "Delete Floor",
      message: `Delete ${selectedFloor}? This only removes the floor tab.`,
      onConfirm: async () => {
        try {
          const response = await apiRequest<{ success: boolean; data: { items: string[] } }>(
            `/api/v1/table-floors?branch_id=${encodeURIComponent(branch.id)}&name=${encodeURIComponent(selectedFloor)}`,
            { method: "DELETE", token },
          );
          const nextFloors = response.data.items.length ? response.data.items : DEFAULT_TABLE_FLOORS;
          setTableFloors(nextFloors);
          setSelectedFloor(nextFloors[0] || "Ground Floor");
          showToast("Floor deleted", "success");
        } catch {
          showToast("Error deleting floor", "error");
        }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }


  async function handleAddCategory() {
    const name = prompt("Enter new category name:");
    if (!name?.trim() || !branch?.id) return;
    try {
      const res = await apiRequest<{ success: boolean; data: { id: string } }>("/api/v1/categories", { method: "POST", token, body: JSON.stringify({ name: name.trim(), branch_id: branch.id }) });
      initData();
      setProductWizard(prev => ({ ...prev, category_id: res.data.id }));
      showToast("Category added", "success");
    } catch { showToast("Failed to add category", "error"); }
  }

  function handleAddProduct() {
    setProductWizard({
      category_id: "",
      name: "",
      price: "",
      tax_rate: String(taxSettings.food_gst_rate ?? 5),
      sku: "",
      description: "",
      image_url: "",
      available: true,
    });
    setShowProductWizard(true);
  }

  async function handleSaveProductWizard(e: React.FormEvent) {
    e.preventDefault();
    if (!branch?.id) {
      showToast("Select a branch before adding menu items", "warning");
      return;
    }
    const price = parseFloat(productWizard.price);
    const taxRate = parseFloat(productWizard.tax_rate);
    if (!productWizard.name.trim() || Number.isNaN(price) || price < 0) {
      showToast("Enter a valid item name and price", "error");
      return;
    }
    try {
      await apiRequest("/api/v1/products", {
        method: "POST",
        token,
        body: JSON.stringify({
          branch_id: branch.id,
          category_id: productWizard.category_id || null,
          name: productWizard.name.trim(),
          price: price.toFixed(2),
          tax_rate: (Number.isNaN(taxRate) ? taxSettings.food_gst_rate : taxRate).toFixed(2),
          sku: productWizard.sku.trim() || null,
          description: productWizard.description.trim() || null,
          image_url: productWizard.image_url.trim() || null,
          available: productWizard.available,
          variants: [],
          addons: [],
          combo_items: [],
        }),
      });
      setShowProductWizard(false);
      initData();
      showToast("Product added", "success");
    } catch { showToast("Error adding product", "error"); }
  }

  function handleAddEmployee() {
    setEmployeeWizard({ id: "", name: "", employee_id: "", email: "", phone: "", role: "waiter", base_salary: "500", password: "" });
    setShowEmployeeWizard(true);
  }

  function handleEditEmployee(emp: Employee) {
    const payroll = payrolls.find((row) => row.employee_record_id === emp.id || row.employee_id === emp.employee_id);
    setEmployeeWizard({
      id: emp.id,
      name: emp.name,
      employee_id: emp.employee_id,
      email: emp.email,
      phone: emp.phone || "",
      role: emp.role,
      base_salary: payroll?.day_salary ?? payroll?.base_salary ?? "0",
      password: "",
    });
    setShowEmployeeWizard(true);
  }

  async function handleSaveEmployeeWizard(e: React.FormEvent) {
    e.preventDefault();
    const isEditing = Boolean(employeeWizard.id);
    if (!employeeWizard.name.trim() || !employeeWizard.employee_id.trim() || !employeeWizard.email.trim() || (!isEditing && !employeeWizard.password.trim())) {
      showToast(isEditing ? "Name, ID, and email are required" : "Name, ID, email, and password are required", "error");
      return;
    }
    if (employeeWizard.password && employeeWizard.password.length < 8) {
      showToast("Password must be at least 8 characters", "error");
      return;
    }
    try {
      if (isEditing) {
        await apiRequest(`/api/v1/employees/${employeeWizard.id}`, { method: "PATCH", token, body: JSON.stringify({ name: employeeWizard.name, email: employeeWizard.email, phone: employeeWizard.phone || null, role: employeeWizard.role, base_salary: parseFloat(employeeWizard.base_salary) || 0, ...(employeeWizard.password ? { password: employeeWizard.password } : {}) }) });
      } else {
        await apiRequest("/api/v1/employees", { method: "POST", token, body: JSON.stringify({ branch_id: branch?.id, name: employeeWizard.name, employee_id: employeeWizard.employee_id, email: employeeWizard.email, phone: employeeWizard.phone || null, role: employeeWizard.role, base_salary: parseFloat(employeeWizard.base_salary) || 0, password: employeeWizard.password }) });
      }
      setShowEmployeeWizard(false);
      initData(); showToast(isEditing ? "Employee updated" : "Employee added", "success");
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : "Error saving employee";
      showToast(message, "error");
    }
  }

  function handleDeleteEmployee(emp: Employee) {
    setConfirmModal({
      isOpen: true,
      title: "Delete Staff",
      message: `Delete ${emp.name}? Their login account and staff record will be removed.`,
      onConfirm: async () => {
        try {
          const endpoint = emp.user_id ? `/api/v1/users/${emp.user_id}` : `/api/v1/employees/${emp.id}`;
          await apiRequest(endpoint, { method: "DELETE", token });
          initData();
          showToast("Staff deleted", "success");
        } catch (error) {
          const message = error instanceof Error && error.message ? error.message : "Error deleting staff";
          showToast(message, "error");
        }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }

  function handleManagerClock(employeeId: string, type: "in" | "out") {
    setAttendanceWizard({ employee_id: employeeId, type, hours: 9 });
    setShowAttendanceWizard(true);
  }

  async function handleSaveAttendanceWizard(e: React.FormEvent) {
    e.preventDefault();
    try {
      const endpoint = attendanceWizard.type === "in" ? "/api/v1/attendance/check-in" : "/api/v1/attendance/check-out";
      await apiRequest(endpoint, { method: "POST", token, body: JSON.stringify({ employee_id: attendanceWizard.employee_id, shift_type: "General" }) });
      setShowAttendanceWizard(false);
      initData(); showToast(`Clocked ${attendanceWizard.type} successfully`, "success");
    } catch { showToast(`Clock ${attendanceWizard.type} failed`, "error"); }
  }

  function handleAddIncentive() {
    setIncentiveWizard({ id: "", employee_id: "", amount: "" });
    setShowIncentiveWizard(true);
  }

  function handleEditIncentive(inc: any) {
    setIncentiveWizard({ id: inc.id, employee_id: inc.employee_record_id || "", amount: inc.incentive_amount.toString() });
    setShowIncentiveWizard(true);
  }

  async function handleSaveIncentiveWizard(e: React.FormEvent) {
    e.preventDefault();
    if (!incentiveWizard.amount) return;
    try {
      if (incentiveWizard.id) {
        await apiRequest(`/api/v1/incentives/${incentiveWizard.id}`, { method: "PATCH", token, body: JSON.stringify({ employee_id: incentiveWizard.employee_id || null, incentive_amount: parseFloat(incentiveWizard.amount) }) });
        showToast("Incentive updated", "success");
      } else {
        await apiRequest("/api/v1/incentives", { method: "POST", token, body: JSON.stringify({ branch_id: branch?.id, employee_id: incentiveWizard.employee_id || null, sales_amount: 0, incentive_amount: parseFloat(incentiveWizard.amount) }) });
        showToast("Incentive added", "success");
      }
      setShowIncentiveWizard(false);
      await initData();
    } catch { showToast("Error saving incentive", "error"); }
  }

  function handleDeleteIncentive(incentiveId: string, name: string) {
    setConfirmModal({
      isOpen: true,
      title: "Delete Incentive",
      message: `Delete incentive for ${name}?`,
      onConfirm: async () => {
        try {
          await apiRequest(`/api/v1/incentives/${incentiveId}`, { method: "DELETE", token });
          await initData();
          showToast("Incentive deleted", "success");
        } catch { showToast("Error deleting incentive", "error"); }
        setConfirmModal((prev) => ({ ...prev, isOpen: false }));
      },
    });
  }

  async function handlePayoutIncentive(incentiveId: string) {
    try {
      await apiRequest(`/api/v1/incentives/${incentiveId}/payout`, { method: "POST", token });
      await initData(); showToast("Incentive added to salary", "success");
    } catch { showToast("Error paying incentive", "error"); }
  }

  async function handleUpdateLeave(leaveId: string, updates: Partial<LeaveRequest>) {
    try {
      await apiRequest(`/api/v1/leaves/${leaveId}`, { method: "PATCH", token, body: JSON.stringify(updates) });
      await initData();
      showToast("Leave updated", "success");
      return true;
    } catch {
      showToast("Error updating leave", "error");
      return false;
    }
  }

  function handleApplyLeave() {
    const today = new Date();
    const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    setLeaveWizard({ employee_id: employees[0]?.id || "", type: "sick", start_date: localDate, end_date: localDate, reason: "" });
    setShowLeaveWizard(true);
  }

  async function handleSaveLeaveWizard(e: React.FormEvent) {
    e.preventDefault();
    if (!branch?.id || !leaveWizard.employee_id || !leaveWizard.start_date || !leaveWizard.end_date || !leaveWizard.reason.trim()) {
      showToast("Staff, dates, and reason are required", "error");
      return;
    }
    try {
      await apiRequest("/api/v1/leaves", {
        method: "POST",
        token,
        body: JSON.stringify({
          branch_id: branch.id,
          employee_id: leaveWizard.employee_id,
          type: leaveWizard.type,
          start_date: leaveWizard.start_date,
          end_date: leaveWizard.end_date,
          reason: leaveWizard.reason.trim(),
        }),
      });
      setShowLeaveWizard(false);
      await initData();
      showToast("Leave applied", "success");
    } catch { showToast("Error applying leave", "error"); }
  }

  function handleEditPayroll(p: PayrollLog) {
    const daySalary = parseFloat(p.day_salary ?? p.base_salary) || 0;
    const payableDays = p.payable_days ?? 0;
    setPayrollWizard({ employee_id: p.employee_id, id: p.id, daily_wage: daySalary, days_present: payableDays, base: daySalary * payableDays, incentives: parseFloat(p.incentives ?? "0") || 0 });
    setShowPayrollWizard(true);
  }

  async function handleSavePayrollWizard(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiRequest(`/api/v1/payroll/${payrollWizard.id}`, { method: "PATCH", token, body: JSON.stringify({ day_salary: payrollWizard.daily_wage }) });
      setShowPayrollWizard(false);
      initData(); showToast("Payroll adjusted", "success");
    } catch { showToast("Error updating payroll", "error"); }
  }

  async function handleSaveSecurity(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiRequest("/api/v1/admin/security-settings", { method: "PATCH", token, body: JSON.stringify(security) });
      showToast("Security policy updated successfully!", "success");
    } catch { showToast("Error saving settings", "error"); }
  }

  async function handleMergeTables(e: React.FormEvent) {
    e.preventDefault();
    if (!mergeT1 || !mergeT2) return;
    try {
      await apiRequest("/api/v1/tables/merge", { method: "POST", token, body: JSON.stringify({ table_id_1: mergeT1, table_id_2: mergeT2 }) });
      setMergeT1("");
      setMergeT2("");
      initData(); showToast("Tables merged!", "success");
    } catch { showToast("Failed to merge tables.", "error"); }
  }

  async function handleSplitTable(tableId: string) {
    try {
      await apiRequest("/api/v1/tables/split", { method: "POST", token, body: JSON.stringify({ table_id: tableId }) });
      initData(); showToast("Table split back to available!", "success");
    } catch { showToast("Split failed", "error"); }
  }

  async function handleKdsStatus(orderId: string, status: string) {
    try {
      await apiRequest(`/api/v1/kds/orders/${orderId}`, { method: "PATCH", token, body: JSON.stringify({ kds_status: status }) });
      if (branch) await refreshKdsOrders(branch.id);
      showToast(`Order marked as ${status}`, "success");
    } catch { showToast("Failed to update KDS status", "error"); }
  }

  async function handleOrderServed(orderId: string) {
    try {
      await apiRequest(`/api/v1/kds/orders/${orderId}`, { method: "PATCH", token, body: JSON.stringify({ kds_status: "served" }) });
      if (branch) await refreshKdsOrders(branch.id);
      showToast("Order marked as served", "success");
    } catch { showToast("Failed to mark served", "error"); }
  }

  async function handleOrderToKDS(orderId: string) {
    try {
      await apiRequest(`/api/v1/orders/${orderId}/send-to-kitchen`, { method: "POST", token });
      initData();
      if (branch) refreshMetrics(branch.id);
      showToast("Order sent to kitchen", "success");
    } catch { showToast("Failed to send order", "error"); }
  }

  async function handleCashOutOrder(order: BackendOrder) {
    if (!["unpaid", "partial"].includes(order.payment_status)) {
      showToast("This order does not have an outstanding balance", "info");
      return;
    }
    const paidAmount = refundablePayments(order).reduce((sum, payment) => sum + parseFloat(payment.amount || "0"), 0);
    const dueAmount = Math.max(parseFloat(order.total || "0") - paidAmount, 0);
    if (dueAmount <= 0) {
      showToast("No balance due", "info");
      return;
    }
    try {
      await apiRequest(`/api/v1/orders/${order.id}/payments`, {
        method: "POST",
        token,
        body: JSON.stringify({ payments: [{ method: "cash", amount: dueAmount.toFixed(2) }] }),
      });
      initData();
      if (branch) refreshMetrics(branch.id);
      showToast("Cash-out completed", "success");
    } catch { showToast("Cash-out failed", "error"); }
  }

  async function handleGatewayCashOutOrder(order: BackendOrder) {
    if (!["unpaid", "partial"].includes(order.payment_status)) {
      showToast("This order does not have an outstanding balance", "info");
      return;
    }
    try {
      await handleGatewayOrderPayment(order.id);
      initData();
      if (branch) refreshMetrics(branch.id);
      showToast("Gateway payment captured", "success");
    } catch (error) {
      const message = error instanceof Error && error.message === "Payment cancelled" ? "Payment cancelled" : readableApiError(error, "Gateway payment failed");
      showToast(message, "error");
    }
  }

  function openRefundWizard(order: BackendOrder) {
    const payments = refundablePayments(order);
    const payment = payments[0];
    if (!payment) {
      showToast("No captured payment is available to refund", "warning");
      return;
    }
    setRefundWizard({
      order,
      payment_id: payment.id,
      amount: Number(payment.amount).toFixed(2),
      reason: "",
    });
  }

  async function handleOrderRefund(event: React.FormEvent) {
    event.preventDefault();
    if (!refundWizard.order || refundSubmitting) return;
    const amount = Number(refundWizard.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      showToast("Enter a valid refund amount", "warning");
      return;
    }
    setRefundSubmitting(true);
    try {
      const response = await apiRequest<{
        success: boolean;
        data: { refund: { status: string }; order: BackendOrder; reused: boolean };
      }>(`/api/v1/orders/${refundWizard.order.id}/refunds`, {
        method: "POST",
        token,
        body: JSON.stringify({
          payment_id: refundWizard.payment_id,
          amount: amount.toFixed(2),
          reason: refundWizard.reason.trim() || "customer_request",
        }),
      });
      setRefundWizard({ order: null, payment_id: "", amount: "", reason: "" });
      await initData();
      if (branch) await refreshMetrics(branch.id);
      showToast(
        ["processed", "completed", "refunded"].includes(response.data.refund.status)
          ? "Refund completed"
          : "Refund submitted. Waiting for Razorpay confirmation.",
        "success",
      );
    } catch (error) {
      try {
        if (!branch?.id) throw new Error("No branch selected");
        const refreshed = await apiRequest<{ success: boolean; data: { items: BackendOrder[] } }>(
          `/api/v1/orders?branch_id=${branch.id}`,
          { token },
        );
        const persistedOrder = refreshed.data.items.find((order) => order.id === refundWizard.order?.id);
        if (persistedOrder && didRefundStateAdvance(refundWizard.order.payment_status, persistedOrder.payment_status)) {
          setOrders(refreshed.data.items);
          setRefundWizard({ order: null, payment_id: "", amount: "", reason: "" });
          if (branch) await refreshMetrics(branch.id);
          showToast(
            persistedOrder.payment_status === "refund_pending"
              ? "Refund submitted. Waiting for Razorpay confirmation."
              : "Refund completed",
            "success",
          );
          return;
        }
      } catch {
        // Preserve the original refund error when reconciliation is unavailable.
      }
      showToast(readableApiError(error, "Refund failed"), "error");
    } finally {
      setRefundSubmitting(false);
    }
  }

  async function handlePrintBill(orderId: string) {
    try {
      const receipt = await printReceipt(orderId, token);
      const win = window.open("", "_blank", "width=420,height=640");
      if (win) {
        const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch] || ch));
        const receiptLines = receipt.text.split("\n");
        const scanIndex = receiptLines.findIndex((line) => line.includes("Scan & Pay"));
        const receiptBeforeQr = scanIndex >= 0 ? receiptLines.slice(0, scanIndex + 1).join("\n") : receipt.text;
        const receiptAfterQr = scanIndex >= 0 ? receiptLines.slice(scanIndex + 1).join("\n") : "";
        const qrSource = receipt.upi_qr_url || (receipt.upi_payment_uri ? `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(receipt.upi_payment_uri)}` : "");
        win.document.write(`
          <!doctype html>
          <html>
            <head>
              <title>Restaurant Bill</title>
              <style>
                @page { size: 80mm auto; margin: 0; }
                * { box-sizing: border-box; }
                body {
                  margin: 0;
                  background: #fff;
                  color: #000;
                }
                .receipt-paper {
                  width: 80mm;
                  min-height: 100vh;
                  padding: 4mm 2.5mm;
                  background: #fff;
                }
                pre {
                  margin: 0;
                  white-space: pre;
                  overflow: hidden;
                  font: 10.5px/1.32 "Courier New", "Lucida Console", Consolas, monospace;
                  letter-spacing: 0;
                  color: #000;
                }
                .qr-wrap {
                  display: ${qrSource ? "flex" : "none"};
                  justify-content: center;
                  padding: 2mm 0 1.5mm;
                }
                .qr-wrap img {
                  width: 34mm;
                  height: 34mm;
                  object-fit: contain;
                  image-rendering: pixelated;
                }
                @media screen {
                  body {
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    background: #e5e7eb;
                    padding: 12px;
                  }
                  .receipt-paper {
                    box-shadow: 0 12px 32px rgba(0,0,0,0.18);
                  }
                }
                @media print {
                  body { background: #fff; padding: 0; }
                  .receipt-paper { box-shadow: none; }
                }
              </style>
            </head>
            <body>
              <div class="receipt-paper">
                <pre>${escapeHtml(receiptBeforeQr)}</pre>
                <div class="qr-wrap">${qrSource ? `<img src="${escapeHtml(qrSource)}" alt="UPI QR Code" />` : ""}</div>
                ${receiptAfterQr ? `<pre>${escapeHtml(receiptAfterQr)}</pre>` : ""}
              </div>
            </body>
          </html>
        `);
        win.document.close();
        win.focus();
        win.print();
      }
      showToast("Bill sent to printer", "success");
    } catch { showToast("Failed to print bill", "error"); }
  }

  async function handleDeleteHeldOrder(order: BackendOrder) {
    if (order.status !== "held") return;
    try {
      await apiRequest(`/api/v1/orders/${order.id}`, { method: "PATCH", token, body: JSON.stringify({ status: "cancelled" }) });
      initData();
      if (branch) refreshMetrics(branch.id);
      showToast("On-hold order deleted", "success");
    } catch { showToast("Failed to delete order", "error"); }
  }

  async function handleRecordPO(e: React.FormEvent, supplier: string, item: string, qty: string, cost: string) {
    e.preventDefault();
    if (!branch) return;
    try {
      await apiRequest(`/api/v1/inventory/purchase-orders`, { 
        method: "POST", token, 
        body: JSON.stringify({ 
          branch_id: branch.id,
          supplier_name: supplier,
          items: [{ name: item, quantity: qty, cost_price: cost }]
        }) 
      });
      initData();
      showToast("Purchase order recorded. Stock updated!", "success");
    } catch { showToast("Failed to record PO", "error"); }
  }

  async function triggerExport(format: "csv" | "pdf" | "excel") {
    if (!branch) return;
    try {
      const url = `${API_BASE}/api/v1/reports/sales/export?branch_id=${branch.id}&format=${format}`;
      const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await response.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `sales_report.${format === "excel" ? "xls" : format}`;
      link.click();
      showToast(`Exporting as ${format.toUpperCase()}…`, "info");
    } catch { showToast("Export failed", "error"); }
  }

  // Active orders/KDS count badges
  const activeOrderCount = orders.filter((o) => o.status === "active").length;
  const newOnlineDeliveryCount = onlineDeliveryOrders.filter((order) => order.status === "new").length;
  const activeOnlineDeliveryCount = onlineDeliveryOrders.filter((order) => ["new", "accepted", "ready", "picked_up"].includes(order.status)).length;
  const filteredOnlineDeliveryOrders = useMemo(() => (
    onlineDeliveryTab === "all"
      ? onlineDeliveryOrders
      : onlineDeliveryOrders.filter((order) => order.status === onlineDeliveryTab)
  ), [onlineDeliveryOrders, onlineDeliveryTab]);
  // Filtered products
  const filteredProducts = products.filter((p) => {
    const availability = p.available as boolean | number | string;
    return availability !== false && availability !== 0 && availability !== "false" && p.name.toLowerCase().includes(search.toLowerCase()) && (posCategory === "All" || p.category_id === posCategory);
  });

  // ── Sample KDS orders if none from API ────────────────
  const kdsOrders = visibleKdsOrders(orders);
  const kdsNewCount = kdsOrders.filter((o) => o.kds_status === "new").length;
  const pendingDiscountCount = discountRequests.length || metrics.pending_discount_requests || 0;

  const tableNameById = useMemo(() => {
    const map = new Map<string, string>();
    tables.forEach((table) => map.set(table.id, table.name));
    return map;
  }, [tables]);

  const ordersForTab = useMemo(() => {
    return orders
      .filter((order) => order.order_type === ordersTab)
      .filter((order) => {
        const itemText = (order.items || []).map((item) => `${item.name} ${item.quantity}`).join(" ").toLowerCase();
        const tableText = order.table_id ? (tableNameById.get(order.table_id) || order.table_id).toLowerCase() : "";
        const totalText = parseFloat(order.total || "0").toFixed(2);
        return (
          (!orderFilters.orderId || order.id.toLowerCase().includes(orderFilters.orderId.toLowerCase())) &&
          (!orderFilters.type || order.order_type === orderFilters.type) &&
          (!orderFilters.tableNo || tableText.includes(orderFilters.tableNo.toLowerCase())) &&
          (!orderFilters.items || itemText.includes(orderFilters.items.toLowerCase())) &&
          (!orderFilters.total || totalText.includes(orderFilters.total)) &&
          (!orderFilters.kds || order.kds_status === orderFilters.kds) &&
          (!orderFilters.payment || order.payment_status === orderFilters.payment) &&
          (!orderFilters.status || order.status === orderFilters.status)
        );
      });
  }, [orders, ordersTab, orderFilters, tableNameById]);

  const dailySales = metrics.sales_charts?.daily?.length ? metrics.sales_charts.daily : [0, 0, 0, 0, 0, 0, 0];
  const dailyLabels = metrics.sales_charts?.daily_labels?.length ? metrics.sales_charts.daily_labels : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const maxDailySales = Math.max(...dailySales, 1);
  const activeStaffDetails = metrics.active_staff_details ?? [];
  const formatAttendanceTime = (value?: string | null) => (
    value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "-"
  );
  const attendanceDateKey = (value: string | Date) => {
    const date = value instanceof Date ? value : new Date(value);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const formatAttendanceDuration = (row: AttendanceLog) => {
    const start = new Date(row.check_in).getTime();
    const end = row.check_out ? new Date(row.check_out).getTime() : Date.now();
    if (!start || end <= start) return "-";
    const minutes = Math.floor((end - start) / 60000);
    return `${Math.floor(minutes / 60)} h ${minutes % 60} m`;
  };
  const activeAttendanceByEmployee = useMemo(() => {
    const map = new Map<string, AttendanceLog>();
    attendance.forEach((row) => {
      if (!row.check_out && !map.has(row.employee_id)) map.set(row.employee_id, row);
    });
    return map;
  }, [attendance]);
  const latestAttendanceByEmployee = useMemo(() => {
    const map = new Map<string, AttendanceLog>();
    attendance.forEach((row) => {
      const existing = map.get(row.employee_id);
      if (!existing || new Date(row.check_in).getTime() > new Date(existing.check_in).getTime()) map.set(row.employee_id, row);
    });
    return map;
  }, [attendance]);
  const todayAttendance = useMemo(() => {
    const todayKey = attendanceDateKey(new Date());
    return attendance.filter((row) => attendanceDateKey(row.check_in) === todayKey);
  }, [attendance]);
  const todayWorkHours = useMemo(() => {
    return Math.round(todayAttendance.reduce((acc, att) => {
      if (!att.check_out) return acc;
      const diff = new Date(att.check_out).getTime() - new Date(att.check_in).getTime();
      return acc + Math.max(diff, 0) / (1000 * 60 * 60);
    }, 0));
  }, [todayAttendance]);
  const currentClockedInStaff = useMemo(
    () => currentAttendance.filter((row) => row.status === "clocked_in").length,
    [currentAttendance],
  );
  const filteredAttendance = useMemo(() => {
    const search = attendanceFilters.search.trim().toLowerCase();
    return attendance.filter((row) => {
      const name = String(row.name || "");
      const empId = String(row.employee_id || "");
      const matchesSearch = !search || name.toLowerCase().includes(search) || empId.toLowerCase().includes(search);
      const matchesDate = !attendanceFilters.date || attendanceDateKey(row.check_in) === attendanceFilters.date;
      const status = (row.overtime_status && row.overtime_status !== "none") ? row.overtime_status : (row.overtime_minutes > 0 ? "pending" : "none");
      const matchesOvertime = !attendanceFilters.overtime || status === attendanceFilters.overtime;
      return matchesSearch && matchesDate && matchesOvertime;
    });
  }, [attendance, attendanceFilters]);
  const todayOrderTypes = metrics.today_order_types ?? {
    dine_in: { orders: 0, sales: "0.00" },
    takeaway: { orders: 0, sales: "0.00" },
    delivery: { orders: 0, sales: "0.00" },
  };
  const weeklyAttendance = metrics.weekly_attendance ?? { labels: dailyLabels, users: [] };
  const monthlyAttendance = metrics.monthly_attendance ?? { month: "", users: [] };
  const userRole = useMemo(() => getRoleFromToken(token), [token]);
  const employeeRoleOptions = useMemo(
    () => ([
      ["waiter", "Waiter"],
      ["cashier", "Cashier"],
      ["manager", "Manager"],
      ["kitchen_staff", "Kitchen Staff"],
      ["accountant", "Accountant"],
    ] as const).filter(([role]) => userRole !== "manager" || role !== "manager"),
    [userRole],
  );
  const visibleNav = useMemo(
    () => nav.filter((item) => canAccessNav(userRole, item.label as NavSection)),
    [userRole],
  );
  const orderStatusCounts = metrics.order_status_counts || {};
  const liveOperations = [
    { label: "Completed Orders", value: metrics.completed_orders ?? 0, color: "var(--success)" },
    { label: "Pending Orders", value: metrics.pending_orders ?? 0, color: "var(--amber)" },
    { label: "Available Tables", value: metrics.available_tables ?? 0, color: "var(--success)" },
    { label: "Occupied Tables", value: metrics.occupied_tables ?? metrics.active_tables, color: "var(--amber)" },
    { label: "Reserved Tables", value: metrics.reserved_tables ?? 0, color: "var(--info)" },
    { label: "Cleaning Tables", value: metrics.cleaning_tables ?? 0, color: "var(--danger)" },
    { label: "Pending Payments", value: metrics.pending_payments ?? 0, color: "var(--amber)" },
    { label: "Pending Payroll", value: metrics.pending_payroll_count ?? 0, color: "var(--danger)" },
    { label: "POs Today", value: metrics.purchase_orders_today ?? 0, color: "var(--accent)" },
    { label: "Pending Discounts", value: metrics.pending_discount_requests ?? 0, color: "var(--info)" },
  ];

  const localGatewayCollectionTotal = useMemo(
    () => Object.values(metrics.payment_gateway_totals || {}).reduce((sum, value) => sum + moneyNumber(value), 0),
    [metrics.payment_gateway_totals],
  );
  const localGatewayPayoutTotal = useMemo(
    () => Object.values(metrics.payout_gateway_totals || {}).reduce((sum, value) => sum + moneyNumber(value), 0),
    [metrics.payout_gateway_totals],
  );
  const localRazorpayPayments = useMemo(() => {
    return orders
      .flatMap((order) => (order.payments || [])
        .filter((payment) => payment.provider === "razorpay" || payment.method === "razorpay" || Boolean(payment.gateway_order_id))
        .map((payment) => ({
          id: payment.id,
          orderId: order.id,
          amount: moneyNumber(payment.amount),
          status: gatewayPaymentDisplayStatus(payment),
          gatewayOrderId: payment.gateway_order_id || "-",
          gatewayPaymentId: payment.gateway_payment_id || "-",
          orderStatus: order.payment_status,
          createdAt: order.created_at || "",
        })))
      .sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime());
  }, [orders]);
  const localRazorpayPayouts = useMemo(() => {
    return payrolls
      .filter((payroll) => payroll.payout_provider === "razorpayx" || Boolean(payroll.payout_id))
      .map((payroll) => ({
        id: payroll.id,
        employee: payroll.name,
        period: payroll.period,
        amount: moneyNumber(payroll.net_salary),
        status: gatewayPayoutDisplayStatus(payroll),
        payoutId: payroll.payout_id || "-",
        reference: payroll.payment_reference || "-",
      }));
  }, [payrolls]);
  const resolvedRazorpayMetrics = useMemo(
    () => resolveRazorpayDashboardMetrics(razorpayProviderSnapshot, {
      netCollections: localGatewayCollectionTotal,
      payouts: localGatewayPayoutTotal,
    }),
    [localGatewayCollectionTotal, localGatewayPayoutTotal, razorpayProviderSnapshot],
  );
  const razorpayPayments = useMemo(() => {
    if (razorpayProviderSnapshot?.payments.status !== "live") return localRazorpayPayments;
    return razorpayProviderSnapshot.payments.items.map((payment) => {
      const providerStatus = payment.status.toLowerCase();
      const displayStatus = providerStatus === "failed"
        ? "Failed"
        : providerStatus === "captured"
          ? "Captured"
          : providerStatus === "refunded"
            ? "Refunded"
            : "Pending";
      return {
        id: payment.id,
        orderId: payment.local_order_id || payment.gateway_order_id || payment.id,
        amount: moneyNumber(payment.amount),
        status: displayStatus,
        gatewayOrderId: payment.gateway_order_id || "-",
        gatewayPaymentId: payment.id,
        orderStatus: payment.status,
        createdAt: payment.created_at ? new Date(payment.created_at * 1000).toISOString() : "",
      };
    });
  }, [localRazorpayPayments, razorpayProviderSnapshot]);
  const razorpayPayouts = useMemo(() => {
    if (razorpayProviderSnapshot?.payouts.status !== "live") return localRazorpayPayouts;
    const payrollById = new Map(payrolls.map((payroll) => [payroll.id, payroll]));
    return razorpayProviderSnapshot.payouts.items.map((payout) => {
      const payroll = payout.local_payroll_id ? payrollById.get(payout.local_payroll_id) : undefined;
      return {
        id: payout.local_payroll_id || payout.id,
        employee: payroll?.name || "Payroll payout",
        period: payroll?.period || "-",
        amount: moneyNumber(payout.amount),
        status: gatewayPayoutDisplayStatus({ payout_status: payout.status, status: payout.status }),
        payoutId: payout.id,
        reference: payout.utr || "-",
      };
    });
  }, [localRazorpayPayouts, payrolls, razorpayProviderSnapshot]);
  const gatewayCollectionTotal = resolvedRazorpayMetrics.netCollections;
  const gatewayGrossCollectionTotal = resolvedRazorpayMetrics.grossCollections;
  const gatewayRefundTotal = resolvedRazorpayMetrics.refunds;
  const gatewayPayoutTotal = resolvedRazorpayMetrics.payouts;
  const pendingRazorpayPayments = razorpayPayments.filter((payment) => payment.status === "Pending").length;
  const capturedRazorpayPayments = razorpayPayments.filter((payment) => ["Captured", "Refunded"].includes(payment.status)).length;
  const gatewayNetSettlement = resolvedRazorpayMetrics.netFlow;
  const razorpayProviderMode = razorpayProviderSnapshot?.modes.payments === "test"
    || razorpayProviderSnapshot?.modes.payouts === "test"
    ? "test"
    : razorpayProviderSnapshot?.modes.payments === "live"
      ? "live"
      : "unknown";
  const razorpayDataStatus = resolvedRazorpayMetrics.status === "live"
    ? razorpayProviderMode === "live" ? "Provider live" : `Provider synced (${razorpayProviderMode})`
    : resolvedRazorpayMetrics.status === "partial"
      ? "Partial provider data"
      : resolvedRazorpayMetrics.status === "not_configured"
        ? "Local data only"
        : resolvedRazorpayMetrics.status === "unavailable"
          ? "Provider unavailable"
          : "Local data";
  const razorpayDataDetail = resolvedRazorpayMetrics.status === "live"
    ? `Razorpay API ${razorpayProviderMode} mode, ${razorpayProviderSnapshot?.window.days || 30}-day window`
    : resolvedRazorpayMetrics.status === "partial"
      ? "Live where available, local fallback for missing feeds"
      : razorpayProviderError || "Provider sync is not available";
  const gatewaySetupBadges = [
    { label: "Razorpay", service: integrationStatus?.razorpay },
    { label: "RazorpayX", service: integrationStatus?.razorpayx },
  ];
  const deliverySetupBadges = [
    { label: "Swiggy", service: integrationStatus?.swiggy },
    { label: "Zomato", service: integrationStatus?.zomato },
  ];
  const resetMailSetup = integrationStatus?.password_reset_mail;
  const setupClass = (service?: IntegrationServiceStatus) => service?.configured ? "connected" : "disconnected";
  const setupLabel = (service?: IntegrationServiceStatus) => service?.configured ? "Ready" : `Missing ${service?.missing?.length || "setup"}`;

  useEffect(() => {
    if (token && visibleNav.length > 0 && !visibleNav.some((item) => item.label === activeNav)) {
      setActiveNav(visibleNav[0].label);
    }
  }, [activeNav, token, visibleNav]);

  useEffect(() => {
    if (!token || activeNav !== "Platform" || !["super_admin", "platform_owner", "platform_admin"].includes(userRole || "")) {
      return;
    }
    Promise.allSettled([
      apiRequest<{ success: boolean; data: any }>("/api/v1/reports/platform-dashboard", { token }),
      apiRequest<{ success: boolean; data: any }>("/api/v1/reports/tenant-analytics", { token }),
    ]).then(([platformResult, tenantResult]) => {
      if (platformResult.status === "fulfilled" && platformResult.value.success) {
        setPlatformMetrics(platformResult.value.data);
      }
      if (tenantResult.status === "fulfilled" && tenantResult.value.success) {
        setTenantMetrics(tenantResult.value.data);
      }
    }).catch(() => {
      showToast("Platform metrics are unavailable", "warning");
    });
  }, [activeNav, showToast, token, userRole]);

  // ─────────────────────────────────────────────────────
  // LOGIN SCREEN
  // ─────────────────────────────────────────────────────
  if (!token) {
    return (
      <main className={`login-container ${theme}`}>
        {/* Decorative floating rings */}
        <div className="login-deco">
          <span /><span /><span /><span />
        </div>

        <div className="login-split">
          {/* Left hero panel */}
          <div className="login-hero">
            <div className="login-hero-logo">
              <div className="login-hero-icon">K</div>
              <div className="login-hero-brand-text">
                <strong>Korvexa POS</strong>
                <span>Enterprise Restaurant Suite</span>
              </div>
            </div>

            <div className="login-hero-body">
              <h1 className="login-hero-title">
                Run every branch<br />
                with <span>one system</span>
              </h1>
              <p className="login-hero-desc">
                Multi-tenant POS with real-time KDS, inventory management, HR & payroll, advanced analytics, and enterprise security.
              </p>
            </div>

            <div className="login-hero-features">
              {["Multi-tenant & branch isolation", "Kitchen Display System (KDS)", "HR · Payroll · Attendance", "Advanced reports & exports"].map((f) => (
                <div key={f} className="login-hero-feature">
                  <div className="login-hero-feature-dot" />
                  <span>{f}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Right form panel */}
          <div className="login-form-panel">
            <button type="button" className="login-theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
              <span>{theme === "light" ? "Dark" : "Light"}</span>
            </button>
            
            <h2 className="login-form-title">Welcome back</h2>
            <p className="login-form-sub">Sign in to your <strong>Korvexa</strong> account</p>

            <div className="login-system-status" aria-label="Application health status">
              <span className={`login-health-pill ${systemStatus.api}`}>
                {systemStatus.api === "connected" ? <CheckCircle2 size={13} /> : systemStatus.api === "checking" ? <Info size={13} /> : <WifiOff size={13} />}
                API {systemStatus.api === "connected" ? "Working" : systemStatus.api === "checking" ? "Checking" : "Issue"}
              </span>
              <span className={`login-health-pill ${systemStatus.db}`}>
                {systemStatus.db === "connected" ? <CheckCircle2 size={13} /> : systemStatus.db === "checking" ? <Info size={13} /> : <WifiOff size={13} />}
                DB {systemStatus.db === "connected" ? "Working" : systemStatus.db === "checking" ? "Checking" : "Issue"}
              </span>
            </div>

            <AnimatePresence>
              {authError && (
                <motion.div
                  key="err"
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="login-error-bar"
                >
                  <Lock size={15} />
                  {authError}
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={handleLogin}>
              <div className="login-field-wrap">
                <label htmlFor="login-email">Email address</label>
                <div className="login-input-row">
                  <span className="login-input-icon"><Mail size={16} /></span>
                  <input
                    id="login-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="admin@korvexa.app"
                    autoComplete="email"
                    required
                  />
                </div>
              </div>

              <div className="login-field-wrap">
                <label htmlFor="login-password">Password</label>
                <div className="login-input-row">
                  <span className="login-input-icon"><Lock size={16} /></span>
                  <input
                    id="login-password"
                    type={showPw ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    required
                    style={{ paddingRight: 44 }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "transparent", border: 0, color: "var(--text-muted)", cursor: "pointer", display: "flex" }}
                    aria-label={showPw ? "Hide password" : "Show password"}
                  >
                    {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="login-form-actions">
                <button type="button" className="login-link-button" onClick={openPasswordReset}>
                  Forgot password?
                </button>
              </div>

              <button type="submit" className="login-submit-btn" disabled={authLoading}>
                {authLoading ? "Signing in…" : "Sign in to Dashboard →"}
              </button>
            </form>

            <p className="login-footer-note">
              Protected by <span>Korvexa Security</span> · Multi-tenant isolation enabled
            </p>
          </div>
        </div>

        {showPasswordReset && (
            <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <motion.div className="modal-box narrow login-reset-modal" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
                <div className="modal-head">
                  <div>
                    <h2>{resetToken ? "Set new password" : "Forgot password"}</h2>
                    <p>{resetToken ? "Create a new password for your account." : "Enter your account email to receive a reset link."}</p>
                  </div>
                  <button className="modal-close" type="button" onClick={closePasswordReset} aria-label="Close">
                    <X size={16} />
                  </button>
                </div>

                {forgotError && (
                  <div className="login-reset-feedback error">
                    <AlertTriangle size={15} />
                    <span>{forgotError}</span>
                  </div>
                )}
                {forgotMessage && (
                  <div className="login-reset-feedback success">
                    <CheckCircle2 size={15} />
                    <span>{forgotMessage}</span>
                  </div>
                )}

                {resetToken ? (
                  <form onSubmit={handleResetPassword} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div className="form-group">
                      <label htmlFor="reset-password">New password</label>
                      <input
                        id="reset-password"
                        type="password"
                        value={resetPassword}
                        onChange={(e) => setResetPassword(e.target.value)}
                        autoComplete="new-password"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="reset-confirm">Confirm password</label>
                      <input
                        id="reset-confirm"
                        type="password"
                        value={resetConfirm}
                        onChange={(e) => setResetConfirm(e.target.value)}
                        autoComplete="new-password"
                        required
                      />
                    </div>
                    <div className="modal-footer">
                      <Button variant="ghost" type="button" onClick={closePasswordReset}>Cancel</Button>
                      <Button type="submit" disabled={resetLoading}>{resetLoading ? "Updating..." : "Update password"}</Button>
                    </div>
                  </form>
                ) : (
                  <form onSubmit={handleForgotPassword} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div className="form-group">
                      <label htmlFor="forgot-email">Email address</label>
                      <input
                        id="forgot-email"
                        type="email"
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        placeholder="admin@korvexa.app"
                        autoComplete="email"
                        required
                      />
                    </div>
                    <div className="modal-footer">
                      <Button variant="ghost" type="button" onClick={closePasswordReset}>Cancel</Button>
                      <Button type="submit" disabled={forgotLoading}>{forgotLoading ? "Sending..." : "Send reset link"}</Button>
                    </div>
                  </form>
                )}
              </motion.div>
            </motion.div>
        )}

      </main>
    );
  }

  // ─────────────────────────────────────────────────────
  // APP SHELL
  // ─────────────────────────────────────────────────────
  return (
    <>
      <ToastContainer toasts={toasts} dismiss={dismissToast} />

      <main className={`app-shell ${theme}`}>
        {/* ── Sidebar ────────────────────────────────── */}
        <aside className="sidebar">
          <div className="brand" onClick={() => setActiveNav("Dashboard")} style={{ cursor: "pointer" }}>
            <div className="brand-mark">K</div>
            <div>
              <strong>Korvexa POS</strong>
              <span>{branch?.name || "Loading…"}</span>
            </div>
          </div>

          <nav>
            {visibleNav.map((item) => {
              const Icon = item.icon;
              const badge =
                item.label === "Orders" ? activeOrderCount :
                item.label === "Online Delivery" ? newOnlineDeliveryCount :
                item.label === "KDS" ? kdsNewCount :
                item.label === "Dashboard" ? pendingDiscountCount :
                0;
              return (
                <button
                  key={item.label}
                  className={activeNav === item.label ? "active" : ""}
                  onClick={() => setActiveNav(item.label)}
                  title={item.label}
                >
                  <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <Icon size={17} />
                    {badge > 0 && (
                      <span style={{ position: "absolute", top: -6, right: -8, minWidth: 16, height: 16, borderRadius: 999, background: "var(--danger)", color: "#fff", fontSize: "0.6rem", fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 3px" }}>
                        {badge}
                      </span>
                    )}
                  </div>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="offline" onClick={handleLogout} role="button" aria-label="Log out">
            <LogOut size={16} />
            <span>Log Out</span>
          </div>
        </aside>

        {/* ── Workspace ──────────────────────────────── */}
        <section className="workspace">
          {/* Topbar */}
          <header className="topbar">
            <div>
              <p>{branch?.name || "Loading…"}</p>
              <h1>{activeNav}</h1>
            </div>
            <div className="context">
              <LiveClock />
              <span className={`status-chip ${systemStatus.api === "connected" ? "connected" : "disconnected"}`}>
                {systemStatus.api === "connected" ? <CheckCircle2 size={13} /> : <WifiOff size={13} />}
                API {systemStatus.api === "connected" ? "Connected" : systemStatus.api === "checking" ? "Checking" : "Disconnected"}
              </span>
              <span className={`status-chip ${systemStatus.db === "connected" ? "connected" : "disconnected"}`}>
                {systemStatus.db === "connected" ? <CheckCircle2 size={13} /> : <WifiOff size={13} />}
                DB {systemStatus.db === "connected" ? "Connected" : systemStatus.db === "checking" ? "Checking" : "Disconnected"}
              </span>
              <span>{email}</span>
              <button title="Toggle theme" onClick={toggleTheme} aria-label="Toggle colour theme">
                {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
              </button>
            </div>
          </header>

          {/* ── Animated page switcher ── */}
          <AnimatePresence mode="wait">
            <motion.div key={activeNav} variants={pageVariants} initial="hidden" animate="visible" exit="exit">

              {/* ══════════════════════════════════════
                  1. DASHBOARD
                 ══════════════════════════════════════ */}
              {activeNav === "Dashboard" && (
                <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>

                  <AnimatePresence>
                    {metrics.notifications?.map((n: any, i: number) => (
                      <motion.div key={i} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        style={{ overflow: "hidden" }}>
                        <div style={{ background: "rgba(251,191,36,0.15)", border: "1px solid rgba(251,191,36,0.4)", borderRadius: 12, padding: "12px 16px", color: "#d97706", display: "flex", gap: 12, alignItems: "center" }}>
                          <AlertTriangle size={18} />
                          <div style={{ flex: 1, fontSize: "0.85rem", fontWeight: 600 }}>{n.message}</div>
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>

                  {/* Metric cards */}
                  <div className="metrics">
                    {[
                      { label: "Today's Sales",  value: `Rs. ${metrics.today_collection ?? metrics.today_sales}`, trend: `${metrics.today_orders ?? 0} orders today`, up: true,  icon: DollarSign,  color: "var(--accent)",   sparkline: "M0,15 L20,13 L40,16 L60,8 L80,11 L100,3" },
                      { label: "Orders",         value: String(metrics.today_orders ?? 0), trend: `${metrics.pending_orders ?? 0} pending now`,  up: true,  icon: ShoppingCart, color: "var(--info)",     sparkline: "M0,18 L20,14 L40,10 L60,12 L80,4 L100,1" },
                      { label: "Active Tables",  value: String(metrics.active_tables),       trend: "Live",   up: true,  icon: Table2,       color: "var(--amber)",    sparkline: "M0,10 L30,12 L60,9 L80,11 L100,8" },
                      { label: "Active Staff",   value: String(metrics.active_staff ?? 0),   trend: activeStaffDetails.length ? `${activeStaffDetails[0].name} checked in` : `${metrics.attendance_today ?? 0} attended`, up: true, icon: Users,   color: "var(--success)", sparkline: "M0,15 L30,12 L70,8 L100,2" },
                      { label: "Low Stock",      value: String(metrics.low_stock_alerts),    trend: `${metrics.total_stock_items ?? 0} items`,  up: false, icon: AlertTriangle, color: metrics.low_stock_alerts > 0 ? "var(--danger)" : "var(--text-muted)", sparkline: "M0,5 L30,8 L60,12 L80,14 L100,18" },
                    ].map((m) => {
                      const Icon = m.icon;
                      return (
                        <motion.div
                          key={m.label}
                          className="metric-card"
                          whileHover={{ y: -4 }}
                          style={{ borderColor: m.label === "Low Stock" && metrics.low_stock_alerts > 0 ? "var(--danger)" : undefined }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span>{m.label}</span>
                            <div style={{ width: 32, height: 32, borderRadius: 8, background: m.color + "18", display: "flex", alignItems: "center", justifyContent: "center" }}>
                              <Icon size={15} color={m.color} />
                            </div>
                          </div>
                          <strong style={{ color: m.label === "Low Stock" && metrics.low_stock_alerts > 0 ? "var(--danger)" : undefined }}>{m.value}</strong>
                          <div className={`trend ${m.up ? "" : "down"}`}>
                            {m.up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                            {m.trend}
                          </div>
                          <svg viewBox="0 0 100 20" width="100%" height="20" style={{ marginTop: 4 }}>
                            <path d={m.sparkline} fill="none" stroke={m.color} strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        </motion.div>
                      );
                    })}
                  </div>

                  {/* Bottom 2-col panels */}
                  <div className="pos-layout">
                    {/* Sales charts */}
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Sales Performance</h2>
                          <p>Daily sales, weekly attendance, and monthly attendance</p>
                        </div>
                      </div>
                      <div className="sales-performance-grid">
                        <div>
                          <h4 style={{ margin: "0 0 8px 0", fontSize: "0.85rem", fontWeight: 700 }}>Daily Sales (Mon-Sun)</h4>
                          <div className="svg-chart-container labeled">
                            {dailySales.map((val, idx) => (
                              <div key={`${dailyLabels[idx]}-${idx}`} className="chart-bar-wrap">
                                <div className="chart-bar" style={{ height: `${Math.max((val / maxDailySales) * 100, val > 0 ? 8 : 3)}%` }}>
                                  <span className="chart-tooltip">Rs. {val.toLocaleString()}</span>
                                </div>
                                <span className="chart-label">{dailyLabels[idx]}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="last-month-sales-card">
                          <span>Last Month Sales</span>
                          <strong>Rs. {metrics.last_month_sales ?? metrics.sales_charts?.last_month_sales?.toFixed(2) ?? "0.00"}</strong>
                          <small>Previous calendar month completed sales</small>
                        </div>
                      </div>
                      <div className="weekly-attendance-card">
                        <div className="weekly-attendance-head">
                          <div>
                            <strong>Weekly Attendance</strong>
                            <span>All working users, including managers</span>
                          </div>
                          <small>{weeklyAttendance.users.length} users</small>
                        </div>
                        {weeklyAttendance.users.length === 0 ? (
                          <p>No weekly attendance data yet</p>
                        ) : (
                          <div className="weekly-attendance-list">
                            <div className="weekly-attendance-row header">
                              <span>User</span>
                              {weeklyAttendance.labels.map((label) => <small key={label}>{label}</small>)}
                              <small>Total</small>
                            </div>
                            {weeklyAttendance.users.slice(0, 8).map((person) => (
                              <div key={person.id} className="weekly-attendance-row">
                                <span>
                                  {person.name}
                                  <em>{person.role || "Staff"}</em>
                                </span>
                                {person.days.map((status, idx) => (
                                  <small key={`${person.id}-${idx}`} className={`attendance-dot ${status}`} title={status}>
                                    {status === "active" ? "A" : status === "present" ? "P" : "-"}
                                  </small>
                                ))}
                                <small>{person.present_days}/7</small>
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="monthly-attendance-card">
                          <div className="weekly-attendance-head">
                            <div>
                              <strong>Monthly Attendance</strong>
                              <span>{monthlyAttendance.month || "Current month"} month-to-date</span>
                            </div>
                            <small>{monthlyAttendance.users.length} users</small>
                          </div>
                          {monthlyAttendance.users.length === 0 ? (
                            <p>No monthly attendance data yet</p>
                          ) : (
                            <div className="monthly-attendance-list">
                              {monthlyAttendance.users.slice(0, 8).map((person) => (
                                <div key={person.id} className="monthly-attendance-row">
                                  <span>
                                    {person.name}
                                    <em>{person.role || "Staff"}</em>
                                  </span>
                                  <strong>{person.present_days}/{person.total_days}</strong>
                                  <small>{person.attendance_percent}%</small>
                                  <div className="monthly-attendance-meter" aria-hidden="true">
                                    <i style={{ width: `${Math.min(Math.max(person.attendance_percent, 0), 100)}%` }} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Live manager operations */}
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Live Manager Operations</h2>
                          <p>Tables, payments, payroll, purchase orders, and approvals</p>
                        </div>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: 999, background: "var(--accent-soft)", color: "var(--accent)" }}>
                          Live
                        </span>
                      </div>
                      <div className="today-sales-split">
                        <div>
                          <span>Total Collection</span>
                          <strong>Rs. {metrics.today_collection ?? metrics.today_sales}</strong>
                        </div>
                        <div>
                          <span>Dine In</span>
                          <strong>{todayOrderTypes.dine_in.orders}</strong>
                          <small>Rs. {todayOrderTypes.dine_in.sales}</small>
                        </div>
                        <div>
                          <span>Takeaway</span>
                          <strong>{todayOrderTypes.takeaway.orders}</strong>
                          <small>Rs. {todayOrderTypes.takeaway.sales}</small>
                        </div>
                        <div>
                          <span>Delivery</span>
                          <strong>{todayOrderTypes.delivery.orders}</strong>
                          <small>Rs. {todayOrderTypes.delivery.sales}</small>
                        </div>
                        <div>
                          <span>Gateway Collection</span>
                          <strong>Rs. {Object.values(metrics.payment_gateway_totals || {}).reduce((sum, value) => sum + parseFloat(value || "0"), 0).toFixed(2)}</strong>
                          <small>{Object.keys(metrics.payment_gateway_totals || {}).join(", ") || "No gateway"}</small>
                        </div>
                        <div>
                          <span>Gateway Payouts</span>
                          <strong>Rs. {Object.values(metrics.payout_gateway_totals || {}).reduce((sum, value) => sum + parseFloat(value || "0"), 0).toFixed(2)}</strong>
                          <small>{Object.keys(metrics.payout_gateway_totals || {}).join(", ") || "No gateway"}</small>
                        </div>
                      </div>
                      <div className="active-staff-list">
                        <div className="active-staff-list-head">
                          <strong>Active Staff</strong>
                          <span>{activeStaffDetails.length} checked in</span>
                        </div>
                        {activeStaffDetails.length === 0 ? (
                          <p>No staff currently checked in</p>
                        ) : activeStaffDetails.slice(0, 5).map((staff) => (
                          <div key={staff.id} className="active-staff-row">
                            <span>{staff.name}</span>
                            <small>{staff.role || "Staff"} · Check-in {staff.check_in_time}</small>
                          </div>
                        ))}
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                        {liveOperations.map((item) => (
                          <div key={item.label} style={{ padding: 12, borderRadius: 10, background: "var(--surface-soft)", border: "1px solid var(--border)" }}>
                            <span style={{ display: "block", color: "var(--text-muted)", fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase" }}>{item.label}</span>
                            <strong style={{ color: item.color, fontSize: "1.25rem", fontVariantNumeric: "tabular-nums" }}>{item.value}</strong>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                        {Object.entries(orderStatusCounts).length === 0 ? (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>No order status data yet</span>
                        ) : Object.entries(orderStatusCounts).map(([status, count]) => (
                          <div key={status} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", color: "var(--text-soft)" }}>
                            <span style={{ textTransform: "capitalize" }}>{status}</span>
                            <strong>{count}</strong>
                          </div>
                        ))}
                      </div>

                      <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
                        <h4 style={{ margin: "0 0 10px 0", fontSize: "0.85rem", fontWeight: 700, color: "var(--amber)" }}>Discount Approvals</h4>
                        {discountRequests.length === 0 ? (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>No pending discount requests</span>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {discountRequests.map(req => (
                              <div key={req.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, background: "var(--amber-soft)", padding: 12, borderRadius: 8, border: "1px solid color-mix(in srgb, var(--amber) 28%, transparent)" }}>
                                <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                                  <strong style={{ display: "block", fontSize: "0.82rem", color: "var(--amber)" }}>
                                    Order #{req.order_id.slice(0, 8)} - {req.is_percentage ? `${req.amount_or_percentage}%` : `Rs. ${req.amount_or_percentage}`} discount
                                  </strong>
                                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Requested by {req.requested_by_name || req.requested_by_id}</span>
                                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, fontSize: "0.72rem" }}>
                                    <span><b>Bill</b><br />Rs. {parseFloat(req.bill_total || "0").toFixed(2)}</span>
                                    <span><b>Discount</b><br />Rs. {parseFloat(req.discount_amount || "0").toFixed(2)}</span>
                                    <span><b>Payable</b><br />Rs. {parseFloat(req.proposed_total || "0").toFixed(2)}</span>
                                  </div>
                                </div>
                                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                                  <Button variant="success" onClick={async () => {
                                    try {
                                      await apiRequest(`/api/v1/discounts/requests/${req.id}/approve`, { method: "PATCH", token, body: JSON.stringify({ status: "approved" }) });
                                      showToast("Discount approved", "success");
                                      initData();
                                    } catch { showToast("Failed to approve discount", "error"); }
                                  }} style={{ fontSize: "0.7rem", minHeight: 32, padding: "0 10px" }}>Accept</Button>
                                  <Button variant="danger" onClick={async () => {
                                    try {
                                      await apiRequest(`/api/v1/discounts/requests/${req.id}/approve`, { method: "PATCH", token, body: JSON.stringify({ status: "rejected" }) });
                                      showToast("Discount rejected", "info");
                                      initData();
                                    } catch { showToast("Failed to reject discount", "error"); }
                                  }} style={{ fontSize: "0.7rem", minHeight: 32, padding: "0 10px" }}>Reject</Button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  2. POS BILLING
                 ══════════════════════════════════════ */}
              {activeNav === "POS Billing" && (
                <section className="pos-layout">
                  {/* Menu panel */}
                  <section className="panel">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <h2>Menu Items</h2>
                      {/* Order type segmented control */}
                      <div style={{ display: "flex", gap: 4, padding: 4, borderRadius: 10, background: "var(--surface-soft)", border: "1px solid var(--border)" }}>
                        {(["dine_in", "takeaway", "delivery"] as const).map((type) => (
                          <button
                            key={type}
                            onClick={() => setOrderType(type)}
                            style={{ padding: "6px 14px", borderRadius: 7, fontSize: "0.78rem", fontWeight: 600, transition: "all 0.15s ease", background: orderType === type ? "var(--accent)" : "transparent", color: orderType === type ? "#fff" : "var(--text-muted)", border: 0 }}
                          >
                            {type === "dine_in" ? "🪑 Dine In" : type === "takeaway" ? "🛍 Takeaway" : "🛵 Delivery"}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Search */}
                    <div style={{ position: "relative", marginBottom: 16 }}>
                      <Search size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search dishes…"
                        style={{ width: "100%", padding: "10px 36px 10px 36px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface-soft)", color: "var(--text)", fontSize: "0.875rem", outline: "none" }}
                      />
                      {search && (
                        <button onClick={() => setSearch("")} style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "transparent", border: 0, color: "var(--text-muted)", cursor: "pointer", display: "flex" }}>
                          <X size={14} />
                        </button>
                      )}
                    </div>

                    {/* Category pills */}
                    <div className="categories-pills">
                      <button className={posCategory === "All" ? "active" : ""} onClick={() => setPosCategory("All")}>All</button>
                      {categories.map((cat) => (
                        <button key={cat.id} className={posCategory === cat.id ? "active" : ""} onClick={() => setPosCategory(cat.id)}>{cat.name}</button>
                      ))}
                    </div>

                    {/* Product grid */}
                    <div className="pos-products">
                      {filteredProducts.length === 0 ? (
                        <div style={{ gridColumn: "1/-1", textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                          <Utensils size={36} style={{ margin: "0 auto 12px", display: "block", opacity: 0.3 }} />
                          <span style={{ fontSize: "0.875rem" }}>No items found</span>
                        </div>
                      ) : filteredProducts.map((p) => (
                        <motion.button key={p.id} className="product-item" onClick={() => addProductToCart(p)} whileHover={{ y: -3 }} whileTap={{ scale: 0.97 }}>
                          <strong>{p.name}</strong>
                          <span className="price">₹{parseFloat(p.price).toFixed(2)}</span>
                          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Tax: {p.tax_rate}%</span>
                        </motion.button>
                      ))}
                    </div>
                  </section>

                  {/* Cart panel */}
                  <section className="panel" style={{ display: "flex", flexDirection: "column" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <ShoppingCart size={18} />
                        <h2>Active Order Cart</h2>
                        {cart.length > 0 && <span style={{ minWidth: 20, height: 20, borderRadius: 999, background: "var(--accent)", color: "#fff", fontSize: "0.68rem", fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 5px" }}>{cart.length}</span>}
                      </div>
                    </div>

                    <div className="form-group" style={{ marginBottom: 16 }}>
                      <label>Assign Table</label>
                      <select value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}>
                        {tables.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.floor_area})</option>)}
                      </select>
                    </div>

                    <div className="cart-scroll" style={{ flex: 1 }}>
                      {cart.length === 0 ? (
                        <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text-muted)" }}>
                          <ShoppingCart size={36} style={{ margin: "0 auto 12px", display: "block", opacity: 0.2 }} />
                          <span style={{ fontSize: "0.875rem" }}>Your cart is empty</span><br />
                          <span style={{ fontSize: "0.78rem", marginTop: 4, display: "inline-block" }}>Select items from the menu</span>
                        </div>
                      ) : cart.map((item) => (
                        <div key={item.product.id} className="cart-row">
                          <div>
                            <strong style={{ fontSize: "0.875rem" }}>{item.product.name}</strong>
                            <span style={{ display: "block", fontSize: "0.78rem", color: "var(--text-muted)" }}>₹{parseFloat(item.product.price).toFixed(2)} each</span>
                          </div>
                          <div className="cart-qty-ctrl">
                            <button onClick={() => setCart((items) => items.map((i) => i.product.id === item.product.id ? { ...i, quantity: Math.max(1, i.quantity - 1) } : i))}>−</button>
                            <span style={{ fontWeight: 700, minWidth: 20, textAlign: "center" }}>{item.quantity}</span>
                            <button onClick={() => addProductToCart(item.product)}>+</button>
                          </div>
                          <strong style={{ fontVariantNumeric: "tabular-nums" }}>₹{(parseFloat(item.product.price) * item.quantity).toFixed(2)}</strong>
                        </div>
                      ))}
                    </div>

                    {/* Totals card */}
                    {cart.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, background: "var(--surface-soft)", border: "1px solid var(--border)", padding: 16, borderRadius: 12, margin: "12px 0" }}>
                        {[["Subtotal", `₹${totals.subtotal.toFixed(2)}`], ["Tax", `₹${totals.tax.toFixed(2)}`], ["Discount", `-₹${totals.discount.toFixed(2)}`]].map(([label, val]) => (
                          <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.875rem" }}>
                            <span style={{ color: "var(--text-muted)" }}>{label}</span>
                            <strong style={{ color: label === "Discount" ? "var(--danger)" : "var(--text)" }}>{val}</strong>
                          </div>
                        ))}
                        <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid var(--border)", paddingTop: 10, fontSize: "1.05rem" }}>
                          <strong>Grand Total</strong>
                          <strong style={{ color: "var(--accent)" }}>₹{totals.total.toFixed(2)}</strong>
                        </div>
                        <button onClick={handleRequestDiscountApproval} style={{ padding: "8px", background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 8, color: "var(--text-muted)", fontSize: "0.8rem", cursor: "pointer", marginTop: 4 }}>
                          + Request Discount Approval
                        </button>
                      </div>
                    )}

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: "auto" }}>
                      <Button variant="secondary" onClick={() => handleCreateOrder("held")}>Hold Order</Button>
                      <Button variant="default" onClick={() => handleCreateOrder("active")}>Send to Kitchen</Button>
                      <Button variant="default" onClick={handleGatewayCartPayment} style={{ gridColumn: "span 2" }}>
                        <CreditCard size={16} /> Pay Online - Rs. {totals.total.toFixed(2)}
                      </Button>
                      <Button variant="success" onClick={() => handlePayment("cash")} style={{ gridColumn: "span 2" }}>
                        ✓ Quick Cash Checkout — ₹{totals.total.toFixed(2)}
                      </Button>
                    </div>
                  </section>
                </section>
              )}

              {/* ══════════════════════════════════════
                  3. TABLE MANAGEMENT
                 ══════════════════════════════════════ */}
              {activeNav === "Table Management" && (
                <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="panel">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <div>
                        <h2>Visual Floor Plan</h2>
                        <p>Real-time table status across all floors</p>
                      </div>
                      <div className="floor-plan-actions">
                        <form onSubmit={handleMergeTables} className="merge-tables-form">
                          <select aria-label="Table A" className="table-select" value={mergeT1} onChange={(e) => setMergeT1(e.target.value)} required>
                            <option value="">Table A</option>
                            {tables.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                          </select>
                          <span className="merge-plus">+</span>
                          <select aria-label="Table B" className="table-select" value={mergeT2} onChange={(e) => setMergeT2(e.target.value)} required>
                            <option value="">Table B</option>
                            {tables.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                          </select>
                          <Button type="submit" variant="default" style={{ whiteSpace: "nowrap" }}>Merge Tables</Button>
                        </form>
                        <Button type="button" variant="default" onClick={handleAddTable} style={{ whiteSpace: "nowrap" }}>
                          <Plus size={16} /> Add Table
                        </Button>
                      </div>
                    </div>

                    {/* Legend */}
                    <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
                      {[["available","var(--success)","Available"],["occupied","var(--amber)","Occupied"],["reserved","var(--accent)","Reserved"],["cleaning","var(--text-muted)","Cleaning"]].map(([k,c,l]) => (
                        <div key={k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.75rem", color: "var(--text-soft)" }}>
                          <div style={{ width: 8, height: 8, borderRadius: 2, background: c }} />
                          {l}
                        </div>
                      ))}
                    </div>

                    <div className="floor-toolbar">
                      <div className="floor-selector">
                        {floorOptions.map((f) => (
                          <button key={f} className={selectedFloor === f ? "active" : ""} onClick={() => setSelectedFloor(f)}>
                            {f}
                            <span>{tables.filter((table) => table.floor_area === f).length}</span>
                          </button>
                        ))}
                      </div>
                      <form className="add-floor-form" onSubmit={handleCreateFloor}>
                        <input
                          aria-label="New floor name"
                          value={newFloorName}
                          maxLength={64}
                          onChange={(e) => setNewFloorName(e.target.value)}
                          placeholder="Add floor"
                        />
                        <Button type="submit" variant="secondary" disabled={!newFloorName.trim()}>
                          <Plus size={14} /> Floor
                        </Button>
                      </form>
                      <div className="floor-edit-actions">
                        {editingFloor === selectedFloor ? (
                          <form className="edit-floor-form" onSubmit={handleSaveFloorRename}>
                            <input
                              aria-label="Edit floor name"
                              value={editFloorName}
                              maxLength={64}
                              onChange={(e) => setEditFloorName(e.target.value)}
                              autoFocus
                            />
                            <Button type="submit" variant="default" disabled={!editFloorName.trim()}>Save</Button>
                            <Button type="button" variant="ghost" onClick={() => { setEditingFloor(""); setEditFloorName(""); }}>Cancel</Button>
                          </form>
                        ) : (
                          <>
                            <Button type="button" variant="secondary" onClick={handleStartEditFloor}>
                              <Edit2 size={14} /> Edit Floor
                            </Button>
                            <Button
                              type="button"
                              variant="danger"
                              onClick={handleDeleteFloor}
                              disabled={tables.some((table) => table.floor_area === selectedFloor)}
                              title={tables.some((table) => table.floor_area === selectedFloor) ? "Move or delete tables before deleting this floor" : "Delete selected floor"}
                            >
                              <Trash2 size={14} /> Delete Floor
                            </Button>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="visual-tables-grid">
                      {tables.filter((t) => t.floor_area === selectedFloor).map((t, idx) => (
                        <motion.div key={t.id} className={`table-card ${t.status}`}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: idx * 0.05, duration: 0.2 }}
                          whileHover={{ y: -5, scale: 1.03 }} whileTap={{ scale: 0.97 }}
                        >
                          <div className="table-card-top">
                            <div>
                              <h3>{t.name}</h3>
                              <span>{t.capacity} seats</span>
                            </div>
                            <div className="status-pill">{statusLabel(t.status)}</div>
                          </div>
                          <div className="table-card-meta">
                            <span>{t.floor_area}</span>
                            {t.merged_with && <span className="merge-tag">Merged</span>}
                            {t.order_id && <span className="merge-tag">Order active</span>}
                          </div>
                          <div className="table-card-actions">
                            <Button variant="default" type="button" onClick={() => handleOpenTableQr(t)}>
                              <Smartphone size={14} /> QR Order
                            </Button>
                            <Button variant="secondary" type="button" onClick={() => handleEditTable(t)}>
                              <Edit2 size={14} /> Edit
                            </Button>
                          {t.merged_with && (
                            <Button variant="secondary" type="button" onClick={() => handleSplitTable(t.id)}>
                              Unmerge Table
                            </Button>
                          )}
                          {t.status === "occupied" && !t.merged_with && (
                            <Button variant="secondary" type="button" onClick={() => handleTableStatus(t.id, "cleaning")}>
                              Mark Cleaning
                            </Button>
                          )}
                          {t.status === "cleaning" && !t.merged_with && (
                            <Button variant="success" type="button" onClick={() => handleTableStatus(t.id, "available")}>
                              Mark Available
                            </Button>
                          )}
                          {t.status === "available" && !t.merged_with && (
                            <Button variant="default" type="button" onClick={() => handleReserveTable(t.id)}>
                              Reserve Table
                            </Button>
                          )}
                          {t.status === "reserved" && !t.merged_with && (
                            <Button variant="success" type="button" onClick={() => handleTableStatus(t.id, "available")}>
                              Release Reservation
                            </Button>
                          )}
                          {t.status !== "out_of_service" && !t.merged_with && t.status !== "occupied" && (
                            <Button variant="secondary" type="button" onClick={() => handleTableStatus(t.id, "out_of_service")}>
                              Unavailable
                            </Button>
                          )}
                          {t.status === "out_of_service" && !t.merged_with && (
                            <Button variant="success" type="button" onClick={() => handleTableStatus(t.id, "available")}>
                              Make Available
                            </Button>
                          )}
                          {t.status !== "occupied" && !t.merged_with && (
                            <Button variant="danger" type="button" onClick={() => handleDeleteTable(t.id)}>
                              <Trash2 size={14} /> Delete
                            </Button>
                          )}
                          </div>
                        </motion.div>
                      ))}
                      {tables.filter((t) => t.floor_area === selectedFloor).length === 0 && (
                        <div style={{ gridColumn: "1/-1", textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                          <Table2 size={36} style={{ margin: "0 auto 12px", display: "block", opacity: 0.2 }} />
                          <span>No tables on {selectedFloor}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  4. ORDERS
                 ══════════════════════════════════════ */}
              {activeNav === "Orders" && (
                <section className="panel">
                  <div className="panel-head">
                    <div>
                      <h2>Orders Console</h2>
                      <p>Manage active and past orders</p>
                    </div>
                    <div style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{orders.length} orders at {branch?.name || "this branch"}</span>
                        <button onClick={() => exportToExcel(orders, "Orders_Export")} style={{ padding: "8px 14px", background: "var(--info-soft)", color: "var(--info)", border: "1px solid var(--info)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease", display: "flex", alignItems: "center", gap: 6 }}><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg> Export Excel</button>
                      <button onClick={() => { if (branch) { refreshOrders(branch.id); refreshMetrics(branch.id); } }} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8, background: "var(--surface-soft)", border: "1px solid var(--border)", color: "var(--text-soft)", fontSize: "0.8rem", fontWeight: 600, cursor: "pointer" }}>
                        <RefreshCw size={13} className={isRefreshing ? "spin" : ""} /> Refresh
                      </button>
                    </div>
                  </div>
                  <div className="order-type-tabs">
                    {[
                      { key: "dine_in", label: "Dine In", count: orders.filter((order) => order.order_type === "dine_in").length },
                      { key: "takeaway", label: "Takeaway", count: orders.filter((order) => order.order_type === "takeaway").length },
                      { key: "delivery", label: "Delivery", count: orders.filter((order) => order.order_type === "delivery").length },
                    ].map((tab) => (
                      <button key={tab.key} className={ordersTab === tab.key ? "active" : ""} onClick={() => setOrdersTab(tab.key as typeof ordersTab)}>
                        <span>{tab.label}</span>
                        <strong>{tab.count}</strong>
                      </button>
                    ))}
                  </div>

                  <div className="orders-filter-grid">
                    <input aria-label="Filter order ID" placeholder="Order ID" value={orderFilters.orderId} onChange={(e) => setOrderFilters((prev) => ({ ...prev, orderId: e.target.value }))} />
                    <select aria-label="Filter type" value={orderFilters.type} onChange={(e) => setOrderFilters((prev) => ({ ...prev, type: e.target.value }))}>
                      <option value="">All Types</option>
                      <option value="dine_in">Dine In</option>
                      <option value="takeaway">Takeaway</option>
                      <option value="delivery">Delivery</option>
                    </select>
                    {ordersTab === "dine_in" && (
                      <input aria-label="Filter table number" placeholder="Table No" value={orderFilters.tableNo} onChange={(e) => setOrderFilters((prev) => ({ ...prev, tableNo: e.target.value }))} />
                    )}
                    <input aria-label="Filter items" placeholder="Items" value={orderFilters.items} onChange={(e) => setOrderFilters((prev) => ({ ...prev, items: e.target.value }))} />
                    <input aria-label="Filter total" placeholder="Total" value={orderFilters.total} onChange={(e) => setOrderFilters((prev) => ({ ...prev, total: e.target.value }))} />
                    <select aria-label="Filter KDS" value={orderFilters.kds} onChange={(e) => setOrderFilters((prev) => ({ ...prev, kds: e.target.value }))}>
                      <option value="">All KDS</option>
                      {Object.keys(kdsStatusMap).map((status) => <option key={status} value={status}>{kdsStatusMap[status].label}</option>)}
                    </select>
                    <select aria-label="Filter payment" value={orderFilters.payment} onChange={(e) => setOrderFilters((prev) => ({ ...prev, payment: e.target.value }))}>
                      <option value="">All Payment</option>
                      {Object.keys(payStatusMap).map((status) => <option key={status} value={status}>{payStatusMap[status].label}</option>)}
                    </select>
                    <select aria-label="Filter status" value={orderFilters.status} onChange={(e) => setOrderFilters((prev) => ({ ...prev, status: e.target.value }))}>
                      <option value="">All Status</option>
                      {Object.keys(orderStatusMap).map((status) => <option key={status} value={status}>{orderStatusMap[status].label}</option>)}
                    </select>
                    <button type="button" onClick={() => setOrderFilters({ orderId: "", type: "", tableNo: "", items: "", total: "", kds: "", payment: "", status: "" })}>Clear</button>
                  </div>

                  <div className="orders-table-wrap">
                    <table className="data-table orders-table">
                      <thead>
                        <tr>
                          <th>Order ID</th>
                          <th>Type</th>
                          {ordersTab === "dine_in" && <th>Table No</th>}
                          <th>Items</th>
                          <th>Total</th>
                          <th>KDS</th>
                          <th>Payment</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ordersForTab.length === 0 ? (
                          <tr><td colSpan={ordersTab === "dine_in" ? 9 : 8} style={{ textAlign: "center", padding: "30px", color: "var(--text-muted)" }}>No {ordersTab.replace("_", " ")} orders match these filters.</td></tr>
                        ) : ordersForTab.map((o) => (
                          <tr key={o.id}>
                            <td><code style={{ fontSize: "0.78rem", background: "var(--surface-soft)", padding: "2px 6px", borderRadius: 4 }}>#{o.id.slice(0, 8)}</code></td>
                            <td style={{ textTransform: "capitalize" }}>{o.order_type.replace("_", " ")}</td>
                            {ordersTab === "dine_in" && <td>{o.table_id ? tableNameById.get(o.table_id) || o.table_id.slice(0, 6) : "No Table"}</td>}
                            <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                              {(o.items || []).slice(0, 2).map((item) => `${item.quantity}x ${item.name}`).join(", ") || "No items"}
                              {(o.items?.length ?? 0) > 2 ? ` +${(o.items?.length ?? 0) - 2}` : ""}
                            </td>
                            <td style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>Rs. {parseFloat(o.total).toFixed(2)}</td>
                            <td><StatusBadge value={o.kds_status} map={kdsStatusMap} /></td>
                            <td><StatusBadge value={o.payment_status} map={payStatusMap} /></td>
                            <td><StatusBadge value={o.status} map={orderStatusMap} /></td>
                            <td>
                              <div className="order-actions">
                                {ordersTab === "dine_in" && o.status === "held" && (
                                  <button type="button" onClick={() => handleOrderToKDS(o.id)}><ChefHat size={13} />KDS</button>
                                )}
                                {ordersTab === "dine_in" && o.status !== "held" && o.kds_status !== "served" && (
                                  <button type="button" onClick={() => handleOrderServed(o.id)}><CheckCircle2 size={13} />Served</button>
                                )}
                                {ordersTab === "dine_in" && (
                                  <button type="button" onClick={() => handlePrintBill(o.id)}><Printer size={13} />Print Bill</button>
                                )}
                                {["unpaid", "partial"].includes(o.payment_status) && (
                                  <>
                                    <button type="button" className="success" onClick={() => handleGatewayCashOutOrder(o)}><CreditCard size={13} />Pay Online</button>
                                    <button type="button" className="success" onClick={() => handleCashOutOrder(o)}><Banknote size={13} />Cash-out</button>
                                  </>
                                )}
                                {canRefundOrder(o) && (
                                  <button type="button" className="danger" onClick={() => openRefundWizard(o)}><RotateCcw size={13} />Refund</button>
                                )}
                                {o.status === "held" && (
                                  <button type="button" className="danger" onClick={() => handleDeleteHeldOrder(o)}><X size={13} />Delete</button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  5. KDS
                 ══════════════════════════════════════ */}
              {activeNav === "Online Delivery" && (
                <section className="online-delivery-page">
                  <div className="online-delivery-summary">
                    {[
                      { label: "New", value: newOnlineDeliveryCount, tone: "warning" },
                      { label: "Active", value: activeOnlineDeliveryCount, tone: "info" },
                      { label: "Delivered", value: onlineDeliveryOrders.filter((order) => order.status === "delivered").length, tone: "success" },
                      { label: "Aggregator sales", value: formatMoney(onlineDeliveryOrders.reduce((sum, order) => sum + moneyNumber(order.total), 0)), tone: "accent" },
                    ].map((item) => (
                      <div key={item.label} className={`online-delivery-kpi ${item.tone}`}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                    ))}
                  </div>

                  <div className="online-delivery-layout">
                    <form className="panel online-delivery-intake" onSubmit={handleCreateOnlineDeliveryOrder}>
                      <div className="panel-head">
                        <div>
                          <h2>Aggregator intake</h2>
                          <p>Add Swiggy, Zomato, or direct delivery orders</p>
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                          {deliverySetupBadges.map(({ label, service }) => (
                            <span key={label} className={`status-chip ${setupClass(service)}`} title={service?.missing?.join(", ") || "Configured"}>
                              {service?.configured ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                              {label} {setupLabel(service)}
                            </span>
                          ))}
                          <Truck size={20} color="var(--accent)" />
                        </div>
                      </div>
                      <div className="delivery-provider-switch">
                        {(["swiggy", "zomato", "own", "other"] as const).map((provider) => (
                          <button
                            type="button"
                            key={provider}
                            className={deliveryDraft.provider === provider ? "active" : ""}
                            onClick={() => setDeliveryDraft((prev) => ({ ...prev, provider }))}
                          >
                            {statusLabel(provider)}
                          </button>
                        ))}
                      </div>
                      <div className="form-grid-2">
                        <div className="form-group">
                          <label>Aggregator order ID</label>
                          <input value={deliveryDraft.external_order_id} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, external_order_id: e.target.value }))} placeholder="ZOM-12458" />
                        </div>
                        <div className="form-group">
                          <label>Customer</label>
                          <input value={deliveryDraft.customer_name} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, customer_name: e.target.value }))} placeholder="Customer name" />
                        </div>
                        <div className="form-group">
                          <label>Phone</label>
                          <input value={deliveryDraft.customer_phone} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, customer_phone: e.target.value }))} placeholder="Customer phone" />
                        </div>
                        <div className="form-group">
                          <label>Payment</label>
                          <select value={`${deliveryDraft.payment_mode}:${deliveryDraft.payment_status}`} onChange={(e) => {
                            const [payment_mode, payment_status] = e.target.value.split(":");
                            setDeliveryDraft((prev) => ({ ...prev, payment_mode, payment_status }));
                          }}>
                            <option value="prepaid:paid">Prepaid</option>
                            <option value="cod:unpaid">Cash on delivery</option>
                            <option value="upi:paid">UPI paid</option>
                            <option value="unknown:pending">Pending</option>
                          </select>
                        </div>
                        <div className="form-group span-2">
                          <label>Delivery address</label>
                          <input value={deliveryDraft.delivery_address} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, delivery_address: e.target.value }))} placeholder="Flat, street, area" />
                        </div>
                        <div className="form-group">
                          <label>Menu item</label>
                          <select value={deliveryDraft.product_id} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, product_id: e.target.value }))} required>
                            <option value="">Select item</option>
                            {products.filter((product) => product.available).map((product) => (
                              <option key={product.id} value={product.id}>{product.name} - {formatMoney(product.price)}</option>
                            ))}
                          </select>
                        </div>
                        <div className="form-group">
                          <label>Quantity</label>
                          <input type="number" min={1} max={99} value={deliveryDraft.quantity} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, quantity: Math.max(1, Number(e.target.value) || 1) }))} />
                        </div>
                        <div className="form-group">
                          <label>Commission</label>
                          <input value={deliveryDraft.commission_amount} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, commission_amount: e.target.value }))} placeholder="0.00" />
                        </div>
                        <div className="form-group">
                          <label>Notes</label>
                          <input value={deliveryDraft.notes} onChange={(e) => setDeliveryDraft((prev) => ({ ...prev, notes: e.target.value }))} placeholder="No onion, extra chutney" />
                        </div>
                      </div>
                      <Button type="submit" variant="default">
                        <Plus size={15} /> Add delivery order
                      </Button>
                    </form>

                    <div className="panel online-delivery-queue">
                      <div className="panel-head">
                        <div>
                          <h2>Live delivery queue</h2>
                          <p>Accept orders into KDS, reject unavailable orders, and close delivery handoffs</p>
                        </div>
                        <Button type="button" variant="secondary" onClick={() => branch && refreshOnlineDelivery(branch.id)}>
                          <RefreshCw size={14} /> Refresh
                        </Button>
                      </div>
                      <div className="delivery-tabs">
                        {(["new", "needs_mapping", "accepted", "ready", "picked_up", "delivered", "all"] as const).map((tab) => (
                          <button key={tab} type="button" className={onlineDeliveryTab === tab ? "active" : ""} onClick={() => setActiveChildRoute("Online Delivery", tab)}>
                            {statusLabel(tab)}
                            <span>{tab === "all" ? onlineDeliveryOrders.length : onlineDeliveryOrders.filter((order) => order.status === tab).length}</span>
                          </button>
                        ))}
                      </div>
                      <div className="delivery-order-list">
                        {filteredOnlineDeliveryOrders.length === 0 ? (
                          <div className="delivery-empty">
                            <Truck size={32} />
                            <span>No {onlineDeliveryTab === "all" ? "online delivery" : statusLabel(onlineDeliveryTab).toLowerCase()} orders</span>
                          </div>
                        ) : filteredOnlineDeliveryOrders.map((order) => (
                          <div key={order.id} className={`delivery-order-card ${order.provider}`}>
                            <div className="delivery-order-head">
                              <div>
                                <span className="delivery-provider">{statusLabel(order.provider)}</span>
                                <strong>#{order.external_order_id}</strong>
                              </div>
                              <span className={`delivery-status ${order.status}`}>{statusLabel(order.status)}</span>
                            </div>
                            <div className="delivery-order-meta">
                              <span>{order.customer_name}</span>
                              <span>{order.payment_status === "paid" ? "Paid" : statusLabel(order.payment_mode)}</span>
                              <strong>{formatMoney(order.total)}</strong>
                            </div>
                            {order.delivery_address && <p>{order.delivery_address}</p>}
                            <div className="delivery-items">
                              {(order.items || []).map((item) => (
                                <span key={`${order.id}-${item.product_id || item.name}`}>{item.quantity}x {item.name}{item.unmapped ? " - map SKU" : ""}</span>
                              ))}
                            </div>
                            <div className="delivery-actions">
                              {order.status === "new" && (
                                <>
                                  <Button type="button" variant="success" onClick={() => handleAcceptOnlineDelivery(order.id)}>Accept to KDS</Button>
                                  <Button type="button" variant="danger" onClick={() => handleUpdateOnlineDelivery(order.id, "rejected")}>Reject</Button>
                                </>
                              )}
                              {order.status === "needs_mapping" && (
                                <Button type="button" variant="secondary" onClick={() => setActiveNav("Menu")}>Map menu SKUs</Button>
                              )}
                              {["accepted", "ready"].includes(order.status) && (
                                <Button type="button" variant="secondary" onClick={() => handleUpdateOnlineDelivery(order.id, "picked_up")}>Mark picked up</Button>
                              )}
                              {order.status === "picked_up" && (
                                <Button type="button" variant="success" onClick={() => handleUpdateOnlineDelivery(order.id, "delivered")}>Mark delivered</Button>
                              )}
                              {order.order_id && <button type="button" onClick={() => setActiveNav("KDS")}>Open KDS</button>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {activeNav === "KDS" && (
                <section>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 16 }}>
                    {(["new", "accepted", "preparing", "ready", "served"] as const).map((col) => {
                      const colOrders = kdsOrders.filter((o) => o.kds_status === col);
                      const colColors: Record<string, string> = { new: "var(--info)", accepted: "var(--accent)", preparing: "var(--amber)", ready: "var(--success)", served: "var(--text-muted)" };
                      return (
                        <div key={col} className="kds-column" style={{ borderTop: `3px solid ${colColors[col]}` }}>
                          <h3 style={{ color: colColors[col], display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            <span>{col.charAt(0).toUpperCase() + col.slice(1)}</span>
                            {colOrders.length > 0 && <span style={{ fontSize: "0.68rem", background: colColors[col] + "22", color: colColors[col], padding: "2px 8px", borderRadius: 999 }}>{colOrders.length}</span>}
                          </h3>
                          {colOrders.length === 0 ? (
                            <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "20px 0", fontSize: "0.8rem" }}>No orders</div>
                          ) : colOrders.map((o) => {
                            const minutes = o.created_at ? Math.floor((Date.now() - new Date(o.created_at).getTime()) / 60000) : 0;
                            const isUrgent = minutes >= 20 && col !== "served";
                            return (
                              <motion.div
                                key={o.id}
                                className="kds-ticket"
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                style={{ borderColor: isUrgent ? "var(--danger)" : undefined, boxShadow: isUrgent ? "0 0 16px var(--danger-soft)" : undefined }}
                              >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                  <h4 style={{ fontSize: "0.875rem" }}>#{o.id.slice(0, 6).toUpperCase()}</h4>
                                  <ElapsedTimer createdAt={o.created_at} />
                                </div>
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "capitalize" }}>{o.order_type.replace("_", " ")}</span>
                                <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                                  {(o.items || []).map((item, i) => (
                                    <div key={i} style={{ fontSize: "0.82rem", padding: "2px 0" }}>{item.quantity}× {item.name}</div>
                                  ))}
                                </div>
                                {col === "new" && (
                                  <Button variant="default" style={{ width: "100%", fontSize: "0.78rem" }} onClick={() => handleKdsStatus(o.id, "accepted")}>
                                    Accept Order
                                  </Button>
                                )}
                                {col === "accepted" && (
                                  <Button variant="default" style={{ width: "100%", fontSize: "0.78rem" }} onClick={() => handleKdsStatus(o.id, "preparing")}>
                                    Start Preparing
                                  </Button>
                                )}
                                {col === "preparing" && (
                                  <Button variant="success" style={{ width: "100%", fontSize: "0.78rem" }} onClick={() => handleKdsStatus(o.id, "ready")}>
                                    Mark Ready
                                  </Button>
                                )}
                                {col === "ready" && (
                                  <Button variant="secondary" style={{ width: "100%", fontSize: "0.78rem", borderColor: "var(--info)", color: "var(--info)" }} onClick={() => handleKdsStatus(o.id, "served")}>
                                    Serve
                                  </Button>
                                )}
                              </motion.div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  6. MENU
                 ══════════════════════════════════════ */}
              {activeNav === "Menu" && (
                <section className="panel">
                  <div className="panel-head menu-panel-head">
                    <div>
                      <h2>Menu Items &amp; Variants</h2>
                      <p>Sizes, variants, add-ons, and combos</p>
                    </div>
                    <div className="menu-panel-actions">
                      <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{products.length} items</span>
                      <Button variant="default" onClick={handleAddProduct}>+ Add Item</Button>
                    </div>
                  </div>
                  <div className="menu-table-shell">
                    <table className="data-table menu-items-table">
                    <colgroup>
                      <col className="menu-col-name" />
                      <col className="menu-col-price" />
                      <col className="menu-col-tax" />
                      <col className="menu-col-variants" />
                      <col className="menu-col-addons" />
                      <col className="menu-col-status" />
                      <col className="menu-col-actions" />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>Item Name</th>
                        <th>Standard Price</th>
                        <th>Tax Rate</th>
                        <th>Sizes / Variants</th>
                        <th>Add-ons</th>
                        <th>Availability</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {products.length === 0 && (
                        <tr><td colSpan={7} style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>Loading menu items...</td></tr>
                      )}
                      {products.map((p) => (
                        <tr key={p.id}>
                          <td data-label="Item Name"><strong>{p.name}</strong></td>
                          <td data-label="Standard Price" style={{ fontVariantNumeric: "tabular-nums" }}>₹{parseFloat(p.price).toFixed(2)}</td>
                          <td data-label="Tax Rate"><span style={{ color: "var(--amber)", fontWeight: 700 }}>{p.tax_rate}%</span></td>
                          <td data-label="Sizes / Variants">
                            {p.variants?.length > 0 ? p.variants.map((v, i) => (
                              <div key={i} style={{ fontSize: "0.78rem" }}>{v.name} (+₹{v.price_delta})</div>
                            )) : <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Standard only</span>}
                          </td>
                          <td data-label="Add-ons">
                            {p.addons?.length > 0 ? p.addons.map((a, i) => (
                              <span key={i} style={{ display: "inline-block", background: "var(--surface-soft)", border: "1px solid var(--border)", padding: "2px 7px", borderRadius: 6, fontSize: "0.72rem", marginRight: 4, marginBottom: 2 }}>{a.name}</span>
                            )) : <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>None</span>}
                          </td>
                          <td data-label="Availability">
                              <button
                                type="button"
                                className="menu-status-button"
                                onClick={() => handleToggleProduct(p.id, p.available)}
                                style={{ fontSize: "0.8rem", fontWeight: 700, padding: "8px 12px", minHeight: "44px", borderRadius: 6, background: p.available ? "var(--success-soft)" : "var(--danger-soft)", color: p.available ? "var(--success)" : "var(--danger)", border: `1px solid ${p.available ? "var(--success)" : "var(--danger)"}`, cursor: "pointer", transition: "all var(--dur-fast) ease" }}
                              >
                                {p.available ? "Available" : "Unavailable"}
                              </button>
                          </td>
                          <td data-label="Actions">
                            <button type="button" className="menu-delete-button" onClick={() => handleDeleteProduct(p.id)} style={{ fontSize: "0.8rem", fontWeight: 700, padding: "8px 12px", minHeight: "44px", borderRadius: 6, background: "var(--surface)", color: "var(--danger)", border: "1px solid var(--border)", cursor: "pointer", transition: "all var(--dur-fast) ease" }}>
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  7. INVENTORY
                 ══════════════════════════════════════ */}
              {activeNav === "Inventory" && (
                <section className="pos-layout">
                  <div className="panel">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <div>
                        <h2>Stock Levels</h2>
                        <p>Low stock alerts &amp; current inventory</p>
                      </div>
                      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: 999, background: "var(--danger-soft)", color: "var(--danger)" }}>
                          {inventoryItems.filter((i) => (parseFloat(i.quantity) || 0) <= (parseFloat(i.low_stock_threshold) || 0)).length} low
                        </span>
                        <Button variant="default" onClick={() => showToast("Add Stock Item coming soon!")}>+ Add Item</Button>
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      {inventoryItems.map((item) => {
                        const curQty = parseFloat(item.quantity) || 0;
                        const threshold = parseFloat(item.low_stock_threshold) || 0;
                        const maxQty = Math.max(curQty * 2, threshold * 3, 10);
                        return (
                          <div key={item.id} style={{ padding: 14, borderRadius: 10, background: "var(--surface-soft)", border: "1px solid var(--border)" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                              <strong style={{ fontSize: "0.875rem" }}>{item.name}</strong>
                              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Threshold: {item.low_stock_threshold} {item.unit}</span>
                                <button onClick={() => handleDeleteInventoryItem(item.id)} style={{ background: "transparent", color: "var(--danger)", border: 0, cursor: "pointer", padding: "2px 4px", borderRadius: 4 }}>×</button>
                              </div>
                            </div>
                            <StockBar current={curQty} max={maxQty} unit={item.unit} />
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="panel">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <h2>Record Purchase Order</h2>
                    </div>
                    <form 
                      style={{ display: "flex", flexDirection: "column", gap: 14 }} 
                      onSubmit={(e) => {
                        const form = e.currentTarget;
                        handleRecordPO(
                          e,
                          (form.elements.namedItem('supplier') as HTMLInputElement).value,
                          (form.elements.namedItem('ingredient') as HTMLInputElement).value,
                          (form.elements.namedItem('qty') as HTMLInputElement).value,
                          (form.elements.namedItem('cost') as HTMLInputElement).value
                        );
                        form.reset();
                      }}
                    >
                      <div className="form-group">
                        <label htmlFor="po-supplier">Supplier</label>
                        <input id="po-supplier" name="supplier" type="text" defaultValue="Metro Fresh Foods" required />
                      </div>
                      <div className="form-group">
                        <label htmlFor="po-ingredient">Ingredient</label>
                        <input id="po-ingredient" name="ingredient" type="text" placeholder="e.g. Chicken Breast" required />
                      </div>
                      <div className="form-group">
                        <label htmlFor="po-qty">Quantity</label>
                        <input id="po-qty" name="qty" type="number" placeholder="e.g. 10" min="1" required />
                      </div>
                      <div className="form-group">
                        <label htmlFor="po-cost">Unit Cost (₹)</label>
                        <input id="po-cost" name="cost" type="number" placeholder="e.g. 450" min="0" step="0.01" required />
                      </div>
                      <Button type="submit" variant="default">
                        Receive Stock
                      </Button>
                    </form>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  8. STAFF
                 ══════════════════════════════════════ */}
              {activeNav === "Staff" && (
                <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="tab-nav staff-tab-nav" style={{ width: "100%", display: "flex" }}>
                    {(["directory", "attendance", "payroll", "incentives", "leaves"] as const).map((tab) => (
                      <button
                        key={tab}
                        className={staffTab === tab ? "active" : ""}
                        onClick={() => setActiveChildRoute("Staff", tab)}
                        style={{ textTransform: "capitalize", flex: 1 }}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>

                  {staffTab === "directory" && (
                    <>
                      <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Employee Directory</h2>
                          <p>Manage your staff members and their roles</p>
                        </div>
                        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{employees.length} staff registered at {branch?.name}</span>
                          <button onClick={() => exportToExcel(employees, "Employee_Directory")} style={{ padding: "8px 14px", background: "var(--info-soft)", color: "var(--info)", border: "1px solid var(--info)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease", display: "flex", alignItems: "center", gap: 6 }}><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg> Export Excel</button>
                            <Button variant="default" onClick={handleAddEmployee}>+ Add Staff</Button>
                        </div>
                      </div>
                      <div className="table-responsive">
<table className="data-table">
                        <thead>
                          <tr>
                            <th>Employee</th>
                            <th>Role</th>
                            <th>Email</th>
                            <th>Phone</th>
                            <th>Joined</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {employees.length === 0 ? (
                            <tr><td colSpan={6} style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>No employees found</td></tr>
                          ) : employees.map((emp) => (
                            <tr key={emp.id}>
                              <td>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <AvatarCircle name={emp.name} size={34} />
                                  <div>
                                    <strong style={{ display: "block", fontSize: "0.875rem" }}>{emp.name}</strong>
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", textTransform: "capitalize" }}>#{emp.employee_id}</span>
                                  </div>
                                </div>
                              </td>
                              <td style={{ textTransform: "capitalize" }}>{emp.role.replace(/_/g, " ")}</td>
                              <td>{emp.email}</td>
                              <td>{emp.phone || "-"}</td>
                              <td>{new Date(emp.joining_date).toLocaleDateString()}</td>
                              <td>
                                <div style={{ display: "flex", gap: 6 }}>
                                  <button onClick={() => handleEditEmployee(emp)} style={{ padding: "6px 10px", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, fontSize: "0.75rem", cursor: "pointer" }}>Edit</button>
                                  <button onClick={() => handleDeleteEmployee(emp)} style={{ padding: "6px 10px", background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: 6, fontSize: "0.75rem", cursor: "pointer" }}>Delete</button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        </table>
</div>
                      </div>

                      
                    </>
                  )}

                  {staffTab === "attendance" && (
<>
<div className="panel">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                          <div>
                            <h2>Attendance Dashboard</h2>
                            <p>Manage today's check-ins and overtime</p>
                          </div>
                          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                            <Button variant="secondary" onClick={handleCleanupAttendance} style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}>Cleanup Old Logs (&gt;2 mos)</Button>
                          </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 15, marginBottom: 20 }}>
                          <div style={{ padding: 15, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12 }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Current Month</span>
                            <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: 5 }}>{new Date().toLocaleString('default', { month: 'long', year: 'numeric' })}</div>
                          </div>
                          <div style={{ padding: 15, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12 }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Total Work-Hours (Today)</span>
                            <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: 5 }}>
                              {todayWorkHours} hrs
                            </div>
                          </div>
                          <div style={{ padding: 15, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12 }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Today's Active Staff</span>
                            <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: 5, color: 'var(--success)' }}>
                              {currentClockedInStaff} On-duty
                            </div>
                          </div>
                        </div>
                      </div>

<div className="panel">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                          <div>
                            <h2>Today's Staff Attendance</h2>
                            <p>Clock each staff member in or out</p>
                          </div>
                          <span style={{ color: "var(--text-muted)", fontSize: "0.82rem", fontWeight: 700 }}>{currentAttendance.length} staff</span>
                        </div>
                        <div className="table-responsive">
                          <table className="data-table">
                            <thead><tr><th>Member Name</th><th>Role</th><th>Clock In</th><th>Clock Out</th><th>Status</th><th>Actions</th></tr></thead>
                            <tbody>
                              {currentAttendance.length === 0 ? (
                                <tr><td colSpan={6} style={{ textAlign: "center", padding: 24, color: "var(--text-muted)" }}>No active staff found</td></tr>
                              ) : currentAttendance.map((row) => (
                                <tr key={row.id}>
                                  <td>
                                    <strong style={{ fontSize: "0.875rem" }}>{row.name}</strong>
                                    <span style={{ display: "block", color: "var(--text-muted)", fontSize: "0.72rem" }}>#{row.employee_id}</span>
                                  </td>
                                  <td style={{ textTransform: "capitalize" }}>{row.role.replace(/_/g, " ")}</td>
                                  <td style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatAttendanceTime(row.check_in)}</td>
                                  <td style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatAttendanceTime(row.check_out)}</td>
                                  <td>
                                    <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: row.status === "clocked_in" ? "var(--success-soft)" : row.status === "clocked_out" ? "var(--info-soft)" : "var(--surface)", color: row.status === "clocked_in" ? "var(--success)" : row.status === "clocked_out" ? "var(--info)" : "var(--text-muted)", textTransform: "uppercase" }}>
                                      {row.status.replace(/_/g, " ")}
                                    </span>
                                  </td>
                                  <td>
                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                      <Button variant="secondary" onClick={() => handleClockIn(row.id)} disabled={row.status === "clocked_in"} style={{ minHeight: 40, fontSize: "0.78rem" }}>Clock In</Button>
                                      <Button variant="default" onClick={() => handleClockOut(row.id)} disabled={row.status !== "clocked_in"} style={{ minHeight: 40, fontSize: "0.78rem" }}>Clock Out</Button>
                                      <Button variant="secondary" onClick={() => handleRequestOvertime(row.attendance_id || undefined)} disabled={row.status !== "clocked_in" || !row.attendance_id} style={{ minHeight: 40, fontSize: "0.78rem" }}>Request OT</Button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

<div className="panel">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                          <div>
                            <h2>Attendance Logs</h2>
                            <p>Search, filter, edit, approve, and reject attendance records</p>
                          </div>
                          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.82rem", fontWeight: 700 }}>{filteredAttendance.length} records</span>
                          </div>
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "minmax(180px, 1.4fr) minmax(150px, 0.8fr) minmax(150px, 0.8fr) auto", gap: 10, marginBottom: 14 }}>
                          <input className="input-field" value={attendanceFilters.search} onChange={(e) => setAttendanceFilters((prev) => ({ ...prev, search: e.target.value }))} placeholder="Filter employee or ID" style={{ minHeight: 44 }} />
                          <input className="input-field" type="date" value={attendanceFilters.date} onChange={(e) => setAttendanceFilters((prev) => ({ ...prev, date: e.target.value }))} style={{ minHeight: 44 }} />
                          <select className="input-field" value={attendanceFilters.overtime} onChange={(e) => setAttendanceFilters((prev) => ({ ...prev, overtime: e.target.value }))} style={{ minHeight: 44 }}>
                            <option value="">All OT statuses</option>
                            <option value="none">No OT</option>
                            <option value="pending">Pending OT</option>
                            <option value="approved">Approved OT</option>
                            <option value="rejected">Rejected OT</option>
                          </select>
                          <Button variant="secondary" onClick={() => setAttendanceFilters({ search: "", date: "", overtime: "" })}>Clear</Button>
                        </div>
                        <div className="table-responsive">
<table className="data-table">
                          <thead><tr><th>Member Name</th><th>Date</th><th>Clock In</th><th>Clock Out</th><th>Time Worked</th><th>Overtime</th><th>Actions</th></tr></thead>
                          <tbody>
                            {filteredAttendance.length === 0 ? (
                              <tr><td colSpan={7} style={{ textAlign: "center", padding: 24, color: "var(--text-muted)" }}>No attendance records match the filters</td></tr>
                            ) : filteredAttendance.map((att) => {
                              const otStatus = (att.overtime_status && att.overtime_status !== "none") ? att.overtime_status : (att.overtime_minutes > 0 ? "pending" : "none");
                              return (
                                <tr key={att.id}>
                                  <td><strong style={{ fontSize: "0.875rem" }}>{att.name}</strong><span style={{ display: "block", color: "var(--text-muted)", fontSize: "0.72rem" }}>#{att.employee_id}</span></td>
                                  <td style={{ fontSize: "0.82rem" }}>{new Date(att.check_in).toLocaleDateString()}</td>
                                  <td style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatAttendanceTime(att.check_in)}</td>
                                  <td>{att.check_out ? <span style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatAttendanceTime(att.check_out)}</span> : <span style={{ color: "var(--success)", fontSize: "0.78rem", fontWeight: 700 }}>Active</span>}</td>
                                  <td style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatAttendanceDuration(att)}</td>
                                  <td style={{ fontSize: "0.8rem", color: otStatus === "approved" ? "var(--success)" : otStatus === "rejected" ? "var(--danger)" : att.overtime_minutes > 0 ? "var(--amber)" : "var(--text-muted)" }}>
                                    {att.overtime_minutes} min
                                    {att.overtime_minutes > 0 && <span style={{ display: "block", fontSize: "0.7rem", textTransform: "capitalize" }}>{otStatus}</span>}
                                  </td>
                                  <td>
                                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                      <button onClick={() => handleEditAttendance(att.id, att.check_in, att.check_out || "")} style={{ padding: "8px 10px", minHeight: 44, background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 7, fontSize: "0.75rem", cursor: "pointer" }}>Edit</button>
                                      <button onClick={() => handleDeleteAttendance(att.id)} style={{ padding: "8px 10px", minHeight: 44, background: "var(--danger-soft)", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: 7, fontSize: "0.75rem", cursor: "pointer" }}>Del</button>
                                      {att.overtime_minutes > 0 && otStatus === "pending" && (
                                        <>
                                          <button onClick={() => handleApproveOvertime(att.id, true)} style={{ padding: "8px 10px", minHeight: 44, background: "var(--success)", color: "white", border: 0, borderRadius: 7, fontSize: "0.75rem", cursor: "pointer" }}>Approve OT</button>
                                          <button onClick={() => handleApproveOvertime(att.id, false)} style={{ padding: "8px 10px", minHeight: 44, background: "var(--danger)", color: "white", border: 0, borderRadius: 7, fontSize: "0.75rem", cursor: "pointer" }}>Reject OT</button>
                                        </>
                                      )}
                                      {!att.check_out && att.overtime_minutes <= 0 && (
                                        <button onClick={() => handleRequestOvertime(att.id)} style={{ padding: "8px 10px", minHeight: 44, background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent)", borderRadius: 7, fontSize: "0.75rem", cursor: "pointer" }}>Request OT</button>
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
</>
)}

{staffTab === "payroll" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Payroll Processing</h2>
                          <p>Pending and completed payouts</p>
                        </div>
                      </div>
                      <div className="table-responsive">
<table className="data-table">
                        <thead><tr><th>Name</th><th>Day Salary</th><th>Payable Days</th><th>Incentives</th><th>Net Paid</th><th>Status</th><th>Method</th><th>Actions</th></tr></thead>
                        <tbody>
                          {payrolls.length === 0 ? (
                            <tr><td colSpan={8} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>No payroll data</td></tr>
                          ) : payrolls.map((p, idx) => (
                            <tr key={idx}>
                              <td><strong style={{ fontSize: "0.875rem" }}>{p.name}</strong></td>
                              <td style={{ fontVariantNumeric: "tabular-nums" }}>₹{parseFloat(p.day_salary ?? p.base_salary).toFixed(0)}</td>
                              <td>
                                <strong style={{ fontSize: "0.85rem" }}>{p.payable_days ?? 0} days</strong>
                                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
                                  Present {p.present_days ?? 0} · Leave {p.approved_leave_days ?? 0} · Absent {p.absent_days ?? 0}
                                </div>
                              </td>
                              <td style={{ fontVariantNumeric: "tabular-nums", color: "var(--success)", fontWeight: 700 }}>₹{parseFloat(p.incentives ?? "0").toFixed(0)}</td>
                              <td style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>₹{parseFloat(p.net_salary).toFixed(0)}</td>
                              <td>
                                <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "2px 8px", borderRadius: 999, background: p.status === "paid" ? "var(--success-soft)" : "var(--amber-soft)", color: p.status === "paid" ? "var(--success)" : "var(--amber)" }}>
                                  {p.status.toUpperCase()}
                                </span>
                              </td>
                              <td>
                                {p.payment_mode ? (
                                  <div>
                                    <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--text)" }}>
                                      {payrollPaymentLabels[p.payment_mode] ?? p.payment_mode.toUpperCase()}
                                    </span>
                                    {p.payment_reference && (
                                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        Ref: {p.payment_reference}
                                      </div>
                                    )}
                                    {p.payout_provider && (
                                      <div style={{ fontSize: "0.7rem", color: "var(--accent)", marginTop: 2 }}>
                                        {p.payout_provider} {p.payout_status || ""}
                                      </div>
                                    )}
                                    {p.payout_id && (
                                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        ID: {p.payout_id}
                                      </div>
                                    )}
                                  </div>
                                ) : <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>-</span>}
                              </td>
                              <td>
                                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                                  <button onClick={() => handleEditPayroll(p)} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: "0.8rem" }}>Edit</button>
                                  <button onClick={() => handleDeletePayroll(p.id, p.name)} style={{ background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: "0.8rem" }}>Delete</button>
                                  {canSubmitPayrollPayout(p) && <Button variant="success" onClick={() => openPayoutWizard(p)} style={{ fontSize: "0.8rem" }}>Payout</Button>}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
</div>
                    </div>
                  )}

                  {staffTab === "incentives" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Incentives &amp; Commissions</h2>
                          <p>Performance rewards</p>
                        </div>
                          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                            <button onClick={() => exportToExcel(incentives, "Incentives")} style={{ padding: "8px 14px", background: "var(--info-soft)", color: "var(--info)", border: "1px solid var(--info)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease", display: "flex", alignItems: "center", gap: 6 }}><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg> Export Excel</button>
                              <Button className="primary" onClick={handleAddIncentive}>+ Add Incentive</Button>
                          </div>
                      </div>
                      <div className="table-responsive">
<table className="data-table">
                        <thead><tr><th>Name</th><th>Sales Amount</th><th>Incentive Amount</th><th>Date</th><th>Actions</th></tr></thead>
                        <tbody>
                          {incentives.length === 0 ? (
                            <tr><td colSpan={5} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>No incentives found</td></tr>
                          ) : incentives.map((inc, idx) => (
                            <tr key={idx}>
                              <td><strong style={{ fontSize: "0.875rem" }}>{inc.name}</strong></td>
                              <td style={{ fontVariantNumeric: "tabular-nums" }}>₹{parseFloat(inc.sales_amount).toFixed(2)}</td>
                              <td style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, color: "var(--success)" }}>₹{parseFloat(inc.incentive_amount).toFixed(2)}</td>
                              <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{inc.date}</td>
                              <td>
                                <div style={{ display: "flex", gap: 6 }}>
                                  <button onClick={() => handleEditIncentive(inc)} style={{ padding: "6px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: "0.8rem", cursor: "pointer" }}>
                                    Edit
                                  </button>
                                  <button onClick={() => handleDeleteIncentive(inc.id, inc.name)} style={{ padding: "6px 12px", background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: 6, fontSize: "0.8rem", cursor: "pointer" }}>
                                    Delete
                                  </button>
                                  <button onClick={() => handlePayoutIncentive(inc.id)} style={{ padding: "6px 12px", background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer" }}>
                                    Payout
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
</div>
                    </div>
                  )}
                
                  {staffTab === "leaves" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Leave Approvals</h2>
                          <p>Manage staff time-off requests</p>
                        </div>
                        <div style={{ display: "flex", gap: 10 }}>
                          <Button variant="default" onClick={handleApplyLeave}>Apply Leave</Button>
                          <button onClick={() => exportToExcel(leaveRequests, "Leaves_Export")} style={{ padding: "8px 14px", background: "var(--info-soft)", color: "var(--info)", border: "1px solid var(--info)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease", display: "flex", alignItems: "center", gap: 6 }}><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg> Export Excel</button>
                          <select className="input-field" value={leaveFilter} onChange={(e) => setLeaveFilter(e.target.value)} style={{ minWidth: 150 }}>
                            <option value="all">All Requests</option>
                            <option value="pending">Pending</option>
                            <option value="approved">Approved</option>
                            <option value="rejected">Rejected</option>
                          </select>
                        </div>
                      </div>
                      <div className="table-responsive">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Employee</th>
                              <th>Type</th>
                              <th>Dates</th>
                              <th>Reason</th>
                              <th>Status</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {leaveRequests.filter(lr => leaveFilter === "all" || lr.status === leaveFilter).length === 0 ? (
                              <tr><td colSpan={6} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>No leave requests found</td></tr>
                            ) : leaveRequests.filter(lr => leaveFilter === "all" || lr.status === leaveFilter).map((lr) => (
                              <tr key={lr.id}>
                                <td>
                                  <strong style={{ fontSize: "0.875rem", display: "block" }}>{lr.name}</strong>
                                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{lr.employee_id}</span>
                                </td>
                                <td style={{ textTransform: "capitalize" }}>{lr.type}</td>
                                <td style={{ fontSize: "0.85rem", color: "var(--text-soft)" }}>
                                  {lr.start_date} &rarr; {lr.end_date}
                                </td>
                                <td style={{ fontSize: "0.85rem", color: "var(--text-muted)", maxWidth: 200, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{lr.reason}</td>
                                <td>
                                  <span style={{ padding: "4px 8px", borderRadius: 4, fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase",
                                    background: lr.status === "pending" ? "var(--amber-soft)" : lr.status === "approved" ? "var(--success-soft)" : "var(--danger-soft)",
                                    color: lr.status === "pending" ? "var(--amber)" : lr.status === "approved" ? "var(--success)" : "var(--danger)"
                                  }}>
                                    {lr.status}
                                  </span>
                                </td>
                                <td>
                                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                    {lr.status === "pending" && (
                                      <>
                                        <button onClick={() => handleUpdateLeave(lr.id, { status: "approved" })} style={{ padding: "6px 12px", background: "var(--success-soft)", color: "var(--success)", border: "1px solid var(--success)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 700, cursor: "pointer", transition: "all 0.15s ease" }}>Approve</button>
                                        <button onClick={() => handleUpdateLeave(lr.id, { status: "rejected" })} style={{ padding: "6px 12px", background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: 6, fontSize: "0.8rem", fontWeight: 600, cursor: "pointer", transition: "all 0.15s ease" }}>Reject</button>
                                      </>
                                    )}
                                    <button onClick={() => {
                                      setEditLeaveWizard({ id: lr.id, type: lr.type, start_date: lr.start_date, end_date: lr.end_date, reason: lr.reason, status: lr.status });
                                      setShowEditLeaveWizard(true);
                                    }} style={{ padding: "6px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: "0.8rem", cursor: "pointer", transition: "all 0.15s ease" }}>
                                      Edit
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* ══════════════════════════════════════
                  9. REPORTS
                 ══════════════════════════════════════ */}
              {activeNav === "Reports" && (
                <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="pos-layout">
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Daily Sales Summary</h2>
                          <p>Revenue breakdown for today</p>
                        </div>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10, background: "var(--surface-soft)", padding: 16, borderRadius: 12, border: "1px solid var(--border)" }}>
                        {[
                          ["Sales Revenue", `₹${metrics.today_sales}`, "var(--text)"],
                          ["Tax Collected", `₹${(parseFloat(metrics.today_sales) * 0.0825).toFixed(2)}`, "var(--amber)"],
                          ["Discounts Applied", "-₹10.00", "var(--danger)"],
                          ["Net Revenue", `₹${(parseFloat(metrics.today_sales) - 10).toFixed(2)}`, "var(--accent)"],
                        ].map(([label, val, color]) => (
                          <div key={label as string} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: label === "Discounts Applied" ? "1px solid var(--border)" : "none" }}>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>{label as string}</span>
                            <strong style={{ color: color as string, fontVariantNumeric: "tabular-nums" }}>{val as string}</strong>
                          </div>
                        ))}
                      </div>

                      {/* Top sellers horizontal bar chart */}
                      <h3 style={{ marginTop: 20, marginBottom: 12, fontSize: "0.95rem", fontWeight: 700 }}>Top Selling Items</h3>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {(metrics.top_selling_products.length > 0 ? metrics.top_selling_products : [{ name: "Paneer Tikka Bowl", quantity: 48 }, { name: "Margherita Pizza", quantity: 36 }, { name: "Filter Coffee", quantity: 62 }, { name: "Masala Dosa", quantity: 29 }]).map((p, idx) => {
                          const maxQty = Math.max(...(metrics.top_selling_products.length > 0 ? metrics.top_selling_products : [{ quantity: 62 }]).map((x: any) => x.quantity));
                          const pct = (p.quantity / (maxQty || 1)) * 100;
                          return (
                            <div key={idx} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                                <span style={{ color: "var(--text-soft)" }}>{p.name}</span>
                                <strong style={{ color: "var(--accent)" }}>{p.quantity} orders</strong>
                              </div>
                              <div style={{ height: 6, borderRadius: 999, background: "var(--border)", overflow: "hidden" }}>
                                <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, delay: idx * 0.1, ease: [0.16, 1, 0.3, 1] }} style={{ height: "100%", background: "linear-gradient(90deg, var(--accent), var(--accent-2))", borderRadius: 999 }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Export Reports</h2>
                          <p>Download business reports with full data</p>
                        </div>
                      </div>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: 20 }}>
                        Download detailed reports containing order logs, tax summary, margins, and staff data.
                      </p>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {[
                          { label: "Export CSV — Raw Data", format: "csv" as const, color: "var(--success)" },
                          { label: "Export PDF — Formatted Report", format: "pdf" as const, color: "var(--danger)" },
                          { label: "Export Excel — Spreadsheet", format: "excel" as const, color: "var(--info)" },
                        ].map(({ label, format, color }) => (
                          <button
                            key={format}
                            onClick={() => triggerExport(format)}
                            style={{ padding: "12px 16px", background: color + "15", border: `1px solid ${color}40`, borderRadius: 10, color, fontWeight: 700, fontSize: "0.875rem", cursor: "pointer", textAlign: "left", transition: "all 0.15s ease" }}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {/* ══════════════════════════════════════
                  10. SETTINGS
                 ══════════════════════════════════════ */}
              {activeNav === "Razorpay Dashboard" && (
                <section className="razorpay-dashboard">
                  <div className="razorpay-hero panel">
                    <div>
                      <span className="razorpay-kicker">Auto-refresh every 30 seconds</span>
                      <h2>Razorpay control room</h2>
                      <p>Track provider collections, refunds, pending checkout orders, RazorpayX payouts, and net gateway movement for the selected branch.</p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                        <span
                          className={`status-chip ${resolvedRazorpayMetrics.status === "live" ? "connected" : "disconnected"}`}
                          title={razorpayDataDetail}
                        >
                          {resolvedRazorpayMetrics.status === "live" ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                          {razorpayDataStatus}
                        </span>
                        {gatewaySetupBadges.map(({ label, service }) => (
                          <span key={label} className={`status-chip ${setupClass(service)}`} title={service?.missing?.join(", ") || "Configured"}>
                            {service?.configured ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                            {label} {setupLabel(service)}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="razorpay-refresh-card">
                      <span>{razorpayRefreshing ? "Refreshing provider" : razorpayDataStatus}</span>
                      <strong>{razorpayLastRefresh || "Waiting for first sync"}</strong>
                      <small>{razorpayDataDetail}</small>
                      <Button type="button" onClick={() => refreshRazorpayDashboard(true)} disabled={razorpayRefreshing}>
                        <RefreshCw size={15} className={razorpayRefreshing ? "spin-icon" : ""} />
                        Refresh now
                      </Button>
                    </div>
                  </div>

                  <div className="razorpay-kpi-grid">
                    {[
                      {
                        label: "Net collections",
                        value: formatMoney(gatewayCollectionTotal),
                        hint: `${capturedRazorpayPayments} captured payments, ${resolvedRazorpayMetrics.collectionSource} data`,
                        tone: "success",
                      },
                      {
                        label: "Processed refunds",
                        value: gatewayRefundTotal === null ? "Not synced" : formatMoney(gatewayRefundTotal),
                        hint: gatewayRefundTotal === null ? "Provider payment and refund feeds required" : "Deducted from gross collections",
                        tone: gatewayRefundTotal === null ? "warning" : "danger",
                      },
                      {
                        label: "Gateway payouts",
                        value: formatMoney(gatewayPayoutTotal),
                        hint: `${razorpayPayouts.length} RazorpayX payouts, ${resolvedRazorpayMetrics.payoutSource} data`,
                        tone: "info",
                      },
                      { label: "Net gateway flow", value: formatMoney(gatewayNetSettlement), hint: gatewayNetSettlement >= 0 ? "Collection is above payouts" : "Payouts are above collection", tone: gatewayNetSettlement >= 0 ? "accent" : "danger" },
                      { label: "Pending gateway orders", value: String(pendingRazorpayPayments), hint: "Created checkout orders not captured yet", tone: pendingRazorpayPayments > 0 ? "warning" : "success" },
                    ].map((card) => (
                      <div key={card.label} className={`razorpay-kpi ${card.tone}`}>
                        <span>{card.label}</span>
                        <strong>{card.value}</strong>
                        <small>{card.hint}</small>
                      </div>
                    ))}
                  </div>

                  <div className="razorpay-rail">
                    <div className="panel razorpay-flow-panel incoming">
                      <div className="panel-head">
                        <div>
                          <h2>Incoming collections</h2>
                          <p>Gateway payments received through online billing and cash-out</p>
                        </div>
                        <CreditCard size={20} />
                      </div>
                      <div className="razorpay-total-line">
                        <span>Net collections</span>
                        <strong>{formatMoney(gatewayCollectionTotal)}</strong>
                      </div>
                      <div className="razorpay-breakdown">
                        {resolvedRazorpayMetrics.collectionSource === "provider" ? (
                          <>
                            <div>
                              <span>Gross captured</span>
                              <strong>{formatMoney(gatewayGrossCollectionTotal)}</strong>
                            </div>
                            <div>
                              <span>Processed refunds</span>
                              <strong>-{formatMoney(gatewayRefundTotal)}</strong>
                            </div>
                            <div>
                              <span>Net collections</span>
                              <strong>{formatMoney(gatewayCollectionTotal)}</strong>
                            </div>
                          </>
                        ) : Object.entries(metrics.payment_gateway_totals || {}).length === 0 ? (
                          <p>No Razorpay collection recorded yet.</p>
                        ) : Object.entries(metrics.payment_gateway_totals || {}).map(([provider, value]) => (
                          <div key={provider}>
                            <span>{statusLabel(provider)}</span>
                            <strong>{formatMoney(value)}</strong>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="panel razorpay-flow-panel outgoing">
                      <div className="panel-head">
                        <div>
                          <h2>Outgoing payouts</h2>
                          <p>RazorpayX salary and UPI payout activity</p>
                        </div>
                        <Smartphone size={20} />
                      </div>
                      <div className="razorpay-total-line">
                        <span>Total paid out</span>
                        <strong>{formatMoney(gatewayPayoutTotal)}</strong>
                      </div>
                      <div className="razorpay-breakdown">
                        {razorpayProviderSnapshot?.payouts.status === "live" ? (
                          <>
                            <div>
                              <span>Processed</span>
                              <strong>{formatMoney(razorpayProviderSnapshot.payouts.amounts.processed)}</strong>
                            </div>
                            <div>
                              <span>In flight</span>
                              <strong>{formatMoney(razorpayProviderSnapshot.payouts.amounts.in_flight)}</strong>
                            </div>
                            <div>
                              <span>Failed or reversed</span>
                              <strong>{formatMoney(razorpayProviderSnapshot.payouts.amounts.failed)}</strong>
                            </div>
                          </>
                        ) : Object.entries(metrics.payout_gateway_totals || {}).length === 0 ? (
                          <p>No RazorpayX payout recorded yet.</p>
                        ) : Object.entries(metrics.payout_gateway_totals || {}).map(([provider, value]) => (
                          <div key={provider}>
                            <span>{statusLabel(provider)}</span>
                            <strong>{formatMoney(value)}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="razorpay-table-grid">
                    <div className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>Recent gateway payments</h2>
                          <p>{razorpayProviderSnapshot?.payments.status === "live" ? "Latest provider-confirmed payments" : "Latest locally recorded checkout payments"}</p>
                        </div>
                        <span className="status-chip connected">{razorpayPayments.length} rows</span>
                      </div>
                      <div className="table-responsive">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Order</th>
                              <th>Amount</th>
                              <th>Status</th>
                              <th>Gateway order</th>
                              <th>Payment ID</th>
                            </tr>
                          </thead>
                          <tbody>
                            {razorpayPayments.length === 0 ? (
                              <tr><td colSpan={5} className="empty-cell">No Razorpay payments yet</td></tr>
                            ) : razorpayPayments.slice(0, 10).map((payment) => (
                              <tr key={payment.id}>
                                <td>#{payment.orderId.slice(0, 8)}</td>
                                <td>{formatMoney(payment.amount)}</td>
                                <td><span className={`razorpay-status ${payment.status.toLowerCase()}`}>{payment.status}</span></td>
                                <td className="mono-cell">{payment.gatewayOrderId}</td>
                                <td className="mono-cell">{payment.gatewayPaymentId}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>RazorpayX payouts</h2>
                          <p>{razorpayProviderSnapshot?.payouts.status === "live" ? "Latest provider-confirmed payout states" : "Locally recorded payroll payout states"}</p>
                        </div>
                        <span className="status-chip connected">{razorpayPayouts.length} rows</span>
                      </div>
                      <div className="table-responsive">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Staff</th>
                              <th>Period</th>
                              <th>Amount</th>
                              <th>Status</th>
                              <th>Payout ID</th>
                            </tr>
                          </thead>
                          <tbody>
                            {razorpayPayouts.length === 0 ? (
                              <tr><td colSpan={5} className="empty-cell">No RazorpayX payouts yet</td></tr>
                            ) : razorpayPayouts.slice(0, 10).map((payout) => (
                              <tr key={payout.id}>
                                <td>{payout.employee}</td>
                                <td>{payout.period}</td>
                                <td>{formatMoney(payout.amount)}</td>
                                <td><span className={`razorpay-status ${payout.status.toLowerCase()}`}>{payout.status}</span></td>
                                <td className="mono-cell">{payout.payoutId}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {activeNav === "Settings" && (
                <section style={{ maxWidth: 660 }}>
                  {/* Tab nav */}
                  <div className="tab-nav settings-tab-nav">
                    {(["security", "profile", "integrations", "appearance"] as const).map((tab) => (
                      <button key={tab} onClick={() => setActiveChildRoute("Settings", tab)} style={{ padding: "8px 20px", borderRadius: 9, fontSize: "0.85rem", fontWeight: 600, textTransform: "capitalize", border: 0, cursor: "pointer", transition: "all 0.15s ease", background: settingsTab === tab ? "var(--accent)" : "transparent", color: settingsTab === tab ? "#fff" : "var(--text-muted)" }}>
                        {tab}
                      </button>
                    ))}
                  </div>

                  {settingsTab === "security" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Security Policy</h2>
                          <p>Manage lockout, session, and authentication rules</p>
                        </div>
                        <ShieldCheck size={20} color="var(--accent)" />
                      </div>
                      <form onSubmit={handleSaveSecurity} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                        <div className="form-grid">
                          <div className="form-group">
                            <label>Min Password Length</label>
                            <input type="number" value={security.password_min_length} onChange={(e) => setSecurity({ ...security, password_min_length: parseInt(e.target.value) })} min="6" max="32" required />
                          </div>
                          <div className="form-group">
                            <label>Session Timeout (min)</label>
                            <input type="number" value={security.session_timeout_minutes} onChange={(e) => setSecurity({ ...security, session_timeout_minutes: parseInt(e.target.value) })} min="5" max="1440" required />
                          </div>
                          <div className="form-group">
                            <label>Failed Login Limit</label>
                            <input type="number" value={security.login_attempts_threshold} onChange={(e) => setSecurity({ ...security, login_attempts_threshold: parseInt(e.target.value) })} min="3" max="20" required />
                          </div>
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                          {[
                            { key: "multi_device_login" as const, label: "Allow Multi-Device Login", desc: "Users can sign in from multiple devices simultaneously" },
                            { key: "two_factor_auth" as const, label: "Enforce Two-Factor Authentication", desc: "Require OTP/TOTP on every login" },
                          ].map(({ key, label, desc }) => (
                            <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 16, background: "var(--surface-soft)", border: "1px solid var(--border)", borderRadius: 12 }}>
                              <div>
                                <strong style={{ display: "block", fontSize: "0.875rem" }}>{label}</strong>
                                <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{desc}</span>
                              </div>
                              <ToggleSwitch checked={security[key]} onChange={(v) => setSecurity({ ...security, [key]: v })} id={key} />
                            </div>
                          ))}
                        </div>


                        <Button type="submit" variant="default">
                          Save Security Settings
                        </Button>
                      </form>
                    </div>
                  )}

                  {settingsTab === "profile" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}><h2>Profile Settings</h2></div>
                      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
                        <AvatarCircle name={email} size={56} />
                        <div>
                          <strong style={{ display: "block", fontSize: "1rem" }}>{email}</strong>
                          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Super Admin · {branch?.name}</span>
                        </div>
                      </div>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Display Name</label>
                          <input type="text" defaultValue="Admin" />
                        </div>
                        <div className="form-group">
                          <label>Email Address</label>
                          <input type="email" value={email} readOnly style={{ opacity: 0.6 }} />
                        </div>
                        <div className="form-group" style={{ gridColumn: "span 2" }}>
                          <label>New Password</label>
                          <input type="password" placeholder="Leave blank to keep current" />
                        </div>
                      </div>
                      <Button variant="default" onClick={() => showToast("Profile updated!", "success")} style={{ marginTop: 16 }}>
                        Save Profile
                      </Button>
                    </div>
                  )}

                  {settingsTab === "integrations" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                        <div>
                          <h2>Integrations</h2>
                          <p>Payment, password reset mail, and delivery provider setup</p>
                        </div>
                        <Button type="button" variant="secondary" onClick={() => refreshIntegrationStatus(branch?.id)}>
                          <RefreshCw size={14} /> Refresh
                        </Button>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {[
                          { label: "Password reset mail", service: resetMailSetup },
                          ...gatewaySetupBadges,
                          ...deliverySetupBadges,
                        ].map(({ label, service }) => (
                          <div key={label} className="integration-settings-row">
                            <div>
                              <strong style={{ display: "block", fontSize: "0.875rem" }}>{label}</strong>
                              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                                {service?.configured ? "Configured" : `Missing: ${service?.missing?.join(", ") || "configuration"}`}
                              </span>
                              {service?.webhook_url && (
                                <code style={{ display: "block", marginTop: 4, fontSize: "0.72rem", color: "var(--text-muted)", wordBreak: "break-all" }}>
                                  {service.webhook_url}
                                </code>
                              )}
                            </div>
                            <div className="integration-settings-actions">
                              {label === "Password reset mail" && (
                                <Button
                                  type="button"
                                  variant="secondary"
                                  onClick={testPasswordResetMail}
                                  disabled={!service?.configured || resetMailTesting}
                                  title={service?.configured ? "Send a test message to your account email" : "Complete mail setup before testing"}
                                >
                                  <MailCheck size={14} />
                                  {resetMailTesting ? "Sending..." : "Send test email"}
                                </Button>
                              )}
                              <span className={`status-chip ${setupClass(service)}`}>
                                {service?.configured ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                                {setupLabel(service)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {settingsTab === "appearance" && (
                    <div className="panel">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}><h2>Appearance</h2></div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 16, background: "var(--surface-soft)", border: "1px solid var(--border)", borderRadius: 12 }}>
                          <div>
                            <strong style={{ display: "block", fontSize: "0.875rem" }}>Dark Mode</strong>
                            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Use dark theme across the application</span>
                          </div>
                          <ToggleSwitch checked={theme === "dark"} onChange={toggleTheme} id="dark-mode-toggle" />
                        </div>
                        <div style={{ padding: 16, background: "var(--surface-soft)", border: "1px solid var(--border)", borderRadius: 12 }}>
                          <strong style={{ display: "block", fontSize: "0.875rem", marginBottom: 4 }}>Current Theme</strong>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                            {theme === "dark" ? "🌙 Dark Mode — OLED-optimised, low emission" : "☀️ Light Mode — Clean, high-contrast"}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {activeNav === "Admin Panel" && userRole && (
                <AdminPage
                  token={token}
                  branches={branches}
                  users={users}
                  userRole={userRole}
                  activeTab={(resolvedRoute?.child as AdminTab) || "stores"}
                  onTabChange={(tab) => setActiveChildRoute("Admin Panel", tab)}
                  onRefresh={initData}
                  showToast={showToast}
                  apiRequest={apiRequest}
                />
              )}

              {activeNav === "Platform" && (
                <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="panel-head">
                    <div>
                      <h2>Platform Overview</h2>
                      <p>Cross-tenant usage and system operating status</p>
                    </div>
                    <span className={`status-chip ${platformMetrics?.system_health === "Healthy" ? "connected" : "disconnected"}`}>
                      {platformMetrics?.system_health || "Waiting for data"}
                    </span>
                  </div>

                  <div className="metrics">
                    {[
                      { label: "Platform Revenue", value: formatMoney(platformMetrics?.total_revenue), icon: DollarSign, color: "var(--success)" },
                      { label: "Active Tenants", value: String(platformMetrics?.active_tenants ?? 0), icon: Warehouse, color: "var(--accent)" },
                      { label: "Total Stores", value: String(platformMetrics?.total_stores ?? 0), icon: Store, color: "var(--info)" },
                      { label: "Total Users", value: String(platformMetrics?.total_users ?? 0), icon: Users, color: "var(--amber)" },
                    ].map((metric) => {
                      const Icon = metric.icon;
                      return (
                        <div className="metric-card" key={metric.label}>
                          <Icon size={19} color={metric.color} />
                          <span>{metric.label}</span>
                          <strong>{metric.value}</strong>
                        </div>
                      );
                    })}
                  </div>

                  <div className="dashboard-grid">
                    <div className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>Platform Operations</h2>
                          <p>Current service consumption</p>
                        </div>
                      </div>
                      <div className="razorpay-breakdown">
                        {[
                          ["Active subscriptions", platformMetrics?.active_subscriptions ?? 0],
                          ["API usage", platformMetrics?.api_usage || "Unavailable"],
                          ["Storage usage", platformMetrics?.storage_usage || "Unavailable"],
                          ["Database usage", platformMetrics?.database_usage || "Unavailable"],
                        ].map(([label, value]) => (
                          <div key={String(label)}>
                            <span>{label}</span>
                            <strong>{value}</strong>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="panel">
                      <div className="panel-head">
                        <div>
                          <h2>Current Tenant</h2>
                          <p>Tenant-wide operating totals</p>
                        </div>
                      </div>
                      <div className="razorpay-breakdown">
                        {[
                          ["Revenue", formatMoney(tenantMetrics?.revenue)],
                          ["Orders", tenantMetrics?.orders ?? 0],
                          ["Customers", tenantMetrics?.customers ?? 0],
                          ["Inventory health", tenantMetrics?.inventory_health || "Unavailable"],
                        ].map(([label, value]) => (
                          <div key={String(label)}>
                            <span>{label}</span>
                            <strong>{value}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
              )}

            </motion.div>
          </AnimatePresence>
        </section>
      <AnimatePresence>
        {showProductWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Add Menu Item</h2>
                  <p>{branch?.name || "Current branch"}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowProductWizard(false)} aria-label="Close add item wizard">
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleSaveProductWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group span-2">
                      <label htmlFor="menu-item-category">Category</label>
                      <div style={{ display: "flex", gap: 8 }}>
                        <select id="menu-item-category" value={productWizard.category_id} onChange={(e) => setProductWizard(prev => ({ ...prev, category_id: e.target.value }))}>
                          <option value="">None</option>
                          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                        <Button type="button" variant="ghost" onClick={handleAddCategory}>+ New</Button>
                      </div>
                    </div>
                    <div className="form-group span-2">
                    <label htmlFor="menu-item-name">Item Name *</label>
                    <input id="menu-item-name" autoFocus value={productWizard.name} onChange={(e) => setProductWizard((prev) => ({ ...prev, name: e.target.value }))} placeholder="e.g. Paneer Tikka Bowl" required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="menu-item-price">Standard Price *</label>
                    <input id="menu-item-price" type="number" min="0" step="0.01" value={productWizard.price} onChange={(e) => setProductWizard((prev) => ({ ...prev, price: e.target.value }))} placeholder="0.00" required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="menu-item-tax">GST Rate %</label>
                    <input id="menu-item-tax" type="number" min="0" max="100" step="0.01" value={productWizard.tax_rate} onChange={(e) => setProductWizard((prev) => ({ ...prev, tax_rate: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label htmlFor="menu-item-sku">SKU</label>
                    <input id="menu-item-sku" value={productWizard.sku} onChange={(e) => setProductWizard((prev) => ({ ...prev, sku: e.target.value }))} placeholder="Kitchen code" />
                  </div>
                  <div className="form-group">
                    <label htmlFor="menu-item-image">Image URL</label>
                    <input id="menu-item-image" type="url" value={productWizard.image_url} onChange={(e) => setProductWizard((prev) => ({ ...prev, image_url: e.target.value }))} placeholder="https://..." />
                  </div>
                  <div className="form-group span-2">
                    <label htmlFor="menu-item-description">Description</label>
                    <textarea id="menu-item-description" value={productWizard.description} onChange={(e) => setProductWizard((prev) => ({ ...prev, description: e.target.value }))} placeholder="Short kitchen or menu note" />
                  </div>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-soft)", fontSize: "0.86rem", fontWeight: 700 }}>
                  <input type="checkbox" checked={productWizard.available} onChange={(e) => setProductWizard((prev) => ({ ...prev, available: e.target.checked }))} />
                  Available for billing
                </label>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowProductWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit"><Plus size={16} /> Save Item</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showEmployeeWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>{employeeWizard.id ? "Edit Employee" : "Add Employee"}</h2>
                  <p>{branch?.name || "Current branch"}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowEmployeeWizard(false)}>
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleSaveEmployeeWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group span-2">
                    <label>Employee Name *</label>
                    <input autoFocus value={employeeWizard.name} onChange={(e) => setEmployeeWizard({ ...employeeWizard, name: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label>Employee ID *</label>
                    <input value={employeeWizard.employee_id} onChange={(e) => setEmployeeWizard({ ...employeeWizard, employee_id: e.target.value })} required disabled={Boolean(employeeWizard.id)} />
                  </div>
                  <div className="form-group">
                    <label>Email *</label>
                    <input type="email" value={employeeWizard.email} onChange={(e) => setEmployeeWizard({ ...employeeWizard, email: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label>{employeeWizard.id ? "New Password" : "Password *"}</label>
                    <input type="password" minLength={8} value={employeeWizard.password} onChange={(e) => setEmployeeWizard({ ...employeeWizard, password: e.target.value })} required={!employeeWizard.id} placeholder={employeeWizard.id ? "Leave blank to keep current" : ""} />
                  </div>
                  <div className="form-group">
                    <label>Phone</label>
                    <input value={employeeWizard.phone} onChange={(e) => setEmployeeWizard({ ...employeeWizard, phone: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Role</label>
                    <select value={employeeWizard.role} onChange={(e) => setEmployeeWizard({ ...employeeWizard, role: e.target.value })}>
                      {employeeRoleOptions.map(([role, label]) => <option key={role} value={role}>{label}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Day Salary (₹)</label>
                    <input type="number" min="0" step="1" value={employeeWizard.base_salary} onChange={(e) => setEmployeeWizard({ ...employeeWizard, base_salary: e.target.value })} />
                  </div>
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowEmployeeWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit"><Plus size={16} /> {employeeWizard.id ? "Update Employee" : "Add Employee"}</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showIncentiveWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Add Incentive</h2>
                  <p>Reward performance</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowIncentiveWizard(false)}>
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleSaveIncentiveWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group span-2">
                    <label>Staff</label>
                    <select autoFocus value={incentiveWizard.employee_id} onChange={(e) => setIncentiveWizard({ ...incentiveWizard, employee_id: e.target.value })}>
                      {!incentiveWizard.id && <option value="">All Staff</option>}
                      {employees.map((emp) => (
                        <option key={emp.id} value={emp.id}>{emp.name} ({emp.employee_id})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group span-2">
                    <label>Incentive Amount (₹) *</label>
                    <input type="number" min="1" step="1" value={incentiveWizard.amount} onChange={(e) => setIncentiveWizard({ ...incentiveWizard, amount: e.target.value })} required />
                  </div>
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowIncentiveWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit"><Banknote size={16} /> Add Incentive</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showPayoutWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box narrow" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Payroll Payout</h2>
                  <p>{payoutWizard.name} · ₹{parseFloat(payoutWizard.net_salary || "0").toFixed(2)}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowPayoutWizard(false)}><X size={16} /></button>
              </div>
              <form onSubmit={handlePayPayroll} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-group">
                  <label>Payment Method</label>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                    {([
                      ["cash", Banknote],
                      ["upi", Smartphone],
                      ["bank", CreditCard],
                      ["payroll", Receipt],
                    ] as const).map(([mode, Icon]) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setPayoutWizard((prev) => ({ ...prev, payment_mode: mode, use_gateway: mode === "upi" ? prev.use_gateway : false }))}
                        style={{
                          minHeight: 48,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 8,
                          borderRadius: 8,
                          border: payoutWizard.payment_mode === mode ? "1px solid var(--accent)" : "1px solid var(--border)",
                          background: payoutWizard.payment_mode === mode ? "var(--accent-soft)" : "var(--surface-soft)",
                          color: payoutWizard.payment_mode === mode ? "var(--accent)" : "var(--text)",
                          fontWeight: 800,
                        }}
                      >
                        <Icon size={16} />
                        {payrollPaymentLabels[mode]}
                      </button>
                    ))}
                  </div>
                </div>
                {payoutWizard.payment_mode === "upi" && (
                  <div className="form-group">
                    <label>UPI Payout Type</label>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                      <button
                        type="button"
                        onClick={() => setPayoutWizard((prev) => ({ ...prev, use_gateway: true, payment_reference: "" }))}
                        style={{ minHeight: 46, borderRadius: 8, border: payoutWizard.use_gateway ? "1px solid var(--accent)" : "1px solid var(--border)", background: payoutWizard.use_gateway ? "var(--accent-soft)" : "var(--surface-soft)", color: payoutWizard.use_gateway ? "var(--accent)" : "var(--text)", fontWeight: 800 }}
                      >
                        RazorpayX
                      </button>
                      <button
                        type="button"
                        onClick={() => setPayoutWizard((prev) => ({ ...prev, use_gateway: false, recipient_upi: "" }))}
                        style={{ minHeight: 46, borderRadius: 8, border: !payoutWizard.use_gateway ? "1px solid var(--accent)" : "1px solid var(--border)", background: !payoutWizard.use_gateway ? "var(--accent-soft)" : "var(--surface-soft)", color: !payoutWizard.use_gateway ? "var(--accent)" : "var(--text)", fontWeight: 800 }}
                      >
                        Manual UPI
                      </button>
                    </div>
                  </div>
                )}
                {payoutWizard.payment_mode === "upi" && payoutWizard.use_gateway && (
                  <div className="form-group">
                    <label>Recipient UPI ID *</label>
                    <input
                      type="text"
                      value={payoutWizard.recipient_upi}
                      onChange={(e) => setPayoutWizard((prev) => ({ ...prev, recipient_upi: e.target.value }))}
                      placeholder="staff@upi"
                      required
                    />
                  </div>
                )}
                <div className="form-group">
                  <label>{payoutWizard.payment_mode === "upi" && !payoutWizard.use_gateway ? "UPI Transaction Reference *" : "Payment Reference"}</label>
                  <input
                    type="text"
                    value={payoutWizard.payment_reference}
                    onChange={(e) => setPayoutWizard((prev) => ({ ...prev, payment_reference: e.target.value }))}
                    placeholder={payoutWizard.payment_mode === "upi" && !payoutWizard.use_gateway ? "UPI transaction ID" : "Optional reference"}
                    disabled={payoutWizard.payment_mode === "upi" && payoutWizard.use_gateway}
                    required={payoutWizard.payment_mode === "upi" && !payoutWizard.use_gateway}
                  />
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowPayoutWizard(false)}>Cancel</Button>
                  <Button variant="success" type="submit">Confirm Payout</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showAttendanceWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div><h2>{attendanceWizard.type === "in" ? "Clock In" : "Clock Out"}</h2><p>Manager Override</p></div>
                <button className="modal-close" type="button" onClick={() => setShowAttendanceWizard(false)}><X size={16} /></button>
              </div>
              <form onSubmit={handleSaveAttendanceWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-group">
                  <label>Shift Hours (Default 9 hrs)</label>
                  <input type="number" min="1" max="24" step="0.5" value={attendanceWizard.hours} onChange={(e) => setAttendanceWizard({ ...attendanceWizard, hours: parseFloat(e.target.value) || 9 })} required />
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowAttendanceWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Save Time</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showPayrollWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div><h2>Edit Day Salary</h2><p>Absent days are deducted unless leave is approved</p></div>
                <button className="modal-close" type="button" onClick={() => setShowPayrollWizard(false)}><X size={16} /></button>
              </div>
              <form onSubmit={handleSavePayrollWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label>Day Salary (₹)</label>
                    <input type="number" min="0" value={payrollWizard.daily_wage} onChange={(e) => {
                      const dw = parseFloat(e.target.value) || 0;
                      setPayrollWizard({ ...payrollWizard, daily_wage: dw, base: dw * payrollWizard.days_present });
                    }} />
                  </div>
                  <div className="form-group">
                    <label>Payable Days</label>
                    <input type="number" min="0" max="31" value={payrollWizard.days_present} readOnly />
                  </div>
                  <div className="form-group span-2">
                    <label>Calculated Pay (₹)</label>
                    <input type="number" min="0" value={payrollWizard.base} readOnly />
                  </div>
                  <div className="form-group span-2">
                    <label>Included Incentives (₹)</label>
                    <input type="number" min="0" value={payrollWizard.incentives} readOnly />
                  </div>
                  <div className="form-group span-2">
                    <label><strong>Final Net Pay (₹)</strong></label>
                    <div style={{ padding: "12px", background: "var(--surface-soft)", borderRadius: 6, fontWeight: 700, fontSize: "1.1rem" }}>
                      ₹{payrollWizard.base + payrollWizard.incentives}
                    </div>
                  </div>
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowPayrollWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Update Payroll</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {refundWizard.order && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box narrow" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Refund Payment</h2>
                  <p>Order #{refundWizard.order.id.slice(0, 8)}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setRefundWizard({ order: null, payment_id: "", amount: "", reason: "" })} aria-label="Close refund">
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleOrderRefund} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-group">
                  <label>Captured Payment</label>
                  <select
                    value={refundWizard.payment_id}
                    onChange={(event) => {
                      const payment = refundablePayments(refundWizard.order || {}).find((item) => item.id === event.target.value);
                      setRefundWizard((current) => ({
                        ...current,
                        payment_id: event.target.value,
                        amount: payment ? Number(payment.amount).toFixed(2) : current.amount,
                      }));
                    }}
                  >
                    {refundablePayments(refundWizard.order).map((payment) => (
                      <option key={payment.id} value={payment.id}>
                        {(payment.provider || payment.method || "Payment").toUpperCase()} - Rs. {Number(payment.amount).toFixed(2)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Refund Amount</label>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={refundWizard.amount}
                    onChange={(event) => setRefundWizard((current) => ({ ...current, amount: event.target.value }))}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Reason</label>
                  <input
                    value={refundWizard.reason}
                    onChange={(event) => setRefundWizard((current) => ({ ...current, reason: event.target.value }))}
                    placeholder="Customer request"
                    maxLength={255}
                  />
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setRefundWizard({ order: null, payment_id: "", amount: "", reason: "" })}>Cancel</Button>
                  <Button variant="danger" type="submit" disabled={refundSubmitting}>
                    <RotateCcw size={15} /> {refundSubmitting ? "Submitting..." : "Submit Refund"}
                  </Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      {/* Confirm Modal */}
      <AnimatePresence>
        {confirmModal.isOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="modal-overlay">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} className="modal-box narrow">
              <div className="modal-head">
                <div>
                  <h2>{confirmModal.title}</h2>
                  <p>Confirm this action</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))} aria-label="Close confirmation">
                  <X size={16} />
                </button>
              </div>
              <div className="confirm-message">
                <AlertTriangle size={18} />
                <p>{confirmModal.message}</p>
              </div>
              <div className="modal-footer">
                <Button variant="ghost" type="button" onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}>Cancel</Button>
                <Button variant="danger" type="button" onClick={confirmModal.onConfirm}>Confirm</Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Discount Modal */}
      <AnimatePresence>
        {discountModal.isOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="modal-overlay">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} className="modal-box">
              <div className="modal-head">
                <h2>Request Discount</h2>
                <button className="modal-close" onClick={() => setDiscountModal(prev => ({ ...prev, isOpen: false }))}><X size={16} /></button>
              </div>
              <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '15px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '5px' }}>Discount Type</label>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <Button 
                      variant={discountModal.type === 'percentage' ? 'default' : 'secondary'} 
                      onClick={() => setDiscountModal(prev => ({ ...prev, type: 'percentage' }))}
                      style={{ flex: 1 }}
                    >Percentage (%)</Button>
                    <Button 
                      variant={discountModal.type === 'fixed' ? 'default' : 'secondary'} 
                      onClick={() => setDiscountModal(prev => ({ ...prev, type: 'fixed' }))}
                      style={{ flex: 1 }}
                    >Fixed Amount</Button>
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '5px' }}>Amount</label>
                  <input 
                    type="number" 
                    value={discountModal.amount} 
                    onChange={e => setDiscountModal(prev => ({ ...prev, amount: e.target.value }))} 
                    placeholder={discountModal.type === 'percentage' ? "e.g. 10" : "e.g. 50"}
                    className="input-field" 
                    style={{ width: '100%', padding: '10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)' }}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ marginTop: '1.5rem', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <Button variant="secondary" onClick={() => setDiscountModal(prev => ({ ...prev, isOpen: false }))}>Cancel</Button>
                <Button variant="default" onClick={submitDiscountRequest}>Submit Request</Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      
      {/* Overtime Wizard */}
      <AnimatePresence>
        {showOvertimeWizard && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="modal-overlay">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} className="modal-box">
              <div className="modal-head">
                <h2>Request Overtime</h2>
                <button className="modal-close" type="button" onClick={() => setShowOvertimeWizard(false)}><X size={16} /></button>
              </div>
              <form onSubmit={handleSaveOvertimeWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Overtime Minutes</label>
                  <input type="number" min="1" step="1" value={overtimeWizard.minutes} onChange={(e) => setOvertimeWizard({ ...overtimeWizard, minutes: parseInt(e.target.value) || 0 })} required className="input-field" />
                </div>
                <div className="modal-footer" style={{ marginTop: 16, display: "flex", gap: 12, justifyContent: "flex-end" }}>
                  <Button variant="ghost" type="button" onClick={() => setShowOvertimeWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Submit Request</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Attendance Wizard */}
      <AnimatePresence>
        {showEditAttendanceWizard && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="modal-overlay">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} className="modal-box">
              <div className="modal-head">
                <h2>Edit Attendance Log</h2>
                <button className="modal-close" type="button" onClick={() => setShowEditAttendanceWizard(false)}><X size={16} /></button>
              </div>
              <form onSubmit={handleSaveEditAttendanceWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Date</label>
                  <input type="date" value={editAttendanceWizard.date} onChange={(e) => setEditAttendanceWizard({ ...editAttendanceWizard, date: e.target.value })} required className="input-field" />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Check-In (24hr HH:MM) e.g., 09:00</label>
                  <input type="time" value={editAttendanceWizard.checkIn} onChange={(e) => setEditAttendanceWizard({ ...editAttendanceWizard, checkIn: e.target.value })} required className="input-field" />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Check-Out (24hr HH:MM) e.g., 18:00 (Leave blank for 9hr default)</label>
                  <input type="time" value={editAttendanceWizard.checkOut} onChange={(e) => setEditAttendanceWizard({ ...editAttendanceWizard, checkOut: e.target.value })} className="input-field" />
                </div>
                <div className="modal-footer" style={{ marginTop: 16, display: "flex", gap: 12, justifyContent: "flex-end" }}>
                  <Button variant="ghost" type="button" onClick={() => setShowEditAttendanceWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Save Log</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Edit Table Wizard */}
      <AnimatePresence>
        {showEditTableWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Edit Table</h2>
                  <p>{selectedFloor} floor plan</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowEditTableWizard(false)} aria-label="Close edit table wizard"><X size={16} /></button>
              </div>
              <form onSubmit={handleSaveEditTableWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group span-2">
                    <label htmlFor="edit-table-name">Table Name *</label>
                    <input id="edit-table-name" autoFocus type="text" value={editTableWizard.name} onChange={(e) => setEditTableWizard({ ...editTableWizard, name: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="edit-table-floor">Floor / Area</label>
                    <select
                      id="edit-table-floor"
                      value={editTableWizard.floor_area}
                      onChange={(e) => setEditTableWizard({ ...editTableWizard, floor_area: e.target.value })}
                      required
                    >
                      {floorOptions.map((floor) => (
                        <option key={floor} value={floor}>{floor}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="edit-table-capacity">Capacity</label>
                    <input id="edit-table-capacity" type="number" min="1" max="40" step="1" value={editTableWizard.capacity} onChange={(e) => setEditTableWizard({ ...editTableWizard, capacity: parseInt(e.target.value) || 1 })} required />
                  </div>
                  <div className="form-group span-2">
                    <label htmlFor="edit-table-status">Status</label>
                    <select
                      id="edit-table-status"
                      value={editTableWizard.status}
                      onChange={(e) => setEditTableWizard({ ...editTableWizard, status: e.target.value as TableState["status"] })}
                      required
                    >
                      <option value="available">Available</option>
                      <option value="reserved">Reserved</option>
                      <option value="cleaning">Cleaning</option>
                      <option value="out_of_service">Unavailable</option>
                    </select>
                  </div>
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowEditTableWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Save Table</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Table Wizard */}
      <AnimatePresence>
        {showTableWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Add New Table</h2>
                  <p>{selectedFloor} floor plan</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowTableWizard(false)} aria-label="Close add table wizard"><X size={16} /></button>
              </div>
              <form onSubmit={handleSaveTableWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group span-2">
                    <label htmlFor="new-table-name">Table Name *</label>
                    <input id="new-table-name" autoFocus type="text" value={tableWizard.name} onChange={(e) => setTableWizard({ ...tableWizard, name: e.target.value })} placeholder="e.g. T10" required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="new-table-floor">Floor / Area</label>
                    <select
                      id="new-table-floor"
                      value={tableWizard.floor_area}
                      onChange={(e) => setTableWizard({ ...tableWizard, floor_area: e.target.value })}
                      required
                    >
                      {floorOptions.map((floor) => (
                        <option key={floor} value={floor}>{floor}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="new-table-capacity">Capacity</label>
                    <input id="new-table-capacity" type="number" min="1" max="40" step="1" value={tableWizard.capacity} onChange={(e) => setTableWizard({ ...tableWizard, capacity: parseInt(e.target.value) || 1 })} required />
                  </div>
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowTableWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit"><Plus size={16} /> Add Table</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>


      {/* Leave Wizards */}
      <AnimatePresence>
        {showLeaveWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Apply Leave</h2>
                  <p>{branch?.name || "Current branch"}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowLeaveWizard(false)}>
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleSaveLeaveWizard} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label>Staff *</label>
                    <select className="input-field" value={leaveWizard.employee_id} onChange={(e) => setLeaveWizard({ ...leaveWizard, employee_id: e.target.value })} required>
                      <option value="" disabled>Select staff</option>
                      {employees.map((emp) => (
                        <option key={emp.id} value={emp.id}>{emp.name} ({emp.employee_id})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Type</label>
                    <select className="input-field" value={leaveWizard.type} onChange={(e) => setLeaveWizard({ ...leaveWizard, type: e.target.value as any })}>
                      <option value="sick">Sick</option>
                      <option value="vacation">Vacation</option>
                      <option value="unpaid">Unpaid</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Start Date *</label>
                    <input type="date" className="input-field" value={leaveWizard.start_date} onChange={(e) => setLeaveWizard({ ...leaveWizard, start_date: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label>End Date *</label>
                    <input type="date" className="input-field" value={leaveWizard.end_date} onChange={(e) => setLeaveWizard({ ...leaveWizard, end_date: e.target.value })} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Reason *</label>
                  <input type="text" className="input-field" value={leaveWizard.reason} onChange={(e) => setLeaveWizard({ ...leaveWizard, reason: e.target.value })} required />
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowLeaveWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit"><Plus size={16} /> Apply Leave</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showEditLeaveWizard && (
          <motion.div className="modal-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="modal-box" initial={{ scale: 0.96, y: 18 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 18 }}>
              <div className="modal-head">
                <div>
                  <h2>Edit Leave Request</h2>
                  <p>{branch?.name || "Current branch"}</p>
                </div>
                <button className="modal-close" type="button" onClick={() => setShowEditLeaveWizard(false)}>
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={async (e) => {
                e.preventDefault();
                const updated = await handleUpdateLeave(editLeaveWizard.id, editLeaveWizard);
                if (updated) setShowEditLeaveWizard(false);
              }} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="form-grid-2">
                  <div className="form-group">
                    <label>Type</label>
                    <select className="input-field" value={editLeaveWizard.type} onChange={(e) => setEditLeaveWizard({ ...editLeaveWizard, type: e.target.value as any })}>
                      <option value="sick">Sick</option>
                      <option value="vacation">Vacation</option>
                      <option value="unpaid">Unpaid</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Status</label>
                    <select className="input-field" value={editLeaveWizard.status} onChange={(e) => setEditLeaveWizard({ ...editLeaveWizard, status: e.target.value as any })}>
                      <option value="pending">Pending</option>
                      <option value="approved">Approved</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Start Date *</label>
                    <input type="date" className="input-field" value={editLeaveWizard.start_date} onChange={(e) => setEditLeaveWizard({ ...editLeaveWizard, start_date: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label>End Date *</label>
                    <input type="date" className="input-field" value={editLeaveWizard.end_date} onChange={(e) => setEditLeaveWizard({ ...editLeaveWizard, end_date: e.target.value })} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Reason *</label>
                  <input type="text" className="input-field" value={editLeaveWizard.reason} onChange={(e) => setEditLeaveWizard({ ...editLeaveWizard, reason: e.target.value })} required />
                </div>
                <div className="modal-footer">
                  <Button variant="ghost" type="button" onClick={() => setShowEditLeaveWizard(false)}>Cancel</Button>
                  <Button variant="default" type="submit">Save Changes</Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </main>
    </>
  );
}

export default App;




