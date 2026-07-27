import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Pencil, RotateCcw, ShieldAlert, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import ReasonDialog from "@/components/ReasonDialog";
import { MonthPicker, currentMonthKey, DateRangePicker } from "@/components/PeriodPicker";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type AdminRecord, type OverrideAuditRow } from "@/lib/api";
import {
  useAdminClearMetric,
  useAdminDeleteNorm,
  useAdminRecords,
  useAdminRevertNorm,
  useAdminSetNorm,
  useDeleteAdminRecord,
  useDeletePayrollPeriodAdmin,
  useForceRecalculatePayrollAdmin,
  useForceRoleAdmin,
  useOverrideAudit,
  usePatchAdminRecord,
  usePatchPayslipAdmin,
  useRecalculateAttendanceAdmin,
  useRestoreAdminRecord,
  useUnlockPayrollPeriodAdmin,
  useUsers,
} from "@/lib/queries";

// ─────────────────────────────────────────────────────────────────
// OYLIK_JARIMA_REJASI.md 11-bo'lim — Dasturchi rejimi (super-admin).
// Backend allaqachon Bosqich 3.5'da tayyor (api/routers/admin_override.py);
// bu sahifa shu API'ning yagona web interfeysi. `editMode` o'chiq holatda
// FAQAT ko'rish — tugmalar yashiriladi (11.5-band: "tumbler yoqilmaguncha
// qizil tugmalar umuman ko'rinmaydi").
// ─────────────────────────────────────────────────────────────────

// Server (`admin_override.py::ENTITY_REGISTRY`) bilan BIR XIL — PATCH uchun
// oq ro'yxat mos kelmasa server 400 qaytaradi, lekin shu ro'yxat frontendда
// qaysi maydonlar tahrirlanishini ko'rsatish uchun kerak.
const ENTITY_META: Record<string, { label: string; fields: string[]; soft: boolean }> = {
  norm: { label: "Normalar", fields: ["value", "metric_type", "effective_from"], soft: true },
  attendance: {
    label: "Davomat",
    fields: ["status", "note", "late_minutes", "early_leave_minutes", "worked_minutes"],
    soft: false,
  },
  excused_day: { label: "Sababli kunlar", fields: ["reason", "status"], soft: false },
  task: { label: "Vazifalar", fields: ["title", "description", "deadline", "status"], soft: false },
  daily_result: { label: "Kunlik natijalar", fields: ["conversations_count", "visits_count"], soft: false },
  mobilograf_video: { label: "Mobilograf video", fields: ["status", "video_type"], soft: false },
  overtime: { label: "Qo'shimcha ish", fields: ["minutes", "status", "note"], soft: false },
  salary_rate: { label: "Oylik stavka", fields: ["amount", "pay_basis", "note"], soft: true },
  payroll_adjustment: { label: "Qo'lda qo'shimcha/ushlanma", fields: ["amount", "kind", "reason"], soft: false },
  fine_policy: {
    label: "Jarima qoidasi",
    fields: [
      "free_late_minutes_per_month", "fine_mode", "fine_per_day", "absent_mode", "absent_fine",
      "monthly_cap_percent", "monthly_cap_amount", "fine_applies_to", "is_active", "grace_minutes",
    ],
    soft: false,
  },
  bonus: { label: "Bonus", fields: ["amount"], soft: false },
};

const ROLE_OPTIONS = [
  { value: "employee", label: "Xodim" },
  { value: "hr", label: "HR" },
  { value: "rop", label: "ROP" },
  { value: "boss", label: "Boshliq" },
  { value: "dasturchi", label: "Dasturchi" },
];

function fieldSummary(row: AdminRecord, fields: string[]): string {
  return fields
    .map((f) => `${f}: ${row[f] === null || row[f] === undefined ? "—" : String(row[f])}`)
    .join(" · ");
}

function ownerUserId(row: AdminRecord): number | null {
  const v = row.user_id ?? row.assigned_to;
  return typeof v === "number" ? v : null;
}

// ─────────────────────────────────────────────
// Tab 1: Yozuvlar (universal entity brauzeri)
// ─────────────────────────────────────────────

function RecordEditDialog({
  entity,
  record,
  onClose,
}: {
  entity: string;
  record: AdminRecord | null;
  onClose: () => void;
}) {
  const meta = ENTITY_META[entity];
  const patch = usePatchAdminRecord(entity);
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (record) {
      const init: Record<string, string> = {};
      for (const f of meta.fields) init[f] = record[f] == null ? "" : String(record[f]);
      setValues(init);
    }
    setReason("");
  }, [record, meta]);

  if (!record) return null;

  const handleSubmit = () => {
    if (reason.trim().length < 5) {
      toast.error("Sabab kamida 5 belgi bo'lishi kerak");
      return;
    }
    const changed: Record<string, unknown> = {};
    for (const f of meta.fields) {
      const orig = record[f];
      const raw = values[f];
      if (String(orig ?? "") === raw) continue;
      if (typeof orig === "boolean") changed[f] = raw === "true";
      else if (typeof orig === "number") changed[f] = raw === "" ? null : Number(raw);
      else changed[f] = raw;
    }
    if (Object.keys(changed).length === 0) {
      toast.error("Hech qanday maydon o'zgarmadi");
      return;
    }
    patch.mutate(
      { id: record.id as number, fields: changed, reason: reason.trim() },
      { onSuccess: () => { toast.success("Saqlandi"); onClose(); } }
    );
  };

  return (
    <Dialog open={!!record} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{meta.label} #{String(record.id)} — majburan tahrirlash</DialogTitle>
          <DialogDescription>
            Faqat o'zgargan maydonlar yuboriladi. Server oq ro'yxatdan tashqari maydonni rad etadi.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {meta.fields.map((f) =>
            typeof record[f] === "boolean" ? (
              <label key={f} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={values[f] === "true"}
                  onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.checked ? "true" : "false" }))}
                />
                {f}
              </label>
            ) : (
              <div key={f}>
                <Label htmlFor={`f-${f}`}>{f}</Label>
                <Input
                  id={`f-${f}`}
                  value={values[f] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
                />
              </div>
            )
          )}
          <div>
            <Label htmlFor="edit-reason">Sabab (majburiy, kamida 5 belgi)</Label>
            <textarea
              id="edit-reason"
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Bekor qilish
          </Button>
          <Button type="button" disabled={patch.isPending} onClick={handleSubmit}>
            {patch.isPending ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RecordsTab({ editMode }: { editMode: boolean }) {
  const [entity, setEntity] = useState("norm");
  const meta = ENTITY_META[entity];
  const query = useAdminRecords(entity);
  const usersQuery = useUsers(undefined, true);
  const del = useDeleteAdminRecord(entity);
  const restore = useRestoreAdminRecord(entity);
  const [editing, setEditing] = useState<AdminRecord | null>(null);
  const [deleting, setDeleting] = useState<AdminRecord | null>(null);

  const nameById = useMemo(() => {
    const m = new Map<number, string>();
    (usersQuery.data ?? []).forEach((u) => m.set(u.id, u.full_name));
    return m;
  }, [usersQuery.data]);

  const columns: ColumnDef<AdminRecord>[] = [
    { id: "id", header: "ID", cell: ({ row }) => String(row.original.id) },
    {
      id: "owner",
      header: "Egasi",
      cell: ({ row }) => {
        const uid = ownerUserId(row.original);
        return uid ? (nameById.get(uid) ?? `#${uid}`) : "—";
      },
    },
    { id: "summary", header: "Tafsilot", cell: ({ row }) => fieldSummary(row.original, meta.fields) },
    {
      id: "status",
      header: "Holat",
      cell: ({ row }) =>
        row.original.deleted_at ? (
          <span className="text-rose-600">O'chirilgan</span>
        ) : (
          <span className="text-emerald-600">Faol</span>
        ),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) =>
        editMode ? (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setEditing(row.original)}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            {row.original.deleted_at ? (
              meta.soft && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-emerald-600 hover:text-emerald-700"
                  onClick={() =>
                    restore.mutate(
                      { id: row.original.id as number, reason: "Dasturchi tomonidan tiklandi" },
                      { onSuccess: () => toast.success("Tiklandi") }
                    )
                  }
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
              )
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-rose-600 hover:text-rose-700"
                onClick={() => setDeleting(row.original)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <Select value={entity} onValueChange={setEntity}>
        <SelectTrigger className="w-64">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(ENTITY_META).map(([key, m]) => (
            <SelectItem key={key} value={key}>
              {m.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        empty={{ text: "Yozuv topilmadi." }}
      />

      <RecordEditDialog entity={entity} record={editing} onClose={() => setEditing(null)} />
      <ReasonDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`${meta.label} #${deleting ? String(deleting.id) : ""} — o'chirasizmi?`}
        description={
          meta.soft
            ? "Yumshoq o'chiriladi — keyin 'Tiklash' bilan qaytarish mumkin."
            : "Bu jadval yumshoq o'chirishni qo'llab-quvvatlamaydi — QATTIQ o'chiriladi (butunlay, faqat AuditLog'da nusxasi qoladi)."
        }
        destructive
        loading={del.isPending}
        onConfirm={(reason) => {
          if (!deleting) return;
          del.mutate(
            { id: deleting.id as number, reason },
            { onSuccess: () => { toast.success("O'chirildi"); setDeleting(null); } }
          );
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 2: Normalar (cheklovsiz belgilash/tozalash/qaytarish)
// ─────────────────────────────────────────────

function NormsTab({ editMode }: { editMode: boolean }) {
  const usersQuery = useUsers(undefined, true);
  const setNorm = useAdminSetNorm();
  const clearMetric = useAdminClearMetric();
  const revertNorm = useAdminRevertNorm();

  const [userId, setUserId] = useState<number | null>(null);
  const [metric, setMetric] = useState("");
  const [value, setValue] = useState("");
  const [pendingAction, setPendingAction] = useState<"set" | "clear" | "revert" | null>(null);

  if (!editMode) {
    return (
      <p className="text-sm text-slate-500">
        Dasturchi rejimini yoqing — normani cheklovsiz belgilash/tozalash/qaytarish shu yerda.
        Alohida yozuvlarni ko'rish/tahrirlash uchun «Yozuvlar» tabidan «Normalar» ni tanlang.
      </p>
    );
  }

  const canSubmit = userId !== null && metric.trim().length > 0;

  return (
    <div className="max-w-xl space-y-4">
      <p className="text-sm text-slate-500">
        Oddiy «Normalar» sahifasidan farqli — bu yerda HAR QANDAY rolga (HR/ROP/Boshliq ham) va
        lavozim metrikasi cheklovisiz istalgan metrikaga qiymat qo'yiladi (11.3-band).
      </p>
      <div>
        <Label>Xodim</Label>
        <Select value={userId ? String(userId) : undefined} onValueChange={(v) => setUserId(Number(v))}>
          <SelectTrigger>
            <SelectValue placeholder="Tanlang" />
          </SelectTrigger>
          <SelectContent>
            {(usersQuery.data ?? []).map((u) => (
              <SelectItem key={u.id} value={String(u.id)}>
                {u.full_name} ({u.role})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label htmlFor="norm-metric">Metrika</Label>
        <Input
          id="norm-metric"
          placeholder="masalan: suhbat, tashrif, oddiy_video, dumaloq_video"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="norm-value">Qiymat (faqat «Belgilash» uchun)</Label>
        <Input id="norm-value" type="number" min={0} value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={!canSubmit || !value}
          onClick={() => setPendingAction("set")}
        >
          Belgilash
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!canSubmit}
          onClick={() => setPendingAction("revert")}
        >
          Oldingi qiymatga qaytarish
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="text-rose-600 hover:text-rose-700"
          disabled={!canSubmit}
          onClick={() => setPendingAction("clear")}
        >
          Metrikani butunlay tozalash
        </Button>
      </div>

      <ReasonDialog
        open={pendingAction === "set"}
        onOpenChange={(o) => !o && setPendingAction(null)}
        title={`${metric} = ${value} belgilanadi`}
        loading={setNorm.isPending}
        onConfirm={(reason) => {
          if (!userId) return;
          setNorm.mutate(
            { userId, metric: metric.trim(), value: Number(value), reason },
            { onSuccess: () => { toast.success("Norma belgilandi"); setPendingAction(null); } }
          );
        }}
      />
      <ReasonDialog
        open={pendingAction === "revert"}
        onOpenChange={(o) => !o && setPendingAction(null)}
        title={`${metric} — oldingi qiymatga qaytarilsinmi?`}
        loading={revertNorm.isPending}
        onConfirm={(reason) => {
          if (!userId) return;
          revertNorm.mutate(
            { userId, metric: metric.trim(), reason },
            {
              onSuccess: (r) => {
                toast.success(
                  r.current_value !== null ? `Qaytarildi: ${r.current_value}` : "Qaytarildi (oldingi yozuv yo'q)"
                );
                setPendingAction(null);
              },
            }
          );
        }}
      />
      <ReasonDialog
        open={pendingAction === "clear"}
        onOpenChange={(o) => !o && setPendingAction(null)}
        title={`${metric} metrikasi BUTUNLAY tozalanadi`}
        description="Shu xodimning shu metrika bo'yicha barcha faol tarix qatorlari yumshoq o'chiriladi."
        destructive
        loading={clearMetric.isPending}
        onConfirm={(reason) => {
          if (!userId) return;
          clearMetric.mutate(
            { userId, metric: metric.trim(), reason },
            {
              onSuccess: (r) => { toast.success(`${r.cleared} ta yozuv tozalandi`); setPendingAction(null); },
            }
          );
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 3: Payroll qulflari
// ─────────────────────────────────────────────

function PayrollAdminTab({ editMode }: { editMode: boolean }) {
  const [period, setPeriod] = useState(currentMonthKey());
  const usersQuery = useUsers(undefined, true);
  const unlock = useUnlockPayrollPeriodAdmin();
  const forceRecalc = useForceRecalculatePayrollAdmin();
  const deletePeriod = useDeletePayrollPeriodAdmin();
  const patchPayslip = usePatchPayslipAdmin();

  const [action, setAction] = useState<"unlock" | "recalc" | "delete" | null>(null);
  const [payslipUserId, setPayslipUserId] = useState<number | null>(null);
  const [payslipField, setPayslipField] = useState("net");
  const [payslipValue, setPayslipValue] = useState("");
  const [patchingPayslip, setPatchingPayslip] = useState(false);

  if (!editMode) {
    return (
      <p className="text-sm text-slate-500">
        Dasturchi rejimini yoqing — qulflangan davrni ochish, majburan qayta hisoblash, tasdiqlangan
        varaqani qo'lda tuzatish yoki butun davrni bekor qilish shu yerda.
      </p>
    );
  }

  const payslipFields = [
    "base_amount", "fine_amount", "absent_deduction", "overtime_amount",
    "bonus_amount", "adjustments_plus", "adjustments_minus", "gross", "net", "status",
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <Label>Davr</Label>
        <MonthPicker value={period} onChange={setPeriod} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => setAction("unlock")}>
          Qulfni ochish
        </Button>
        <Button size="sm" variant="outline" onClick={() => setAction("recalc")}>
          Majburan qayta hisoblash
        </Button>
        <Button size="sm" variant="destructive" onClick={() => setAction("delete")}>
          Butun davrni bekor qilish
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Tasdiqlangan varaqani qo'lda tuzatish</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label>Xodim</Label>
            <Select
              value={payslipUserId ? String(payslipUserId) : undefined}
              onValueChange={(v) => setPayslipUserId(Number(v))}
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
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Maydon</Label>
              <Select value={payslipField} onValueChange={setPayslipField}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {payslipFields.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Yangi qiymat</Label>
              <Input value={payslipValue} onChange={(e) => setPayslipValue(e.target.value)} />
            </div>
          </div>
          <Button
            size="sm"
            disabled={!payslipUserId || !payslipValue}
            onClick={() => setPatchingPayslip(true)}
          >
            Tuzatish
          </Button>
        </CardContent>
      </Card>

      <ReasonDialog
        open={action === "unlock"}
        onOpenChange={(o) => !o && setAction(null)}
        title={`«${period}» davrining qulfi ochiladi`}
        loading={unlock.isPending}
        onConfirm={(reason) => {
          unlock.mutate(
            { period, reason },
            { onSuccess: () => { toast.success("Qulf ochildi"); setAction(null); } }
          );
        }}
      />
      <ReasonDialog
        open={action === "recalc"}
        onOpenChange={(o) => !o && setAction(null)}
        title={`«${period}» davri MAJBURAN qayta hisoblanadi`}
        description="Qulf avtomatik ochiladi (agar bo'lsa) va butun davr qayta hisoblanadi."
        destructive
        loading={forceRecalc.isPending}
        onConfirm={(reason) => {
          forceRecalc.mutate(
            { period, reason },
            {
              onSuccess: (r) => {
                toast.success(`${r.calculated} xodim qayta hisoblandi`);
                setAction(null);
              },
            }
          );
        }}
      />
      <ReasonDialog
        open={action === "delete"}
        onOpenChange={(o) => !o && setAction(null)}
        title={`«${period}» davri BUTUNLAY bekor qilinadi`}
        description="Barcha payslip va qatorlari o'chiriladi. Bu qaytarib bo'lmaydi (faqat AuditLog'da nusxa qoladi)."
        destructive
        requireTypedConfirmation={period}
        loading={deletePeriod.isPending}
        onConfirm={(reason) => {
          deletePeriod.mutate(
            { period, reason },
            {
              onSuccess: (r) => {
                toast.success(`${r.deleted_payslips} ta payslip o'chirildi`);
                setAction(null);
              },
            }
          );
        }}
      />
      <ReasonDialog
        open={patchingPayslip}
        onOpenChange={setPatchingPayslip}
        title={`Payslip #${payslipUserId ?? ""} — ${payslipField} = ${payslipValue}`}
        description="Keyingi qayta hisoblash bu qiymatni ustidan yozib yuboradi — faqat qulflangan (yakuniy) davrda ishlating."
        destructive
        loading={patchPayslip.isPending}
        onConfirm={(reason) => {
          if (!payslipUserId) return;
          const isNumeric = payslipField !== "status";
          patchPayslip.mutate(
            {
              period,
              userId: payslipUserId,
              fields: { [payslipField]: isNumeric ? Number(payslipValue) : payslipValue },
              reason,
            },
            { onSuccess: () => { toast.success("Payslip tuzatildi"); setPatchingPayslip(false); } }
          );
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 4: Tizim (davomat qayta hisoblash, rolni majburan o'zgartirish)
// ─────────────────────────────────────────────

function SystemTab({ editMode }: { editMode: boolean }) {
  const usersQuery = useUsers(undefined, true);
  const recalcAttendance = useRecalculateAttendanceAdmin();
  const forceRole = useForceRoleAdmin();

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [recalcOpen, setRecalcOpen] = useState(false);

  const [roleUserId, setRoleUserId] = useState<number | null>(null);
  const [newRole, setNewRole] = useState("employee");
  const [roleOpen, setRoleOpen] = useState(false);

  if (!editMode) {
    return (
      <p className="text-sm text-slate-500">
        Dasturchi rejimini yoqing — davomatni ommaviy qayta hisoblash (masalan grace sozlamasi
        o'zgargandan keyin) va rolni matritsasiz o'zgartirish shu yerda.
      </p>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Davomatni qayta hisoblash</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-slate-500">
            Berilgan oraliqdagi barcha check-in bo'lgan yozuvlarni joriy ish jadvali/grace qoidasiga
            qarab qayta hisoblaydi.
          </p>
          <DateRangePicker
            from={dateFrom}
            to={dateTo}
            withPresets={false}
            onChange={(f, t) => { setDateFrom(f); setDateTo(t); }}
          />
          <Button size="sm" disabled={!dateFrom || !dateTo} onClick={() => setRecalcOpen(true)}>
            Qayta hisoblash
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Rolni matritsasiz o'zgartirish</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label>Xodim</Label>
            <Select value={roleUserId ? String(roleUserId) : undefined} onValueChange={(v) => setRoleUserId(Number(v))}>
              <SelectTrigger>
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(usersQuery.data ?? []).map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.full_name} ({u.role})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Yangi rol</Label>
            <Select value={newRole} onValueChange={setNewRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button size="sm" variant="destructive" disabled={!roleUserId} onClick={() => setRoleOpen(true)}>
            Rolni o'zgartirish
          </Button>
        </CardContent>
      </Card>

      <ReasonDialog
        open={recalcOpen}
        onOpenChange={setRecalcOpen}
        title={`${dateFrom} — ${dateTo} oralig'i qayta hisoblanadi`}
        loading={recalcAttendance.isPending}
        onConfirm={(reason) => {
          recalcAttendance.mutate(
            { dateFrom, dateTo, reason },
            {
              onSuccess: (r) => { toast.success(`${r.recalculated} ta yozuv qayta hisoblandi`); setRecalcOpen(false); },
            }
          );
        }}
      />
      <ReasonDialog
        open={roleOpen}
        onOpenChange={setRoleOpen}
        title="Rol o'zgartiriladi"
        description="Agar o'z rolingizni o'zgartirsangiz — Boshliqqa darhol xabar ketadi (11.6-band)."
        destructive
        loading={forceRole.isPending}
        onConfirm={(reason) => {
          if (!roleUserId) return;
          forceRole.mutate(
            { userId: roleUserId, role: newRole, reason },
            { onSuccess: () => { toast.success("Rol o'zgartirildi"); setRoleOpen(false); } }
          );
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 5: Override tarixi
// ─────────────────────────────────────────────

function formatChange(value: Record<string, unknown> | null): string {
  if (!value) return "—";
  return Object.entries(value)
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(", ");
}

function AuditTab() {
  const query = useOverrideAudit();
  const usersQuery = useUsers(undefined, true);
  const nameById = useMemo(() => {
    const m = new Map<number, string>();
    (usersQuery.data ?? []).forEach((u) => m.set(u.id, u.full_name));
    return m;
  }, [usersQuery.data]);

  const columns: ColumnDef<OverrideAuditRow>[] = [
    {
      id: "created_at",
      header: "Vaqt",
      cell: ({ row }) => new Date(row.original.created_at).toLocaleString("uz-UZ"),
    },
    {
      id: "action",
      header: "Amal",
      cell: ({ row }) => row.original.action.replace(/^override_/, ""),
    },
    {
      id: "actor",
      header: "Kim",
      cell: ({ row }) =>
        row.original.actor_id ? (nameById.get(row.original.actor_id) ?? `#${row.original.actor_id}`) : "tizim",
    },
    {
      id: "target",
      header: "Kimga",
      cell: ({ row }) =>
        row.original.target_user_id
          ? (nameById.get(row.original.target_user_id) ?? `#${row.original.target_user_id}`)
          : "—",
    },
    {
      id: "change",
      header: "O'zgarish",
      enableSorting: false,
      cell: ({ row }) => (
        <div className="max-w-md text-xs text-slate-500">
          <div>oldin: {formatChange(row.original.before)}</div>
          <div>keyin: {formatChange(row.original.after)}</div>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={query.data}
      isLoading={query.isLoading}
      error={query.error ? query.error.message : null}
      onRetry={() => query.refetch()}
      empty={{ text: "Hali override amali yo'q." }}
    />
  );
}

// ─────────────────────────────────────────────

export default function AdminOverride() {
  const [editMode, setEditMode] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dasturchi rejimi"
        description="Cheklovsiz boshqaruv — har bir amal audit qilinadi va Boshliqqa ko'rinadi."
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4">
        <div className="flex items-start gap-2 text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <b>Dasturchi rejimi</b> — bu yerdagi amallar oddiy matritsalarni chetlab o'tadi
            (metrika/rol cheklovisiz, qulflarni ochib). Rejim o'chiq bo'lsa faqat ko'rish mumkin.
          </span>
        </div>
        <Button
          size="sm"
          variant={editMode ? "destructive" : "outline"}
          onClick={() => setEditMode((v) => !v)}
        >
          <ShieldAlert className="mr-2 h-4 w-4" />
          {editMode ? "Rejim YOQIQ — o'chirish" : "Rejimni yoqish"}
        </Button>
      </div>

      <Tabs defaultValue="records">
        <TabsList>
          <TabsTrigger value="records">Yozuvlar</TabsTrigger>
          <TabsTrigger value="norms">Normalar</TabsTrigger>
          <TabsTrigger value="payroll">Payroll</TabsTrigger>
          <TabsTrigger value="system">Tizim</TabsTrigger>
          <TabsTrigger value="audit">Override tarixi</TabsTrigger>
        </TabsList>
        <TabsContent value="records">
          <RecordsTab editMode={editMode} />
        </TabsContent>
        <TabsContent value="norms">
          <NormsTab editMode={editMode} />
        </TabsContent>
        <TabsContent value="payroll">
          <PayrollAdminTab editMode={editMode} />
        </TabsContent>
        <TabsContent value="system">
          <SystemTab editMode={editMode} />
        </TabsContent>
        <TabsContent value="audit">
          <AuditTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
