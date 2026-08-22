/**
 * «Mening o'rnim» — xodim kabineti (TZ 3.16 / S-40).
 *
 * ⚠️ MOBIL KO'RINISH (S-40 qabul mezoni): kichik ekranda butun
 * tashkiliy daraxtni chizib bo'lmaydi va xodimga u kerak ham emas —
 * unga O'Z ATROFI kerak: rahbarim → men → menga bo'ysunadiganlar.
 *
 * ⚠️ Bog'lanish `users.manager_id` bo'yicha, LAVOZIM ierarxiyasidan
 * alohida: bir lavozimda bir necha xodim bo'ladi va ular turli
 * rahbarlarga bo'ysunishi mumkin.
 */
import { ArrowDown, Network, User as UserIcon, Users } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgMyPlace } from "@/lib/queries";

export default function MyPlace() {
  const { data, isLoading } = useOrgMyPlace();

  return (
    <div className="space-y-4">
      <PageHeader title="Mening o'rnim" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Network className="h-4 w-4" />
            Tuzilmadagi o'rnim
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !data ? (
            <div className="text-sm text-slate-600">Ma'lumot yo'q.</div>
          ) : (
            <div className="space-y-2 text-sm">
              {/* ── Rahbarim ── */}
              {data.manager ? (
                <>
                  <div className="rounded border bg-slate-50 px-3 py-2">
                    <div className="text-xs text-slate-600">Rahbarim</div>
                    <div className="font-medium">{data.manager.full_name}</div>
                  </div>
                  <div className="flex justify-center">
                    <ArrowDown className="h-4 w-4 text-slate-400" />
                  </div>
                </>
              ) : (
                <div className="rounded border border-dashed px-3 py-2 text-xs text-slate-600">
                  Rahbaringiz belgilanmagan — HR ga ayting.
                </div>
              )}

              {/* ── Men ── */}
              <div className="rounded border-2 border-slate-800 px-3 py-2">
                <div className="flex items-center gap-1 text-xs text-slate-600">
                  <UserIcon className="h-3.5 w-3.5" />
                  Men
                </div>
                <div className="font-medium">{data.me.full_name}</div>
                <div className="text-xs text-slate-600">
                  {data.me.position ? data.me.position.name : "Lavozim belgilanmagan"}
                  {data.has_description && (
                    <span> · yo'riqnoma {data.description_version}-versiya</span>
                  )}
                </div>
              </div>

              {/* ── Menga bo'ysunadiganlar ── */}
              {!!data.subordinates.length && (
                <>
                  <div className="flex justify-center">
                    <ArrowDown className="h-4 w-4 text-slate-400" />
                  </div>
                  <div className="rounded border px-3 py-2">
                    <div className="mb-1 flex items-center gap-1 text-xs text-slate-600">
                      <Users className="h-3.5 w-3.5" />
                      Menga bo'ysunadiganlar ({data.subordinates.length})
                    </div>
                    <ul className="space-y-0.5">
                      {data.subordinates.map((u) => (
                        <li key={u.id}>{u.full_name}</li>
                      ))}
                    </ul>
                  </div>
                </>
              )}

              {!data.has_description && data.me.position && (
                <p className="text-xs text-amber-700">
                  ⚠️ Lavozimingiz uchun yo'riqnoma hali kiritilmagan.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
