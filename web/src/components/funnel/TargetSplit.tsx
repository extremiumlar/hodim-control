/**
 * Targetni xodimlarga tarqatish (voronka 5-bosqich).
 *
 * ⚠️ TAVSIYA — avtomatik qo'yilmaydi. Rahbar ko'radi, roziligini bildiradi,
 * shundagina norma yoziladi: bu raqam xodimning oylik KPI'siga bevosita
 * ta'sir qiladi, tizim uni jimgina o'zgartirmasligi kerak.
 */
import { UserCheck, Users } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplyTargetSplit, useTargetSplit } from "@/lib/queries";

export default function TargetSplit({
  period,
  canEdit,
}: {
  period: string;
  canEdit: boolean;
}) {
  const q = useTargetSplit(period);
  const apply = useApplyTargetSplit(period);
  const d = q.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="size-4" /> Targetni xodimlarga tarqatish
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.isLoading && !d ? (
          <Skeleton className="h-40 w-full" />
        ) : !d?.ready ? (
          <p className="rounded-md bg-muted p-3 text-sm">{d?.reason ?? "Ma'lumot yo'q"}</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Oylik raqam xodimlarning <b>ish kunlari</b> yig'indisiga bo'linadi — har kimga
              bir xil kunlik norma, lekin oylik ulush har xil (ta'til va dam kuni hisobga
              olinadi).
            </p>

            {d.groups.map((g) => (
              <div key={g.metric} className="rounded-lg border p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-medium">{g.label}</span>
                    {g.source === "default" && (
                      <Badge variant="secondary" className="ml-2 border-0 bg-red-100 text-red-800">
                        taxminiy farazdan
                      </Badge>
                    )}
                    <div className="text-xs text-muted-foreground">
                      Oylik maqsad: <b>{g.monthly_target ?? "—"}</b> · jami ish kuni:{" "}
                      {g.person_days} · kunlik norma:{" "}
                      <b>{g.suggested_daily ?? "—"}</b>
                    </div>
                  </div>
                  {canEdit && g.suggested_daily !== null && (
                    <Button
                      size="sm"
                      disabled={apply.isPending}
                      onClick={() =>
                        apply.mutate(
                          { period, metric: g.metric },
                          {
                            onSuccess: (r) =>
                              toast.success(
                                `${r.applied} ta xodimga norma qo'yildi` +
                                  (r.skipped_no_permission
                                    ? ` · ${r.skipped_no_permission} tasiga ruxsat yo'q`
                                    : "")
                              ),
                          }
                        )
                      }
                    >
                      <UserCheck className="mr-2 size-4" />
                      Tasdiqlab qo'yish
                    </Button>
                  )}
                </div>

                {g.problem ? (
                  <p className="rounded bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950/30">
                    {g.problem}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-xs uppercase text-muted-foreground">
                          <th className="py-1.5 text-left font-medium">Xodim</th>
                          <th className="py-1.5 text-right font-medium">Ish kuni</th>
                          <th className="py-1.5 text-right font-medium">Hozirgi</th>
                          <th className="py-1.5 text-right font-medium">Tavsiya (kunlik)</th>
                          <th className="py-1.5 text-right font-medium">Oyiga</th>
                        </tr>
                      </thead>
                      <tbody>
                        {g.employees.map((e) => (
                          <tr key={e.user_id} className="border-b last:border-0">
                            <td className="py-1.5">{e.full_name}</td>
                            <td className="py-1.5 text-right font-mono">{e.working_days}</td>
                            <td className="py-1.5 text-right font-mono text-muted-foreground">
                              {e.current_daily ?? "—"}
                            </td>
                            <td className="py-1.5 text-right font-mono font-semibold">
                              {e.suggested_daily}
                              {e.diff !== null && e.diff !== 0 && (
                                <span
                                  className={`ml-1 text-xs ${
                                    e.diff > 0 ? "text-amber-700" : "text-emerald-700"
                                  }`}
                                >
                                  ({e.diff > 0 ? "+" : ""}
                                  {e.diff})
                                </span>
                              )}
                            </td>
                            <td className="py-1.5 text-right font-mono">{e.month_total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}

            <p className="text-xs text-muted-foreground">
              «Tasdiqlab qo'yish» bosilgunicha hech kimning normasi o'zgarmaydi.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
