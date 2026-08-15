/**
 * Teskari kalkulyator (voronka 4-bosqich) — «10 uy» dan kerakli raqamlar.
 *
 * MUHIM TAMOYIL: har bir farazning QAYERDAN kelgani ochiq ko'rsatiladi —
 * o'lchangan (measured), qo'lda kiritilgan (override) yoki zaxira taxmin
 * (default). Rejaning ishonchliligi shunga bog'liq va uni yashirish
 * «ishonchli ko'rinishdagi o'ylab topilgan raqam» degani bo'lardi.
 */
import { useEffect, useState } from "react";
import { Calculator, Info } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtMoney } from "@/lib/utils";
import { useFunnelTarget, useSaveFunnelTarget } from "@/lib/queries";

const SOURCE_LABELS: Record<string, { text: string; cls: string }> = {
  measured: { text: "o'lchangan", cls: "bg-emerald-100 text-emerald-800" },
  override: { text: "qo'lda", cls: "bg-amber-100 text-amber-900" },
  default: { text: "taxminiy", cls: "bg-red-100 text-red-800" },
};

const FIELDS: { key: string; label: string; unit: string; hint: string }[] = [
  { key: "lead_to_visit", label: "Lid → tashrif", unit: "%", hint: "lidning qanchasi ofisga keladi" },
  { key: "visit_to_contract", label: "Tashrif → shartnoma", unit: "%", hint: "tashrifning qanchasi sotuvga aylanadi" },
  { key: "talks_per_lead", label: "Lid boshiga suhbat", unit: "ta", hint: "bitta lid uchun nechta gaplashish" },
  { key: "pickup_rate", label: "Ko'tarish foizi", unit: "%", hint: "urinishning qanchasi javob beriladi" },
  { key: "cpl", label: "Lid narxi (CPL)", unit: "so'm", hint: "reklama xarajati ÷ lid" },
  { key: "reach_to_lead", label: "Qamrov → lid", unit: "%", hint: "reklamani ko'rganlarning qanchasi lid bo'ladi" },
];

const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("ru-RU").replace(/,/g, " ");

export default function TargetCalculator({
  period,
  canEdit,
}: {
  period: string;
  canEdit: boolean;
}) {
  const [target, setTarget] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const q = useFunnelTarget(period, target ? Number(target) : undefined);
  const save = useSaveFunnelTarget(period);
  const d = q.data;

  // Saqlangan maqsad birinchi yuklashda maydonga tushadi (foydalanuvchi
  // hali hech nima yozmagan bo'lsa).
  useEffect(() => {
    if (!target && d?.saved_target) setTarget(String(d.saved_target));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.saved_target]);

  const assumptions = d?.assumptions ?? {};

  const handleSave = () => {
    const overrides: Record<string, number> = {};
    for (const [k, v] of Object.entries(draft)) {
      if (v !== "" && !Number.isNaN(Number(v))) overrides[k] = Number(v);
    }
    save.mutate(
      {
        period,
        target_contracts: target ? Number(target) : null,
        assumptions: Object.keys(overrides).length ? overrides : null,
      },
      { onSuccess: () => toast.success("Maqsad saqlandi") }
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Calculator className="size-4" /> Teskari kalkulyator — maqsaddan rejaga
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="tg-target">Oylik maqsad — nechta uy?</Label>
            <Input
              id="tg-target"
              type="number"
              min={1}
              className="w-44"
              placeholder="masalan 10"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              disabled={!canEdit}
            />
          </div>
          {canEdit && (
            <Button onClick={handleSave} disabled={save.isPending}>
              {save.isPending ? "Saqlanmoqda…" : "Maqsadni saqlash"}
            </Button>
          )}
        </div>

        {q.isLoading && !d ? (
          <Skeleton className="h-56 w-full" />
        ) : !d || d.chain.length === 0 ? (
          <p className="rounded-md bg-muted p-3 text-sm">
            {d?.hint ?? "Maqsad kiriting — kerakli lid, suhbat va byudjet hisoblanadi."}
          </p>
        ) : (
          <>
            {d.baseline_confidence === "yo'q" && (
              <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                Hali birorta ham <b>yetilgan</b> oy o'lchanmagan — reja butunlay taxminiy
                farazlarga qurilgan. Raqamlarga ishonch past, konversiya o'lchangach qayta
                ko'ring.
              </p>
            )}

            <div className="space-y-1.5">
              {d.chain.map((c) => (
                <div
                  key={c.key}
                  className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-2.5 ${
                    c.key === "contracts"
                      ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30"
                      : "bg-card"
                  }`}
                >
                  <span className="text-sm font-medium">{c.label}</span>
                  <span className="font-mono text-sm font-bold tabular-nums">
                    {c.value === null ? (
                      <span className="text-muted-foreground">hisoblanmadi</span>
                    ) : (
                      fmt(c.value)
                    )}
                  </span>
                </div>
              ))}
            </div>

            {d.budget !== null && d.budget !== undefined && (
              <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:bg-amber-950/30">
                <div className="text-sm">Kerakli reklama byudjeti</div>
                <div className="font-mono text-xl font-bold">{fmtMoney(d.budget)} so'm</div>
              </div>
            )}

            {d.missing.length > 0 && (
              <p className="flex items-start gap-2 text-xs text-muted-foreground">
                <Info className="mt-0.5 size-3.5 shrink-0" />
                Hisoblanmagan qatorlar uchun quyidagi faraz yetishmayapti:{" "}
                <b>{d.missing.join(", ")}</b> — pastdagi maydonlarga kiriting yoki
                xarajat/qamrovni to'ldiring.
              </p>
            )}

            {d.sensitivity.length > 0 && (
              <div className="rounded-lg bg-muted p-3 text-sm">
                <div className="mb-1 font-medium">Nimani yaxshilash eng foydali</div>
                <ul className="space-y-1">
                  {d.sensitivity.map((s) => (
                    <li key={s.label}>
                      {s.label}: <b>{fmt(s.leads_saved)}</b> ta kam lid kerak
                      {s.budget_saved ? ` · ${fmtMoney(s.budget_saved)} so'm tejaladi` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="border-t pt-4">
              <div className="mb-2 text-sm font-medium">
                Farazlar{" "}
                <span className="font-normal text-muted-foreground">
                  (bo'sh qoldirilsa o'lchangan qiymat ishlatiladi)
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {FIELDS.map((f) => {
                  const a = assumptions[f.key];
                  const src = a?.source ? SOURCE_LABELS[a.source] : null;
                  return (
                    <div key={f.key}>
                      <Label htmlFor={`as-${f.key}`} className="flex items-center gap-2">
                        {f.label}
                        {src && (
                          <Badge variant="secondary" className={`${src.cls} border-0`}>
                            {src.text}
                          </Badge>
                        )}
                      </Label>
                      <Input
                        id={`as-${f.key}`}
                        type="number"
                        step="0.1"
                        min={0}
                        disabled={!canEdit}
                        placeholder={a?.value !== null && a?.value !== undefined ? `${a.value} ${f.unit}` : "yo'q"}
                        value={draft[f.key] ?? ""}
                        onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                      />
                      <p className="mt-0.5 text-xs text-muted-foreground">{f.hint}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
