import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ACCESS_TOKEN_KEY,
  AUTH_SESSION_EXPIRED_EVENT,
  AUTH_TOKEN_REFRESHED_EVENT,
  REFRESH_TOKEN_KEY,
  apiRequest,
  storeAuthTokens,
} from "./api";

function mockResponse(status: number, payload: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("API authentication refresh", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("rotates tokens and retries an expired authenticated request", async () => {
    storeAuthTokens("expired-access", "valid-refresh");
    const refreshedEvents: string[] = [];
    window.addEventListener(
      AUTH_TOKEN_REFRESHED_EVENT,
      (event) => refreshedEvents.push((event as CustomEvent<string>).detail),
      { once: true },
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(mockResponse(200, {
        success: true,
        data: { access_token: "new-access", refresh_token: "new-refresh" },
      }))
      .mockResolvedValueOnce(mockResponse(200, { success: true, data: { items: ["loaded"] } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest<{ success: boolean; data: { items: string[] } }>("/api/v1/branches", {
      token: "expired-access",
    });

    expect(result.data.items).toEqual(["loaded"]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect((fetchMock.mock.calls[2][1] as RequestInit).headers).toEqual(expect.any(Headers));
    expect(((fetchMock.mock.calls[2][1] as RequestInit).headers as Headers).get("Authorization")).toBe("Bearer new-access");
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe("new-access");
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe("new-refresh");
    expect(refreshedEvents).toEqual(["new-access"]);
  });

  it("clears stale tokens and announces an expired session when refresh fails", async () => {
    storeAuthTokens("expired-access", "expired-refresh");
    let expiredEvents = 0;
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, () => { expiredEvents += 1; }, { once: true });
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(mockResponse(401, { detail: "expired" }))
        .mockResolvedValueOnce(mockResponse(401, { detail: "invalid refresh" })),
    );

    await expect(apiRequest("/api/v1/branches", { token: "expired-access" })).rejects.toThrow();

    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(expiredEvents).toBe(1);
  });
});
