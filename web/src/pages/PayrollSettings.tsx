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
  type SalaryRate,
} from "@/lib/api";
import {
  useCreateSalaryRate,
  useDeleteFinePolicy,
  useFinePolicies,
  useOvertimeProfiles,
  usePositions,
  useSalaryRates,
  useUpsertFinePolicy,
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
  fine_applies_to: "net_salary",
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
              <Label>Jarima qayerdan yechiladi</Label>
              <Select
                value={draft.fine_applies_to}
                onValueChange={(v) => setDraft((d) => ({ ...d, fine_applies_to: v as FinePolicyInput["fine_applies_to"] }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="net_salary">To'g'ridan-to'g'ri oylikdan</SelectItem>
                  <SelectItem value="bonus_first">Avval bonusdan</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

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
        row.original.fine_applies_to === "bonus_first" ? "Avval bonusdan" : "To'g'ridan-to'g'ri oylikdan",
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
// Tab 2: Oylik stavkalar
// ─────────────────────────────────────────────

function SalaryRateTab() {
  const usersQuery = useUsers();
  const [userId, setUserId] = useState<number | null>(null);
  const ratesQuery = useSalaryRates(userId ?? 0, userId !== null);
  const createRate = useCreateSalaryRate();

  const [amount, setAmount] = useState("");
  const [payBasis, setPayBasis] = useState("monthly");
  const [effectiveFrom, setEffectiveFrom] = useState(format(new Date(), "yyyy-MM-dd"));
  const [note, setNote] = useState("");

  const rateColumns: ColumnDef<SalaryRate>[] = [
    {
      accessorKey: "effective_from",
      header: "Kuchga kirgan",
      cell: ({ row }) => format(new Date(row.original.effective_from), "dd.MM.yyyy"),
    },
    { accessorKey: "amount", header: "Summa", cell: ({ row }) => fmtMoney(row.original.amount) },
    {
      accessorKey: "pay_basis",
      header: "Asos",
      cell: ({ row }) =>
        ({ monthly: "Oylik", daily: "Kunlik", hourly: "Soatlik" })[row.original.pay_basis] ??
        row.original.pay_basis,
    },
    { accessorKey: "note", header: "Izoh", cell: ({ row }) => row.original.note ?? "—" },
  ];

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
    createRate.mutate(
      { user_id: userId, amount: n, pay_basis: payBasis, effective_from: effectiveFrom, note: note || null },
      {
        onSuccess: () => {
          toast.success("Stavka qo'shildi");
          setAmount("");
          setNote("");
        },
      }
    );
  };

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <Card className="h-fit md:col-span-1">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yangi stavka</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <Label>Xodim</Label>
            <Select value={userId ? String(userId) : undefined} onValueChange={(v) => setUserId(Number(v))}>
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
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <Label htmlFor="sr-amount">Summa (so'm)</Label>
              <Input
                id="sr-amount"
                type="number"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
            <div>
              <Label>Hisob asosi</Label>
              <Select value={payBasis} onValueChange={setPayBasis}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Oylik (qat'iy)</SelectItem>
                  <SelectItem value="daily">Kunbay</SelectItem>
                  <SelectItem value="hourly">Soatbay</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="sr-date">Kuchga kirish sanasi</Label>
              <Input
                id="sr-date"
                type="date"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="sr-note">Izoh (ixtiyoriy)</Label>
              <Input id="sr-note" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <Button type="submit" disabled={createRate.isPending || !userId} className="w-full">
              {createRate.isPending ? "Saqlanmoqda..." : "Qo'shish"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="md:col-span-2">
        <h3 className="mb-2 font-semibold">Stavka tarixi</h3>
        {!userId ? (
          <p className="text-sm text-slate-500">Tarixni ko'rish uchun xodimni tanlang.</p>
        ) : (
          <DataTable
            columns={rateColumns}
            data={ratesQuery.data}
            isLoading={ratesQuery.isLoading}
            error={ratesQuery.error ? ratesQuery.error.message : null}
            onRetry={() => ratesQuery.refetch()}
            empty={{ text: "Bu xodim uchun hali stavka kiritilmagan." }}
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Tab 3: Qo'shimcha ish
// ─────────────────────────────────────────────

function OvertimeProfileDialog({
  userId,
  initial,
  onClose,
}: {
  userId: number | null;
  initial: OvertimeProfile | null;
  onClose: () => void;
}) {
  const upsert = useUpsertOvertimeProfile();
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [mode, setMode] = useState<"derived" | "fixed_rate">(initial?.mode ?? "derived");
  const [multiplier, setMultiplier] = useState(initial?.multiplier != null ? String(initial.multiplier) : "1.5");
  const [fixedRate, setFixedRate] = useState(
    initial?.fixed_rate_per_hour != null ? String(initial.fixed_rate_per_hour) : ""
  );
  const [minMinutes, setMinMinutes] = useState(String(initial?.min_minutes ?? 15));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!userId) return;
    if (mode === "derived" && !multiplier) {
      toast.error("Koeffitsient kiriting (masalan 1.5)");
      return;
    }
    if (mode === "fixed_rate" && !fixedRate) {
      toast.error("So'm/soat kiriting");
      return;
    }
    upsert.mutate(
      {
        userId,
        data: {
          enabled,
          mode,
          multiplier: mode === "derived" ? Number(multiplier) : null,
          fixed_rate_per_hour: mode === "fixed_rate" ? Number(fixedRate) : null,
          norm_hours_source: "schedule",
          min_minutes: Number(minMinutes) || 0,
        },
      },
      { onSuccess: () => { toast.success("Profil saqlandi"); onClose(); } }
    );
  };

  return (
    <Dialog open={userId !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Qo'shimcha ish profili</DialogTitle>
          <DialogDescription>Faqat shu xodimga yoqilgan bo'lsa qo'shimcha ish hisoblanadi.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Yoqilgan
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
            <Button type="submit" disabled={upsert.isPending}>
              {upsert.isPending ? "Saqlanmoqda..." : "Saqlash"}
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
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [addUserId, setAddUserId] = useState<number | null>(null);

  const profiledIds = new Set((profilesQuery.data ?? []).map((p) => p.user_id));
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
    { accessorKey: "min_minutes", header: "Min. daqiqa" },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Button variant="ghost" size="sm" onClick={() => setEditingUserId(row.original.user_id)}>
          <Pencil className="mr-1 h-3.5 w-3.5" />
          Tahrirlash
        </Button>
      ),
    },
  ];

  const editingProfile = profilesQuery.data?.find((p) => p.user_id === editingUserId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <Select value={addUserId ? String(addUserId) : undefined} onValueChange={(v) => setAddUserId(Number(v))}>
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
          disabled={!addUserId}
          onClick={() => {
            setEditingUserId(addUserId);
            setAddUserId(null);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Yoqish
        </Button>
      </div>
      <DataTable
        columns={columns}
        data={profilesQuery.data}
        isLoading={profilesQuery.isLoading}
        error={profilesQuery.error ? profilesQuery.error.message : null}
        onRetry={() => profilesQuery.refetch()}
        empty={{ text: "Hali hech kimga qo'shimcha ish yoqilmagan." }}
      />
      <OvertimeProfileDialog
        userId={editingUserId}
        initial={editingProfile}
        onClose={() => setEditingUserId(null)}
      />
    </div>
  );
}

export default function PayrollSettings() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Ish haqi sozlamalari"
        description="Jarima qoidasi, oylik stavkalar va qo'shimcha ish profillari."
      />
      <Tabs defaultValue="policy">
        <TabsList>
          <TabsTrigger value="policy">Jarima qoidasi</TabsTrigger>
          <TabsTrigger value="rates">Oylik stavkalar</TabsTrigger>
          <TabsTrigger value="overtime">Qo'shimcha ish</TabsTrigger>
        </TabsList>
        <TabsContent value="policy">
          <FinePolicyTab />
        </TabsContent>
        <TabsContent value="rates">
          <SalaryRateTab />
        </TabsContent>
        <TabsContent value="overtime">
          <OvertimeProfileTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
