import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import App from "./App";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;

function authToken(role = "tenant_owner") {
  return `header.${btoa(JSON.stringify({ sub: "owner-1", role, tenant_id: "tenant-1" }))}.sig`;
}

function findButton(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent?.includes(label),
  );
}

function apiPayload(url: string) {
  if (url.includes("/api/v1/branches")) {
    return { success: true, data: { items: [{ id: "branch-1", name: "Main Store", code: "MAIN", status: "active" }] } };
  }
  if (url.includes("/api/v1/integrations/status")) {
    const ready = { configured: true, missing: [] };
    return {
      success: true,
      data: {
        password_reset_mail: ready,
        razorpay: { ...ready, webhook_url: "https://api.example.com/api/v1/integrations/razorpay/webhook" },
        razorpayx: { ...ready, webhook_url: "https://api.example.com/api/v1/integrations/razorpayx/webhook" },
        swiggy: ready,
        zomato: ready,
      },
    };
  }
  if (url.includes("/api/v1/reports/manager-dashboard")) {
    return {
      success: true,
      data: {
        today_sales: "0.00",
        today_collection: "0.00",
        revenue: "0.00",
        last_month_sales: "0.00",
        today_orders: 0,
        total_orders: 0,
        completed_orders: 0,
        pending_orders: 0,
        active_orders: 0,
        active_tables: 0,
        available_tables: 0,
        occupied_tables: 0,
        reserved_tables: 0,
        cleaning_tables: 0,
        low_stock_alerts: 0,
        total_stock_items: 0,
        attendance_today: 0,
        purchase_orders_today: 0,
        purchase_orders_month: 0,
        pending_discount_requests: 0,
        pending_payroll_count: 0,
        top_selling_products: [],
        active_staff: 0,
        pending_payments: 0,
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
      },
    };
  }
  if (url.includes("/api/v1/settings/tax")) {
    return { success: true, data: { food_gst_rate: 5, service_charge_rate: 0 } };
  }
  if (url.includes("/api/v1/admin/security-settings")) {
    return {
      success: true,
      data: {
        password_min_length: 8,
        session_timeout_minutes: 30,
        multi_device_login: true,
        two_factor_auth: false,
        login_attempts_threshold: 5,
      },
    };
  }
  if (url.includes("/api/v1/integrations/password-reset-mail/test")) {
    return { success: true, data: { email_delivery: "sent", recipient: "owner@example.com" } };
  }
  return { success: true, data: { items: [] } };
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="route-path">{location.pathname}{location.search}</output>;
}

function BackButton() {
  const navigate = useNavigate();
  return <button data-testid="history-back" onClick={() => navigate(-1)}>Test back</button>;
}

function routedApp(initialPath = "/dashboard") {
  return (
    <MemoryRouter key={initialPath} initialEntries={[initialPath]}>
      <App />
      <LocationProbe />
      <BackButton />
    </MemoryRouter>
  );
}

async function settle(delay = 500) {
  await new Promise((resolve) => window.setTimeout(resolve, delay));
}

afterEach(() => {
  if (root) {
    act(() => root?.unmount());
    root = null;
  }
  localStorage.clear();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("App integration settings", () => {
  it("sends a password reset mail test from the configured mail row", async () => {
    localStorage.setItem("token", authToken());
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = apiPayload(url);
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp("/settings/integrations"));
      await Promise.resolve();
      await Promise.resolve();
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    });

    const testButton = findButton(container, "Send test email");
    expect(testButton).toBeTruthy();

    await act(async () => {
      testButton?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/integrations/password-reset-mail/test"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(container.textContent).toContain("Test email sent");
  });
});

describe("App routes", () => {
  it("opens every sidebar screen on its canonical route", async () => {
    localStorage.setItem("token", authToken("super_admin"));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    const screens = [
      ["Dashboard", "/dashboard", "Sales Performance"],
      ["POS Billing", "/pos", "Menu Items"],
      ["Orders", "/orders", "Orders Console"],
      ["Online Delivery", "/online-delivery", "Aggregator intake"],
      ["KDS", "/kds", "No orders"],
      ["Table Management", "/tables", "Visual Floor Plan"],
      ["Menu", "/menu", "Menu Items & Variants"],
      ["Inventory", "/inventory", "Stock Levels"],
      ["Staff", "/staff", "Employee Directory"],
      ["Reports", "/reports", "Daily Sales Summary"],
      ["Razorpay Dashboard", "/razorpay", "Razorpay control room"],
      ["Settings", "/settings", "Security Policy"],
      ["Admin Panel", "/admin", "Store Management"],
      ["Platform", "/platform", "Platform Overview"],
    ] as const;

    root = createRoot(container);

    for (const [section, path, marker] of screens) {
      await act(async () => {
        root?.render(routedApp(path));
        await settle(350);
      });
      expect(container.querySelector('[data-testid="route-path"]')?.textContent, section).toBe(path);
      expect(container.querySelector("h1")?.textContent, section).toBe(section);
      expect(container.textContent, section).toContain(marker);
    }
  }, 60_000);

  it("opens a tabbed screen directly from its URL", async () => {
    localStorage.setItem("token", authToken());
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp("/staff/payroll"));
      await settle();
    });

    expect(container.querySelector("h1")?.textContent).toBe("Staff");
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/staff/payroll");
    const payrollTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "payroll" && button.classList.contains("active"),
    );
    expect(payrollTab, container.textContent || "").toBeTruthy();
  });

  it("restores delivery and admin tabs from nested routes", async () => {
    localStorage.setItem("token", authToken("super_admin"));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(routedApp("/online-delivery/needs-mapping"));
      await settle(350);
    });
    const mappingTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Needs Mapping") && button.classList.contains("active"),
    );
    expect(mappingTab, container.textContent || "").toBeTruthy();

    await act(async () => {
      root?.render(routedApp("/admin/security"));
      await settle(350);
    });
    const securityTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Security Policy") && button.classList.contains("active"),
    );
    expect(securityTab, container.textContent || "").toBeTruthy();
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/admin/security");
  });

  it("updates the URL from sidebar navigation and responds to history back", async () => {
    localStorage.setItem("token", authToken());
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp());
      await settle();
    });

    await act(async () => {
      container.querySelector<HTMLButtonElement>('button[title="Orders"]')?.click();
      await settle(50);
    });
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/orders");
    expect(container.querySelector("h1")?.textContent).toBe("Orders");

    await act(async () => {
      container.querySelector<HTMLButtonElement>('button[title="Settings"]')?.click();
      await settle(50);
    });
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/settings");

    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-testid="history-back"]')?.click();
      await settle(500);
    });
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/orders");
    expect(container.querySelector("h1")?.textContent).toBe("Orders");
  });

  it("canonicalizes legacy routes and rejects role-forbidden routes", async () => {
    localStorage.setItem("token", authToken("cashier"));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp("/admin-panel/users"));
      await settle();
    });

    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/dashboard");
    expect(container.querySelector("h1")?.textContent).toBe("Dashboard");
  });

  it("opens password reset only on the reset route", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp("/reset-password?token=reset-123"));
      await settle(50);
    });

    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/reset-password?token=reset-123");
    expect(container.textContent).toContain("Set new password");
  });

  it("closes the forgot-password modal when browser history returns to login", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = apiPayload(String(input));
      return {
        ok: true,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
      } as Response;
    }));
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(routedApp("/login"));
      await settle(50);
    });
    await act(async () => {
      findButton(container, "Forgot password")?.click();
      await settle(50);
    });
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/forgot-password");
    expect(container.textContent).toContain("Send reset link");

    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-testid="history-back"]')?.click();
      await settle(500);
    });
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe("/login");
    expect(container.textContent).not.toContain("Send reset link");
  });
});
