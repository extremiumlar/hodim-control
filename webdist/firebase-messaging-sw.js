/* Firebase Cloud Messaging service worker — WEB PUSH (iPhone uchun asosiy yo'l).
 *
 * NEGA `public/` ichida va aynan shu nom bilan: Firebase SDK bu faylni
 * ILDIZ scope'dan (`/firebase-messaging-sw.js`) qidiradi. `src/` ichiga
 * qo'yilsa Vite uni hash'langan nom bilan `assets/` ga ko'chirardi va SDK
 * topa olmasdi.
 *
 * NEGA sozlama QUERY orqali keladi (`?config=...`): service worker Vite env
 * o'zgaruvchilarini KO'RMAYDI (u build'dan o'tmaydi, `public/` dan xom
 * ko'chiriladi). Build paytida matn almashtirish ham mumkin edi, lekin u
 * jimgina buzilishi mumkin — query esa ro'yxatdan o'tkazish paytida
 * `lib/push.ts` tomonidan aniq uzatiladi va noto'g'ri bo'lsa darhol bilinadi.
 * Bu qiymatlar MAXFIY EMAS — Firebase web config ochiq ma'lumot; himoya
 * server tomonidagi service-account kalitida.
 *
 * ⚠️ iOS SHARTLARI (Apple cheklovi, kod bilan chetlab o'tib bo'lmaydi):
 *   1. iOS 16.4+ ;
 *   2. sayt BOSH EKRANGA qo'shilgan (standalone) bo'lishi SHART — oddiy
 *      Safari tabida push umuman kelmaydi.
 */
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js");

try {
  const raw = new URL(self.location).searchParams.get("config");
  if (raw) {
    firebase.initializeApp(JSON.parse(raw));
    const messaging = firebase.messaging();

    // Ilova YOPIQ/fonda bo'lganda kelgan xabar. Backend `webpush.notification`
    // blokini yuboradi, ya'ni brauzer odatda o'zi ko'rsatadi — bu ishlovchi
    // data-only xabar kelgan holat uchun zaxira.
    messaging.onBackgroundMessage((payload) => {
      const n = payload.notification || {};
      self.registration.showNotification(n.title || "N.B hodimlar", {
        body: n.body || "",
        icon: "/icon-192.png",
        badge: "/icon-192.png",
        tag: (payload.data && payload.data.category) || "default",
        data: { path: (payload.data && payload.data.path) || "/" },
      });
    });
  }
} catch (e) {
  // Sozlama yo'q/buzuq — push shunchaki ishlamaydi. Service worker'ning
  // o'zi baribir ro'yxatdan o'tadi, ya'ni sahifa ishlashdan to'xtamaydi.
}

// Bildirishnoma bosilganda kerakli sahifani ochish. Ilova allaqachon ochiq
// bo'lsa YANGI oyna ochilmaydi, mavjudi fokusga olinadi — aks holda har
// bosishda yangi PWA oynasi paydo bo'lardi.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const path = (event.notification.data && event.notification.data.path) || "/";
  const url = new URL(path, self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) {
          if ("navigate" in client) client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
