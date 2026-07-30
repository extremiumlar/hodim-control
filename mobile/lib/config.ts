import Constants from "expo-constants";

// Lokal dev: telefon "localhost"ni o'zining ichida qidiradi, shuning uchun
// kompyuterning LAN IP'si kerak. Expo dev-server manzilidan avtomatik olinadi
// (masalan "192.168.137.1:8081" -> "http://192.168.137.1:8000").
function devApiBase(): string | null {
  const hostUri = Constants.expoConfig?.hostUri;
  if (!hostUri) return null;
  const host = hostUri.split(":")[0];
  return `http://${host}:8000`;
}

export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? devApiBase() ?? "http://localhost:8000";

// ── WebView (davomat) uchun SAYT manzili — API manzili EMAS ──
// Prod'da bitta domen: API "/api" ostida, React sayt ildizda
// (deploy/cpanel/passenger_wsgi.py) → "https://domen.uz/api" -> "https://domen.uz".
function stripApiSuffix(api: string): string {
  return api.replace(/\/api\/?$/, "");
}

// Dev'da sayt vite'da (5173, HTTPS), API esa 8000-portda — ikki xil port,
// shuning uchun API manzilidan hisoblab bo'lmaydi, hostUri'dan qurish kerak.
// DIQQAT: vite dev'da o'z-o'zidan imzolangan sertifikat ishlatadi va WebView
// uni rad etadi — dev'da davomat ekranini sinash uchun prod manzilini
// EXPO_PUBLIC_WEB_BASE_URL bilan majburan berish qulayroq.
function devWebBase(): string | null {
  const hostUri = Constants.expoConfig?.hostUri;
  if (!hostUri) return null;
  return `https://${hostUri.split(":")[0]}:5173`;
}

export const WEB_BASE_URL =
  process.env.EXPO_PUBLIC_WEB_BASE_URL ?? devWebBase() ?? stripApiSuffix(API_BASE_URL);
