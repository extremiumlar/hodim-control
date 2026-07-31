/**
 * Push bildirishnomalar — ruxsat, token va toifalar.
 *
 * NEGA `getDevicePushTokenAsync` (nativ FCM tokeni), Expo tokeni EMAS:
 * `getExpoPushTokenAsync` EAS `projectId` talab qiladi, bizda esa build
 * butunlay lokal va Expo hisobi ataylab ishlatilmaydi
 * (MOBIL_ILOVA_REJASI.md 8.5). Backend to'g'ridan-to'g'ri FCM HTTP v1 ga
 * yuboradi (`api/services/push.py`) — bildirishnoma matnida oylik/bonus
 * summasi bo'lgani uchun ortiqcha uchinchi tomon relay'i ham keraksiz.
 *
 * Token FAQAT server tomonida ma'noga ega: qaysi toifa yoqiq, tinch soatlar
 * va Telegram takrorlanmasligi — hammasi backendda hal qilinadi. Ilova
 * shunchaki token beradi va toifalarni ko'rsatadi.
 */
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import {
  deletePushToken,
  fetchPushSettings,
  registerPushToken,
  savePushSettings,
  type PushSettings,
} from "./api";

export type { PushSettings };

/**
 * Ilova ochiq turganda kelgan bildirishnoma ham ko'rinsin.
 * Modul yuklanganda BIR MARTA o'rnatiladi (React komponentidan tashqarida) —
 * aks holda har renderda qayta ro'yxatdan o'tardi.
 */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/**
 * Android'da bildirishnoma kanallari. Kanal = foydalanuvchi tizim
 * sozlamalarida alohida boshqara oladigan toifa. Backend har xabarda
 * `channel_id` yuboradi (`api/services/push.py: _fcm_message`), shuning
 * uchun kanallar SHU nomlar bilan oldindan yaratilishi kerak — aks holda
 * Android xabarni standart kanalga tashlaydi va ovoz sozlamasi ishlamaydi.
 */
const CHANNELS: { id: string; name: string }[] = [
  { id: "late_warning", name: "Kechikish ogohlantirishi" },
  { id: "tasks", name: "Vazifalar" },
  { id: "decisions", name: "Qaror natijasi" },
  { id: "plan_reminders", name: "Reja eslatmalari" },
  { id: "approvals", name: "Tasdiq kutilmoqda" },
  { id: "sales_signals", name: "Sotuv signallari" },
  { id: "digests", name: "Kunlik/haftalik xulosa" },
];

async function ensureChannels(): Promise<void> {
  if (Platform.OS !== "android") return;
  for (const c of CHANNELS) {
    await Notifications.setNotificationChannelAsync(c.id, {
      name: c.name,
      importance: Notifications.AndroidImportance.DEFAULT,
    });
    // Tinch soatlar (22:00-08:00) uchun ovozsiz juftlik — backend o'sha
    // paytda `<toifa>_quiet` kanalini tanlaydi.
    await Notifications.setNotificationChannelAsync(`${c.id}_quiet`, {
      name: `${c.name} (jim)`,
      importance: Notifications.AndroidImportance.LOW,
      sound: null,
    });
  }
}

/**
 * Ruxsat so'raydi va tokenni serverga yozadi.
 * Qaytaradi: token muvaffaqiyatli ro'yxatdan o'tdimi.
 *
 * Emulyatorda push ishlamaydi (`Device.isDevice`) — u yerda jim `false`
 * qaytadi, xato ko'rsatilmaydi.
 */
export async function registerForPush(): Promise<boolean> {
  if (!Device.isDevice) return false;

  await ensureChannels();

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    // Android 13+ da tizim so'rovi shu chaqiruvda chiqadi.
    const asked = await Notifications.requestPermissionsAsync();
    status = asked.status;
  }
  if (status !== "granted") return false;

  try {
    const device = await Notifications.getDevicePushTokenAsync();
    await registerPushToken(String(device.data), Platform.OS === "ios" ? "ios" : "android");
    return true;
  } catch {
    // FCM sozlanmagan APK'da token olinmaydi — bu XATO EMAS, push shunchaki
    // o'chiq. Telegram xabarlari avvalgidek keladi.
    return false;
  }
}

/** Chiqishda — bu qurilmaga endi push ketmasin. */
export async function unregisterPush(): Promise<void> {
  if (!Device.isDevice) return;
  try {
    const device = await Notifications.getDevicePushTokenAsync();
    await deletePushToken(String(device.data), Platform.OS === "ios" ? "ios" : "android");
  } catch {
    // Token olinmasa ham chiqishga to'sqinlik qilmaydi.
  }
}

export const getPushSettings = fetchPushSettings;
export const updatePushSettings = savePushSettings;

/**
 * Bildirishnoma bosilganda ochiladigan bo'lim yo'li.
 * Backend har push'ga `data.path` qo'shadi (`api/notify.py`).
 */
export function pathFromNotification(
  response: Notifications.NotificationResponse | null
): string | null {
  const data = response?.notification?.request?.content?.data as
    | Record<string, unknown>
    | undefined;
  const path = data?.path;
  // Faqat o'z saytimizning ichki yo'li — tashqi manzil ochilmasin.
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) return null;
  return path;
}
