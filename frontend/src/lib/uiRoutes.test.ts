import { describe, expect, it } from "vitest";
import {
  APP_ROUTES,
  isPublicAuthPath,
  pathForSection,
  resolveAppRoute,
} from "./uiRoutes";

describe("UI route registry", () => {
  it("round-trips every sidebar section through a canonical path", () => {
    expect(APP_ROUTES).toHaveLength(14);
    for (const route of APP_ROUTES) {
      expect(pathForSection(route.section)).toBe(route.path);
      expect(resolveAppRoute(route.path)).toEqual({
        section: route.section,
        canonicalPath: route.path,
        child: null,
      });
    }
  });

  it("exposes the platform dashboard as a real route", () => {
    expect(pathForSection("Platform")).toBe("/platform");
    expect(resolveAppRoute("/platform-dashboard")).toEqual({
      section: "Platform",
      canonicalPath: "/platform",
      child: null,
    });
  });

  it("resolves bookmarks for each tabbed screen", () => {
    expect(resolveAppRoute("/staff/payroll")).toMatchObject({ section: "Staff", child: "payroll" });
    expect(resolveAppRoute("/settings/integrations")).toMatchObject({ section: "Settings", child: "integrations" });
    expect(resolveAppRoute("/online-delivery/needs-mapping")).toMatchObject({ section: "Online Delivery", child: "needs_mapping" });
    expect(resolveAppRoute("/admin/security")).toMatchObject({ section: "Admin Panel", child: "security" });
  });

  it("canonicalizes supported legacy names and trailing slashes", () => {
    expect(resolveAppRoute("/pos-billing/")?.canonicalPath).toBe("/pos");
    expect(resolveAppRoute("/table-management")?.canonicalPath).toBe("/tables");
    expect(resolveAppRoute("/razorpay-dashboard")?.canonicalPath).toBe("/razorpay");
    expect(resolveAppRoute("/admin-panel/users")?.canonicalPath).toBe("/admin/users");
  });

  it("rejects unknown screens and invalid tab names", () => {
    expect(resolveAppRoute("/not-a-screen")).toBeNull();
    expect(resolveAppRoute("/staff/not-a-tab")).toBeNull();
    expect(resolveAppRoute("/orders/extra")).toBeNull();
  });

  it("recognizes only the public authentication paths", () => {
    expect(isPublicAuthPath("/login")).toBe(true);
    expect(isPublicAuthPath("/forgot-password")).toBe(true);
    expect(isPublicAuthPath("/reset-password/")).toBe(true);
    expect(isPublicAuthPath("/orders")).toBe(false);
  });
});
