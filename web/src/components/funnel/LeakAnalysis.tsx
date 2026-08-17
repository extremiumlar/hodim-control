/**
 * Bo'g'in tahlili va «agar ...» stsenariylari (voronka 7-bosqich, 1-2 band).
 *
 * Ikki savol: qayerda qancha yo'qolyapti (o'tmish) va bitta narsani
 * o'zgartirsak nima bo'ladi (kelajak). Ma'lumot yetmasa — «hisoblanmadi»
 * va nima yetishmayotgani aytiladi, taxminiy raqam o'ylab topilmaydi.
 */
import { TrendingDown, Wand2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtMoney } from "@/lib/utils";
import { useFunnelAnalysis } from "@/lib/queries";

const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("ru-RU").replace(/,/g, " ");

const SRC_LABEL: Record<string, string> = {
  measured: "o'lchangan",
  override: "qo'lda",
  default: "taxminiy",
};

export default function LeakAnalysis({ period }: { period: string }) {
  const q = useFunnelAnalysis(period);
  const leaks = q.data?.leaks;
  const sc = q.data?.scenarios;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <TrendingDown className="size-4" /> Qayerda yo'qotyapmiz — va nima qilsak o'zgaradi
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {q.isLoading && !q.data ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <>
            {leaks && (
              <div>
                <div className="mb-1.5 text-sm text-muted-foreground">
                  Shu oyda kelgan <b>{fmt(leaks.total_leads)}</b> lid qayerda tushib qoldi
                  {leaks.mature === false && (
                    <Badge variant="secondary" className="ml-2 border-0 text-xs">
                      kogorta hali to'liq emas
                    </Badge>
                  )}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs uppercase text-muted-foreground">
                        <th className="py-2 text-left font-medium">Bo'g'in</th>
                        <th className="py-2 text-right font-medium">Kirdi</th>
                        <th className="py-2 text-right font-medium">O'tdi</th>
                        <th className="py-2 text-right font-medium">Yo'qoldi</th>
                        <th className="py-2 text-right font-medium">~Shartnoma</th>
                        <th className="py-2 text-right font-medium">Reklama puli</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaks.steps.map((s) => {
                        const worst = leaks.biggest_leak?.label === s.label;
                        return (
                          <tr
                            key={s.label}
                            className={`border-b last:border-0 ${
                              worst ? "bg-amber-50 dark:bg-amber-950/30" : ""
                            }`}
                          >
                            <td className="py-1.5">
                              {s.label}
                              {worst && (
                                <Badge className="ml-2 border-0 bg-amber-200 text-amber-900">
                                  eng katta
                                </Badge>
                              )}
                            </td>
                            <td className="py-1.5 text-right font-mono">{fmt(s.entered)}</td>
                            <td className="py-1.5 text-right font-mono">{fmt(s.passed)}</td>
                            <td className="py-1.5 text-right font-mono font-semibold">
                              {fmt(s.lost)}
                              {s.loss_pct !== null && (
                                <span className="ml-1 text-xs text-muted-foreground">
                                  ({s.loss_pct}%)
                                </span>
                              )}
                            </td>
                            <td className="py-1.5 text-right font-mono text-muted-foreground">
                              {s.contracts_lost === null ? "—" : `~${s.contracts_lost}`}
                            </td>
                            <td className="py-1.5 text-right font-mono">
                              {s.money_lost === null ? "—" : fmtMoney(s.money_lost)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {leaks.cpl === null && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Reklama puli ustuni bo'sh — CPL o'lchanmagan. Xarajat kiritilsa, har bir
                    yo'qolgan lid qancha pulga tushgani ko'rinadi.
                  </p>
                )}
                <p className="mt-1 text-xs text-muted-foreground">{leaks.note}</p>
              </div>
            )}

            {sc && (
              <div className="border-t pt-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                  <Wand2 className="size-4" /> Agar…
                </div>
                <div className="space-y-2">
                  {sc.scenarios.map((s) => (
                    <div
                      key={s.key}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
                    >
                      <div>
                        <span className="font-medium">{s.label}</span>
                        {s.detail && (
                          <span className="ml-2 text-muted-foreground">{s.detail}</span>
                        )}
                        {s.sources?.filter(Boolean).map((src, i) => (
                          <Badge
                            key={`${s.key}-${i}`}
                            variant="secondary"
                            className={`ml-1 border-0 text-xs ${
                              src === "default" ? "bg-red-100 text-red-800" : ""
                            }`}
                          >
                            {SRC_LABEL[src] ?? src}
                          </Badge>
                        ))}
                      </div>
                      <div className="font-mono text-sm">
                        {s.extra_contracts === null ? (
                          <span className="text-muted-foreground">
                            hisoblanmadi
                            {s.missing?.length ? ` (${s.missing.join(", ")} yo'q)` : ""}
                          </span>
                        ) : (
                          <span className="font-semibold text-emerald-700">
                            +{s.extra_contracts} uy
                            {s.budget_saved
                              ? ` · ${fmtMoney(s.budget_saved)} so'm tejaladi`
                              : ""}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
