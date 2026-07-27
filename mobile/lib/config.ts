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
