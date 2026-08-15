/**
 * KPI (bonus) stavkalari — 3 darajali va tarixiy.
 *
 * NEGA KERAK: ilgari stavkalar backend kodida konstanta edi
 * (`PLACEHOLDER_RATE_PER_CONVERSATION = 2000`), ya'ni HR ularni o'zgartira
 * olmasdi — har o'zgarish uchun dasturchi va deploy kerak edi. Mobilograf
 * video stavkasi esa 0 bo'lgani uchun uning KPI'si doim nol chiqardi.
 *
 * Naqsh `Oylik stavkalar` tabi bilan ATAYLAB bir xil: mavjud qator hech
 * qachon tahrirlanmaydi, faqat yangi `effective_from` bilan qator
 * qo'shiladi. Shu tufayli o'tgan oy bonusi qayta hisoblanganda ham
 * o'zgarmaydi.
 */
import { useMemo, useState } from "react";
import { format, startOfMonth } from "date-fns";
import { toast } from "sonner";

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
import { KPI_METRIC_LABELS, type KpiMetric, type KpiRate } from "@/lib/api";
import { useCreateKpiRate, useKpiRates, usePositions, useUsers } from "@/lib/queries";

const METRICS = Object.keys(KPI_METRIC_LABELS) as KpiMetric[];

const SCOPE_LABELS: Record<string, string> = {
  global: "Hamma uchun",
  position: "Lavozim",
  user: "Xodim",
};

function scopeText(r: KpiRate): string {
  if (r.scope === "global") return "Hamma uchun";
  return `${SCOPE_LABELS[r.scope]}: ${r.scope_label ?? `#${r.scope_id}`}`;
}

export default function KpiRateTab() {
  const ratesQuery = useKpiRates();
  const usersQuery = useUsers();
  const positionsQuery = usePositions();
  const create = useCreateKpiRate();

  const [scope, setScope] = useState<"global" | "position" | "user">("global");
  const [scopeId, setScopeId] = useState<string>("");
  const [metric, setMetric] = useState<KpiMetric>("suhbat");
  const [amount, setAmount] = useState("");
  // Default — JORIY OY BOSHI, bugungi kun EMAS.
  //
  // NEGA (§2.4): KPI bonusi stavkani OY BOSHIGA qarab aniqlaydi
  // (`bonus.py: resolve_kpi_rate(..., period_start)`). Default bugun bo'lsa,
  // HR 15-avgustda stavka kiritganda avgust uchun stavka TOPILMAYDI va
  // bonus 0 chiqadi — HR uchun bu «stavka kiritdim, lekin ishlamadi» bo'lib
  // ko'rinardi. Oy boshi esa shu oyning butun hisobiga qo'llanadi.
  const [effectiveFrom, setEffectiveFrom] = useState(format(startOfMonth(new Date()), "yyyy-MM-dd"));
  // Oy boshidan KEYINGI sana tanlansa — shu oy hisobiga kirmasligi haqida
  // ogohlantirish (jim qolish HRni chalkashtiradi).
  const kpiLateStart = effectiveFrom > format(startOfMonth(new Date()), "yyyy-MM-dd");
  const [note, setNote] = useState("");

  const rows = ratesQuery.data ?? [];

  // Ko'rsatkich bo'yicha guruhlab ko'rsatamiz — HR "suhbat qancha turadi"
  // degan savolga bitta joyda javob topsin.
  const grouped = useMemo(() => {
    const map = new Map<KpiMetric, KpiRate[]>();
    for (const r of rows) {
      const list = map.get(r.metric) ?? [];
      list.push(r);
      map.set(r.metric, list);
    }
    return map;
  }, [rows]);

  const targetMissing = scope !== "global" && !scopeId;
  const amountInvalid = amount === "" || Number(amount) < 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yangi KPI stavkasi</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-slate-500">
            Bitta ko'rsatkich birligi uchun necha so'm. Amaldagi stavka:{" "}
            <b>xodim → lavozim → hamma uchun</b> tartibida qidiriladi va sana bo'yicha
            eng so'nggisi olinadi. Mavjud stavka <b>tahrirlanmaydi</b> — yangi sana bilan
            yangi qator qo'shing, shunda o'tgan oylar bonusi buzilmaydi.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="kpi-scope">Kimga</Label>
              <Select
                value={scope}
                onValueChange={(v) => {
                  setScope(v as typeof scope);
                  setScopeId("");
                }}
              >
                <SelectTrigger id="kpi-scope">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Hamma uchun</SelectItem>
                  <SelectItem value="position">Lavozim</SelectItem>
                  <SelectItem value="user">Alohida xodim</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {scope !== "global" && (
              <div className="space-y-1.5">
                <Label htmlFor="kpi-target">
                  {scope === "position" ? "Lavozim" : "Xodim"}{" "}
                  <span className="text-rose-600">*</span>
                </Label>
                <Select value={scopeId} onValueChange={setScopeId}>
                  <SelectTrigger id="kpi-target">
                    <SelectValue placeholder="Tanlang..." />
                  </SelectTrigger>
                  <SelectContent>
                    {scope === "position"
                      ? (positionsQuery.data ?? []).map((p) => (
                          <SelectItem key={p.id} value={String(p.id)}>
                            {p.name}
                          </SelectItem>
                        ))
                      : (usersQuery.data ?? []).map((u) => (
                          <SelectItem key={u.id} value={String(u.id)}>
                            {u.full_name}
                          </SelectItem>
                        ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="kpi-metric">Ko'rsatkich</Label>
              <Select value={metric} onValueChange={(v) => setMetric(v as KpiMetric)}>
                <SelectTrigger id="kpi-metric">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {METRICS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {KPI_METRIC_LABELS[m]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kpi-amount">
                Bir dona uchun (so'm) <span className="text-rose-600">*</span>
              </Label>
              <Input
                id="kpi-amount"
                type="number"
                min={0}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="masalan: 5000"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kpi-from">Qaysi sanadan</Label>
              <Input
                id="kpi-from"
                type="date"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
              />
              {kpiLateStart ? (
                <p className="text-xs text-amber-700">
                  ⚠️ Bu stavka <b>shu oy bonusiga KIRMAYDI</b> — bonus oy boshidagi
                  stavkaga qarab hisoblanadi. Shu oyga qo'llanishi uchun oy boshini tanlang.
                </p>
              ) : (
                <p className="text-xs text-slate-500">
                  Odatda oy boshi qo'yiladi — shu oyning butun bonus hisobiga qo'llanadi.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="kpi-note">Izoh (ixtiyoriy)</Label>
              <Input
                id="kpi-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="masalan: 2026 yil indeksatsiyasi"
              />
            </div>
          </div>

          <Button
            size="sm"
            disabled={targetMissing || amountInvalid || create.isPending}
            onClick={() =>
              create.mutate(
                {
                  scope,
                  scope_id: scope === "global" ? null : Number(scopeId),
                  metric,
                  amount: Number(amount),
                  effective_from: effectiveFrom,
                  note: note.trim() || null,
                },
                {
                  onSuccess: () => {
                    toast.success("Stavka qo'shildi");
                    setAmount("");
                    setNote("");
                  },
                }
              )
            }
          >
            {create.isPending ? "Saqlanmoqda..." : "Qo'shish"}
          </Button>
        </CardContent>
      </Card>

      <div>
        <h3 className="mb-2 font-semibold">Amaldagi stavkalar va tarix</h3>
        {ratesQuery.isLoading ? (
          <div className="text-sm text-slate-400">Yuklanmoqda...</div>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
            Hali birorta stavka kiritilmagan — hozircha KPI bonusi <b>0</b> hisoblanadi.
            <br />
            Yuqoridagi shakldan birinchi stavkani qo'shing.
          </div>
        ) : (
          <div className="space-y-4">
            {METRICS.filter((m) => grouped.has(m)).map((m) => (
              <div key={m} className="rounded-lg border border-slate-200 bg-white">
                <div className="border-b border-slate-100 px-4 py-2 text-sm font-medium">
                  {KPI_METRIC_LABELS[m]}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs uppercase text-slate-500">
                        <th className="px-4 py-2 text-left font-normal">Kimga</th>
                        <th className="px-4 py-2 text-right font-normal">Stavka</th>
                        <th className="px-4 py-2 text-left font-normal">Sanadan</th>
                        <th className="px-4 py-2 text-left font-normal">Izoh</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(grouped.get(m) ?? []).map((r) => (
                        <tr key={r.id} className="border-t border-slate-100">
                          <td className="px-4 py-2">{scopeText(r)}</td>
                          <td className="px-4 py-2 text-right tabular-nums">
                            {r.amount.toLocaleString("ru-RU")}
                          </td>
                          <td className="px-4 py-2">
                            {format(new Date(r.effective_from), "dd.MM.yyyy")}
                          </td>
                          <td className="px-4 py-2 text-slate-500">{r.note ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
