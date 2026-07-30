import { useState } from "react";
import { format } from "date-fns";
import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  Download,
  Lock,
  RefreshCw,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import { fmtMoney } from "@/lib/utils";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { MonthPicker, currentMonthKey } from "@/components/PeriodPicker";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { type PayslipRow, type ReadinessIssue } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useApprovePayrollPeriod,
  useCalculatePayroll,
  useDownloadPayrollExport,
  usePayrollPeriods,
  usePayrollPreflight,
  usePayslipDetail,
  usePayslips,
} from "@/lib/queries";

// fmtMoney lib/utils.ts ga ko'chirildi — xodim kabineti (me/Payroll.tsx) ham
// AYNAN shu formatni ishlatishi kerak, aks holda bir xil summa ikki sahifada
// boshqacha ko'rinardi.

// Oylik hisobdan OLDINGI tayyorlik ogohlantirishi — Attendance.tsx'dagi
// ReadinessSection bilan bir xil ruh, lekin payrollga xos guruhlar bilan.
function PreflightSection({ period }: { period: string }) {
  const query = usePayrollPreflight(period);
  const data = query.data;

  if (query.isLoading) return <Skeleton className="h-20 w-full rounded-xl" />;
  if (query.error || !data) return null;

  const groups: { items: ReadinessIssue[]; label: string; hint: string }[] = [
    { items: data.no_salary_rate, label: "Stavka kiritilmagan", hint: "bu xodim hisobga kirmaydi" },
    { items: data.pending_overtime, label: "Qo'shimcha ish tasdiqlanmagan", hint: "hisobga kirmaydi" },
    { items: data.attendance.no_schedule, label: "Ish jadvali yo'q", hint: "kechikish taxminiy" },
    { items: data.attendance.open_checkouts, label: "«Ketdim» yopilmagan", hint: "ishlangan vaqt noaniq" },
    { items: data.attendance.auto_closed, label: "Avtomatik yopilgan kunlar", hint: "ishlangan vaqt taxminiy" },
    { items: data.attendance.pending_excused, label: "Sababli kun hal qilinmagan", hint: "jarimani bekor qilishi mumkin" },
    { items: data.attendance.no_face, label: "Yuz ro'yxatdan o'tmagan", hint: "check-in qila olmaydi" },
  ].filter((g) => g.items.length > 0);

  if (data.ok) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        Ma'lumot to'liq tayyor — hisoblashdan oldin bo'sh joy yo'q.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-800">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        Hisoblashdan oldin e'tibor bering
      </div>
      <ul className="space-y-2">
        {groups.map((g) => (
          <li key={g.label}>
            <div className="mb-1 text-xs font-medium text-amber-800">
              {g.label}{" "}
              <span className="rounded bg-amber-100 px-1.5 py-0.5">{g.items.length}</span>
              <span className="ml-2 font-normal text-amber-700">— {g.hint}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {g.items.slice(0, 10).map((it, i) => (
                <span
                  key={`${it.user_id}-${it.date ?? i}`}
                  className="rounded-md bg-white px-2 py-0.5 text-xs text-amber-900"
                  title={it.detail ?? undefined}
                >
                  {it.full_name}
                  {it.date && ` · ${format(new Date(it.date), "dd.MM")}`}
                </span>
              ))}
              {g.items.length > 10 && (
                <span className="px-1 text-xs text-amber-700">va yana {g.items.length - 10} ta</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PayslipDetailDialog({
  period,
  userId,
  onClose,
}: {
  period: string;
  userId: number | null;
  onClose: () => void;
}) {
  const query = usePayslipDetail(period, userId ?? 0, userId !== null);
  const d = query.data;

  return (
    <Dialog open={userId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{d ? d.full_name : "Yuklanmoqda..."}</DialogTitle>
          <DialogDescription>
            {d && `${d.period} — har bir summaning kelib chiqishi quyida`}
          </DialogDescription>
        </DialogHeader>

        {query.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : !d ? (
          <p className="text-sm text-slate-500">Ma'lumot topilmadi.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg bg-slate-50 p-3">
              <div>
                <div className="text-xs text-slate-500">Sof (net)</div>
                <div className="text-2xl font-semibold">{fmtMoney(d.net)}</div>
              </div>
              <StatusBadge kind="payslip" status={d.status} />
            </div>

            <div className="space-y-1.5">
              <div className="text-xs font-medium text-slate-500">Qatorlar</div>
              {d.items.length === 0 ? (
                <p className="text-sm text-slate-400">Qator yo'q.</p>
              ) : (
                <div className="divide-y rounded-lg border">
                  {d.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                      <div>
                        <div>{item.label}</div>
                        {item.quantity != null && item.rate != null && (
                          <div className="text-xs text-slate-400">
                            {item.quantity} × {fmtMoney(item.rate)}
                          </div>
                        )}
                      </div>
                      <div className={item.amount < 0 ? "font-medium text-rose-600" : "font-medium"}>
                        {item.amount < 0 ? "−" : ""}
                        {fmtMoney(Math.abs(item.amount))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-slate-400">Rejadagi kunlar</div>
                <div>{d.scheduled_days} kun</div>
              </div>
              <div>
                <div className="text-xs text-slate-400">Ishlangan</div>
                <div>{d.worked_days} kun</div>
              </div>
              <div>
                <div className="text-xs text-slate-400">Kechikish</div>
                <div>
                  {d.late_days} kun ({d.fined_late_days} jarimali)
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400">Kelmagan / Sababli</div>
                <div>
                  {d.absent_days} / {d.excused_days} kun
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between border-t pt-3 text-sm">
              <span className="text-slate-500">Jami (gross)</span>
              <span className="font-medium">{fmtMoney(d.gross)}</span>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function Payroll() {
  const { user } = useAuth();
  const canManage = !!user && ["hr", "boss", "dasturchi"].includes(user.role);

  const [period, setPeriod] = useState(currentMonthKey());
  const [detailUserId, setDetailUserId] = useState<number | null>(null);
  const [confirmApprove, setConfirmApprove] = useState(false);

  const periodsQuery = usePayrollPeriods();
  const payslipsQuery = usePayslips(period);
  const calculate = useCalculatePayroll();
  const approve = useApprovePayrollPeriod();
  const downloadExport = useDownloadPayrollExport();

  const periodInfo = periodsQuery.data?.find((p) => p.period === period);
  const isLocked = periodInfo?.locked ?? false;
  const isApproved = periodInfo?.status === "approved" || periodInfo?.status === "paid";

  const rows = payslipsQuery.data ?? [];
  const totals = rows.reduce(
    (acc, r) => ({
      net: acc.net + r.net,
      fine: acc.fine + r.fine_amount + r.absent_deduction,
      overtime: acc.overtime + r.overtime_amount,
    }),
    { net: 0, fine: 0, overtime: 0 }
  );

  const columns: ColumnDef<PayslipRow>[] = [
    { accessorKey: "full_name", header: "Xodim", cell: ({ row }) => <b>{row.original.full_name}</b> },
    {
      accessorKey: "base_amount",
      header: "Asosiy oylik",
      cell: ({ row }) => fmtMoney(row.original.base_amount),
    },
    {
      id: "late",
      header: "Kechikish",
      cell: ({ row }) =>
        row.original.late_days > 0 ? (
          <span>
            {row.original.late_days} kun
            {row.original.fined_late_days > 0 && (
              <span className="text-rose-600"> ({row.original.fined_late_days} jarimali)</span>
            )}
          </span>
        ) : (
          "—"
        ),
    },
    {
      id: "fine",
      header: "Jarima",
      cell: ({ row }) => {
        const total = row.original.fine_amount + row.original.absent_deduction;
        return total > 0 ? <span className="text-rose-600">−{fmtMoney(total)}</span> : "—";
      },
    },
    {
      accessorKey: "overtime_amount",
      header: "Qo'shimcha ish",
      cell: ({ row }) =>
        row.original.overtime_amount > 0 ? `+${fmtMoney(row.original.overtime_amount)}` : "—",
    },
    {
      accessorKey: "bonus_amount",
      header: "Bonus",
      cell: ({ row }) => (row.original.bonus_amount > 0 ? `+${fmtMoney(row.original.bonus_amount)}` : "—"),
    },
    {
      accessorKey: "net",
      header: "Sof (net)",
      cell: ({ row }) => <b>{fmtMoney(row.original.net)}</b>,
    },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="payslip" status={row.original.status} />,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ish haqi"
        description="Oylik ish haqi, kechikish jarimasi va qo'shimcha ish hisob-kitobi."
      >
        <MonthPicker value={period} onChange={setPeriod} />
        {rows.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            disabled={downloadExport.isPending}
            onClick={() =>
              downloadExport.mutate(period, { onSuccess: () => toast.success("Excel fayl yuklab olindi") })
            }
          >
            <Download className="mr-2 h-4 w-4" />
            {downloadExport.isPending ? "Tayyorlanmoqda..." : "Excel"}
          </Button>
        )}
        {canManage && (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={calculate.isPending || isLocked}
              onClick={() =>
                calculate.mutate(
                  { period },
                  { onSuccess: (r) => toast.success(`${r.calculated} xodim hisoblandi.`) }
                )
              }
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {isLocked ? "Qulflangan" : "Hisoblash"}
            </Button>
            {rows.length > 0 && !isApproved && (
              <Button size="sm" onClick={() => setConfirmApprove(true)}>
                <CheckCircle2 className="mr-2 h-4 w-4" />
                Tasdiqlash
              </Button>
            )}
            {isApproved && (
              <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-3 py-1.5 text-sm text-emerald-700">
                <Lock className="h-3.5 w-3.5" />
                Tasdiqlangan
              </span>
            )}
          </>
        )}
      </PageHeader>

      {canManage && !isLocked && <PreflightSection period={period} />}

      {rows.length > 0 && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Xodimlar" value={rows.length} icon={Users} />
          <StatCard label="Jami sof (net)" value={fmtMoney(totals.net)} icon={Banknote} />
          <StatCard label="Jami jarima" value={fmtMoney(totals.fine)} warn={totals.fine > 0} />
          <StatCard label="Jami qo'shimcha ish" value={fmtMoney(totals.overtime)} />
        </div>
      )}

      <DataTable
        columns={columns}
        data={payslipsQuery.data}
        isLoading={payslipsQuery.isLoading}
        error={payslipsQuery.error ? payslipsQuery.error.message : null}
        onRetry={() => payslipsQuery.refetch()}
        onRowClick={(row) => setDetailUserId(row.user_id)}
        searchPlaceholder="Xodim bo'yicha qidirish..."
        empty={{
          text: canManage
            ? "Bu davr uchun hali hisoblanmagan — yuqoridagi «Hisoblash» tugmasini bosing."
            : "Bu davr uchun ma'lumot yo'q.",
        }}
      />

      <PayslipDetailDialog period={period} userId={detailUserId} onClose={() => setDetailUserId(null)} />

      <ConfirmDialog
        open={confirmApprove}
        onOpenChange={setConfirmApprove}
        title={`${period} davrini tasdiqlaysizmi?`}
        description="Tasdiqlangach davr QULFLANADI — qayta hisoblash uchun avval Dasturchi ochishi kerak bo'ladi. Har bir xodimga shaxsiy xabar boradi."
        confirmLabel="Tasdiqlash"
        loading={approve.isPending}
        onConfirm={() =>
          approve.mutate(period, {
            onSuccess: (r) => {
              toast.success(`${r.approved} ta payslip tasdiqlandi.`);
              setConfirmApprove(false);
            },
          })
        }
      />
    </div>
  );
}
