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
    // 401 — token yaroqsiz yoki xodim faolsizlantirilgan (`is_active=false`
    // serverda tokenni darhol kesadi). Saqlangan tokenni SHU YERDA
    // tozalaymiz: ilgari u faqat ilova sovuq ishga tushganda tekshirilardi,
    // ya'ni bekor qilingan token telefonda kun bo'yi qolib ketardi.
    if (auth && resp.status === 401) {
      await clearStoredToken();
    }
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
  /** Ilova ekranida ko'rsatiladi, foydalanuvchi uni BOTGA yozadi. */
  pairing_code: string;
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

/**
 * UX2-qoldiq #13: WebView uchun QISQA muddatli (30 daq) token. Asosiy 30
 * kunlik JWT SecureStore'da qoladi; WebView localStorage'iga faqat shu
 * qisqa nusxa kiritiladi — sizib chiqsa ham zarar oynasi kichik.
 */
export function issueWebviewToken(): Promise<{ access_token: string; expires_in_minutes: number }> {
  return request("/auth/webview-token", { method: "POST" });
}

// ── Push bildirishnomalar ──

export interface PushSettings {
  categories: Record<string, boolean>;
  /** Toifa nomlari SERVERDAN keladi — ilova ro'yxatni takrorlamasin. */
  labels: Record<string, string>;
  quiet_from: number;
  quiet_to: number;
}

export function registerPushToken(token: string, platform: "android" | "ios"): Promise<{ ok: boolean }> {
  return request("/me/push/token", { method: "POST", body: { token, platform } });
}

export function deletePushToken(token: string, platform: "android" | "ios"): Promise<{ ok: boolean }> {
  return request("/me/push/token", { method: "DELETE", body: { token, platform } });
}

export function fetchPushSettings(): Promise<PushSettings> {
  return request("/me/push/settings");
}

export function savePushSettings(categories: Record<string, boolean>): Promise<PushSettings> {
  return request("/me/push/settings", { method: "PUT", body: { categories } });
}
