import * as SecureStore from "expo-secure-store";

import { API_BASE_URL } from "./config";

const TOKEN_KEY = "auth_token";

export async function getStoredToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function setStoredToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function clearStoredToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (auth) {
    const token = await getStoredToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // javob JSON emas — statusText yetarli
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ── Auth (MOBIL_ILOVA_REJASI.md 4.1-band) ──

export interface UserOut {
  id: number;
  telegram_id: number | null;
  full_name: string;
  role: string;
  team_id: number | null;
  position: { id: number; name: string; menu_flags: Record<string, boolean> | null; metrics: string[] | null } | null;
}

export interface TokenOut {
  access_token: string;
  user: UserOut;
}

export interface AppLoginStart {
  login_token: string;
  deep_link: string;
  expires_at: string;
}

export function appLoginStart(): Promise<AppLoginStart> {
  return request("/auth/app-login/start", { method: "POST", auth: false });
}

export function appLoginPoll(
  loginToken: string,
): Promise<{ status: "pending" | "confirmed" | "expired"; token: TokenOut | null }> {
  return request("/auth/app-login/poll", {
    method: "POST",
    body: { login_token: loginToken },
    auth: false,
  });
}

export function getMe(): Promise<UserOut> {
  return request("/users/me");
}
