/**
 * Ish jadvali — «Umumiy» ko'rinish (UX-E, J1 muammosi yechimi).
 *
 * Ilgari rahbar 10 xodimning jadvalini tekshirish uchun dropdown'dan 10 marta
 * tanlab chiqishi kerak edi. Endi hamma bir jadvalda: qator — xodim, ustun —
 * hafta kuni. «standart» belgisi (J4) — jadval umuman sozlanmagan xodimni
 * OSHKOR qiladi (unga default 09:00–18:00 qo'llanadi, jarima taxminiy jadval
 * ustiga hisoblanayotgan bo'ladi).
 *
 * Qator bosilsa — «Bitta xodim» tabiga o'sha xodim tanlangan holda o'tiladi.
 */
import { useState } from "react";
import { ChevronLeft, ChevronRight, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAllWeekSchedules } from "@/lib/queries";
import { cn } from "@/lib/utils";

const WD_LETTERS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

/** "09:00" -> "9:00" — katak torroq bo'lsin (7 ustun yonma-yon). */
function shortTime(t: string | null): string {
  if (!t) return "";
  return t.startsWith("0") ? t.slice(1) : t;
}

export default function ScheduleOverviewTab({
  onPick,
}: {
  onPick: (userId: number) => void;
}) {
  const [start, setStart] = useState<string | undefined>(undefined);
  const query = useAllWeekSchedules(start);
  const rows = query.data ?? [];

  const shiftWeek = (deltaDays: number) => {
    const base = rows.length ? new Date(rows[0].days[0].date + "T00:00:00") : new Date();
    base.setDate(base.getDate() + deltaDays);
    setStart(isoDate(base));
  };

  const today = isoDate(new Date());

  if (query.isLoading) {
    return <Skeleton className="h-72 w-full rounded-xl" />;
  }
  if (query.error) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        {query.error.message}
        <Button variant="outline" size="sm" onClick={() => query.refetch()}>
          Qayta urinish
        </Button>
      </div>
    );
  }

  const days = rows[0]?.days ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => shiftWeek(-7)}
            aria-label="Oldingi hafta"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[130px] text-center text-sm font-semibold tabular-nums">
            {days.length ? `${fmtDayMonth(days[0].date)} – ${fmtDayMonth(days[6].date)}` : "—"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => shiftWeek(7)}
            aria-label="Keyingi hafta"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <span className="text-xs text-slate-400">
          Qator bosilsa — o'sha xodim tahrirlash rejimida ochiladi. Sariq katak — alohida
          o'zgartirilgan kun.
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400">
          Ko'rsatadigan xodim yo'q.
        </div>
      ) : (
        <div
          className={cn(
            "overflow-x-auto rounded-xl border border-slate-200 bg-white transition-opacity",
            query.isPlaceholderData && "opacity-60"
          )}
        >
          <table className="w-full border-separate border-spacing-0 text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 z-[2] min-w-[130px] border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-600">
                  Xodim
                </th>
                {days.map((d, i) => (
                  <th
                    key={d.date}
                    className={cn(
                      "min-w-[86px] border-b border-slate-200 px-1 py-1.5 text-center font-semibold",
                      i >= 5 ? "text-rose-400" : "text-slate-500",
                      d.date === today && "bg-blue-50"
                    )}
                  >
                    {WD_LETTERS[i]}
                    <span className="block text-[10px] font-medium text-slate-400 tabular-nums">
                      {fmtDayMonth(d.date)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((emp) => {
                const allUnset = emp.days.every((d) => d.source === "unset");
                return (
                  <tr
                    key={emp.user_id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => onPick(emp.user_id)}
                    title="Tahrirlash uchun bosing"
                  >
                    <td className="sticky left-0 z-[1] border-b border-r border-slate-100 bg-white px-3 py-2 text-[13px] font-medium">
                      {emp.user_full_name}
                    </td>
                    {allUnset ? (
                      <td colSpan={7} className="border-b border-slate-100 px-2 py-2 text-center">
                        <span className="rounded-md bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700">
                          jadval belgilanmagan — standart Du–Ju 09:00–18:00 qo'llanmoqda
                        </span>
                      </td>
                    ) : (
                      emp.days.map((d) => (
                        <td
                          key={d.date}
                          className={cn(
                            "border-b border-slate-100 px-1 py-2 text-center tabular-nums",
                            d.date === today && "bg-blue-50"
                          )}
                        >
                          {d.is_working ? (
                            <span
                              className={cn(
                                "inline-block rounded px-1.5 py-0.5",
                                d.source === "override" &&
                                  "bg-amber-50 font-semibold text-amber-800",
                                d.source === "unset" && "text-slate-400"
                              )}
                              title={
                                d.source === "override"
                                  ? `Alohida o'zgartirilgan${d.note ? `: ${d.note}` : ""}`
                                  : d.source === "unset"
                                    ? "Jadval belgilanmagan — standart vaqt"
                                    : undefined
                              }
                            >
                              {shortTime(d.start_time)}–{shortTime(d.end_time)}
                            </span>
                          ) : (
                            <Moon
                              className={cn(
                                "mx-auto h-3.5 w-3.5 text-slate-300",
                                d.source === "override" && "text-amber-500"
                              )}
                            />
                          )}
                        </td>
                      ))
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
