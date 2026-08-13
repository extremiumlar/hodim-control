/**
 * Rahbar — «Ish kundaligi»: kim nima yozgan, qaysi kunlar bo'sh qolgan.
 *
 * Ikki qatlam:
 *  1. QAMROV jadvali (`/work-log/coverage`) — barcha xodim, oy kesimida
 *     "nechta ish kunidan nechtasida yozgan". Qator bosilsa — o'sha xodim ochiladi.
 *  2. TANLANGAN XODIM oyi (`/work-log?user_id=`) — kunma-kun yozuvlar; ish kuni
 *     bo'lib yozuv yo'q kunlar sariq bilan ajratiladi.
 *
 * MUHIM: bu sahifa hech qanday jarima/pul mantig'iga ULANMAGAN — past qamrov
 * faqat ko'rsatiladi, avtomatik hech narsa qilinmaydi (KUNDALIK_ETIROZ_REJASI.md
 * 1.1-band). Baholash rahbarning ishi.
 *
 * ROP faqat o'z jamoasini ko'radi — backend `list_excused_days` dagi maxfiylik
 * qoidasini takrorlaydi (`work_log.py: VIEW_ROLES` + manager_id filtri).
 */
import { useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { CalendarDays, NotebookPen } from "lucide-react";

import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import MonthNav, { currentMonthKey, monthLabel } from "@/components/attendance/MonthNav";
import { useWorkLogCoverage, useWorkLogMonth } from "@/lib/queries";
import type { WorkLogCoverageRow, WorkLogDay } from "@/lib/api";
import { cn } from "@/lib/utils";

function fmtDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

/** Mahalliy sana ISO ko'rinishida — `toISOString()` UTC'ga o'tkazadi va
 *  Toshkentda (+5) ertalab 05:00 gacha bir kun orqaga surardi. */
function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const WEEKDAYS = ["Dush", "Sesh", "Chor", "Pay", "Juma", "Shan", "Yak"];
function weekdayName(iso: string): string {
  return WEEKDAYS[(new Date(iso + "T00:00:00").getDay() + 6) % 7];
}

function localHm(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "--:--"
    : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Qamrov foizi — 0 ish kunida bo'lish xatosi bo'lmasin. */
function pct(row: WorkLogCoverageRow): number {
  return row.work_days === 0 ? 100 : Math.round((row.logged_days / row.work_days) * 100);
}

function CoverageBar({ row }: { row: WorkLogCoverageRow }) {
  const p = pct(row);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full rounded-full",
            p >= 80 ? "bg-emerald-500" : p >= 50 ? "bg-amber-500" : "bg-rose-500"
          )}
          style={{ width: `${p}%` }}
        />
      </div>
      <span
        className={cn(
          "text-xs font-medium tabular-nums",
          p >= 80 ? "text-emerald-600" : p >= 50 ? "text-amber-600" : "text-rose-600"
        )}
      >
        {p}%
      </span>
    </div>
  );
}

const columns: ColumnDef<WorkLogCoverageRow>[] = [
  {
    accessorKey: "full_name",
    header: "Xodim",
    cell: ({ row }) => <span className="font-medium">{row.original.full_name.trim()}</span>,
  },
  {
    id: "coverage",
    header: "Qamrov",
    cell: ({ row }) => <CoverageBar row={row.original} />,
    sortingFn: (a, b) => pct(a.original) - pct(b.original),
  },
  {
    id: "days",
    header: "Yozilgan kunlar",
    cell: ({ row }) => (
      <span className="tabular-nums text-slate-600">
        {row.original.logged_days} / {row.original.work_days}
      </span>
    ),
  },
  {
    accessorKey: "entries_count",
    header: "Yozuvlar",
    cell: ({ row }) => <span className="tabular-nums text-slate-600">{row.original.entries_count}</span>,
  },
];

/** Tanlangan xodimning oylik kundaligi — kunma-kun. */
function EmployeeMonth({ userId, month }: { userId: number; month: string }) {
  const { data, isLoading, isPlaceholderData } = useWorkLogMonth(userId, month);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
    );
  }
  if (!data) return null;

  // Faqat O'TGAN kunlar (bugungacha), yangisi tepada. Kelajak ish kunlari
  // "yozuv yo'q" bo'lib ko'rinsa, xodim o'nlab kun tashlab ketgandek taassurot
  // qoldirardi — qamrov hisobi ham ularni sanamaydi (work_log.py).
  // Bo'sh dam kunlari ham tashlanadi: hech qanday ma'lumot bermaydi.
  const today = isoToday();
  const days: WorkLogDay[] = [...data.days]
    .filter((d) => d.date <= today && (d.entries.length > 0 || d.is_working))
    .reverse();

  return (
    <div className={cn("space-y-3", isPlaceholderData && "opacity-60")}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">
          {data.user_full_name.trim()} — {monthLabel(data.month)}
        </h3>
        <span className="text-xs text-slate-500">
          {data.logged_days}/{data.work_days} kun · {data.entries_count} yozuv
        </span>
      </div>

      {!days.length ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          Bu oyda yozuv yo'q.
        </p>
      ) : (
        <div className="space-y-2">
          {days.map((d) => {
            const empty = d.entries.length === 0;
            return (
              <div
                key={d.date}
                className={cn(
                  "overflow-hidden rounded-xl border bg-white",
                  empty ? "border-amber-200" : "border-slate-200"
                )}
              >
                <div className="flex items-baseline justify-between gap-2 border-b border-slate-100 px-4 py-2">
                  <span className="text-sm font-semibold tabular-nums">
                    {fmtDayMonth(d.date)}
                    <span className="ml-1.5 text-xs font-normal text-slate-400">
                      {weekdayName(d.date)}
                    </span>
                  </span>
                  {empty ? (
                    <span className="text-xs text-amber-600">yozuv yo'q</span>
                  ) : (
                    <span className="text-xs text-slate-400">{d.entries.length} ta</span>
                  )}
                </div>
                {!empty && (
                  <div className="divide-y divide-slate-100">
                    {d.entries.map((e) => (
                      <div key={e.id} className="flex items-start justify-between gap-3 px-4 py-2.5">
                        <p className="min-w-0 whitespace-pre-line break-words text-sm text-slate-700">
                          {e.text}
                        </p>
                        <span className="shrink-0 text-xs tabular-nums text-slate-400">
                          {localHm(e.created_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function WorkLog() {
  const [month, setMonth] = useState(currentMonthKey());
  const [selected, setSelected] = useState<number | null>(null);
  const coverage = useWorkLogCoverage(month);

  const selectedRow = coverage.data?.rows.find((r) => r.user_id === selected);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ish kundaligi"
        description="Xodimlar kun davomida bajargan ishlarini yozib boradi. Bu yerda faqat ko'rinadi — hech qanday jarima hisoblanmaydi."
      >
        <MonthNav month={month} maxMonth={currentMonthKey()} onChange={setMonth} />
      </PageHeader>

      <DataTable
        columns={columns}
        data={coverage.data?.rows ?? []}
        isLoading={coverage.isLoading}
        error={coverage.error ? coverage.error.message : null}
        onRetry={() => coverage.refetch()}
        searchPlaceholder="Xodim ismi bo'yicha qidirish..."
        empty={{ icon: NotebookPen, text: "Xodim topilmadi." }}
        onRowClick={(row) => setSelected(row.user_id === selected ? null : row.user_id)}
      />

      {selected == null ? (
        <p className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
          <CalendarDays className="h-4 w-4" />
          Kundalikni ko'rish uchun jadvaldan xodimni tanlang.
        </p>
      ) : (
        <EmployeeMonth key={`${selected}-${month}`} userId={selected} month={month} />
      )}

      {selectedRow && selectedRow.work_days > 0 && selectedRow.logged_days === 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          Bu xodim shu oyda umuman yozuv qoldirmagan. Kechki eslatma botga/ilovaga avtomatik
          boradi — kerak bo'lsa shaxsan gaplashing.
        </p>
      )}
    </div>
  );
}
