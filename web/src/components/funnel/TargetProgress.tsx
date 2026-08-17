/**
 * Reja va fakt kuzatuvi + prognoz (voronka 6-bosqich).
 *
 * Savol: «shu tempda oy oxirida nechta bo'ladi?» — javob oyning 10-kunida
 * kerak, 30-kunida emas. Temp ISH KUNI bo'yicha o'lchanadi (kalendar emas):
 * dam olishlar notekis taqsimlangani uchun kalendar foizi chalg'itadi.
 */
import { Activity, TrendingDown, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTargetProgress } from "@/lib/queries";

const STATUS: Record<string, { label: string; cls: string }> = {
  yaxshi: { label: "rejada", cls: "bg-emerald-100 text-emerald-800" },
  chegarada: { label: "chegarada", cls: "bg-amber-100 text-amber-900" },
  orqada: { label: "orqada", cls: "bg-red-100 text-red-800" },
  "noma'lum": { label: "reja yo'q", cls: "bg-slate-100 text-slate-600" },
};

const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("ru-RU").replace(/,/g, " ");

export default function TargetProgress({ period }: { period: string }) {
  const q = useTargetProgress(period);
  const d = q.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="size-4" /> Reja va fakt — oy oxiri prognozi
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.isLoading && !d ? (
          <Skeleton className="h-40 w-full" />
        ) : !d?.ready ? (
          <p className="rounded-md bg-muted p-3 text-sm">{d?.reason ?? "Ma'lumot yo'q"}</p>
        ) : (
          <>
            <div>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span>
                  Oyning <b>{Math.round(d.elapsed.share * 100)}%</b> {d.elapsed.basis}i o'tdi
                </span>
                <span className="font-mono text-xs text-muted-foreground">
                  {d.elapsed.days_passed} / {d.elapsed.days_total}
                </span>
              </div>
              {/* Oddiy progress chizig'i — loyihada `ui/progress` yo'q,
                  bitta karta uchun yangi bog'liqlik keltirish ortiqcha. */}
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${Math.min(100, Math.round(d.elapsed.share * 100))}%` }}
                />
              </div>
            </div>

            {!d.forecast_ready && (
              <p className="rounded-md bg-muted p-3 text-sm">
                Prognoz uchun hali erta — oyning kamida {Math.round(d.min_elapsed * 100)}% ish
                kuni o'tishi kerak. Kichik namunadan qilingan prognoz chalg'itadi.
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2 text-left font-medium">Bosqich</th>
                    <th className="py-2 text-right font-medium">Oylik reja</th>
                    <th className="py-2 text-right font-medium">Hozir kutilgan</th>
                    <th className="py-2 text-right font-medium">Haqiqiy</th>
                    <th className="py-2 text-right font-medium">Farq</th>
                    <th className="py-2 text-right font-medium">Prognoz</th>
                    <th className="py-2 text-right font-medium">Holat</th>
                  </tr>
                </thead>
                <tbody>
                  {d.rows.map((r) => {
                    const st = STATUS[r.status] ?? STATUS["noma'lum"];
                    return (
                      <tr key={r.key} className="border-b last:border-0">
                        <td className="py-1.5 font-medium">{r.label}</td>
                        <td className="py-1.5 text-right font-mono">{fmt(r.plan_month)}</td>
                        <td className="py-1.5 text-right font-mono text-muted-foreground">
                          {fmt(r.expected_now)}
                        </td>
                        <td className="py-1.5 text-right font-mono font-semibold">
                          {fmt(r.actual)}
                        </td>
                        <td
                          className={`py-1.5 text-right font-mono ${
                            r.diff === null ? "" : r.diff < 0 ? "text-red-700" : "text-emerald-700"
                          }`}
                        >
                          {r.diff === null ? "—" : `${r.diff > 0 ? "+" : ""}${fmt(r.diff)}`}
                        </td>
                        <td className="py-1.5 text-right font-mono">
                          {r.forecast === null ? (
                            "—"
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              {r.forecast_gap !== null &&
                                (r.forecast_gap >= 0 ? (
                                  <TrendingUp className="size-3.5 text-emerald-600" />
                                ) : (
                                  <TrendingDown className="size-3.5 text-red-600" />
                                ))}
                              {fmt(r.forecast)}
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 text-right">
                          <Badge variant="secondary" className={`${st.cls} border-0`}>
                            {st.label}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {d.weakest && (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/30">
                Eng ko'p orqada qolayotgan bo'g'in — <b>{d.weakest.label}</b>. Reja buzilayotgan
                bo'lsa avval shu yerni tekshiring.
              </p>
            )}

            <p className="text-xs text-muted-foreground">
              «Hozir kutilgan» — oylik reja × o'tgan ish kunlari ulushi. «Prognoz» — shu temp
              oy oxirigacha davom etsa qancha bo'lishi. Xuddi shu xulosa har kuni guruh
              hisobotiga ham qo'shiladi.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
