/**
 * «Hisobot» tabi — xodimlar xulosasi + kechikish tafsiloti (UX-B/A4).
 *
 * M4 muammosining yechimi: ilgari bitta sahifada UCH xil davr bor edi
 * (yozuvlar — o'z oralig'i, xulosa — qotirilgan 30 kun, kechikish — o'z
 * 7/30/90 tugmalari). Endi BITTA davr tanlagichi ikkala bo'limga ham
 * qo'llanadi — raqamlar bir-biriga mos keladi.
 */
import { useState } from "react";
import { endOfMonth, format, startOfMonth, subMonths } from "date-fns";
import { Clock, Hourglass } from "lucide-react";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import StatCard from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type EmployeeAttendanceSummary, type LateStatRow } from "@/lib/api";
import {
  useAttendanceEmployeeSummary,
  useAttendanceLateStats,
  type AttendancePeriod,
} from "@/lib/queries";

type PeriodKey = "this_month" | "prev_month" | "7" | "30" | "90";

const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
  { key: "this_month", label: "Joriy oy" },
  { key: "prev_month", label: "O'tgan oy" },
  { key: "7", label: "7 kun" },
  { key: "30", label: "30 kun" },
  { key: "90", label: "90 kun" },
];

function periodToParams(key: PeriodKey): AttendancePeriod {
  const iso = (d: Date) => format(d, "yyyy-MM-dd");
  if (key === "this_month") {
    return { date_from: iso(startOfMonth(new Date())), date_to: iso(new Date()) };
  }
  if (key === "prev_month") {
    const prev = subMonths(new Date(), 1);
    return { date_from: iso(startOfMonth(prev)), date_to: iso(endOfMonth(prev)) };
  }
  return { days: Number(key) };
}

const summaryColumns: ColumnDef<EmployeeAttendanceSummary>[] = [
  { accessorKey: "full_name", header: "Xodim", cell: ({ row }) => <b>{row.original.full_name}</b> },
  { accessorKey: "present_days", header: "Kelgan kun" },
  {
    accessorKey: "late_count",
    header: "Kechikish (marta)",
    cell: ({ row }) => (
      <span className={row.original.late_count > 0 ? "text-rose-600" : ""}>
        {row.original.late_count}
      </span>
    ),
  },
  {
    accessorKey: "late_minutes",
    header: "Kechikish (daq)",
    cell: ({ row }) => (
      <span className={row.original.late_minutes > 0 ? "text-rose-600" : ""}>
        {row.original.late_minutes}
      </span>
    ),
  },
  { accessorKey: "early_minutes", header: "Erta ketish (daq)" },
  {
    accessorKey: "worked_minutes",
    header: "Ishlangan (soat)",
    cell: ({ row }) => Math.round((row.original.worked_minutes / 60) * 10) / 10,
  },
];

export default function ReportTab({ active }: { active: boolean }) {
  const [periodKey, setPeriodKey] = useState<PeriodKey>("this_month");
  const period = periodToParams(periodKey);

  const summaryQuery = useAttendanceEmployeeSummary(period, active);
  const lateQuery = useAttendanceLateStats(period, active);
  const lateRows: LateStatRow[] = lateQuery.data ?? [];

  const totalLateMinutes = lateRows.reduce((s, r) => s + r.total_late_minutes, 0);
  const totalWorkedHours = (summaryQuery.data ?? []).reduce(
    (s, r) => s + r.worked_minutes / 60,
    0
  );

  return (
    <div className="space-y-4">
      {/* YAGONA davr tanlagichi — quyidagi HAMMA bo'limga qo'llanadi */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
          {PERIOD_OPTIONS.map((o) => (
            <Button
              key={o.key}
              variant={periodKey === o.key ? "default" : "ghost"}
              size="sm"
              className="h-8"
              onClick={() => setPeriodKey(o.key)}
            >
              {o.label}
            </Button>
          ))}
        </div>
        <span className="text-xs text-slate-400">
          Davr ikkala jadvalga ham qo'llanadi — raqamlar bir-biriga mos.
        </span>
      </div>

      {/* UX2-B4: yuklanish paytida "0 daq" YOLG'ON raqami emas — skelet.
          Rahbar bir soniya bo'lsa ham "hech kim kechikmabdi" deb ko'rmasin. */}
      {summaryQuery.isLoading || lateQuery.isLoading ? (
        <div className="grid grid-cols-2 gap-3 md:max-w-md">
          <Skeleton className="h-[86px] rounded-xl" />
          <Skeleton className="h-[86px] rounded-xl" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:max-w-md">
          <StatCard
            label="Jami kechikish"
            value={`${totalLateMinutes} daq`}
            icon={Hourglass}
            warn={totalLateMinutes > 0}
          />
          <StatCard label="Jami ishlangan" value={`${Math.round(totalWorkedHours)} soat`} icon={Clock} />
        </div>
      )}

      {/* Xodimlar xulosasi */}
      <div>
        <h3 className="mb-2 font-semibold">Xodimlar bo'yicha</h3>
        <DataTable
          columns={summaryColumns}
          data={summaryQuery.data}
          isLoading={summaryQuery.isLoading}
          error={summaryQuery.error ? summaryQuery.error.message : null}
          onRetry={() => summaryQuery.refetch()}
          empty={{ text: "Bu davrda davomat yozuvlari yo'q" }}
        />
      </div>

      {/* Kechikish tafsiloti — kunma-kun */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Hourglass className="h-4 w-4 text-rose-500" />
            Kechikish tafsiloti (kunma-kun)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {lateQuery.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : lateQuery.error ? (
            <div className="text-sm text-rose-600">{lateQuery.error.message}</div>
          ) : lateRows.length === 0 ? (
            <div className="text-sm text-slate-400">Tanlangan davrda hech kim kechikmagan 🎉</div>
          ) : (
            <ul className="space-y-4">
              {lateRows.map((r) => (
                <li key={r.user_id} className="border-b border-slate-100 pb-3 last:border-0 last:pb-0">
                  <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium">{r.full_name}</span>
                    <span className="text-sm font-semibold text-rose-600">
                      jami {r.total_late_minutes} daq
                    </span>
                    <span className="text-xs text-slate-500">
                      {r.late_days} kun · o'rtacha {r.avg_late_minutes} daq · eng ko'p{" "}
                      {r.max_late_minutes} daq
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {r.days.map((d) => (
                      <span
                        key={d.date}
                        className="rounded-md bg-rose-50 px-2 py-0.5 text-xs text-rose-700"
                        title={`${format(new Date(d.date), "dd.MM.yyyy")} — ${d.late_minutes} daqiqa kechikkan`}
                      >
                        {format(new Date(d.date), "dd.MM")} +{d.late_minutes}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
