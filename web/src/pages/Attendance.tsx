import { useEffect, useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import {
  AlertTriangle,
  CalendarCheck,
  CheckCircle2,
  Clock,
  DoorOpen,
  Hourglass,
  LogIn,
  Pencil,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Attendance as AttendanceRow,
  type AttendanceReadiness,
  type EmployeeAttendanceSummary,
  type LateStatRow,
  type ReadinessIssue,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useAttendanceDashboard,
  useAttendanceEmployeeSummary,
  useAttendanceLateStats,
  useAttendanceList,
  useAttendanceReadiness,
  useDeleteAttendance,
  useManualAttendance,
} from "@/lib/queries";
import { fmtLocalTime as fmtTime } from "@/lib/utils";

// <input type="time"> uchun — bo'sh qiymat "" bo'lishi kerak ("—" emas).
function toHm(iso: string | null): string {
  return iso ? fmtTime(iso) : "";
}

// Davomat yozuvini qo'lda tuzatish — HR/Boshliq (backend ATTENDANCE_EDIT_ROLES).
// Vaqtlar mahalliy devor-soati bo'yicha yuboriladi; kechikish/ishlangan vaqtni
// server ish jadvalidan qayta hisoblaydi, shuning uchun bu yerda ular yo'q.
function EditAttendanceDialog({
  row,
  onClose,
}: {
  row: AttendanceRow | null;
  onClose: () => void;
}) {
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const mutation = useManualAttendance();

  // Yangi qator tanlanganda maydonlarni o'sha yozuv qiymatlari bilan to'ldiramiz.
  useEffect(() => {
    setCheckIn(toHm(row?.check_in_time ?? null));
    setCheckOut(toHm(row?.check_out_time ?? null));
    setNote(row?.note ?? "");
    setReason("");
  }, [row]);

  const reasonTooShort = reason.trim().length < 5;
  const invalidOrder = !!checkIn && !!checkOut && checkOut <= checkIn;
  const outWithoutIn = !!checkOut && !checkIn;

  return (
    <Dialog open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {row?.user_full_name} — {row ? format(new Date(row.date), "dd.MM.yyyy") : ""}
          </DialogTitle>
          <DialogDescription>
            Face ID yoki GPS ishlamay qolgan kunni tuzatish. Kechikish va ishlangan vaqt
            ish jadvali bo'yicha qayta hisoblanadi. O'zgarish audit jurnaliga tushadi.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="att-in">Keldim</Label>
              <Input
                id="att-in"
                type="time"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="att-out">Ketdim</Label>
              <Input
                id="att-out"
                type="time"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
              />
            </div>
          </div>
          <p className="-mt-2 text-xs text-slate-500">
            Bo'sh qoldirilsa — o'sha belgi tozalanadi (masalan «Keldim» bo'sh bo'lsa,
            kun «kelmagan» bo'lib qoladi).
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="att-note">Izoh (ixtiyoriy)</Label>
            <Input
              id="att-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Masalan: telefon kamerasi ishlamadi"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="att-reason">
              Sabab <span className="text-rose-600">*</span>
            </Label>
            <Input
              id="att-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nima uchun tuzatilyapti (kamida 5 belgi)"
            />
          </div>

          {invalidOrder && (
            <p className="text-sm text-rose-600">«Ketdim» «Keldim» dan keyin bo'lishi kerak.</p>
          )}
          {outWithoutIn && (
            <p className="text-sm text-rose-600">«Ketdim» ni «Keldim» siz belgilab bo'lmaydi.</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Bekor qilish
          </Button>
          <Button
            disabled={
              !row || reasonTooShort || invalidOrder || outWithoutIn || mutation.isPending
            }
            onClick={() => {
              if (!row) return;
              mutation.mutate(
                {
                  user_id: row.user_id,
                  date: row.date,
                  check_in: checkIn || null,
                  check_out: checkOut || null,
                  note: note.trim() || null,
                  reason: reason.trim(),
                },
                {
                  onSuccess: (updated) => {
                    toast.success(
                      updated.late_minutes > 0
                        ? `Saqlandi — kechikish ${updated.late_minutes} daqiqa.`
                        : "Saqlandi — kechikish yo'q."
                    );
                    onClose();
                  },
                }
              );
            }}
          >
            {mutation.isPending ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Ma'lumot tayyorligi — oylik/jarima hisobidan oldin ko'riladigan "bo'sh joylar".
function ReadinessSection({ dateFrom, dateTo }: { dateFrom: string; dateTo: string }) {
  const query = useAttendanceReadiness({ date_from: dateFrom, date_to: dateTo });
  const data: AttendanceReadiness | undefined = query.data;

  const groups: { key: keyof AttendanceReadiness; label: string; hint: string }[] = [
    { key: "no_schedule", label: "Ish jadvali yo'q", hint: "kechikish taxminiy hisoblanadi" },
    { key: "open_checkouts", label: "«Ketdim» yopilmagan", hint: "ishlangan vaqt 0 bo'lib qolgan" },
    { key: "auto_closed", label: "Avtomatik yopilgan", hint: "ishlangan vaqt taxminiy" },
    { key: "pending_excused", label: "Sababli kun hal qilinmagan", hint: "jarimani bekor qilishi mumkin" },
    { key: "no_face", label: "Yuz ro'yxatdan o'tmagan", hint: "umuman check-in qila olmaydi" },
  ];

  if (query.isLoading) return <Skeleton className="h-24 w-full rounded-xl" />;
  if (query.error || !data) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          {data.ok ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          )}
          Ma'lumot tayyorligi ({format(new Date(data.date_from), "dd.MM")}—
          {format(new Date(data.date_to), "dd.MM")})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.ok ? (
          <p className="text-sm text-slate-500">
            Bo'sh joy yo'q — davomat ma'lumoti oylik hisob uchun tayyor.
          </p>
        ) : (
          <ul className="space-y-3">
            {groups.map(({ key, label, hint }) => {
              const items = data[key] as ReadinessIssue[];
              if (!items.length) return null;
              return (
                <li key={key}>
                  <div className="mb-1 text-sm font-medium">
                    {label}{" "}
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                      {items.length}
                    </span>
                    <span className="ml-2 text-xs font-normal text-slate-500">— {hint}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {items.slice(0, 12).map((it, i) => (
                      <span
                        key={`${it.user_id}-${it.date ?? i}`}
                        className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                        title={it.detail ?? undefined}
                      >
                        {it.full_name}
                        {it.date && ` · ${format(new Date(it.date), "dd.MM")}`}
                      </span>
                    ))}
                    {items.length > 12 && (
                      <span className="px-1 text-xs text-slate-500">
                        va yana {items.length - 12} ta
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
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

// Har bir xodimning kechikish statistikasi — kunma-kun (faqat kechikkan kunlar).
function LateStatsSection() {
  const [days, setDays] = useState(30);
  const query = useAttendanceLateStats(days);
  const rows: LateStatRow[] = query.data ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Hourglass className="h-4 w-4 text-rose-500" />
            Kechikish statistikasi (kunma-kun)
          </CardTitle>
          <div className="flex gap-1">
            {[7, 30, 90].map((d) => (
              <Button
                key={d}
                variant={days === d ? "default" : "outline"}
                size="sm"
                onClick={() => setDays(d)}
              >
                {d} kun
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : query.error ? (
          <div className="text-sm text-rose-600">{query.error.message}</div>
        ) : rows.length === 0 ? (
          <div className="text-sm text-slate-400">
            Tanlangan davrda hech kim kechikmagan 🎉
          </div>
        ) : (
          <ul className="space-y-4">
            {rows.map((r) => (
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
  );
}

export default function Attendance() {
  const { user } = useAuth();
  const isDasturchi = user?.role === "dasturchi";
  // Qo'lda tuzatish — HR/Boshliq/Dasturchi. ROP'da yo'q: u kechikishni ko'radi,
  // lekin uni tuzata olmaydi (backend ham xuddi shu ro'yxatni tekshiradi).
  const canEdit = !!user && ["hr", "boss", "dasturchi"].includes(user.role);
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), "yyyy-MM-dd"));
  const [dateTo, setDateTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [deleting, setDeleting] = useState<AttendanceRow | null>(null);
  const [editing, setEditing] = useState<AttendanceRow | null>(null);

  const dashQuery = useAttendanceDashboard();
  const listQuery = useAttendanceList({ date_from: dateFrom, date_to: dateTo });
  const summaryQuery = useAttendanceEmployeeSummary(30);
  const deleteAttendance = useDeleteAttendance();

  const dash = dashQuery.data;
  const s = dash?.summary;

  // Amallar ustuni: qalam — HR/Boshliq qo'lda tuzatishi; savat — faqat Dasturchi
  // (check-in oqimini qaytadan sinash uchun yozuvni butunlay tozalash).
  const rowColumns = useMemo<ColumnDef<AttendanceRow>[]>(() => {
    const cols = baseRowColumns();
    if (!canEdit && !isDasturchi) return cols;
    return [
      ...cols,
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex gap-1">
            {canEdit && (
              <Button
                variant="ghost"
                size="sm"
                title="Qo'lda tuzatish"
                onClick={() => setEditing(row.original)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
            {isDasturchi && (
              <Button
                variant="ghost"
                size="sm"
                title="O'chirish"
                className="text-rose-600 hover:text-rose-700"
                onClick={() => setDeleting(row.original)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        ),
      },
    ];
  }, [canEdit, isDasturchi]);

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
      ) : dashQuery.error ? (
        // 4.8-band: ilgari xato bo'lsa kartalar shunchaki ko'rinmay qolardi —
        // rahbar buni "bugun hech narsa bo'lmagan" deb tushunishi mumkin edi.
        <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {dashQuery.error.message}
          <Button variant="outline" size="sm" onClick={() => dashQuery.refetch()}>
            Qayta urinish
          </Button>
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
                {dash?.in_office.map((p) => (
                  // 4.11-band: `key={i}` (indeks) o'rniga barqaror kalit — ro'yxat
                  // yangilanganda (avtomatik refresh) React qatorlarni indeks
                  // bo'yicha emas, aynan shu odam bo'yicha moslashtiradi.
                  <li key={`${p.user_name}-${p.check_in_time}`} className="flex items-center justify-between text-sm">
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
                {dash?.recent.map((p) => (
                  <li key={`${p.user_name}-${p.check_in_time}`} className="flex items-center justify-between text-sm">
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

      {/* Ma'lumot tayyorligi — oylik/jarima hisobidan oldingi tekshiruv */}
      <ReadinessSection dateFrom={dateFrom} dateTo={dateTo} />

      {/* Kechikish statistikasi — har xodim kunma-kun necha daqiqa kech qolgani */}
      <LateStatsSection />

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

      {canEdit && <EditAttendanceDialog row={editing} onClose={() => setEditing(null)} />}

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
