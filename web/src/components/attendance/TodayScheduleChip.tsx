/**
 * Bugungi ish jadvali chipi — check-in sahifasining tepasida (UX-D1).
 *
 * X2 muammosining yechimi: «bugun soat nechada kelishim kerak?» degan savol
 * javobi alohida tabda (/me/schedule) yashiringan edi — kechikish xodimga
 * "kutilmagan" bo'lib tuyulardi. Ma'lumot mavjud hafta so'rovidan olinadi
 * (useMyWorkWeek — kesh umumiy), YANGI so'rov yo'q.
 */
import { Clock, Moon } from "lucide-react";
import { useMyWorkWeek } from "@/lib/queries";

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function TodayScheduleChip() {
  const { data } = useMyWorkWeek();
  const today = data?.days.find((d) => d.date === todayIso());
  if (!today) return null;

  if (!today.is_working) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm font-medium text-slate-600">
        <Moon className="h-4 w-4 shrink-0" />
        <span>
          Bugun dam olasiz{today.note ? ` (${today.note})` : ""} — kelsangiz ham kechikish
          yozilmaydi.
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3.5 py-2.5 text-sm font-semibold text-indigo-800">
      <Clock className="h-4 w-4 shrink-0" />
      {/* source="unset" kunlarda API start/end ni null qaytaradi, lekin
          check-in mantiqida standart 09:00–18:00 amal qiladi — "Bugun: –"
          bo'lib qolmasligi uchun o'sha standartni ko'rsatamiz. */}
      <span className="tabular-nums">
        Bugun: {today.start_time ?? "09:00"}–{today.end_time ?? "18:00"}
      </span>
      {today.source === "unset" && (
        <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500">
          standart jadval
        </span>
      )}
      {today.source === "override" && (
        <span
          className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700"
          title={today.note ?? "Bu kun uchun jadval alohida o'zgartirilgan"}
        >
          o'zgartirilgan{today.note ? `: ${today.note}` : ""}
        </span>
      )}
    </div>
  );
}
