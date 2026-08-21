/**
 * «Ma'lumot so'rovlari» — HR paneli (TZ 3.26 / S-26).
 *
 * Xodim so'rov yuboradi, HR shu yerda tasdiqlaydi va SHUNDAN KEYIN
 * baza o'zgaradi. Eski qiymat auditda qoladi.
 *
 * ⚠️ F.I.Sh. kabi maydonlar ogohlantirish bilan belgilanadi: ular
 * hujjatlarga ta'sir qiladi va tasdiqlashdan oldin hujjat so'rash
 * kerak bo'lishi mumkin.
 */
import { useState } from "react";
import { Check, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDecideProfileChange, useProfileChanges } from "@/lib/queries";

export default function ProfileChanges() {
  const [pendingOnly, setPendingOnly] = useState(true);
  const { data, isLoading } = useProfileChanges(pendingOnly);
  const decide = useDecideProfileChange();
  const [note, setNote] = useState<Record<number, string>>({});

  async function qaror(id: number, approve: boolean) {
    await decide.mutateAsync({ id, approve, note: note[id] || null });
    toast.success(approve ? "Tasdiqlandi va ma'lumot yangilandi" : "Rad etildi");
    setNote((n) => ({ ...n, [id]: "" }));
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Ma'lumot so'rovlari" />

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">
            {pendingOnly ? "Kutilayotgan so'rovlar" : "Barcha so'rovlar"}
          </CardTitle>
          <Button size="sm" variant="outline" onClick={() => setPendingOnly((v) => !v)}>
            {pendingOnly ? "Hammasini ko'rsatish" : "Faqat kutilayotganlar"}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              {pendingOnly ? "Kutilayotgan so'rov yo'q." : "So'rov yo'q."}
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((r) => (
                <li key={r.id} className="py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="min-w-[130px] font-medium">{r.user_name}</span>
                    <span className="min-w-[100px] text-xs text-slate-600">
                      {r.field_label}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="text-slate-500 line-through">
                        {r.old_value || "—"}
                      </span>
                      {" → "}
                      <b>{r.new_value}</b>
                    </span>
                    {r.sensitive && (
                      <span className="flex shrink-0 items-center gap-1 text-xs text-rose-700">
                        <ShieldAlert className="h-3.5 w-3.5" />
                        hujjatlarga ta'sir qiladi
                      </span>
                    )}
                    {r.status === "pending" ? (
                      <>
                        <Input
                          value={note[r.id] ?? ""}
                          placeholder="Izoh (ixtiyoriy)"
                          className="h-8 w-44 shrink-0 text-xs"
                          onChange={(e) =>
                            setNote((n) => ({ ...n, [r.id]: e.target.value }))
                          }
                        />
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 shrink-0"
                          title="Tasdiqlash"
                          disabled={decide.isPending}
                          onClick={() => qaror(r.id, true)}
                        >
                          <Check className="h-4 w-4 text-emerald-600" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 shrink-0"
                          title="Rad etish"
                          disabled={decide.isPending}
                          onClick={() => qaror(r.id, false)}
                        >
                          <X className="h-4 w-4 text-rose-600" />
                        </Button>
                      </>
                    ) : (
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${
                          r.status === "approved"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {r.status === "approved" ? "Tasdiqlangan" : "Rad etilgan"}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
