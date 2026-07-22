import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import QrOrderPage from "./QrOrderPage";

function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify({ success: status < 400, data }), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

describe("QR ordering page", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    window.history.replaceState({}, "", "/qr-order?branch_id=branch-1&table_id=table-1");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/qr/menu")) {
        return response({
          branch: { id: "branch-1", name: "QR Branch" },
          table: { id: "table-1", name: "T1", status: "available", floor_area: "Main" },
          categories: [],
          products: [{
            id: "meal-1",
            name: "QR Meal",
            price: "120.00",
            tax_rate: "0.00",
            variants: [{ name: "Large", price_delta: "40.00" }],
            addons: [{ name: "Extra Chutney", price: "20.00" }],
          }],
        });
      }
      if (url.endsWith("/api/v1/qr/orders") && init?.method === "POST") {
        return response({ id: "order-1", total: "180.00", payment_status: "unpaid", kds_status: "new" }, 201);
      }
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("submits selected variants and add-ons without client prices", async () => {
    await act(async () => root.render(<QrOrderPage />));
    await flush();

    const addButton = Array.from(container.querySelectorAll("button")).find((button) => button.getAttribute("aria-label") === "Add QR Meal");
    const variant = container.querySelector<HTMLSelectElement>('select[aria-label="Size for QR Meal"]');
    const addon = container.querySelector<HTMLInputElement>('input[aria-label="Add Extra Chutney to QR Meal"]');
    expect(addButton).toBeTruthy();
    expect(variant).toBeTruthy();
    expect(addon).toBeTruthy();

    await act(async () => {
      addButton!.click();
      variant!.value = "Large";
      variant!.dispatchEvent(new Event("change", { bubbles: true }));
      addon!.click();
    });
    expect(container.textContent).toContain("Rs. 180.00");

    const placeOrder = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Place order"));
    await act(async () => placeOrder!.click());
    await flush();

    const request = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/api/v1/qr/orders") && init?.method === "POST");
    expect(request).toBeTruthy();
    const body = JSON.parse(String(request![1]?.body));
    expect(body.items).toEqual([{
      product_id: "meal-1",
      quantity: 1,
      variant_name: "Large",
      addons: [{ name: "Extra Chutney" }],
    }]);
  });
});
