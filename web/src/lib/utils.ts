import { clsx, type ClassValue } from "clsx";
import { format } from "date-fns";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// 4.10-band: bu funksiya ilgari CheckIn.tsx va Attendance.tsx ichida ikki xil
// usulda (Intl vs date-fns) nusxalangan edi — ikkalasi bir xil natija bersa ham,
// kelajakda biri o'zgarib ikkinchisi o'zgarmasligi (drift) xavfi bor edi. Endi
// YAGONA manba.
export function fmtLocalTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const norm = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`;
  return format(new Date(norm), "HH:mm");
}

// 4.4-band: brauzer Geolocation xatolari ("User denied Geolocation" va h.k.)
// ilgari xom inglizcha holida ko'rsatilardi. `GeolocationPositionError.code`:
// 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE, 3=TIMEOUT (brauzerlararo bir xil).
export function translateGeoError(e: unknown): string {
  const err = e as { code?: number; message?: string } | null | undefined;
  switch (err?.code) {
    case 1:
      return "Joylashuvga ruxsat berilmadi. Brauzer sozlamalaridan GPS ruxsatini yoqing.";
    case 2:
      return "Joylashuvni aniqlab bo'lmadi. Telefon/kompyuterda GPS (joylashuv xizmati) yoqilganini tekshiring.";
    case 3:
      return "Joylashuvni aniqlash vaqti tugadi. Ochiq joyga chiqib qayta urinib ko'ring.";
    default:
      return "GPS xatosi: " + (err?.message || String(e));
  }
}
