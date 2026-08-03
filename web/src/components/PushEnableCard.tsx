/**
 * «Bildirishnomalarni yoqish» — brauzer/PWA uchun (iPhone'ning ASOSIY yo'li).
 *
 * NEGA alohida komponent va nega davomat sahifasida: iPhone'da nativ
 * ilovamiz yo'q, xodim saytni bosh ekranga qo'shib ishlatadi. Push aynan
 * «Keldim/Ketdim bosishni unutmang» eslatmasi uchun kerak, shuning uchun
 * taklif o'sha ish qilinadigan joyda turadi.
 *
 * Android APK'da bu kartochka KO'RSATILMAYDI: u yerda nativ ilova o'z FCM
 * tokenini oladi (`mobile/lib/push.ts`) va WebView ichida ikkinchi marta
 * so'rash chalkashlik bo'lardi.
 */
import { useEffect, useState } from "react";
import { Bell, BellOff, Share } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  checkSupport,
  enableWebPush,
  isIos,
  permissionState,
  pushConfigured,
  type PushSupport,
} from "@/lib/push";

/** Mobil ilova WebView'i — u yerda nativ push bor, takliф kerak emas. */
function isEmbeddedApp(): boolean {
  return (
    new URLSearchParams(window.location.search).get("embed") === "1" ||
    sessionStorage.getItem("embed_mode") === "1"
  );
}

const DISMISS_KEY = "push_prompt_dismissed";

export default function PushEnableCard() {
  const [support, setSupport] = useState<PushSupport | null>(null);
  const [permission, setPermission] = useState<NotificationPermission | "unavailable">("default");
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === "1");

  useEffect(() => {
    setSupport(checkSupport());
    setPermission(permissionState());
  }, []);

  // Sozlanmagan (Firebase kaliti yo'q) yoki ilova ichida — umuman ko'rsatmaymiz.
  if (!pushConfigured || isEmbeddedApp() || support === null) return null;
  // Allaqachon yoqilgan — takrorlab bezor qilmaymiz.
  if (permission === "granted") return null;
  if (dismissed) return null;

  // iOS: bosh ekranga qo'shilmagan. Bu XATO EMAS — yo'riqnoma ko'rsatamiz.
  // (`checkSupport` da bu tekshiruv Notification API'dan OLDIN turadi:
  // Safari tabida `Notification` umuman yo'q va xodim "telefonim eski" deb
  // o'ylab qolardi.)
  if (!support.ok && support.reason === "ios-needs-home-screen") {
    return (
      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <Bell className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
            <div className="text-sm text-blue-900">
              <div className="font-medium">Bildirishnomalarni yoqish (iPhone)</div>
              <p className="mt-1 text-blue-800">
                «Keldim/Ketdim» eslatmasi kelishi uchun saytni bosh ekranga qo'shing:
              </p>
              <ol className="mt-2 list-inside list-decimal space-y-1 text-blue-800">
                <li className="flex flex-wrap items-center gap-1">
                  Pastdagi <Share className="inline h-4 w-4" /> «Ulashish» tugmasini bosing
                </li>
                <li>«Bosh ekranga qo'shish» ni tanlang</li>
                <li>Saytni endi shu ikonkadan oching</li>
                <li>Shu joyda chiqadigan «Yoqish» tugmasini bosing</li>
              </ol>
              <p className="mt-2 text-xs text-blue-700">
                Bu Apple qoidasi — oddiy Safari oynasida bildirishnoma ishlamaydi.
                Telegram xabarlari esa baribir kelib turadi.
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 text-blue-700"
            onClick={() => {
              localStorage.setItem(DISMISS_KEY, "1");
              setDismissed(true);
            }}
          >
            Yashirish
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!support.ok) return null; // brauzer qo'llab-quvvatlamaydi — jim o'tamiz

  if (permission === "denied") {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="flex items-start gap-3 p-4 text-sm text-amber-900">
          <BellOff className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div>
            <div className="font-medium">Bildirishnoma bloklangan</div>
            <p className="mt-1 text-amber-800">
              {isIos()
                ? "Sozlamalar → Bildirishnomalar → «N.B hodimlar» dan yoqing."
                : "Brauzer manzil satridagi qulf belgisini bosib, bildirishnomaga ruxsat bering."}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-start gap-3 text-sm">
          <Bell className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <div className="font-medium">Bildirishnomalarni yoqing</div>
            <p className="text-slate-600">
              «Keldim/Ketdim bosishni unutmang» eslatmasi shu telefonga keladi.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              const res = await enableWebPush();
              setBusy(false);
              setPermission(permissionState());
              if (res.ok) {
                toast.success("Bildirishnomalar yoqildi");
              } else if (res.error === "denied") {
                toast.error("Ruxsat berilmadi — brauzer sozlamasidan yoqishingiz mumkin");
              } else {
                toast.error(`Yoqib bo'lmadi: ${res.error ?? "noma'lum xato"}`);
              }
            }}
          >
            {busy ? "Yoqilmoqda..." : "Yoqish"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              localStorage.setItem(DISMISS_KEY, "1");
              setDismissed(true);
            }}
          >
            Keyinroq
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
