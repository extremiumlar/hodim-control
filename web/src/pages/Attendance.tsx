import { useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import {
  CalendarCheck,
  Clock,
  DoorOpen,
  Hourglass,
  LogIn,
  RefreshCw,
  Trash2,
  UserX,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { DateRangePicker } from "@/components/PeriodPicker";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Attendance as AttendanceRow,
  type EmployeeAttendanceSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useAttendanceDashboard,
  useAttendanceEmployeeSummary,
  useAttendanceList,
  useDeleteAttendance,
} from "@/lib/queries";

// Backend naive-UTC — "Z" qo'shib mahalliy vaqtga o'giramiz.
function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const norm = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`;
  return format(new Date(norm), "HH:mm");
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

function baseRowColumns(): ColumnDef<AttendanceRow>[] {
  return [
    {
      accessorKey: "date",
      header: "Sana",
      cell: ({ row }) => format(new Date(row.original.date), "dd.MM.yyyy"),
    },
    {
      accessorKey: "user_full_name",
      header: "Xodim",
      cell: ({ row }) => <b>{row.original.user_full_name}</b>,
    },
    { accessorKey: "check_in_time", header: "Keldim", cell: ({ row }) => fmtTime(row.original.check_in_time) },
    { accessorKey: "check_out_time", header: "Ketdim", cell: ({ row }) => fmtTime(row.original.check_out_time) },
    {
      accessorKey: "late_minutes",
      header: "Kechikish",
      cell: ({ row }) =>
        row.original.late_minutes > 0 ? (
          <span className="text-rose-600">{row.original.late_minutes} daq</span>
        ) : (
          "—"
        ),
    },
    {
      accessorKey: "worked_minutes",
      header: "Ishlangan",
      cell: ({ row }) =>
        row.original.worked_minutes > 0
          ? `${Math.round((row.original.worked_minutes / 60) * 10) / 10} soat`
          : "—",
    },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="attendance" status={row.original.status} />,
    },
  ];
}

export default function Attendance() {
  const { user } = useAuth();
  const isDasturchi = user?.role === "dasturchi";
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), "yyyy-MM-dd"));
  const [dateTo, setDateTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [deleting, setDeleting] = useState<AttendanceRow | null>(null);

  const dashQuery = useAttendanceDashboard();
  const listQuery = useAttendanceList({ date_from: dateFrom, date_to: dateTo });
  const summaryQuery = useAttendanceEmployeeSummary(30);
  const deleteAttendance = useDeleteAttendance();

  const dash = dashQuery.data;
  const s = dash?.summary;

  // Dasturchi uchun o'chirish ustuni — check-in/check-out oqimini qaytadan
  // sinash uchun (masalan bugungi yozuvni tozalab, yana "Keldim" bosish).
  // Boshliq/HR/ROP'da bu tugma yo'q; backend ham faqat dasturchini qabul qiladi.
  const rowColumns = useMemo<ColumnDef<AttendanceRow>[]>(() => {
    const cols = baseRowColumns();
    if (!isDasturchi) return cols;
    return [
      ...cols,
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            className="text-rose-600 hover:text-rose-700"
            onClick={() => setDeleting(row.original)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        ),
      },
    ];
  }, [isDasturchi]);

  return (
    <div className="space-y-6">
      <PageHeader title="Davomat (kelib-ketish)">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            dashQuery.refetch();
            listQuery.refetch();
            summaryQuery.refetch();
          }}
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          Yangilash
        </Button>
      </PageHeader>

      {/* Bugungi xulosa kartalari */}
      {dashQuery.isLoading ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-[86px] rounded-xl" />
          ))}
        </div>
      ) : (
        s && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
            <StatCard label="Bugun ishlashi kerak" value={s.working_today} icon={Users} />
            <StatCard label="Keldi" value={s.checked_in_today} icon={LogIn} />
            <StatCard label="Hozir ofisda" value={s.present_now} icon={CalendarCheck} />
            <StatCard label="Kechikdi" value={s.late_today} icon={Hourglass} warn={s.late_today > 0} />
            <StatCard label="Ketdi" value={s.left_today} icon={DoorOpen} />
            <StatCard
              label="Kelmagan"
              value={s.not_checked_in}
              icon={UserX}
              warn={s.not_checked_in > 0}
            />
            <StatCard label="Oy: ishlangan soat" value={s.month_worked_hours} icon={Clock} />
          </div>
        )
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Hozir ofisda */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Hozir ofisda ({dash?.in_office.length ?? 0})</CardTitle>
          </CardHeader>
          <CardContent>
            {dashQuery.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : dash?.in_office.length === 0 ? (
              <div className="text-sm text-slate-400">Hech kim yo'q</div>
            ) : (
              <ul className="space-y-2">
                {dash?.in_office.map((p, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span>{p.user_name}</span>
                    <span className="text-slate-500">
                      {fmtTime(p.check_in_time)}
                      {p.late_minutes > 0 && (
                        <span className="ml-2 text-rose-600">+{p.late_minutes} daq</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* So'nggi harakatlar */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Bugungi harakatlar</CardTitle>
          </CardHeader>
          <CardContent>
            {dashQuery.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : dash?.recent.length === 0 ? (
              <div className="text-sm text-slate-400">Hali yozuv yo'q</div>
            ) : (
              <ul className="space-y-2">
                {dash?.recent.map((p, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span>{p.user_name}</span>
                    <span className="flex items-center gap-2 text-slate-500">
                      {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)}
                      <StatusBadge kind="attendance" status={p.status} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 30 kunlik xodim xulosasi */}
      <div>
        <h3 className="mb-2 font-semibold">Xodimlar bo'yicha (oxirgi 30 kun)</h3>
        <DataTable
          columns={summaryColumns}
          data={summaryQuery.data}
          isLoading={summaryQuery.isLoading}
          error={summaryQuery.error ? summaryQuery.error.message : null}
          onRetry={() => summaryQuery.refetch()}
          empty={{ text: "Hali davomat yozuvlari yo'q" }}
        />
      </div>

      {/* Yozuvlar jadvali (sana oralig'i bilan) */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h3 className="font-semibold">Yozuvlar</h3>
          <DateRangePicker
            from={dateFrom}
            to={dateTo}
            onChange={(f, t) => {
              setDateFrom(f);
              setDateTo(t);
            }}
          />
        </div>
        <DataTable
          columns={rowColumns}
          data={listQuery.data}
          isLoading={listQuery.isLoading}
          error={listQuery.error ? listQuery.error.message : null}
          onRetry={() => listQuery.refetch()}
          searchPlaceholder="Xodim bo'yicha qidirish..."
          empty={{ text: "Tanlangan oraliqda yozuv yo'q" }}
        />
      </div>

      {isDasturchi && (
        <ConfirmDialog
          open={deleting !== null}
          onOpenChange={(open) => !open && setDeleting(null)}
          title={
            deleting
              ? `${deleting.user_full_name} — ${format(new Date(deleting.date), "dd.MM.yyyy")} yozuvini o'chirasizmi?`
              : ""
          }
          description="Bu amalni qaytarib bo'lmaydi. Faqat sinov/tozalash uchun (dasturchi huquqi) — xodim shu kun uchun qaytadan Keldim/Ketdim qila oladi."
          confirmLabel="O'chirish"
          destructive
          loading={deleteAttendance.isPending}
          onConfirm={() => {
            if (!deleting) return;
            deleteAttendance.mutate(deleting.id, {
              onSuccess: () => {
                toast.success("Davomat yozuvi o'chirildi.");
                setDeleting(null);
              },
            });
          }}
        />
      )}
    </div>
  );
}
