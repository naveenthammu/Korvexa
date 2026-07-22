const defaultApiBase =
  typeof window === "undefined"
    ? "http://localhost:8000"
    : import.meta.env.DEV
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : window.location.origin;

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? defaultApiBase;

type ApiOptions = RequestInit & { token?: string };

export const ACCESS_TOKEN_KEY = "token";
export const REFRESH_TOKEN_KEY = "refresh_token";
export const AUTH_TOKEN_REFRESHED_EVENT = "korvexa:auth-token-refreshed";
export const AUTH_SESSION_EXPIRED_EVENT = "korvexa:auth-session-expired";

let refreshRequest: Promise<string | null> | null = null;
let sessionExpiredEventSent = false;

function browserStorage(): Storage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

export function storeAuthTokens(accessToken: string, refreshToken?: string | null): void {
  const storage = browserStorage();
  if (!storage) return;
  storage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) storage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  else storage.removeItem(REFRESH_TOKEN_KEY);
  sessionExpiredEventSent = false;
}

export function clearStoredAuthTokens(): void {
  const storage = browserStorage();
  storage?.removeItem(ACCESS_TOKEN_KEY);
  storage?.removeItem(REFRESH_TOKEN_KEY);
}

function dispatchSessionExpired(): void {
  clearStoredAuthTokens();
  if (typeof window === "undefined" || sessionExpiredEventSent) return;
  sessionExpiredEventSent = true;
  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshRequest) return refreshRequest;
  refreshRequest = (async () => {
    const storedRefreshToken = browserStorage()?.getItem(REFRESH_TOKEN_KEY);
    if (!storedRefreshToken) {
      dispatchSessionExpired();
      return null;
    }
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      });
      if (!response.ok) {
        dispatchSessionExpired();
        return null;
      }
      const payload = await response.json();
      const data = payload?.data ?? payload;
      if (!data?.access_token || !data?.refresh_token) {
        dispatchSessionExpired();
        return null;
      }
      storeAuthTokens(data.access_token, data.refresh_token);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(AUTH_TOKEN_REFRESHED_EVENT, { detail: data.access_token }));
      }
      return data.access_token as string;
    } catch {
      dispatchSessionExpired();
      return null;
    }
  })();
  try {
    return await refreshRequest;
  } finally {
    refreshRequest = null;
  }
}

function canRefreshRequest(path: string, token?: string): boolean {
  return Boolean(token) && ![
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
  ].includes(path);
}

export type ReceiptPrintData = {
  text: string;
  receipt_name?: string;
  gst_number?: string;
  upi_id?: string;
  upi_qr_url?: string;
  upi_payment_uri?: string;
  bill_no?: string;
};

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { token, ...requestOptions } = options;
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response = await fetch(`${API_BASE}${path}`, { ...requestOptions, headers });
  if (response.status === 401 && canRefreshRequest(path, token)) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      headers.set("Authorization", `Bearer ${refreshedToken}`);
      response = await fetch(`${API_BASE}${path}`, { ...requestOptions, headers });
    }
  }
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
}

export async function printReceipt(orderId: string, token: string): Promise<ReceiptPrintData> {
  const printResponse = await fetch(`${API_BASE}/api/v1/orders/${orderId}/receipt-print`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (printResponse.ok) {
    const payload = await printResponse.json();
    return payload.data ?? payload;
  }

  const response = await fetch(`${API_BASE}/api/v1/orders/${orderId}/receipt`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return { text: await response.text() };
}
