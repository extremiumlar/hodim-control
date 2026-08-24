/**
 * «Instruktajlarim» — xodim kabineti (TZ 3.6 / S-48).
 *
 * ⚠️ QOG'OZ JURNAL OGOHLANTIRISHI EKRANDA KO'RSATILADI. TZ 3.6
 * qabul mezoni buni talab qiladi: tugma bosilishi qo'l qo'yish
 * o'rniga o'tmaydi. Faqat kod izohida qolsa, ekranda ishlaydigan
 * odam uni hech qachon ko'rmasdi.
 */
import { AlertTriangle, CheckCircle2, HardHat } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBriefingAck, useMyBriefings } from "@/lib/queries";

export default function MyBriefings() {
  const { data, isLoading } = useMyBriefings();
  const tanish = useBriefingAck();

  return (
    <div className="space-y-4">
      <PageHeader title="Instruktajlarim" />

      <div className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Bu qayd <b>qog'oz jurnal</b> o'rnini bosmaydi — instruktaj jurnaliga
          imzo qo'yish baribir shart.
        </span>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : !data?.length ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-slate-600">
            Sizga instruktaj tayinlanmagan.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {data.map((b) => (
            <Card key={b.id}>
              <CardContent className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    {b.acknowledged ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                    ) : (
                      <HardHat className="h-4 w-4 shrink-0 text-slate-500" />
                    )}
                    {b.title}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-600">
                    {b.kind_label} · {b.held_on}
                    {b.acknowledged && b.acknowledged_at
                      ? ` · tanishdingiz ${b.acknowledged_at.slice(0, 10)}`
                      : ""}
                  </div>
                  {b.note && (
                    <p className="mt-1 text-xs text-slate-600">{b.note}</p>
                  )}
                </div>
                {!b.acknowledged && (
                  <Button
                    size="sm"
                    className="shrink-0"
                    disabled={tanish.isPending}
                    onClick={() => tanish.mutate(b.id)}
                  >
                    ✅ Tanishdim
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
