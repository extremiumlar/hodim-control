import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

// Ilova "/verifix" prefiksi (basePath) ostida ishlaydi. router.push/replace va
// <Link> basePath'ni avtomatik qo'shadi, lekin xom window.location.href QO'SHMAYDI —
// shuning uchun to'liq sahifa redirect'larida prefiksni qo'lda qo'shamiz, aks holda
// brauzer /login ga o'tib, gateway ostidagi asosiy ilovaga (hodimlar_tizimi) qaytadi.
// next.config.js dagi basePath bilan bir xil bo'lishi shart.
const BASE_PATH = "/verifix";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Brauzerda token qo'shamiz
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("verifix_access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 401 da refresh ga urinib ko'ramiz
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original?._retry && typeof window !== "undefined") {
      original._retry = true;
      const refresh = localStorage.getItem("verifix_refresh_token");
      if (refresh) {
        try {
          const r = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
          localStorage.setItem("verifix_access_token", r.data.access);
          original.headers.Authorization = `Bearer ${r.data.access}`;
          return api(original);
        } catch {
          localStorage.removeItem("verifix_access_token");
          localStorage.removeItem("verifix_refresh_token");
          window.location.href = BASE_PATH + "/login";
        }
      } else {
        window.location.href = BASE_PATH + "/login";
      }
    }
    return Promise.reject(err);
  }
);

export async function login(username: string, password: string) {
  const r = await axios.post(`${API_BASE}/auth/token/`, { username, password });
  localStorage.setItem("verifix_access_token", r.data.access);
  localStorage.setItem("verifix_refresh_token", r.data.refresh);
  return r.data;
}

export function logout() {
  localStorage.removeItem("verifix_access_token");
  localStorage.removeItem("verifix_refresh_token");
  if (typeof window !== "undefined") window.location.href = BASE_PATH + "/login";
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("verifix_access_token");
}
