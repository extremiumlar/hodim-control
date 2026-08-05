/**
 * «📅 Oylik davomatim» — xodimning o'z tarixi kalendari (UX-D2).
 *
 * X1 muammosining yechimi: xodim o'z tarixini UMUMAN ko'ra olmasdi — "shu oy
 * nechi marta kechikdim, qaysi kunlar?" javobi faqat rahbarda yoki jarima
 * kelganda ma'lum bo'lardi. Ma'lumot: GET /attendance/me/history (UX-A3),
 * rang tili rahbar matritsasi bilan AYNAN bir xil (bitta MonthCalendar).
 */
import { useState } from "react";
import { CellDetail, MonthCalendar } from "@/components/attendance/MonthCalendar";
import MonthNav, { currentMonthKey } from "@/components/attendance/MonthNav";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type MatrixCell } from "@/lib/api";
import { useMyAttendanceHistory } from "@/lib/queries";
import { cn } from "@/lib/utils";

export default function MyHistoryCard() {
  const [month, setMonth] = useState(currentMonthKey());
  const [selected, setSelected] = useState<MatrixCell | null>(null);
  const query = useMyAttendanceHistory(month);
  const data = query.data;

  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">📅 Oylik davomatim</h3>
          {/* Kelajak oy xodimga kerak emas — tugma o'chiq (D2 qabul mezoni). */}
          <MonthNav
            month={month}
            maxMonth={currentMonthKey()}
            onChange={(m) => {
              setSelected(null);
              setMonth(m);
            }}
          />
        </div>

        {query.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : query.error ? (
          <p className="text-sm text-rose-600">
            Tarixni yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
          </p>
        ) : !data ? null : (
          <div className={cn("space-y-3", query.isPlaceholderData && "opacity-60")}>
            <p className="text-xs text-slate-500">
              <b className="tabular-nums">{data.totals.present_days} kun</b> kelgansiz ·{" "}
              <b
                className={cn(
                  "tabular-nums",
                  data.totals.late_count > 0 ? "text-rose-600" : "text-emerald-600"
                )}
              >
                {data.totals.late_count > 0
                  ? `${data.totals.late_count} kechikish (${data.totals.late_minutes} daq)`
                  : "kechikish yo'q"}
              </b>{" "}
              · <b className="tabular-nums">{data.totals.worked_hours} soat</b> ishlangan
            </p>
            <MonthCalendar
              cells={data.days}
              selected={selected?.date ?? null}
              onSelect={(c) => setSelected(selected?.date === c.date ? null : c)}
            />
            {selected && <CellDetail cell={selected} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
