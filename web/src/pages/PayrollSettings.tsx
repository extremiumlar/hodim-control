import { FormEvent, useEffect, useState } from "react";
import { format } from "date-fns";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
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
import {
  type FinePolicy,
  type FinePolicyInput,
  type OvertimeProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useDeleteFinePolicy,
  useFinePolicies,
  useFinePolicyEditors,
  useOvertimeProfiles,
  usePositions,
  useSetFinePolicyEditor,
  useUpsertFinePolicy,
  useUpsertGlobalOvertimeProfile,
  useUpsertOvertimeProfile,
  useUsers,
} from "@/lib/queries";

const fmtMoney = (n: number) => `${Math.round(n).toLocaleString("uz-UZ").replace(/,/g, " ")} so'm`;

// ─────────────────────────────────────────────
// Tab 1: Jarima qoidasi
// ─────────────────────────────────────────────

const emptyPolicyDraft = (): FinePolicyInput => ({
  scope: "global",
  scope_id: null,
  free_late_minutes_per_month: 60,
  fine_mode: "per_day",
  fine_per_day: 0,
  absent_mode: "fixed",
  absent_fine: 0,
  early_leave_enabled: false,
  monthly_cap_percent: 20,
  monthly_cap_amount: null,
  fine_applies_to: "bonus_first",
  fine_remainder_mode: "drop",
  // Issiq lid (2026-08-06, egasining talabi): boshlang'ich 10 daqiqa / 0 so'm
  hot_lead_cool_minutes: 10,
  hot_lead_fine: 0,
  is_active: true,
});

function FinePolicyDialog({
  open,
  onClose,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  initial: FinePolicy | null;
}) {
  const [draft, setDraft] = useState<FinePolicyInput>(emptyPolicyDraft());
  const positionsQuery = usePositions();
  const usersQuery = useUsers();
  const upsert = useUpsertFinePolicy();

  useEffect(() => {
    if (initial) {
      setDraft({
        scope: initial.scope,
        scope_id: initial.scope_id,
        grace_minutes: initial.grace_minutes,
        free_late_minutes_per_month: initial.free_late_minutes_per_month ?? 0,
        fine_mode: initial.fine_mode,
        fine_per_day: initial.fine_per_day,
        absent_mode: initial.absent_mode,
        absent_fine: initial.absent_fine,
        early_leave_enabled: initial.early_leave_enabled,
        early_leave_per_minute: initial.early_leave_per_minute,
        monthly_cap_percent: initial.monthly_cap_percent,
        monthly_cap_amount: initial.monthly_cap_amount,
        fine_applies_to: initial.fine_applies_to,
        fine_remainder_mode: initial.fine_remainder_mode ?? "drop",
        hot_lead_cool_minutes: initial.hot_lead_cool_minutes ?? 10,
        hot_lead_fine: initial.hot_lead_fine ?? 0,
        is_active: initial.is_active,
      });
    } else {
      setDraft(emptyPolicyDraft());
    }
  }, [initial, open]);

  const capMissing = draft.monthly_cap_percent == null && draft.monthly_cap_amount == null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.scope !== "global" && !draft.scope_id) {
      toast.error("Lavozim yoki xodimni tanlang");
      return;
    }
    if (capMissing) {
      toast.error("Oylik jarima chegarasi (foiz yoki qat'iy summa) majburiy");
      return;
    }
    upsert.mutate(draft, {
      onSuccess: () => {
        toast.success("Qoida saqlandi");
        onClose();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "Qoidani tahrirlash" : "Yangi jarima qoidasi"}</DialogTitle>
          <DialogDescription>
            Qamrov: xodim &gt; lavozim &gt; global. Aniqrog'i doim ustun turadi.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Qamrov</Label>
              <Select
                value={draft.scope}
                onValueChange={(v) => setDraft((d) => ({ ...d, scope: v as FinePolicyInput["scope"], scope_id: null }))}
                disabled={!!initial}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (hammaga)</SelectItem>
                  <SelectItem value="position">Lavozimga</SelectItem>
                  <SelectItem value="user">Bitta xodimga</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {draft.scope === "position" && (
              <div>
                <Label>Lavozim</Label>
                <Select
                  value={draft.scope_id ? String(draft.scope_id) : undefined}
                  onValueChange={(v) => setDraft((d) => ({ ...d, scope_id: Number(v) }))}
                  disabled={!!initial}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Tanlang" />
                  </SelectTrigger>
                  <SelectContent>
                    {(positionsQuery.data ?? []).map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {draft.scope === "user" && (
              <div>
                <Label>Xodim</Label>
                <Select
                  value={draft.scope_id ? String(draft.scope_id) : undefined}
                  onValueChange={(v) => setDraft((d) => ({ ...d, scope_id: Number(v) }))}
                  disabled={!!initial}
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
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="fp-limit">Bepul kechikish limiti (daq/oy)</Label>
              <Input
                id="fp-limit"
                type="number"
                min={0}
                value={draft.free_late_minutes_per_month}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, free_late_minutes_per_month: Number(e.target.value) }))
                }
                required
              />
            </div>
            <div>
              <Label htmlFor="fp-fine-day">Jarima (so'm/kun, limitdan keyin)</Label>
              <Input
                id="fp-fine-day"
                type="number"
                min={0}
                value={draft.fine_per_day ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, fine_per_day: Number(e.target.value) }))}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="fp-absent">Kelmagan kun jarimasi (so'm)</Label>
              <Input
                id="fp-absent"
                type="number"
                min={0}
                value={draft.absent_fine ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, absent_fine: Number(e.target.value) }))}
                required
              />
            </div>
            <div>
              <Label>Ushlanma qayerdan olinadi</Label>
              <Select
                value={draft.fine_applies_to}
                onValueChange={(v) => setDraft((d) => ({ ...d, fine_applies_to: v as FinePolicyInput["fine_applies_to"] }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="bonus_first">Avval bonusdan (tavsiya etiladi)</SelectItem>
                  <SelectItem value="net_salary">To'g'ridan-to'g'ri oylikdan</SelectItem>
                </SelectContent>
              </Select>
              {draft.fine_applies_to === "net_salary" && (
                <p className="mt-1 text-xs text-rose-700">
                  ⚠️ Ish haqidan to'g'ridan-to'g'ri ushlab qolish qonunda cheklangan.
                  Odatda <b>avval bonusdan</b> tanlanadi.
                </p>
              )}
            </div>
          </div>

          {/* S-02: bonus ushlanmadan kam bo'lsa qoldiq nima bo'ladi. Bu
              BIZNES qarori — kodda qotirilmaydi, shuning uchun panelda. */}
          {draft.fine_applies_to === "bonus_first" && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <Label>Bonus yetmasa, qolgan qismi nima bo'ladi</Label>
              <Select
                value={draft.fine_remainder_mode ?? "drop"}
                onValueChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    fine_remainder_mode: v as FinePolicyInput["fine_remainder_mode"],
                  }))
                }
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="drop">Umuman olinmaydi</SelectItem>
                  <SelectItem value="carry_next_month">Keyingi oy bonusidan olinadi</SelectItem>
                  <SelectItem value="from_salary">Oylikdan ushlanadi</SelectItem>
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-slate-600">
                {draft.fine_remainder_mode === "carry_next_month"
                  ? "Qoldiq keyingi oyga o'tadi va o'sha oy bonusidan olinadi. Ish haqiga tegilmaydi."
                  : draft.fine_remainder_mode === "from_salary"
                    ? "Qoldiq to'g'ridan-to'g'ri ish haqidan ushlanadi."
                    : "Bonus qancha bo'lsa shuncha olinadi, qolgani hisobdan chiqariladi. Ish haqiga tegilmaydi."}
              </p>
              {draft.fine_remainder_mode === "from_salary" && (
                <p className="mt-2 rounded border border-rose-200 bg-rose-50 px-2 py-1.5 text-xs text-rose-800">
                  🔴 <b>Diqqat:</b> ish haqidan ushlab qolish faqat qonunda nazarda tutilgan
                  hollarda mumkin. Bu tanlov <b>auditga yoziladi</b> (kim va qachon yoqqani).
                </p>
              )}
            </div>
          )}

          {/* Issiq lid qoidasi — egasining talabi (2026-08-06). Faqat GLOBAL
              qoidada o'qiladi (backend: hot_lead.hot_lead_rules), shuning uchun
              boshqa scope'da ko'rsatilmaydi (chalkashmasin). */}
          {draft.scope === "global" && (
            <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
              <div className="mb-2 text-sm font-medium text-orange-900">
                🔥 Issiq lid (speed-to-lead) qoidasi
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="fp-hot-min">Necha daqiqada sovuydi</Label>
                  <Input
                    id="fp-hot-min"
                    type="number"
                    min={1}
                    max={240}
                    value={draft.hot_lead_cool_minutes ?? ""}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, hot_lead_cool_minutes: Number(e.target.value) }))
                    }
                  />
                </div>
                <div>
                  <Label htmlFor="fp-hot-fine">Sovutgani uchun jarima (so'm)</Label>
                  <Input
                    id="fp-hot-fine"
                    type="number"
                    min={0}
                    value={draft.hot_lead_fine ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, hot_lead_fine: Number(e.target.value) }))}
                  />
                </div>
              </div>
              <p className="mt-2 text-xs text-orange-800">
                Lid CRM'ga tushgandan keyin shu vaqt ichida qo'ng'iroq bo'lmasa — operator
                lidni «sovutgan» hisoblanadi: guruhga ismi bilan chiqadi va shu jarima
                e'lon qilinadi. Operatorga 3/5/7/9-daqiqada shaxsiy ogohlantirish boradi.
                Jarima 0 bo'lsa xabarda summa ko'rsatilmaydi.
              </p>
            </div>
          )}

          <div>
            <Label className="mb-1.5 block">
              Oylik jarima chegarasi (cap) <span className="text-rose-600">*</span>
            </Label>
            <div className="grid grid-cols-2 gap-3">
              <Input
                type="number"
                min={0}
                max={100}
                placeholder="Foiz (masalan 20)"
                value={draft.monthly_cap_percent ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    monthly_cap_percent: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
              <Input
                type="number"
                min={0}
                placeholder="yoki qat'iy summa"
                value={draft.monthly_cap_amount ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    monthly_cap_amount: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Ikkalasidan kamida bittasi majburiy — jarima summasi shu chegaradan oshmaydi.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.is_active ?? true}
              onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
            />
            Faol
          </label>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Bekor qilish
            </Button>
            <Button type="submit" disabled={upsert.isPending}>
              {upsert.isPending ? "Saqlanmoqda..." : "Saqlash"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FinePolicyTab() {
  const query = useFinePolicies();
  const del = useDeleteFinePolicy();
  const [editing, setEditing] = useState<FinePolicy | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<FinePolicy | null>(null);

  const scopeLabel = (p: FinePolicy) => {
    if (p.scope === "global") return "Global";
    if (p.scope === "position") return `Lavozim: ${p.scope_label ?? p.scope_id}`;
    return `Xodim: ${p.scope_label ?? p.scope_id}`;
  };

  const columns: ColumnDef<FinePolicy>[] = [
    { id: "scope", header: "Qamrov", cell: ({ row }) => scopeLabel(row.original) },
    {
      id: "limit",
      header: "Bepul limit",
      cell: ({ row }) => `${row.original.free_late_minutes_per_month ?? 0} daq/oy`,
    },
    {
      id: "fine",
      header: "Jarima/kun",
      cell: ({ row }) => (row.original.fine_per_day != null ? fmtMoney(row.original.fine_per_day) : "—"),
    },
    {
      id: "absent",
      header: "Kelmagan kun",
      cell: ({ row }) => (row.original.absent_fine != null ? fmtMoney(row.original.absent_fine) : "—"),
    },
    {
      id: "cap",
      header: "Cap",
      cell: ({ row }) =>
        row.original.monthly_cap_percent != null
          ? `${row.original.monthly_cap_percent}%`
          : row.original.monthly_cap_amount != null
            ? fmtMoney(row.original.monthly_cap_amount)
            : "—",
    },
    {
      id: "applies_to",
      header: "Manba",
      cell: ({ row }) =>
        row.original.fine_applies_to === "bonus_first"
          ? `Avval bonusdan · qoldiq: ${
              { drop: "olinmaydi", carry_next_month: "keyingi oyga", from_salary: "oylikdan" }[
                row.original.fine_remainder_mode ?? "drop"
              ]
            }`
          : "To'g'ridan-to'g'ri oylikdan",
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => setEditing(row.original)}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-rose-600 hover:text-rose-700"
            onClick={() => setDeleting(row.original)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Yangi qoida
        </Button>
      </div>
      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        empty={{
          text: "Hali jarima qoidasi yo'q — jarima tizimi to'liq O'CHIQ. Global qoida qo'shing.",
        }}
      />
      <FinePolicyDialog open={creating} onClose={() => setCreating(false)} initial={null} />
      <FinePolicyDialog open={!!editing} onClose={() => setEditing(null)} initial={editing} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`"${deleting ? scopeLabel(deleting) : ""}" qoidasini o'chirasizmi?`}
        destructive
        loading={del.isPending}
        onConfirm={() => {
          if (!deleting) return;
          del.mutate(deleting.id, {
            onSuccess: () => {
              toast.success("Qoida o'chirildi");
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 3: Qo'shimcha ish
// ─────────────────────────────────────────────

function OvertimeProfileDialog({
  target,
  initial,
  onClose,
}: {
  /** `{scope:"global"}` — barchaga default; `{scope:"user"}` — istisno. */
  target: { scope: "global" } | { scope: "user"; userId: number } | null;
  initial: OvertimeProfile | null;
  onClose: () => void;
}) {
  const upsert = useUpsertOvertimeProfile();
  const upsertGlobal = useUpsertGlobalOvertimeProfile();
  const isGlobal = target?.scope === "global";
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [autoApprove, setAutoApprove] = useState(initial?.auto_approve ?? false);
  const [mode, setMode] = useState<"derived" | "fixed_rate">(initial?.mode ?? "derived");
  const [multiplier, setMultiplier] = useState(initial?.multiplier != null ? String(initial.multiplier) : "1.5");
  const [fixedRate, setFixedRate] = useState(
    initial?.fixed_rate_per_hour != null ? String(initial.fixed_rate_per_hour) : ""
  );
  const [minMinutes, setMinMinutes] = useState(String(initial?.min_minutes ?? 15));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!target) return;
    if (mode === "derived" && !multiplier) {
      toast.error("Koeffitsient kiriting (masalan 1.5)");
      return;
    }
    if (mode === "fixed_rate" && !fixedRate) {
      toast.error("So'm/soat kiriting");
      return;
    }
    const data = {
      enabled,
      auto_approve: autoApprove,
      mode,
      multiplier: mode === "derived" ? Number(multiplier) : null,
      fixed_rate_per_hour: mode === "fixed_rate" ? Number(fixedRate) : null,
      norm_hours_source: "schedule" as const,
      min_minutes: Number(minMinutes) || 0,
    };
    const ok = { onSuccess: () => { toast.success("Profil saqlandi"); onClose(); } };
    if (target.scope === "global") upsertGlobal.mutate(data, ok);
    else upsert.mutate({ userId: target.userId, data }, ok);
  };

  return (
    <Dialog open={target !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isGlobal ? "Hamma uchun qo'shimcha ish" : "Qo'shimcha ish profili (istisno)"}
          </DialogTitle>
          <DialogDescription>
            {isGlobal
              ? "Bu sozlama BARCHA xodimga amal qiladi — yangi ishga kirganlar ham avtomatik qamrab olinadi."
              : "Bu xodimga alohida qoida. Kiritilsa, hamma uchun sozlamadan USTUN turadi."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Yoqilgan
          </label>

          {/* Tasdiq bosqichi ATAYLAB saqlanadi (tasdiqsiz pul payslip'ga
              kirmasin), lekin HR xohlasa uni avtomatlashtira oladi. */}
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={autoApprove}
              onChange={(e) => setAutoApprove(e.target.checked)}
            />
            <span>
              Avtomatik tasdiqlansin
              <span className="block text-xs text-slate-500">
                Yoqilmasa har kunlik farq «kutilmoqda» bo'lib turadi va tasdiqlanmaguncha
                oylikka KIRMAYDI.
              </span>
            </span>
          </label>

          <div>
            <Label>Hisoblash rejimi</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as "derived" | "fixed_rate")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="derived">O'z oyligidan (soatlik = oylik ÷ norma soat)</SelectItem>
                <SelectItem value="fixed_rate">Qat'iy summa (so'm/soat)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {mode === "derived" ? (
            <div>
              <Label htmlFor="ot-mult">Koeffitsient (masalan 1.5)</Label>
              <Input
                id="ot-mult"
                type="number"
                step="0.1"
                min={0.1}
                value={multiplier}
                onChange={(e) => setMultiplier(e.target.value)}
                required
              />
            </div>
          ) : (
            <div>
              <Label htmlFor="ot-rate">So'm/soat</Label>
              <Input
                id="ot-rate"
                type="number"
                min={1}
                value={fixedRate}
                onChange={(e) => setFixedRate(e.target.value)}
                required
              />
            </div>
          )}

          <div>
            <Label htmlFor="ot-min">Minimal daqiqa (kamrog'i hisoblanmaydi)</Label>
            <Input
              id="ot-min"
              type="number"
              min={0}
              value={minMinutes}
              onChange={(e) => setMinMinutes(e.target.value)}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Bekor qilish
            </Button>
            <Button type="submit" disabled={upsert.isPending || upsertGlobal.isPending}>
              {upsert.isPending || upsertGlobal.isPending ? "Saqlanmoqda..." : "Saqlash"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function OvertimeProfileTab() {
  const profilesQuery = useOvertimeProfiles();
  const usersQuery = useUsers();
  const [editing, setEditing] = useState<
    { scope: "global" } | { scope: "user"; userId: number } | null
  >(null);
  const [addUserId, setAddUserId] = useState<number | null>(null);

  const rows = profilesQuery.data ?? [];
  // §3.2: profil endi IKKI DARAJALI. Global qator — barchaga default,
  // xodim qatorlari esa istisno. Ilgari faqat ikkinchisi bor edi va
  // `enabled` default o'chiq bo'lgani uchun jonli bazada yoqilgan profil
  // 0 ta edi — ya'ni qo'shimcha ish umuman hisoblanmasdi.
  const globalProfile = rows.find((p) => p.scope === "global") ?? null;
  const userProfiles = rows.filter((p) => p.scope !== "global");

  const profiledIds = new Set(userProfiles.map((p) => p.user_id));
  const addableUsers = (usersQuery.data ?? []).filter((u) => !profiledIds.has(u.id));

  const columns: ColumnDef<OvertimeProfile>[] = [
    { accessorKey: "user_full_name", header: "Xodim" },
    {
      accessorKey: "enabled",
      header: "Holat",
      cell: ({ row }) =>
        row.original.enabled ? (
          <span className="text-emerald-600">Yoqilgan</span>
        ) : (
          <span className="text-slate-400">O'chirilgan</span>
        ),
    },
    {
      accessorKey: "mode",
      header: "Rejim",
      cell: ({ row }) =>
        row.original.mode === "derived"
          ? `O'z oyligidan × ${row.original.multiplier ?? "?"}`
          : `${fmtMoney(row.original.fixed_rate_per_hour ?? 0)}/soat`,
    },
    {
      accessorKey: "auto_approve",
      header: "Tasdiq",
      cell: ({ row }) =>
        row.original.auto_approve ? (
          <span className="text-emerald-600">Avtomatik</span>
        ) : (
          <span className="text-slate-500">Qo'lda</span>
        ),
    },
    { accessorKey: "min_minutes", header: "Min. daqiqa" },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            row.original.user_id != null &&
            setEditing({ scope: "user", userId: row.original.user_id })
          }
        >
          <Pencil className="mr-1 h-3.5 w-3.5" />
          Tahrirlash
        </Button>
      ),
    },
  ];

  const editingProfile =
    editing === null
      ? null
      : editing.scope === "global"
        ? globalProfile
        : (userProfiles.find((p) => p.user_id === editing.userId) ?? null);

  return (
    <div className="space-y-4">
      {/* ── Hamma uchun default ── */}
      <div
        className={`rounded-xl border p-4 ${
          globalProfile?.enabled
            ? "border-emerald-200 bg-emerald-50"
            : "border-amber-200 bg-amber-50"
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium">
              {globalProfile?.enabled
                ? "Qo'shimcha ish HAMMA uchun yoqilgan"
                : "Qo'shimcha ish hali hech kimga yoqilmagan"}
            </div>
            <p className="mt-1 max-w-2xl text-xs text-slate-600">
              {globalProfile?.enabled ? (
                <>
                  Har kuni ishlangan vaqt reja bilan solishtiriladi; ortiqcha va kam vaqt oy
                  bo'yicha <b>qo'shilib-ayirilib</b> bitta summaga aylanadi.{" "}
                  {globalProfile.mode === "derived"
                    ? `Soatlik stavka = oylik ÷ norma soat × ${globalProfile.multiplier ?? "?"}.`
                    : `${fmtMoney(globalProfile.fixed_rate_per_hour ?? 0)}/soat.`}{" "}
                  {globalProfile.auto_approve
                    ? "Yozuvlar avtomatik tasdiqlanadi."
                    : "Yozuvlar tasdiqlanmaguncha oylikka kirmaydi."}
                </>
              ) : (
                <>
                  Shu sababli oylik hisobida qo'shimcha ish <b>doim 0</b> chiqadi. Bir marta
                  yoqing — yangi ishga kirgan xodimlar ham avtomatik qamrab olinadi.
                </>
              )}
            </p>
          </div>
          <Button size="sm" onClick={() => setEditing({ scope: "global" })}>
            {globalProfile ? "O'zgartirish" : "Hammaga yoqish"}
          </Button>
        </div>
      </div>

      {/* ── Istisnolar ── */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-600">
          Alohida qoidalar
          <span className="ml-2 font-normal text-xs text-slate-500">
            — faqat umumiy sozlamadan farq qiladigan xodimlar uchun
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={addUserId ? String(addUserId) : undefined}
            onValueChange={(v) => setAddUserId(Number(v))}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Xodim tanlang..." />
            </SelectTrigger>
            <SelectContent>
              {addableUsers.map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            disabled={!addUserId}
            onClick={() => {
              if (addUserId) setEditing({ scope: "user", userId: addUserId });
              setAddUserId(null);
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            Qo'shish
          </Button>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={userProfiles}
        isLoading={profilesQuery.isLoading}
        error={profilesQuery.error ? profilesQuery.error.message : null}
        onRetry={() => profilesQuery.refetch()}
        empty={{ text: "Istisno yo'q — hammaga umumiy sozlama amal qiladi." }}
      />
      <OvertimeProfileDialog
        target={editing}
        initial={editingProfile}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}


/**
 * Kechikish normasi huquqini boshqarish — FAQAT Boshliq/Dasturchi ko'radi.
 * Egasining qarori: "balkim hr o'zgartira olar balkim rop, uni kimgadir
 * biriktirish funksiyasini dasturchi yoki boss hal qiladi".
 */
function FinePolicyEditorsCard() {
  const usersQuery = useUsers();
  const editorsQuery = useFinePolicyEditors();
  const setEditor = useSetFinePolicyEditor();
  const [userId, setUserId] = useState<string>("");
  const [reason, setReason] = useState("");
  const [granted, setGranted] = useState(true);

  function submit() {
    if (!userId) return toast.error("Xodimni tanlang");
    if (reason.trim().length < 5) return toast.error("Sabab kamida 5 belgi");
    setEditor.mutate(
      { userId: Number(userId), granted, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success(granted ? "Huquq berildi" : "Huquq olindi");
          setReason("");
        },
      }
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Kechikish normasini o'zgartirish huquqi</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-slate-500">
          Tanlangan odam <b>faqat jarima qoidasini</b> o'zgartira oladi — oylik hisoblash,
          tasdiqlash va stavkalar unga ochilmaydi. HR/Boshliq/Dasturchida bu huquq roli
          bo'yicha allaqachon bor.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label>Xodim</Label>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger className="min-w-[220px]">
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(usersQuery.data ?? [])
                  .filter((u) => !["hr", "boss", "dasturchi"].includes(u.role))
                  .map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.full_name} ({u.role}){u.can_edit_fine_policy ? " — huquqi bor" : ""}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[220px] flex-1">
            <Label>Sabab</Label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nima uchun (kamida 5 belgi)"
            />
          </div>
          <Button onClick={() => { setGranted(true); submit(); }} disabled={setEditor.isPending}>
            Berish
          </Button>
          <Button
            variant="outline"
            onClick={() => { setGranted(false); submit(); }}
            disabled={setEditor.isPending}
          >
            Olib qo'yish
          </Button>
        </div>

        <div className="rounded-lg border border-slate-200 p-3">
          <div className="mb-1 text-xs font-medium text-slate-500">Hozir huquqi borlar</div>
          {editorsQuery.isLoading ? (
            <div className="text-xs text-slate-400">Yuklanmoqda...</div>
          ) : (editorsQuery.data ?? []).length === 0 ? (
            <div className="text-xs text-slate-400">Hech kimga berilmagan.</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {(editorsQuery.data ?? []).map((e) => (
                <li key={e.id}>
                  {e.full_name} <span className="text-xs text-slate-400">({e.role})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function PayrollSettings() {
  const { user } = useAuth();
  // Roli bo'yicha to'liq payroll boshqaruvchisi — u stavka/qo'shimcha ish
  // tablarini ham ko'radi. Faqat `can_edit_fine_policy` bayrog'i bilan
  // kirgan odamga ular KO'RSATILMAYDI: backend baribir 403 beradi, tab
  // ochilsa xodim "nega ishlamayapti?" degan holatga tushardi.
  const isPayrollManager = ["hr", "boss", "dasturchi"].includes(user?.role ?? "");
  const canGrant = ["boss", "dasturchi"].includes(user?.role ?? "");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ish haqi sozlamalari"
        description={
          isPayrollManager
            ? "Jarima qoidasi va qo'shimcha ish profillari. Oylik/KPI stavkalari «Ish haqi» sahifasiga ko'chirildi."
            : "Sizga kechikish/jarima qoidasini o'zgartirish huquqi berilgan."
        }
      />
      <Tabs defaultValue="policy">
        <TabsList>
          <TabsTrigger value="policy">Jarima qoidasi</TabsTrigger>
          {isPayrollManager && <TabsTrigger value="overtime">Qo'shimcha ish</TabsTrigger>}
        </TabsList>
        <TabsContent value="policy">
          <div className="space-y-6">
            <FinePolicyTab />
            {canGrant && <FinePolicyEditorsCard />}
          </div>
        </TabsContent>
        {isPayrollManager && (
          <TabsContent value="overtime">
            <OvertimeProfileTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
