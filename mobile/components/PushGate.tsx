/**
 * Push'ning ilova darajasidagi qismi:
 *   1. Kirgan foydalanuvchi uchun tokenni ro'yxatdan o'tkazish (va har
 *      ochilishda `last_seen_at`ni yangilash — backend aynan shunga qarab
 *      Telegram xabarini takrorlash/takrorlamaslikni hal qiladi).
 *   2. Bildirishnoma bosilganda tegishli bo'limni ochish.
 *
 * NEGA ALOHIDA KOMPONENT: `_layout.tsx` faqat provayderlarni yig'adi va
 * `useAuth`ni CHAQIRA OLMAYDI — u `AuthProvider` ichida bo'lishi shart.
 * Shu komponent provayder ichida turadi va hech narsa render qilmaydi.
 */
import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { useEffect, useRef } from "react";

import { useAuth } from "../lib/auth";
import { pathFromNotification, registerForPush } from "../lib/push";

function openFromPath(path: string) {
  router.push({ pathname: "/view", params: { path, title: "Bildirishnoma" } } as never);
}

export default function PushGate() {
  const { user } = useAuth();
  // Sovuq startdagi bildirishnoma BIR MARTA ochilsin — aks holda har
  // render/qayta ulanishda o'sha ekran qayta-qayta ochilaverardi.
  const coldStartHandled = useRef(false);

  useEffect(() => {
    if (!user) return;
    void registerForPush();
  }, [user]);

  useEffect(() => {
    if (!user) return;

    // (a) Ilova YOPIQ bo'lganda bosilgan bildirishnoma.
    if (!coldStartHandled.current) {
      coldStartHandled.current = true;
      void Notifications.getLastNotificationResponseAsync().then((response) => {
        const path = pathFromNotification(response);
        if (path) openFromPath(path);
      });
    }

    // (b) Ilova ochiq/fonda bo'lganda bosilgan bildirishnoma.
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      const path = pathFromNotification(response);
      if (path) openFromPath(path);
    });
    return () => sub.remove();
  }, [user]);

  return null;
}
