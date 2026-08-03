/**
 * Web push (brauzer/PWA) — iPhone uchun ASOSIY yo'l.
 *
 * NEGA Firebase SDK, xom Web Push emas: backend allaqachon FCM HTTP v1
 * (`messages:send`) orqali yuboradi. FCM web tokenlari ham AYNAN shu API
 * bilan ishlaydi, ya'ni serverga yangi yuborish yo'li yozish SHART EMAS —
 * token oddiygina `push_tokens` jadvaliga `platform="web"` bilan tushadi.
 * Xom Web Push (VAPID + pywebpush) tanlansa, ikkinchi mustaqil yuborish
 * qatlami paydo bo'lardi.
 *
 * Android'da bu KERAK EMAS — u yerda nativ APK o'z FCM tokenini oladi
 * (`mobile/lib/push.ts`). Bu modul brauzer/PWA uchun.
 */
import { api } from "./api";

// Firebase web config — MAXFIY EMAS (ochiq ma'lumot). Himoya server
// tomonidagi service-account kalitida. Bo'sh bo'lsa modul o'zini jimgina
// o'chirib qo'yadi va UI "sozlanmagan" holatini ko'rsatadi.
const CONFIG = {
  apiKey: import.meta.env.VITE_FCM_API_KEY ?? "",
  authDomain: import.meta.env.VITE_FCM_AUTH_DOMAIN ?? "",
  projectId: import.meta.env.VITE_FCM_PROJECT_ID ?? "",
  messagingSenderId: import.meta.env.VITE_FCM_SENDER_ID ?? "",
  appId: import.meta.env.VITE_FCM_APP_ID ?? "",
};
const VAPID_KEY = import.meta.env.VITE_FCM_VAPID_KEY ?? "";

export const pushConfigured = Boolean(CONFIG.apiKey && CONFIG.projectId && VAPID_KEY);

/** PWA bosh ekrandan ochilganmi (iOS'da push uchun SHART). */
export function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari'ning eski, nostandart bayrog'i — `matchMedia` ba'zi
    // versiyalarda standalone PWA'da ham false qaytaradi.
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function isIos(): boolean {
  // iPadOS 13+ o'zini "Macintosh" deb tanishtiradi — sensorli ekran bo'yicha
  // ajratamiz, aks holda iPad iOS emas deb hisoblanardi.
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
}

export type PushSupport =
  | { ok: true }
  | { ok: false; reason: "not-configured" | "ios-needs-home-screen" | "unsupported" };

/**
 * Shu brauzerda web push mumkinmi.
 *
 * iOS'da tartib MUHIM: `standalone` tekshiruvi Notification API'dan OLDIN
 * turadi. Sabab — iOS Safari'ning oddiy tabida `Notification` obyekti
 * umuman mavjud emas, ya'ni "unsupported" deb xulosa chiqarilardi va xodim
 * "telefonim eski" deb o'ylardi. Aslida yechim — bosh ekranga qo'shish.
 */
export function checkSupport(): PushSupport {
  if (!pushConfigured) return { ok: false, reason: "not-configured" };
  if (isIos() && !isStandalone()) return { ok: false, reason: "ios-needs-home-screen" };
  if (!("serviceWorker" in navigator) || typeof Notification === "undefined") {
    return { ok: false, reason: "unsupported" };
  }
  return { ok: true };
}

export function permissionState(): NotificationPermission | "unavailable" {
  if (typeof Notification === "undefined") return "unavailable";
  return Notification.permission;
}

async function swRegistration(): Promise<ServiceWorkerRegistration> {
  // Sozlama query orqali uzatiladi — service worker Vite env'ni ko'rmaydi
  // (`public/firebase-messaging-sw.js` izohiga qarang).
  const url = `/firebase-messaging-sw.js?config=${encodeURIComponent(JSON.stringify(CONFIG))}`;
  return navigator.serviceWorker.register(url, { scope: "/" });
}

/**
 * Ruxsat so'raydi va tokenni serverga yozadi.
 *
 * ⚠️ FAQAT foydalanuvchi BOSGANDA chaqirilsin: iOS ruxsat so'rovini
 * foydalanuvchi harakatisiz (masalan sahifa ochilganda) bloklaydi va
 * `Notification.permission` jimgina "denied" bo'lib qoladi — keyin uni
 * qaytarish faqat sayt sozlamalarini qo'lda tozalash bilan mumkin.
 */
export async function enableWebPush(): Promise<{ ok: boolean; error?: string }> {
  const support = checkSupport();
  if (!support.ok) return { ok: false, error: support.reason };

  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return { ok: false, error: "denied" };

    // Dinamik import: Firebase SDK ~200 KB. Bildirishnomani yoqmagan
    // xodim (va butun rahbar paneli) uni umuman yuklamaydi.
    const [{ initializeApp }, { getMessaging, getToken }] = await Promise.all([
      import("firebase/app"),
      import("firebase/messaging"),
    ]);

    const registration = await swRegistration();
    const app = initializeApp(CONFIG);
    const token = await getToken(getMessaging(app), {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: registration,
    });
    if (!token) return { ok: false, error: "no-token" };

    await api.registerPushToken(token, "web");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "error" };
  }
}

/** Chiqishda/o'chirishda — bu brauzerga endi push ketmasin. */
export async function disableWebPush(): Promise<void> {
  if (!pushConfigured) return;
  try {
    const [{ initializeApp }, { getMessaging, getToken, deleteToken }] = await Promise.all([
      import("firebase/app"),
      import("firebase/messaging"),
    ]);
    const registration = await swRegistration();
    const messaging = getMessaging(initializeApp(CONFIG));
    const token = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: registration,
    });
    if (token) {
      await api.unregisterPushToken(token, "web");
      await deleteToken(messaging);
    }
  } catch {
    // Token olinmasa ham chiqishga to'sqinlik qilmasin.
  }
}
