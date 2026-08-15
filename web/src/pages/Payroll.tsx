import { useEffect, useRef, useState } from "react";
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
import { useQueryClient } from "@tanstack/react-query";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AdvanceTab from "@/components/payroll/AdvanceTab";
import KpiRateTab from "@/components/payroll/KpiRateTab";
import SalaryRateTab from "@/components/payroll/SalaryRateTab";
import { type PayslipRow, type ReadinessIssue } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useApprovePayrollPeriod,
  useHrApprovePayrollPeriod,
  useCalculatePayroll,
  useDownloadPayrollExport,
  qk,
  usePayrollCalcStatus,
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

  // Davr holati ATAYLAB shu yerda (ilgari `PayrollTable` ichida edi): «Oylik
  // stavkalar» tabi ham `preflight` ni so'raydi va oldin u DOIM joriy oyni
  // ishlatardi. HR boshqa oyga o'tgan zahoti ikkita TURLI kalit paydo bo'lib,
  // og'ir `collect_readiness` ikki marta ishlardi (§4.2). Endi ikkalasi bir xil
  // `period` ni ishlatadi — react-query keshni bo'lishadi va so'rov bitta.
  const [period, setPeriod] = useState(currentMonthKey());

  // Stavka va avans tablari FAQAT payroll boshqaruvchilarida. ROP bu
  // sahifaga kira oladi (o'z jamoasining payslip'ini ko'rish uchun), lekin
  // pul kiritish huquqi yo'q — backend ham 403 beradi.
  if (!canManage) return <PayrollTable period={period} setPeriod={setPeriod} />;

  return (
    <Tabs defaultValue="payslips" className="space-y-6">
      <TabsList>
        <TabsTrigger value="payslips">Hisob-kitob</TabsTrigger>
        {/* «Oylik stavkalar» va «KPI stavkalari» ilgari Sozlamalarda edi —
            egasining talabi bo'yicha shu yerga ko'chirildi: stavka sozlama
            emas, u xodimning puli va hisob-kitob bilan yonma-yon turishi
            kerak. Sozlamalarda faqat QOIDALAR qoldi (jarima, qo'shimcha ish
            profillari). */}
        <TabsTrigger value="rates">Oylik stavkalar</TabsTrigger>
        <TabsTrigger value="kpi">KPI stavkalari</TabsTrigger>
        <TabsTrigger value="advances">Avans</TabsTrigger>
      </TabsList>
      <TabsContent value="payslips">
        <PayrollTable period={period} setPeriod={setPeriod} />
      </TabsContent>
      <TabsContent value="rates">
        <SalaryRateTab period={period} />
      </TabsContent>
      <TabsContent value="kpi">
        <KpiRateTab />
      </TabsContent>
      <TabsContent value="advances">
        <AdvanceTab />
      </TabsContent>
    </Tabs>
  );
}

function PayrollTable({
  period,
  setPeriod,
}: {
  period: string;
  setPeriod: (p: string) => void;
}) {
  const { user } = useAuth();
  const canManage = !!user && ["hr", "boss", "dasturchi"].includes(user.role);
  // YAKUNIY tasdiq — faqat Boshliq/Dasturchi (2026-08-08, vazifalar
  // ajratildi). HR bu tugmani KO'RMAYDI: backend ham 403 qaytaradi, lekin
  // ko'rinib turib bosilmaydigan tugma yomon UX bo'lardi.
  const canFinalApprove = !!user && ["boss", "dasturchi"].includes(user.role);

  const [detailUserId, setDetailUserId] = useState<number | null>(null);
  const [confirmApprove, setConfirmApprove] = useState(false);
  const [confirmHrApprove, setConfirmHrApprove] = useState(false);

  const periodsQuery = usePayrollPeriods();
  const payslipsQuery = usePayslips(period);
  const calculate = useCalculatePayroll();
  const queryClient = useQueryClient();

  // ── Fon rejimidagi hisoblash (§4.3) ──
  // Hisob endi so'rov ichida emas, alohida cron jarayonida ketadi — shuning
  // uchun tugma bosilgach natija DARHOL kelmaydi. Sahifa holatni 3 soniyada
  // bir so'rab progressni ko'rsatadi. `watchCalc` faqat shu sahifa ochilgan
  // seansda so'ralgan bo'lsa yoqiladi (boshqa sahifalarda bekorga so'rov
  // yubormasin), lekin sahifa yangilangach ham davom etsin uchun
  // `periodInfo` orqali ham tekshiriladi.
  const [watchCalc, setWatchCalc] = useState(false);
  const calcQuery = usePayrollCalcStatus(period, watchCalc);
  const calcState = calcQuery.data?.state;
  const isCalculating = calcState === "queued" || calcState === "running";
  const prevCalcState = useRef<string | undefined>(undefined);

  useEffect(() => {
    // Davr almashsa kuzatuv qayta boshlansin — boshqa oyning progressini
    // ko'rsatib qolmasin.
    setWatchCalc(false);
    prevCalcState.current = undefined;
  }, [period]);

  useEffect(() => {
    if (prevCalcState.current === calcState) return;
    const oldState = prevCalcState.current;
    prevCalcState.current = calcState;
    // Faqat HAQIQIY o'tishda xabar beramiz: sahifa yangi ochilganda eski
    // `done` holatini ko'rib «tayyor» deb qichqirmasin.
    if (!oldState || oldState === calcState) return;
    if (calcState === "done") {
      toast.success(`${calcQuery.data?.progress ?? 0} xodim hisoblandi.`);
      queryClient.invalidateQueries({ queryKey: ["payroll", "payslips"] });
      queryClient.invalidateQueries({ queryKey: ["payroll", "payslip"] });
      queryClient.invalidateQueries({ queryKey: ["payroll", "periods"] });
    } else if (calcState === "error") {
      toast.error(calcQuery.data?.error ?? "Hisoblashda xato");
    }
  }, [calcState, calcQuery.data, queryClient]);
  const approve = useApprovePayrollPeriod();
  const hrApprove = useHrApprovePayrollPeriod();
  const downloadExport = useDownloadPayrollExport();

  const periodInfo = periodsQuery.data?.find((p) => p.period === period);
  const isLocked = periodInfo?.locked ?? false;
  const isApproved = periodInfo?.status === "approved" || periodInfo?.status === "paid";
  const isHrApproved = periodInfo?.status === "hr_approved";

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
      // MANFIY ham bo'lishi mumkin (2026-08-15): oy bo'yicha kam ishlangan
      // vaqt ortiqchasidan ko'p bo'lsa. Ilgari `> 0` edi va manfiy natija
      // «—» ko'rinardi — ya'ni pul kamaygani jadvalda umuman ko'rinmasdi.
      cell: ({ row }) => {
        const v = row.original.overtime_amount;
        if (!v) return "—";
        return v > 0 ? (
          `+${fmtMoney(v)}`
        ) : (
          <span className="text-rose-600">−{fmtMoney(Math.abs(v))}</span>
        );
      },
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
              disabled={calculate.isPending || isLocked || isCalculating}
              onClick={() =>
                calculate.mutate(
                  { period },
                  {
                    onSuccess: () => {
                      // Natija emas, NAVBAT tasdig'i keldi — endi holatni
                      // kuzatamiz (§4.3).
                      setWatchCalc(true);
                      queryClient.invalidateQueries({ queryKey: qk.payrollCalcStatus(period) });
                      toast.info("Hisoblash navbatga qo'yildi...");
                    },
                  }
                )
              }
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isCalculating ? "animate-spin" : ""}`} />
              {isLocked
                ? "Qulflangan"
                : isCalculating
                  ? `Hisoblanmoqda ${calcQuery.data?.progress ?? 0}/${calcQuery.data?.total ?? 0}`
                  : "Hisoblash"}
            </Button>
            {/* 1-bosqich: HR "tekshirdim, tayyor" — qulflamaydi. */}
            {rows.length > 0 && !isApproved && !isHrApproved && (
              <Button variant="outline" size="sm" onClick={() => setConfirmHrApprove(true)}>
                <CheckCircle2 className="mr-2 h-4 w-4" />
                Tekshirdim — tayyor
              </Button>
            )}
            {/* 2-bosqich: yakuniy tasdiq va QULF — faqat Boshliq/Dasturchi. */}
            {rows.length > 0 && isHrApproved && canFinalApprove && (
              <Button size="sm" onClick={() => setConfirmApprove(true)}>
                <Lock className="mr-2 h-4 w-4" />
                Yakuniy tasdiqlash
              </Button>
            )}
            {isHrApproved && !canFinalApprove && (
              <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-3 py-1.5 text-sm text-amber-800">
                Boshliq tasdig'i kutilmoqda
              </span>
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

      {/* §2.3: HR «KPI oylikka o'tmadi» deb shikoyat qilardi — sabab, bonus
          qatorini faqat oy oxiridagi cron yaratardi. Endi «Hisoblash» o'zi
          bonusni ham yangilaydi; buni AYTIB qo'yish kerak, aks holda HR
          hamon botdagi alohida tugmani qidiradi. */}
      {canManage && !isLocked && (
        <p className="-mt-2 text-xs text-slate-500">
          «Hisoblash» bosilganda <b>KPI bonusi ham shu paytda qayta hisoblanadi</b> — botdan
          alohida hisoblash shart emas.
        </p>
      )}

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
        title={`${period} davrini YAKUNIY tasdiqlaysizmi?`}
        description={
          (periodInfo?.hr_approved_name
            ? `Tekshirgan: ${periodInfo.hr_approved_name}. `
            : "") +
          "Tasdiqlangach davr QULFLANADI — qayta hisoblash uchun avval Dasturchi ochishi kerak bo'ladi. Har bir xodimga shaxsiy xabar boradi."
        }
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

      {/* HR bosqichi — qulflamaydi, shuning uchun ogohlantirish yumshoqroq. */}
      <ConfirmDialog
        open={confirmHrApprove}
        onOpenChange={setConfirmHrApprove}
        title={`${period} — tekshirdingizmi?`}
        description="Bu davr Boshliqqa yakuniy tasdiq uchun yuboriladi va unga xabar boradi. Davr QULFLANMAYDI — kerak bo'lsa hali ham qayta hisoblash mumkin."
        confirmLabel="Ha, tayyor"
        loading={hrApprove.isPending}
        onConfirm={() =>
          hrApprove.mutate(period, {
            onSuccess: () => {
              toast.success("Boshliqqa yuborildi.");
              setConfirmHrApprove(false);
            },
          })
        }
      />
    </div>
  );
}
