export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const UNAUTHORIZED_EVENT = "auth:unauthorized";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /**
     * Serverning `detail` maydoni OBYEKT bo'lsa — o'zgarmagan holda.
     *
     * NEGA: ba'zi xatolar shunchaki matn emas, qaror talab qiladi —
     * masalan avans dublikati (409) `existing_id` bilan keladi va oyna
     * «baribir kiritaman» tugmasini ko'rsatishi kerak. Ilgari obyekt
     * `String()` ga tushib «[object Object]» bo'lib qolardi.
     */
    public payload: Record<string, unknown> | null = null
  ) {
    super(message);
  }
}

/** `detail` matnmi yoki obyektmi — ikkalasini ham bir xil qaytaradi. */
function parseDetail(
  detail: unknown,
  fallback: string
): { message: string; payload: Record<string, unknown> | null } {
  if (typeof detail === "string" && detail) return { message: detail, payload: null };
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    const msg = typeof obj.message === "string" ? obj.message : fallback;
    return { message: msg, payload: obj };
  }
  return { message: fallback, payload: null };
}

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // UX2-MC7: tarmoq uzilganda fetch inglizcha "Failed to fetch" bilan
  // yiqilardi va xodim aynan check-in lahzasida tushunarsiz xato ko'rardi.
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Internet aloqasi yo'q. Tarmoqni tekshirib qayta urinib ko'ring.");
  }

  if (!resp.ok) {
    let raw: unknown = null;
    try {
      const body = await resp.json();
      raw = body.detail;
    } catch {
      // ignore
    }
    const { message, payload } = parseDetail(raw, resp.statusText);
    if (resp.status === 401) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(resp.status, message, payload);
  }

  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

/**
 * Fayl yuklash (multipart). `apiFetch` dan alohida, chunki u har doim
 * `Content-Type: application/json` qo'yadi — FormData bilan bu chegarani
 * (boundary) buzadi va server faylni umuman ko'rmaydi. Bu yerda Content-Type
 * ATAYLAB qo'yilmaydi: brauzer o'zi to'g'ri boundary bilan qo'yadi.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: form, headers });
  } catch {
    throw new ApiError(0, "Internet aloqasi yo'q. Tarmoqni tekshirib qayta urinib ko'ring.");
  }

  if (!resp.ok) {
    let raw: unknown = null;
    try {
      const body = await resp.json();
      raw = body.detail;
    } catch {
      // ignore
    }
    const { message, payload } = parseDetail(raw, resp.statusText);
    if (resp.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(resp.status, message, payload);
  }
  return (await resp.json()) as T;
}
