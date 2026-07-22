import type { NavSection } from "./auth";

export type AppRouteSection = NavSection;

type ChildRoute = {
  segment: string;
  value: string;
  aliases?: string[];
};

export type AppRouteDefinition = {
  section: AppRouteSection;
  path: string;
  aliases?: string[];
  children?: ChildRoute[];
};

export type ResolvedAppRoute = {
  section: AppRouteSection;
  canonicalPath: string;
  child: string | null;
};

export const APP_ROUTES: AppRouteDefinition[] = [
  { section: "Dashboard", path: "/dashboard", aliases: ["/home"] },
  { section: "POS Billing", path: "/pos", aliases: ["/billing", "/pos-billing"] },
  { section: "Orders", path: "/orders" },
  {
    section: "Online Delivery",
    path: "/online-delivery",
    aliases: ["/delivery", "/online-orders"],
    children: [
      { segment: "new", value: "new" },
      { segment: "needs-mapping", value: "needs_mapping", aliases: ["needs_mapping"] },
      { segment: "accepted", value: "accepted" },
      { segment: "ready", value: "ready" },
      { segment: "picked-up", value: "picked_up", aliases: ["picked_up"] },
      { segment: "delivered", value: "delivered" },
      { segment: "all", value: "all" },
    ],
  },
  { section: "KDS", path: "/kds", aliases: ["/kitchen"] },
  { section: "Table Management", path: "/tables", aliases: ["/table-management"] },
  { section: "Menu", path: "/menu" },
  { section: "Inventory", path: "/inventory", aliases: ["/stock"] },
  {
    section: "Staff",
    path: "/staff",
    aliases: ["/employees"],
    children: [
      { segment: "directory", value: "directory" },
      { segment: "attendance", value: "attendance" },
      { segment: "payroll", value: "payroll" },
      { segment: "incentives", value: "incentives" },
      { segment: "leaves", value: "leaves" },
    ],
  },
  { section: "Reports", path: "/reports", aliases: ["/analytics"] },
  { section: "Razorpay Dashboard", path: "/razorpay", aliases: ["/razorpay-dashboard", "/payments"] },
  {
    section: "Settings",
    path: "/settings",
    aliases: ["/configuration"],
    children: [
      { segment: "security", value: "security" },
      { segment: "profile", value: "profile" },
      { segment: "integrations", value: "integrations" },
      { segment: "appearance", value: "appearance" },
    ],
  },
  {
    section: "Admin Panel",
    path: "/admin",
    aliases: ["/admin-panel"],
    children: [
      { segment: "stores", value: "stores" },
      { segment: "users", value: "users" },
      { segment: "roles", value: "roles" },
      { segment: "taxes", value: "taxes", aliases: ["gst"] },
      { segment: "security", value: "security" },
    ],
  },
  { section: "Platform", path: "/platform", aliases: ["/platform-dashboard"] },
];

const PUBLIC_AUTH_PATHS = new Set(["/login", "/forgot-password", "/reset-password"]);

function normalizePathname(pathname: string): string {
  const withoutQuery = pathname.split(/[?#]/, 1)[0] || "/";
  const withLeadingSlash = withoutQuery.startsWith("/") ? withoutQuery : `/${withoutQuery}`;
  const collapsed = withLeadingSlash.replace(/\/{2,}/g, "/").toLowerCase();
  return collapsed.length > 1 ? collapsed.replace(/\/+$/, "") : collapsed;
}

function routeBaseMatch(pathname: string, route: AppRouteDefinition): string | null {
  for (const candidate of [route.path, ...(route.aliases || [])]) {
    if (pathname === candidate || pathname.startsWith(`${candidate}/`)) return candidate;
  }
  return null;
}

export function resolveAppRoute(pathname: string): ResolvedAppRoute | null {
  const normalized = normalizePathname(pathname);
  for (const route of APP_ROUTES) {
    const matchedBase = routeBaseMatch(normalized, route);
    if (!matchedBase) continue;
    const childSegment = normalized.slice(matchedBase.length).replace(/^\/+/, "");
    if (!childSegment) {
      return { section: route.section, canonicalPath: route.path, child: null };
    }
    if (childSegment.includes("/")) return null;
    const child = route.children?.find(
      (candidate) => candidate.segment === childSegment || candidate.aliases?.includes(childSegment),
    );
    if (!child) return null;
    return {
      section: route.section,
      canonicalPath: `${route.path}/${child.segment}`,
      child: child.value,
    };
  }
  return null;
}

export function pathForSection(section: AppRouteSection): string {
  return APP_ROUTES.find((route) => route.section === section)?.path || "/dashboard";
}

export function childPathForSection(section: AppRouteSection, child: string): string | null {
  const route = APP_ROUTES.find((candidate) => candidate.section === section);
  const childRoute = route?.children?.find((candidate) => candidate.value === child);
  return route && childRoute ? `${route.path}/${childRoute.segment}` : null;
}

export function isPublicAuthPath(pathname: string): boolean {
  return PUBLIC_AUTH_PATHS.has(normalizePathname(pathname));
}
