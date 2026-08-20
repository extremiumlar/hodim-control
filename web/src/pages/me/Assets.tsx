/**
 * «Menga biriktirilgan» — xodim kabineti (TZ 3.11 / S-19).
 *
 * ⚠️ «Qabul qildim» ni FAQAT xodimning o'zi bosadi va vaqt yoziladi.
 * Nizo chiqqanda «men buni olganim yo'q» degan da'voga javob shu yozuv
 * bo'ladi, shuning uchun HR boshqa birov nomidan tasdiqlay olmaydi.
 *
 * Tasdiqlash IDEMPOTENT: qayta bosilsa birinchi vaqt saqlanib qoladi.
 */
import { CheckCircle2, Package, ShieldQuestion } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAcceptAsset, useMyAssets } from "@/lib/queries";

function pul(n: number | null): string {
  return n === null ? "" : `${n.toLocaleString("ru-RU").replace(/ /g, " ")} so'm`;
}

export default function MeAssets() {
  const { data, isLoading } = useMyAssets();
  const accept = useAcceptAsset();

  const tasdiqlanmagan = (data ?? []).filter((a) => !a.accepted).length;

  return (
    <div className="space-y-4">
      <PageHeader title="Menga biriktirilgan" />

      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : !data?.length ? (
        <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
          <Package className="h-4 w-4 shrink-0" />
          Sizga hech qanday mol-mulk biriktirilmagan.
        </div>
      ) : (
        <>
          {tasdiqlanmagan > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <ShieldQuestion className="h-4 w-4 shrink-0" />
              <b>{tasdiqlanmagan} ta</b> buyumni hali tasdiqlamagansiz. Qo'lingizga
              olgan bo'lsangiz «Qabul qildim» ni bosing — bu sizni ham himoya
              qiladi.
            </div>
          )}
          <ul className="divide-y rounded-lg border">
            {data.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
                <Package className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="min-w-[140px] flex-1">
                  <span className="block truncate font-medium">{a.name}</span>
                  <span className="block text-xs text-slate-600">
                    {a.inventory_no} · {a.kind_label} · {a.condition_label}
                    {a.value ? ` · ${pul(a.value)}` : ""}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-xs text-slate-500">
                  {a.assigned_at}
                </span>
                {a.accepted ? (
                  <span className="flex shrink-0 items-center gap-1 text-xs text-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Qabul qilingan
                  </span>
                ) : (
                  <Button
                    size="sm"
                    className="shrink-0"
                    disabled={accept.isPending}
                    onClick={async () => {
                      await accept.mutateAsync(a.id);
                      toast.success(`«${a.name}» qabul qilindi`);
                    }}
                  >
                    Qabul qildim
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-500">
            Buyum sizdan qaytarib olinganda bu ro'yxatdan chiqadi. Nosozlik yoki
            yo'qotish bo'lsa darhol HR ga xabar bering.
          </p>
        </>
      )}
    </div>
  );
}
