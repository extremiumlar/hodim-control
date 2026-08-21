/**
 * Avans — oy o'rtasida qo'lga berilgan pul, oy oxirida oylikdan ayiriladi.
 *
 * NEGA KERAK (2026-08-13, egasining talabi): backendda model bor edi
 * (`PayrollAdjustment`, `kind='minus'`), lekin web panelda HECH QANDAY oyna
 * yo'q edi va ro'yxat qaytaradigan endpoint ham yo'q edi — ya'ni avansni
 * amalda kiritib bo'lmasdi.
 *
 * OQIM (egasining qarori): HR kiritadi -> `pending` (oylikka KIRMAYDI) ->
 * Boshliq tasdiqlaydi -> oylikdan ayiriladi va xodimga xabar boradi.
 * Tasdiqlanmagan avans oylikni O'ZGARTIRMAYDI — bu ataylab: HR bir o'zi
 * pul harakatini yakunlab qo'ymasin (oylik tasdig'i bilan bir xil ruh).
 */
import { useState, type FormEvent } from "react";
import { format } from "date-fns";
import { Banknote, Check, Megaphone, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";

import DataTable from "@/components/DataTable";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import PageHeader from "@/components/PageHeader";
import { MonthPicker, currentMonthKey } from "@/components/PeriodPicker";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, type PayrollAdjustment } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useAdvanceLimit,
  useAdvanceSummary,
  useAnnounceAdvanceDay,
  useBulkDecideAdvances,
  useCreateAdvance,
  useDecideAdvance,
  useDeletePayrollAdjustment,
  useIssueAdvance,
  usePayrollAdjustments,
  useUsers,
} from "@/lib/queries";
import { fmtMoney } from "@/lib/utils";

export default function AdvanceTab() {
  const { user } = useAuth();
  // Tasdiqlash — HR ham qila oladi (2026-08-21, egasining qarori):
  // xodim botdan o'zi so'rov yuboradi, HR uni ko'rib tasdiqlaydi.
  // ⚠️ Vazifalar ajratimi saqlanadi: HR O'ZI KIRITGAN avansni
  // tasdiqlay olmaydi (backend 403 beradi) — quyida tugma ham
  // ko'rsatilmaydi, chunki bosilmaydigan tugma yomon UX.
  const canDecide = !!user && ["hr", "boss", "dasturchi"].includes(user.role);
  const isBoss = !!user && ["boss", "dasturchi"].includes(user.role);
  /** Shu qatorni shu odam tasdiqlay oladimi. */
  const mayDecide = (row: PayrollAdjustment) => isBoss || row.created_by !== user?.id;
  // Avans kunini e'lon qilish (D-01) — HR ham qila oladi: bu pul
  // qarori emas, xabar. Backend ham `_require_manage` bilan yopiq.
  const canManage = !!user && ["hr", "boss", "dasturchi"].includes(user.role);

  const [period, setPeriod] = useState(currentMonthKey());
  const usersQuery = useUsers();
  const listQuery = usePayrollAdjustments({ period, category: "advance" });
  const createAdvance = useCreateAdvance();
  const decide = useDecideAdvance();
  // A-04: «To'lab berildi» — tasdiqdan KEYINGI alohida amal (kassa).
  const issue = useIssueAdvance();
  // A-05: YUMSHOQ o'chirish — qator bazada qoladi, sabab auditga yoziladi.
  const removeAdj = useDeletePayrollAdjustment();
  // D-02/D-03: yig'indi va ketma-ket belgi. FAQAT boshqaruv rollari
  // ko'radi (backend ham `_require_manage` bilan yopiq).
  const summaryQuery = useAdvanceSummary(period);
  const summary = summaryQuery.data ?? null;
  const bulkDecide = useBulkDecideAdvances();
  const announce = useAnnounceAdvanceDay();
  // D-02: tanlab tasdiqlash. «Hammasini belgilash» ataylab yo'q —
  // ko'rilmagan so'rovni tasdiqlab yuborish eng qimmat xato bo'lardi.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // D-01: qo'lda e'lon qilish oynasi.
  const [announceOpen, setAnnounceOpen] = useState(false);
  const [announceDate, setAnnounceDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [announceNote, setAnnounceNote] = useState("");

  const [userId, setUserId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  // Dublikat ogohlantirishi (Avans TZ A-01). Server 409 qaytarsa oyna
  // ochiladi; HR «Baribir kiritish» desa AYNAN o'sha so'rov
  // `confirm_duplicate: true` bilan qayta yuboriladi.
  const [dupWarning, setDupWarning] = useState<string | null>(null);
  // Chegara (A-03) — xodim tanlangan zahoti ko'rinadi, HR ko'r-ko'rona
  // kiritib 400 olmasin.
  const limitQuery = useAdvanceLimit(userId, period);
  const limit = limitQuery.data ?? null;
  // Chegaradan oshiq kiritish — faqat Boshliq/Dasturchi va faqat sabab
  // bilan. HR uchun bu oyna umuman ochilmaydi (backend ham 403 beradi).
  const [overWarning, setOverWarning] = useState<string | null>(null);
  const [overReason, setOverReason] = useState("");
  // O'chirish tasdig'i: qaysi yozuv va nima sabab bilan.
  const [toDelete, setToDelete] = useState<PayrollAdjustment | null>(null);
  const [deleteReason, setDeleteReason] = useState("");

  const rows = listQuery.data ?? [];
  // Ketma-ket belgi (D-03) — xodim bo'yicha tez qidirish uchun.
  const streakByUser = new Map(
    (summary?.streaks ?? []).filter((s) => s.flagged).map((s) => [s.user_id, s])
  );
  const selectedRows = rows.filter(
    (r) => selected.has(r.id) && r.status === "pending" && mayDecide(r)
  );
  const selectedTotal = selectedRows.reduce((sum, r) => sum + r.amount, 0);
  const pendingTotal = rows
    .filter((a) => a.status === "pending")
    .reduce((s, a) => s + a.amount, 0);
  // Tasdiqlangan, lekin hali TO'LANMAGAN — kassa uchun ish ro'yxati.
  const toPayTotal = rows
    .filter((a) => a.status === "approved")
    .reduce((s, a) => s + a.amount, 0);
  const issuedTotal = rows
    .filter((a) => a.status === "issued")
    .reduce((s, a) => s + a.amount, 0);

  // A-04: xodim bo'yicha OYLIK JAMI. Bittalab qatorlarga qarab HR
  // «bu xodim shu oyda jami qancha oldi?» degan savolga javob topa
  // olmasdi — endi yuqorida yig'indi turadi.
  const perEmployee = Object.values(
    rows
      .filter((a) => a.status !== "rejected")
      .reduce<Record<number, { name: string; total: number; count: number }>>((acc, a) => {
        const cur = acc[a.user_id] ?? {
          name: a.full_name ?? `#${a.user_id}`,
          total: 0,
          count: 0,
        };
        cur.total += a.amount;
        cur.count += 1;
        acc[a.user_id] = cur;
        return acc;
      }, {})
  ).sort((x, y) => y.total - x.total);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!userId) {
      toast.error("Xodimni tanlang");
      return;
    }
    const n = Number(amount);
    if (!n || n <= 0) {
      toast.error("Summa musbat son bo'lishi kerak");
      return;
    }
    if (reason.trim().length < 3) {
      toast.error("Sababni yozing (kamida 3 harf)");
      return;
    }
    submit(false);
  };

  /**
   * `force` — dublikat ogohlantirishidan keyin tasdiqlangani.
   * `override` — chegaradan oshiq kiritishga Boshliq roziligi (sabab bilan).
   */
  const submit = (force: boolean, override = false) => {
    if (!userId) return;
    const n = Number(amount);
    createAdvance.mutate(
      {
        user_id: userId,
        period,
        amount: n,
        reason: reason.trim(),
        confirm_duplicate: force,
        ...(override ? { override_limit: true, override_reason: overReason.trim() } : {}),
      },
      {
        onSuccess: () => {
          const nomi = (usersQuery.data ?? []).find((u) => u.id === userId)?.full_name ?? "";
          toast.success(
            nomi
              ? `${nomi} — avans kiritildi, Boshliq tasdig'i kutilmoqda`
              : "Avans kiritildi, Boshliq tasdig'i kutilmoqda"
          );
          setAmount("");
          setReason("");
          setUserId(null);
          setDupWarning(null);
          setOverWarning(null);
          setOverReason("");
        },
        onError: (err) => {
          if (!(err instanceof ApiError)) return;
          // 409 — taqiq emas, savol: «shu avans allaqachon kiritilganmi?»
          if (err.payload?.code === "advance_duplicate") {
            setDupWarning(err.message);
            return;
          }
          // 400 — chegaradan oshdi. HR uchun bu oddiy xato (toast), Boshliq
          // uchun esa istisno qilish imkoni bo'lgan savol.
          if (err.payload?.code === "advance_over_limit") {
            if (canDecide) setOverWarning(err.message);
            else toast.error(err.message);
          }
          // Qolgan xatolarni `useApiMutation` o'zi toast qiladi.
        },
      }
    );
  };

  const columns: ColumnDef<PayrollAdjustment>[] = [
    // D-02: tanlash. Faqat qaror kutayotgan qatorlarda va faqat
    // qaror qila oladigan rolda ko'rinadi.
    ...(canDecide
      ? [
          {
            id: "select",
            header: "",
            cell: ({ row }: { row: { original: PayrollAdjustment } }) =>
              row.original.status === "pending" && mayDecide(row.original) ? (
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={selected.has(row.original.id)}
                  onChange={(e) => {
                    setSelected((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(row.original.id);
                      else next.delete(row.original.id);
                      return next;
                    });
                  }}
                />
              ) : null,
          } as ColumnDef<PayrollAdjustment>,
        ]
      : []),
    {
      accessorKey: "full_name",
      header: "Xodim",
      cell: ({ row }) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <b>{row.original.full_name ?? `#${row.original.user_id}`}</b>
          {/* Manba ko'rinmasa HR ariza orqali kelgan avansni qo'lda takror
              kiritishi mumkin edi — pul ikki marta ayirilardi (A-01). */}
          {row.original.source === "request" && (
            <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[11px] font-medium text-sky-700">
              ariza orqali
            </span>
          )}
          {row.original.source === "bot" && (
            <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700">
              bot orqali
            </span>
          )}
          {/* D-03: ketma-ket avans. ⚠️ JAZO EMAS — suhbat uchun signal.
              Xodimga bu haqda hech qanday xabar ketmaydi va pulga
              ta'sir qilmaydi. Matn neytral: ayblov emas, faqat fakt. */}
          {streakByUser.has(row.original.user_id) && (
            <span
              className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800"
              title="Suhbat uchun signal — jazo emas, pulga ta'sir qilmaydi"
            >
              {streakByUser.get(row.original.user_id)!.months} oy ketma-ket
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: "amount",
      header: "Summa",
      cell: ({ row }) => <span className="text-rose-600">−{fmtMoney(row.original.amount)}</span>,
    },
    {
      accessorKey: "issued_on",
      header: "To'langan sana",
      cell: ({ row }) =>
        row.original.issued_on ? (
          format(new Date(row.original.issued_on), "dd.MM.yyyy")
        ) : (
          // Bo'sh katak emas, IZOH: sana yo'qligi xato emas — pul hali
          // berilmagan degani (A-04).
          <span className="text-slate-400">hali to'lanmagan</span>
        ),
    },
    { accessorKey: "reason", header: "Sabab" },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="advance" status={row.original.status} />,
    },
    {
      id: "who",
      header: "Kim",
      cell: ({ row }) => (
        <div className="text-xs text-slate-500">
          <div>Kiritdi: {row.original.created_by_name ?? "—"}</div>
          {row.original.decided_by_name && <div>Qaror: {row.original.decided_by_name}</div>}
          {row.original.issued_by_name && <div>To'ladi: {row.original.issued_by_name}</div>}
        </div>
      ),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => {
        // Tasdiqlangan/to'langan pulni bekor qilish — Boshliq/Dasturchi
        // ishi (server ham 403 beradi). HR faqat hali qaror qilinmaganini
        // o'chira oladi.
        const isFinal = ["approved", "issued"].includes(row.original.status);
        const canDelete = canDecide || !isFinal;
        const del = canDelete && (
          <Button
            size="sm"
            variant="ghost"
            className="text-slate-400 hover:text-rose-600"
            title="O'chirish"
            disabled={removeAdj.isPending}
            onClick={() => {
              setToDelete(row.original);
              setDeleteReason("");
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        );

        // Tasdiqlangan, lekin to'lanmagan — kassa amali. Uni HR ham
        // bosa oladi (pulni odatda HR/kassa beradi, Boshliq emas).
        if (row.original.status === "approved") {
          return (
            <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={issue.isPending}
              onClick={() =>
                issue.mutate(
                  { adjustmentId: row.original.id },
                  { onSuccess: () => toast.success("To'lab berildi deb belgilandi") }
                )
              }
            >
              <Banknote className="mr-1 h-4 w-4" />
              To'lab berildi
            </Button>
              {del}
            </div>
          );
        }
        if (!canDecide || row.original.status !== "pending" || !mayDecide(row.original)) {
          return del || null;
        }
        return (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { adjustmentId: row.original.id, approve: true },
                  { onSuccess: () => toast.success("Avans tasdiqlandi — xodimga xabar berildi") }
                )
              }
            >
              <Check className="mr-1 h-4 w-4" />
              Tasdiqlash
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { adjustmentId: row.original.id, approve: false },
                  { onSuccess: () => toast.success("Avans rad etildi") }
                )
              }
            >
              <X className="h-4 w-4" />
            </Button>
            {del}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Avans"
        description="Oy o'rtasida berilgan pul. Boshliq tasdiqlagach oy oxirida oylikdan avtomatik ayiriladi."
      >
        <div className="flex items-center gap-2">
          {canManage && (
            <Button variant="outline" size="sm" onClick={() => setAnnounceOpen(true)}>
              <Megaphone className="mr-1 h-4 w-4" />
              Avans kunini e'lon qilish
            </Button>
          )}
          <MonthPicker value={period} onChange={setPeriod} />
        </div>
      </PageHeader>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="h-fit md:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Yangi avans</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <Label>Xodim</Label>
                <Select
                  value={userId ? String(userId) : undefined}
                  onValueChange={(v) => setUserId(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Tanlang" />
                  </SelectTrigger>
                  <SelectContent>
                    {(usersQuery.data ?? []).map((u) => (
                      <SelectItem key={u.id} value={String(u.id)}>
                        {u.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="adv-amount">Summa (so'm)</Label>
                <Input
                  id="adv-amount"
                  type="number"
                  min={1}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="adv-reason">Sabab</Label>
                <Input
                  id="adv-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Masalan: oilaviy ehtiyoj"
                  required
                />
              </div>
              {/* Chegara (A-03) — kiritishdan OLDIN ko'rinadi. Faqat
                  raqam emas, kelib chiqishi ham: HR «nega shuncha?» degan
                  savol bilan qolmasin. */}
              {userId != null && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs">
                  {limitQuery.isLoading && <span className="text-slate-500">Chegara hisoblanmoqda…</span>}
                  {limitQuery.error && (
                    <span className="text-amber-700">
                      Chegarani hisoblab bo'lmadi — kiritishda server tekshiradi.
                    </span>
                  )}
                  {limit && (
                    <>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-slate-600">Ruxsat etilgan eng katta summa</span>
                        <b className={limit.limit > 0 ? "text-emerald-700" : "text-rose-600"}>
                          {fmtMoney(limit.limit)}
                        </b>
                      </div>
                      {limit.limit <= 0 && limit.reason && (
                        <div className="mt-1 text-rose-600">Sabab: {limit.reason}</div>
                      )}
                      <div className="mt-1.5 space-y-0.5 text-slate-500">
                        <div>
                          Sof oylik {fmtMoney(limit.net_salary)} · {limit.worked_days}/
                          {limit.scheduled_days} kun ishlangan
                        </div>
                        <div>
                          Koeffitsient {limit.coefficient} · yuqori chegara {limit.cap_percent}% (
                          {fmtMoney(limit.cap_amount)})
                        </div>
                        {(limit.taken > 0 || limit.deductions > 0) && (
                          <div>
                            Shu oyda olingan avans {fmtMoney(limit.taken)}
                            {limit.deductions > 0 && ` · ushlanma ${fmtMoney(limit.deductions)}`}
                          </div>
                        )}
                        {limit.warnings.map((w) => (
                          <div key={w} className="text-amber-700">
                            {w}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
              <p className="text-xs text-slate-500">
                Avans <b>{period}</b> oyligidan ayiriladi. Kiritilgach Boshliqqa tasdiq uchun xabar
                boradi — tasdiqlangunicha oylikka kirmaydi.{" "}
                <b>Pul tasdiqdan keyin beriladi</b> va ro'yxatdagi «To'lab berildi» tugmasi bilan
                belgilanadi.
              </p>
              <Button type="submit" disabled={createAdvance.isPending || !userId} className="w-full">
                {createAdvance.isPending ? "Saqlanmoqda..." : "Kiritish"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-3 md:col-span-2">
          {/* D-02: yig'indi TASDIQLASHDAN OLDIN. Boshliq bittalab bosib,
              umumiy og'irlikni faqat oxirida bilib qolmasin. */}
          {summary && summary.pending_count > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <b>{summary.pending_employees}</b> xodim jami{" "}
              <b>{fmtMoney(summary.pending_total)}</b> so'raydi
              {summary.today_count > 0 && (
                <>
                  {" "}
                  · bugun: {summary.today_count} ta,{" "}
                  <b>{fmtMoney(summary.today_total)}</b>
                </>
              )}
              {summary.approved_total > 0 && (
                <div className="mt-1 text-xs">
                  Tasdiqlangan, to'lash kutilmoqda (kassa uchun):{" "}
                  <b>{fmtMoney(summary.approved_total)}</b>
                </div>
              )}
            </div>
          )}
          {rows.length > 0 && (
            <div className="flex flex-wrap gap-3 text-sm">
              {pendingTotal > 0 && (
                <span className="rounded-lg bg-amber-50 px-3 py-1.5 text-amber-800">
                  Tasdiq kutilmoqda: <b>{fmtMoney(pendingTotal)}</b>
                </span>
              )}
              {toPayTotal > 0 && (
                <span className="rounded-lg bg-sky-50 px-3 py-1.5 text-sky-800">
                  To'lash kutilmoqda: <b>{fmtMoney(toPayTotal)}</b>
                </span>
              )}
              <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-slate-700">
                To'lab berilgan: <b>{fmtMoney(issuedTotal)}</b>
              </span>
            </div>
          )}
          {perEmployee.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="mb-1.5 text-xs font-medium text-slate-500">
                Xodim bo'yicha oylik jami (rad etilganlar hisobga olinmagan)
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {perEmployee.map((e) => (
                  <span key={e.name} className="text-slate-700">
                    {e.name}: <b>{fmtMoney(e.total)}</b>
                    {e.count > 1 && (
                      <span className="text-slate-400"> ({e.count} ta)</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
          {canDecide && selectedRows.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
              <div className="text-sm text-sky-900">
                Tanlandi: <b>{selectedRows.length}</b> ta ·{" "}
                <b>{fmtMoney(selectedTotal)}</b>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                  Bekor qilish
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={bulkDecide.isPending}
                  onClick={() =>
                    bulkDecide.mutate(
                      { ids: selectedRows.map((r) => r.id), approve: false },
                      {
                        onSuccess: (res) => {
                          toast.success(`${res.decided} ta avans rad etildi`);
                          setSelected(new Set());
                        },
                      }
                    )
                  }
                >
                  Rad etish
                </Button>
                <Button
                  size="sm"
                  disabled={bulkDecide.isPending}
                  onClick={() =>
                    bulkDecide.mutate(
                      { ids: selectedRows.map((r) => r.id), approve: true },
                      {
                        onSuccess: (res) => {
                          toast.success(
                            res.skipped
                              ? `${res.decided} ta tasdiqlandi, ${res.skipped} tasi allaqachon hal qilingan edi`
                              : `${res.decided} ta avans tasdiqlandi`
                          );
                          setSelected(new Set());
                        },
                      }
                    )
                  }
                >
                  <Check className="mr-1 h-4 w-4" />
                  Tanlanganlarni tasdiqlash
                </Button>
              </div>
            </div>
          )}
          <DataTable
            columns={columns}
            data={listQuery.data}
            isLoading={listQuery.isLoading}
            error={listQuery.error ? listQuery.error.message : null}
            onRetry={() => listQuery.refetch()}
            searchPlaceholder="Xodim bo'yicha qidirish..."
            empty={{ text: "Bu oy uchun avans kiritilmagan." }}
          />
        </div>
      </div>

      <AlertDialog open={announceOpen} onOpenChange={setAnnounceOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Avans kunini e'lon qilish</AlertDialogTitle>
            <AlertDialogDescription>
              Barcha mos xodimga xabar boradi: avans qaysi kuni berilishi va unga
              qancha mumkinligi. <b>Shu oyda avtomatik xabar endi yuborilmaydi</b> —
              xodim ikki marta xabar olmasin. Qayta e'lon qilinsa oxirgisi kuchda
              bo'ladi.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="ann-date">Avans beriladigan sana</Label>
              <Input
                id="ann-date"
                type="date"
                value={announceDate}
                onChange={(e) => setAnnounceDate(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="ann-note">Qo'shimcha izoh (ixtiyoriy)</Label>
              <Input
                id="ann-note"
                value={announceNote}
                onChange={(e) => setAnnounceNote(e.target.value)}
                placeholder="Masalan: bayram sababli sana ko'chirildi"
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Bekor qilish</AlertDialogCancel>
            <AlertDialogAction
              disabled={announce.isPending}
              onClick={(e) => {
                e.preventDefault();
                announce.mutate(
                  { advance_date: announceDate, note: announceNote.trim() || null },
                  {
                    onSuccess: (res) => {
                      toast.success(`${res.recipients} xodimga xabar navbatga qo'yildi`);
                      setAnnounceOpen(false);
                      setAnnounceNote("");
                    },
                  }
                );
              }}
            >
              E'lon qilish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={!!toDelete}
        onOpenChange={(o) => {
          if (!o) {
            setToDelete(null);
            setDeleteReason("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Avansni o'chirish</AlertDialogTitle>
            <AlertDialogDescription>
              {toDelete && (
                <>
                  {toDelete.full_name ?? `#${toDelete.user_id}`} — {fmtMoney(toDelete.amount)}.
                  {["approved", "issued"].includes(toDelete.status) && (
                    <b> Bu avans allaqachon tasdiqlangan/to'langan — pul harakatlangan bo'lishi mumkin.</b>
                  )}{" "}
                  Yozuv bazadan yo'qolmaydi: u o'chirilgan deb belgilanadi va oylikdan
                  ayirilmaydi. Kim, qachon va nega o'chirgani auditda qoladi.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="adv-del-reason">O'chirish sababi</Label>
            <Input
              id="adv-del-reason"
              value={deleteReason}
              onChange={(e) => setDeleteReason(e.target.value)}
              placeholder="Masalan: xato kiritilgan, xodim voz kechdi"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Bekor qilish</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 hover:bg-rose-700"
              disabled={removeAdj.isPending}
              onClick={() => {
                if (!toDelete) return;
                removeAdj.mutate(
                  { adjustmentId: toDelete.id, reason: deleteReason.trim() || undefined },
                  {
                    onSuccess: () => {
                      toast.success("Avans o'chirildi");
                      setToDelete(null);
                      setDeleteReason("");
                    },
                  }
                );
              }}
            >
              O'chirish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={!!overWarning}
        onOpenChange={(o) => {
          if (!o) {
            setOverWarning(null);
            setOverReason("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Chegaradan oshiq avans</AlertDialogTitle>
            <AlertDialogDescription>{overWarning}</AlertDialogDescription>
          </AlertDialogHeader>
          {/* Istisno bo'lishi mumkin, lekin IZSIZ emas — sabab auditga
              «advance_over_limit» amali bilan tushadi. */}
          <div className="space-y-1.5">
            <Label htmlFor="adv-override">Istisno sababi (majburiy)</Label>
            <Input
              id="adv-override"
              value={overReason}
              onChange={(e) => setOverReason(e.target.value)}
              placeholder="Masalan: shoshilinch tibbiy xarajat, Boshliq roziligi"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Bekor qilish</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // Sabab bo'sh bo'lsa oyna YOPILMASIN — aks holda bosish
                // bekorga ketib, HR nima bo'lganini tushunmaydi.
                if (!overReason.trim()) {
                  e.preventDefault();
                  toast.error("Istisno sababini yozing");
                  return;
                }
                submit(true, true);
              }}
              disabled={createAdvance.isPending}
            >
              Chegaradan oshiq kiritish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!dupWarning} onOpenChange={(o) => !o && setDupWarning(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Takroriy avansga o'xshaydi</AlertDialogTitle>
            <AlertDialogDescription>{dupWarning}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Bekor qilish</AlertDialogCancel>
            <AlertDialogAction onClick={() => submit(true)} disabled={createAdvance.isPending}>
              Baribir kiritish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
