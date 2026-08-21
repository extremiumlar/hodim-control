/**
 * «Ma'lumotlarim» — xodim kabineti (TZ 3.26 / S-26).
 *
 * ⚠️ Bu forma bazani O'ZGARTIRMAYDI. Xodim so'rov yuboradi, HR
 * tasdiqlaydi, shundan keyin ma'lumot yangilanadi. Telefon va manzil
 * kadr hujjatlariga tushadi — xodim ularni o'zi o'zgartira olsa,
 * hujjatdagi va bazadagi ma'lumot mos kelmay qoladi.
 */
import { useState } from "react";
import { Clock, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useMyProfile,
  useMyProfileChanges,
  useProfileFields,
  useRequestProfileChange,
} from "@/lib/queries";

export default function MeProfile() {
  const { data: profile, isLoading } = useMyProfile();
  const { data: fields } = useProfileFields();
  const { data: myRequests } = useMyProfileChanges();
  const request = useRequestProfileChange();

  const [draft, setDraft] = useState<Record<string, string>>({});

  const joriy = (f: string): string =>
    ((profile as unknown as Record<string, string | null>)?.[f] ?? "") || "";

  async function yubor(field: string, label: string) {
    const qiymat = (draft[field] ?? "").trim();
    if (!qiymat) {
      toast.error("Yangi qiymatni kiriting");
      return;
    }
    await request.mutateAsync({ field, new_value: qiymat });
    toast.success(`«${label}» bo'yicha so'rov yuborildi — HR tasdiqlagach yangilanadi`);
    setDraft((d) => ({ ...d, [field]: "" }));
  }

  const kutilyapti = new Set(profile?.pending_fields ?? []);

  return (
    <div className="space-y-4">
      <PageHeader title="Ma'lumotlarim" />

      <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        O'zgartirish <b>darhol amalga oshmaydi</b>: so'rov HR ga boradi va u
        tasdiqlagach ma'lumot yangilanadi. Bu hujjatlardagi va bazadagi
        ma'lumot bir-biriga mos bo'lib turishi uchun.
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Shaxsiy ma'lumotlar</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(fields ?? []).map((f) => (
              <div key={f.value} className="flex flex-wrap items-end gap-2">
                <div className="min-w-[160px]">
                  <div className="mb-1 text-xs text-slate-600">{f.label}</div>
                  <div className="text-sm font-medium">{joriy(f.value) || "—"}</div>
                </div>
                {kutilyapti.has(f.value) ? (
                  <span className="flex items-center gap-1 pb-1 text-xs text-amber-800">
                    <Clock className="h-3.5 w-3.5" />
                    So'rov ko'rib chiqilmoqda
                  </span>
                ) : (
                  <>
                    <div className="min-w-[180px] flex-1">
                      <Input
                        value={draft[f.value] ?? ""}
                        placeholder="Yangi qiymat"
                        onChange={(e) =>
                          setDraft((d) => ({ ...d, [f.value]: e.target.value }))
                        }
                      />
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={request.isPending}
                      onClick={() => yubor(f.value, f.label)}
                    >
                      So'rov yuborish
                    </Button>
                  </>
                )}
                {f.sensitive && (
                  <span
                    className="flex items-center gap-1 pb-1 text-xs text-rose-700"
                    title="Bu maydon hujjatlarga ta'sir qiladi"
                  >
                    <ShieldAlert className="h-3.5 w-3.5" />
                    hujjatlarga ta'sir qiladi
                  </span>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {myRequests && myRequests.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">So'rovlarim</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {myRequests.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="min-w-[110px] font-medium">{r.field_label}</span>
                  <span className="text-xs text-slate-600">
                    {r.old_value || "—"} → {r.new_value}
                  </span>
                  <span
                    className={`ml-auto rounded px-1.5 py-0.5 text-xs ${
                      r.status === "approved"
                        ? "bg-emerald-100 text-emerald-800"
                        : r.status === "rejected"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-amber-100 text-amber-900"
                    }`}
                  >
                    {r.status === "approved"
                      ? "Tasdiqlandi"
                      : r.status === "rejected"
                        ? "Rad etildi"
                        : "Kutilmoqda"}
                  </span>
                  {r.decision_note && (
                    <span className="w-full text-xs text-slate-500">{r.decision_note}</span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
