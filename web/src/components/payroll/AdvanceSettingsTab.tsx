/**
 * Avans sozlamalari — uch darajali qamrov (Avans TZ B-01 / B-02).
 *
 * NEGA ALOHIDA TAB: bu qiymatlar xodim qancha pul ola olishini belgilaydi
 * va ular jarima qoidasiga hech qanday aloqasi yo'q. A blokda ikkita
 * sozlama vaqtincha «Ushlanma qoidasi» formasining ichida turgan edi —
 * u yerda ular begona ko'rinardi va topilmasdi.
 *
 * QAMROV: xodim > lavozim > global. Global qator YETARLI — qolgan ikkisi
 * faqat istisno kerak bo'lganda (masalan bir lavozimga kattaroq
 * koeffitsient). Qamrov o'chirilsa xodim/lavozim kengroq darajaga qaytadi.
 */
import { useState, type FormEvent } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import ConfirmDialog from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
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
import { type AdvanceSettings, type AdvanceSettingsInput } from "@/lib/api";
import {
  useAdvanceSettings,
  useDeleteAdvanceSettings,
  usePositions,
  useUpsertAdvanceSettings,
  useUsers,
} from "@/lib/queries";
import { fmtMoney } from "@/lib/utils";

const BO_SH: AdvanceSettingsInput = {
  scope: "global",
  scope_id: null,
  advance_day: 20,
  coefficient: 0.5,
  cap_percent: 50,
  min_amount: null,
  reminder_time: "14:00",
  pending_on_close: "carry",
  reason_required: false,
  is_active: true,
  effective_from: null,
};

const SCOPE_LABEL: Record<string, string> = {
  global: "Hamma uchun",
  position: "Lavozim",
  user: "Xodim",
};

export default function AdvanceSettingsTab() {
  const listQuery = useAdvanceSettings();
  const positions = usePositions();
  const users = useUsers();
  const upsert = useUpsertAdvanceSettings();
  const remove = useDeleteAdvanceSettings();

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<AdvanceSettingsInput>(BO_SH);
  const [toDelete, setToDelete] = useState<AdvanceSettings | null>(null);

  const rows = listQuery.data ?? [];
  const hasGlobal = rows.some((r) => r.scope === "global" && r.is_active);

  const openNew = () => {
    // Global hali yo'q bo'lsa — birinchi navbatda O'SHA kerak, chunki
    // usiz `resolve_advance_settings` hech kimga qoida topmaydi.
    setDraft({ ...BO_SH, scope: hasGlobal ? "position" : "global" });
    setOpen(true);
  };

  const openEdit = (row: AdvanceSettings) => {
    setDraft({
      scope: row.scope,
      scope_id: row.scope_id,
      advance_day: row.advance_day,
      coefficient: row.coefficient,
      cap_percent: row.cap_percent,
      min_amount: row.min_amount,
      reminder_time: row.reminder_time,
      pending_on_close: row.pending_on_close,
      reason_required: row.reason_required,
      is_active: row.is_active,
      effective_from: row.effective_from,
    });
    setOpen(true);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.scope !== "global" && !draft.scope_id) {
      toast.error(draft.scope === "position" ? "Lavozimni tanlang" : "Xodimni tanlang");
      return;
    }
    upsert.mutate(
      { ...draft, scope_id: draft.scope === "global" ? null : draft.scope_id },
      {
        onSuccess: () => {
          toast.success("Avans sozlamasi saqlandi");
          setOpen(false);
        },
      }
    );
  };

  return (
    <div className="space-y-4">
      {!hasGlobal && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <b>Umumiy sozlama yo'q.</b> Shu holatda bot avans kuni xabarini{" "}
          <b>umuman yubormaydi</b>, chegara esa sukut bo'yicha qiymatlar bilan hisoblanadi
          (koeffitsient 0.5, yuqori chegara 50%). HR qo'lda kiritish yo'li ishlayveradi.
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-base">Avans qoidalari</CardTitle>
          <Button size="sm" onClick={openNew}>
            <Plus className="mr-1 h-4 w-4" />
            Qo'shish
          </Button>
        </CardHeader>
        <CardContent>
          {listQuery.isLoading && <div className="text-sm text-slate-500">Yuklanmoqda…</div>}
          {!listQuery.isLoading && rows.length === 0 && (
            <div className="text-sm text-slate-500">Hali birorta qoida kiritilmagan.</div>
          )}
          <div className="space-y-2">
            {rows.map((r) => (
              <div
                key={r.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 p-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <b className="text-sm">{SCOPE_LABEL[r.scope] ?? r.scope}</b>
                    {r.scope_name && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
                        {r.scope_name}
                      </span>
                    )}
                    {!r.is_active && (
                      <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600">
                        o'chirilgan
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    Har oyning {r.advance_day}-kuni, soat {r.reminder_time} · koeffitsient{" "}
                    {r.coefficient} · yuqori chegara {r.cap_percent}%
                    {r.min_amount != null && ` · eng kam ${fmtMoney(r.min_amount)}`}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-500">
                    Oy yopilganda:{" "}
                    {r.pending_on_close === "carry" ? "keyingi oyga o'tadi" : "bekor bo'ladi"} ·
                    sabab {r.reason_required ? "majburiy" : "ixtiyoriy"}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => openEdit(r)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-slate-400 hover:text-rose-600"
                    onClick={() => setToDelete(r)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Avans qoidasi</DialogTitle>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <div>
              <Label>Qamrov</Label>
              <Select
                value={draft.scope}
                onValueChange={(v) =>
                  setDraft((d) => ({ ...d, scope: v as AdvanceSettings["scope"], scope_id: null }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Hamma uchun</SelectItem>
                  <SelectItem value="position">Lavozim</SelectItem>
                  <SelectItem value="user">Xodim</SelectItem>
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-slate-500">
                Xodim &gt; lavozim &gt; hamma. Torroq qoida topilsa kengrog'i o'qilmaydi.
              </p>
            </div>

            {draft.scope !== "global" && (
              <div>
                <Label>{draft.scope === "position" ? "Lavozim" : "Xodim"}</Label>
                <Select
                  value={draft.scope_id ? String(draft.scope_id) : undefined}
                  onValueChange={(v) => setDraft((d) => ({ ...d, scope_id: Number(v) }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Tanlang" />
                  </SelectTrigger>
                  <SelectContent>
                    {(draft.scope === "position" ? positions.data ?? [] : users.data ?? []).map(
                      (x: { id: number; name?: string; full_name?: string }) => (
                        <SelectItem key={x.id} value={String(x.id)}>
                          {x.name ?? x.full_name}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="as-day">Avans kuni</Label>
                <Input
                  id="as-day"
                  type="number"
                  min={1}
                  max={28}
                  value={draft.advance_day}
                  onChange={(e) => setDraft((d) => ({ ...d, advance_day: Number(e.target.value) }))}
                />
                <p className="mt-1 text-xs text-slate-500">
                  Oyning shu kunidan boshlab xabar ketadi. 28 dan oshmaydi — fevralda
                  29–31-kun yo'q va xabar o'sha oyda umuman yuborilmasdi.
                </p>
              </div>
              <div>
                <Label htmlFor="as-time">Xabar soati</Label>
                <Input
                  id="as-time"
                  type="time"
                  value={draft.reminder_time}
                  onChange={(e) => setDraft((d) => ({ ...d, reminder_time: e.target.value }))}
                />
                <p className="mt-1 text-xs text-slate-500">Mahalliy vaqt (Toshkent).</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="as-coef">Koeffitsient</Label>
                <Input
                  id="as-coef"
                  type="number"
                  step="0.05"
                  min={0.05}
                  max={1}
                  value={draft.coefficient}
                  onChange={(e) => setDraft((d) => ({ ...d, coefficient: Number(e.target.value) }))}
                />
                <p className="mt-1 text-xs text-slate-500">
                  Shu kungacha ishlab bo'lingan pulning qancha qismi. 0.5 = yarmi.
                </p>
              </div>
              <div>
                <Label htmlFor="as-cap">Yuqori chegara (%)</Label>
                <Input
                  id="as-cap"
                  type="number"
                  min={1}
                  max={100}
                  value={draft.cap_percent}
                  onChange={(e) => setDraft((d) => ({ ...d, cap_percent: Number(e.target.value) }))}
                />
                <p className="mt-1 text-xs text-slate-500">
                  Koeffitsient qancha bo'lishidan qat'i nazar oylikning shu foizidan oshmaydi.
                </p>
              </div>
            </div>

            <div>
              <Label htmlFor="as-min">Eng kam summa (so'm)</Label>
              <Input
                id="as-min"
                type="number"
                min={0}
                value={draft.min_amount ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    min_amount: e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
                placeholder="masalan 200000"
              />
              <p className="mt-1 text-xs text-slate-500">
                Chegarasi shundan kam qolgan xodimga avans taklif qilinmaydi — mayda summa
                uchun butun oqimni ishga tushirishning ma'nosi yo'q. Bo'sh = cheklov yo'q.
              </p>
            </div>

            <div>
              <Label className="mb-1.5 block">Oy yopilganda tasdiqlanmagan avans</Label>
              <div className="space-y-1.5">
                {[
                  {
                    v: "carry",
                    t: "Keyingi oyga o'tadi",
                    d: "Tasdiq kutishda qoladi — pul so'ragan odam javobsiz qolmaydi.",
                  },
                  {
                    v: "cancel",
                    t: "Avtomatik bekor bo'ladi",
                    d: "Rad etiladi va xodimga sabab bilan xabar boradi.",
                  },
                ].map((o) => (
                  <label key={o.v} className="flex items-start gap-2.5">
                    <input
                      type="radio"
                      className="mt-0.5 h-4 w-4"
                      checked={draft.pending_on_close === o.v}
                      onChange={() =>
                        setDraft((d) => ({
                          ...d,
                          pending_on_close: o.v as AdvanceSettings["pending_on_close"],
                        }))
                      }
                    />
                    <span>
                      <span className="text-sm text-slate-800">{o.t}</span>
                      <span className="mt-0.5 block text-xs text-slate-600">{o.d}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <label className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4"
                checked={draft.reason_required}
                onChange={(e) => setDraft((d) => ({ ...d, reason_required: e.target.checked }))}
              />
              <span>
                <span className="text-sm font-medium text-slate-800">Sabab majburiy bo'lsin</span>
                <span className="mt-0.5 block text-xs text-slate-600">
                  Yoqilsa: kamida 5 belgi va ma'noli — «avans», «kerak», «pul» o'tmaydi.
                  O'chiq bo'lsa ixtiyoriy (botdagi tugmali oqim uchun shu qulay).
                </span>
              </span>
            </label>

            <label className="flex items-center gap-2.5">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={draft.is_active}
                onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
              />
              <span className="text-sm text-slate-800">Qoida faol</span>
            </label>

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Bekor qilish
              </Button>
              <Button type="submit" disabled={upsert.isPending}>
                {upsert.isPending ? "Saqlanmoqda…" : "Saqlash"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Qoidani o'chirish"
        description={
          toDelete
            ? `${SCOPE_LABEL[toDelete.scope] ?? toDelete.scope}${
                toDelete.scope_name ? ` — ${toDelete.scope_name}` : ""
              } qoidasi o'chiriladi. Shundan keyin kengroq darajadagi qoida amal qiladi.`
            : ""
        }
        confirmLabel="O'chirish"
        onConfirm={() => {
          if (!toDelete) return;
          remove.mutate(toDelete.id, {
            onSuccess: () => {
              toast.success("Qoida o'chirildi");
              setToDelete(null);
            },
          });
        }}
      />
    </div>
  );
}
