import { describe, expect, it } from "vitest";
import { qrOrderUrl } from "./qr";

describe("qr order url", () => {
  it("uses the configured public app URL for customer QR links", () => {
    expect(
      qrOrderUrl({
        branchId: "branch 123",
        tableId: "table/7",
        currentOrigin: "http://localhost:5173",
        publicAppUrl: " https://pos.example.com/app/ ",
      }),
    ).toBe("https://pos.example.com/app/qr-order?branch_id=branch%20123&table_id=table%2F7");
  });

  it("falls back to the current browser origin when no public URL is configured", () => {
    expect(
      qrOrderUrl({
        branchId: "branch 123",
        tableId: "table/7",
        currentOrigin: "http://localhost:5173",
        publicAppUrl: "   ",
      }),
    ).toBe("http://localhost:5173/qr-order?branch_id=branch%20123&table_id=table%2F7");
  });
});
