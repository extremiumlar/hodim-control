/**
 * Operator kesimida konversiya — «kim yaxshi yopadi» (voronka 7-bosqich).
 *
 * MAVJUD STATISTIKADAN FARQI: u mehnat HAJMINI ko'rsatadi (nechta tashrif),
 * bu esa SIFATNI — «o'z lidining qanchasini aylantirdi». Ko'p ishlagan
 * xodim konversiyasi past bo'lishi mumkin va aksincha.
 */
import { Award, Users2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useFunnelOperators } from "@/lib/queries";

const pct = (v: number | null) => (v === null ? "—" : `${v}%`);
const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("ru-RU").replace(/,/g, " ");

export default function OperatorQuality({ month }: { month: string }) {
  const q = useFunnelOperators(month);
  const d = q.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users2 className="size-4" /> Kim yaxshi yopadi — operator kesimida konversiya
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {q.isLoading && !d ? (
          <Skeleton className="h-56 w-full" />
        ) : !d ? null : (
          <>
            <p className="text-sm text-muted-foreground">{d.note}</p>

            {(d.best_operator || d.worst_operator) && (
              <div className="flex flex-wrap gap-2">
                {d.best_operator && (
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm dark:bg-emerald-950/30">
                    <Award className="size-4 text-emerald-600" />
                    Eng yuqori: <b>{d.best_operator.full_name}</b> (
                    {pct(d.best_operator.lead_to_visit)})
                  </span>
                )}
                {d.worst_operator && (
                  <span className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm dark:bg-amber-950/30">
                    Eng past: <b>{d.worst_operator.full_name}</b> (
                    {pct(d.worst_operator.lead_to_visit)})
                  </span>
                )}
              </div>
            )}

            <div>
              <div className="mb-1.5 text-sm font-medium">
                Operator — lid → tashrif{" "}
                <span className="font-normal text-muted-foreground">
                  (o'zi olib kelgan lidlari bo'yicha)
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase text-muted-foreground">
                      <th className="py-2 text-left font-medium">Xodim</th>
                      <th className="py-2 text-right font-medium">Lid</th>
                      <th className="py-2 text-right font-medium">Tashrif</th>
                      <th className="py-2 text-right font-medium">Konversiya</th>
                      <th className="py-2 text-right font-medium">Suhbat / tashrif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.operators.map((r) => (
                      <tr key={r.responsible_id} className="border-b last:border-0">
                        <td className="py-1.5">
                          {r.full_name}
                          {!r.ranked && (
                            <Badge variant="secondary" className="ml-2 border-0 text-xs">
                              namuna kichik
                            </Badge>
                          )}
                        </td>
                        <td className="py-1.5 text-right font-mono">{fmt(r.leads)}</td>
                        <td className="py-1.5 text-right font-mono">{fmt(r.visits)}</td>
                        <td className="py-1.5 text-right font-mono font-semibold">
                          {pct(r.lead_to_visit)}
                        </td>
                        <td className="py-1.5 text-right font-mono text-muted-foreground">
                          {fmt(r.talks_per_visit)}
                        </td>
                      </tr>
                    ))}
                    {d.operators.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-3 text-muted-foreground">
                          Bu davrda lid yo'q.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <div className="mb-1.5 text-sm font-medium">
                Menejer — tashrif → shartnoma{" "}
                <span className="font-normal text-muted-foreground">
                  (o'zi qabul qilgan tashriflar bo'yicha)
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase text-muted-foreground">
                      <th className="py-2 text-left font-medium">Xodim</th>
                      <th className="py-2 text-right font-medium">Tashrif</th>
                      <th className="py-2 text-right font-medium">Shartnoma</th>
                      <th className="py-2 text-right font-medium">Konversiya</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.managers.map((r) => (
                      <tr key={r.responsible_id} className="border-b last:border-0">
                        <td className="py-1.5">
                          {r.full_name}
                          {!r.ranked && (
                            <Badge variant="secondary" className="ml-2 border-0 text-xs">
                              namuna kichik
                            </Badge>
                          )}
                        </td>
                        <td className="py-1.5 text-right font-mono">{fmt(r.visits)}</td>
                        <td className="py-1.5 text-right font-mono font-semibold">
                          {fmt(r.contracts)}
                        </td>
                        <td className="py-1.5 text-right font-mono">{pct(r.visit_to_contract)}</td>
                      </tr>
                    ))}
                    {d.managers.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-3 text-muted-foreground">
                          Bu davrda tashrif yo'q.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              «Namuna kichik» — {d.min_leads} liddan (menejerda {d.min_visits} tashrifdan) kam
              bo'lgan xodim: foizi tasodifga bog'liq, shuning uchun eng yaxshi/past tanlovida
              qatnashmaydi.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
