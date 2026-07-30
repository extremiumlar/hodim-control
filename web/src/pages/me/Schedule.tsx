/**
 * Xodim kabineti — «Ish jadvali».
 *
 * Botdagi «🗓 Ish jadvali» bilan AYNAN bir xil ma'lumot: bot
 * `/work-schedule/{tg}/me/week` ni, bu sahifa `/work-schedule/me/week` ni
 * chaqiradi, ikkalasi ham `_effective_week(db, user, start)` yordamchisiga
 * boradi. Ko'rsatish qoidalari ham botdagi `_fmt_day` bilan bir xil:
 *   unset            -> "belgilanmagan"
 *   is_working=false -> "🌙 dam olish (izoh)"
 *   aks holda        -> "09:00–18:00 (izoh)"
 * Farq bo'lsa — demak mantiq ikki joyda takrorlangan, tuzatish kerak.
 */
import { useState } from "react";
import { ChevronLeft, ChevronRight, Moon } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyWorkWeek } from "@/lib/queries";
import type { EffectiveDay } from "@/lib/api";
import { cn } from "@/lib/utils";

// bot/handlers/work_schedule.py: WEEKDAYS bilan bir xil
const WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];

function isoDate(d: Date): string {
  // Mahalliy sanani ISO qilamiz. `toISOString()` UTC'ga o'tkazadi va
  // Toshkentda (+5) ertalab soat 05:00 dan oldin BIR KUN ORQAGA surardi.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

/** Botdagi `_fmt_day` bilan bir xil qoida. */
function dayLabel(day: EffectiveDay): { text: string; muted: boolean; rest: boolean } {
  if (day.source === "unset") return { text: "belgilanmagan", muted: true, rest: false };
  if (!day.is_working) return { text: "Dam olish", muted: false, rest: true };
  return { text: `${day.start_time}–${day.end_time}`, muted: false, rest: false };
}

export default function Schedule() {
  // `start` — hafta ichidagi istalgan sana; backend dushanbaga tekislaydi.
  const [start, setStart] = useState<string | undefined>(undefined);
  // isPlaceholderData — hafta almashtirilgan, lekin yangi ma'lumot hali
  // kelmagan: eski hafta ko'rinib turadi (keepPreviousData), shuning uchun
  // xodimga "yangilanmoqda" degan engil belgi kerak.
  const { data, isLoading, isError, isPlaceholderData } = useMyWorkWeek(start);

  const shiftWeek = (deltaDays: number) => {
    const base = data ? new Date(data.days[0].date + "T00:00:00") : new Date();
    base.setDate(base.getDate() + deltaDays);
    setStart(isoDate(base));
  };

  const today = isoDate(new Date());

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-9 w-full rounded-lg" />
        {Array.from({ length: 7 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Jadvalni yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  const first = data.days[0].date;
  const last = data.days[data.days.length - 1].date;

  return (
    <div className="space-y-3">
      {/* Hafta almashtirish — tugmalar barmoq uchun 44px'dan katta */}
      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-1 py-1">
        <button
          onClick={() => shiftWeek(-7)}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-slate-500 active:bg-slate-100"
          aria-label="Oldingi hafta"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold tabular-nums">
          {fmtDayMonth(first)} – {fmtDayMonth(last)}
        </span>
        <button
          onClick={() => shiftWeek(7)}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-slate-500 active:bg-slate-100"
          aria-label="Keyingi hafta"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Jadval EMAS, ro'yxat: 360px da 7 qator gorizontal scrollsiz sig'adi */}
      <div
        className={cn(
          "overflow-hidden rounded-xl border border-slate-200 bg-white transition-opacity",
          isPlaceholderData && "opacity-50"
        )}
      >
        {data.days.map((day, i) => {
          const label = dayLabel(day);
          const isToday = day.date === today;
          return (
            <div
              key={day.date}
              className={cn(
                "flex min-h-[56px] items-center gap-3 px-4 py-3",
                i > 0 && "border-t border-slate-100",
                isToday && "bg-blue-50"
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={cn("truncate text-sm font-medium", isToday && "text-blue-700")}>
                    {WEEKDAYS[day.weekday]}
                  </span>
                  {isToday && (
                    <span className="shrink-0 rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                      bugun
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 tabular-nums">{fmtDayMonth(day.date)}</div>
              </div>

              <div className="shrink-0 text-right">
                <div
                  className={cn(
                    "flex items-center justify-end gap-1.5 text-sm font-semibold tabular-nums",
                    label.muted && "font-normal text-slate-400",
                    label.rest && "text-slate-500"
                  )}
                >
                  {label.rest && <Moon className="h-4 w-4" />}
                  {label.text}
                </div>
                {day.note && <div className="text-xs text-slate-400">{day.note}</div>}
                {/* Alohida o'zgartirilgan kun — xodim "nega bugun boshqacha?"
                    degan savolga javob topsin */}
                {day.source === "override" && !day.note && (
                  <div className="text-xs text-amber-600">o'zgartirilgan</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="px-1 text-xs text-slate-400">
        Jadvalni rahbaringiz belgilaydi. «belgilanmagan» kunlar uchun standart
        ish vaqti qo'llanadi.
      </p>
    </div>
  );
}
