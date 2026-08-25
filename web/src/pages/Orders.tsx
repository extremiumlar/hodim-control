/**
 * «Buyruqlar reyestri» — HR (TZ 3.21 / S-50).
 *
 * ⚠️ TAHRIRLASH TUGMASI YO'Q va bo'lmaydi. Chiqarilgan buyruq —
 * imzolangan hujjat; xato bo'lsa u BEKOR QILINADI va bekor qilish
 * ham yangi buyruq bilan rasmiylashtiriladi. Backendda ham
 * `PUT`/`PATCH`/`DELETE` endpointlari yo'q.
 *
 * ⚠️ RAQAM QO'LDA KIRITILMAYDI — uni tizim beradi. Aks holda HR
 * tasodifan mavjud raqamni takrorlab qo'yardi.
 */
import { useState } from "react";
import { Ban, FileText } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCancelOrder, useOrders } from "@/lib/queries";

export default function Orders() {
  const { data, isLoading } = useOrders();
  const bekor = useCancelOrder();
  const [sabab, setSabab] = useState<Record<number, string>>({});

  return (
    <div className="space-y-4">
      <PageHeader title="Buyruqlar reyestri" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" />
            Reyestr
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : !data?.length ? (
            <p className="text-sm text-slate-600">Hali buyruq chiqarilmagan.</p>
          ) : (
            <div className="space-y-2 text-sm">
              {data.map((o) => (
                <div
                  key={o.id}
                  className={`rounded border px-3 py-2 ${
                    o.status === "cancelled" ? "bg-slate-50 text-slate-500" : ""
                  }`}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="min-w-0">
                      <b>№ {o.number}</b>
                      <span className="text-xs"> · {o.kind_label}</span>
                      {o.full_name && (
                        <span className="text-xs"> · {o.full_name}</span>
                      )}
                    </span>
                    <span className="shrink-0 text-xs">
                      {o.order_date}
                      {o.status === "cancelled" ? " · ❌ bekor qilingan" : ""}
                    </span>
                  </div>
                  {o.cancels_order_id && (
                    <div className="mt-0.5 text-xs">
                      Bekor qiladi: buyruq #{o.cancels_order_id}
                      {o.cancel_reason ? ` — ${o.cancel_reason}` : ""}
                    </div>
                  )}
                  {o.note && <div className="mt-0.5 text-xs">{o.note}</div>}

                  {o.status === "active" && o.kind !== "cancellation" && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Input
                        className="h-8 max-w-xs text-xs"
                        placeholder="Bekor qilish sababi"
                        value={sabab[o.id] ?? ""}
                        onChange={(e) =>
                          setSabab((s) => ({ ...s, [o.id]: e.target.value }))
                        }
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={bekor.isPending || !(sabab[o.id] ?? "").trim()}
                        onClick={() =>
                          bekor.mutate(
                            { id: o.id, reason: sabab[o.id] ?? "" },
                            {
                              onSuccess: (yangi) => {
                                toast.success(`Bekor qilindi — № ${yangi.number}`);
                                setSabab((s) => ({ ...s, [o.id]: "" }));
                              },
                            }
                          )
                        }
                      >
                        <Ban className="mr-1 h-3.5 w-3.5" />
                        Bekor qilish
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
