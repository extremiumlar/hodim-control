/**
 * Xodim profilidagi «Davomat» kartasi (UX-C qabul mezoni: EmployeeProfile'da
 * davomat BO'LIMI UMUMAN YO'Q edi — rahbar xodim bilan gaplashishdan oldin
 * tarixini ko'ra olmasdi).
 *
 * Ma'lumot: matritsa endpointining `user_id` filtri (alohida endpoint emas) —
 * rahbar matritsasi bilan AYNAN bir xil hisoblash va rang tili.
 */
import { useState } from "react";
import { CalendarCheck } from "lucide-react";
import { CellDetail, MonthCalendar } from "@/components/attendance/MonthCalendar";
import MonthNav, { currentMonthKey } from "@/components/attendance/MonthNav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type MatrixCell } from "@/lib/api";
import { useAttendanceMatrix } from "@/lib/queries";
import { cn } from "@/lib/utils";

export default function EmployeeAttendanceCard({ userId }: { userId: number }) {
  const [month, setMonth] = useState(currentMonthKey());
  const [selected, setSelected] = useState<MatrixCell | null>(null);
  const query = useAttendanceMatrix(month, userId);
  const emp = query.data?.employees[0];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarCheck className="h-4 w-4 text-emerald-600" />
            Davomat
          </CardTitle>
          <MonthNav
            month={month}
            onChange={(m) => {
              setSelected(null);
              setMonth(m);
            }}
          />
        </div>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : query.error ? (
          <div className="text-sm text-rose-600">{query.error.message}</div>
        ) : !emp ? (
          <div className="text-sm text-slate-400">
            Bu xodim davomat kuzatuviga kirmaydi (Boshliq roli yoki faolsiz).
          </div>
        ) : (
          <div className={cn("space-y-3", query.isPlaceholderData && "opacity-60")}>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
              <span>
                Kelgan: <b className="tabular-nums">{emp.totals.present_days} kun</b>
              </span>
              <span className={emp.totals.late_count > 0 ? "text-rose-600" : ""}>
                Kechikish:{" "}
                <b className="tabular-nums">
                  {emp.totals.late_count > 0
                    ? `${emp.totals.late_count} marta · ${emp.totals.late_minutes} daq`
                    : "yo'q"}
                </b>
              </span>
              <span className={emp.totals.absent_days > 0 ? "text-rose-600" : ""}>
                Kelmagan: <b className="tabular-nums">{emp.totals.absent_days} kun</b>
              </span>
              <span>
                Ishlangan: <b className="tabular-nums">{emp.totals.worked_hours} soat</b>
              </span>
            </div>
            <div className="max-w-sm">
              <MonthCalendar
                cells={emp.cells}
                selected={selected?.date ?? null}
                onSelect={(c) => setSelected(selected?.date === c.date ? null : c)}
              />
            </div>
            {selected && (
              <div className="max-w-sm">
                <CellDetail cell={selected} />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
