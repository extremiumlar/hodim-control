/**
 * «Mening o'rnim» — xodim kabineti (TZ 3.16 / S-40, S-41).
 *
 * To'rt qism: tuzilmadagi o'rni · lavozim yo'riqnomasi + «Tanishdim» ·
 * kuzatiladigan ko'rsatkichlari · butun tuzilma sxemasi.
 *
 * ⚠️ MOBIL KO'RINISH (S-40 qabul mezoni): kichik ekranda butun
 * tashkiliy daraxtni chizib bo'lmaydi va xodimga birinchi navbatda u
 * kerak ham emas — unga O'Z ATROFI kerak: rahbarim → men → menga
 * bo'ysunadiganlar. Butun sxema pastda, yopiladigan bo'limda.
 *
 * ⚠️ Bog'lanish `users.manager_id` bo'yicha, LAVOZIM ierarxiyasidan
 * alohida: bir lavozimda bir necha xodim bo'ladi va ular turli
 * rahbarlarga bo'ysunishi mumkin.
 *
 * ⚠️ ISH HAQI VA BAHO BU SAHIFAGA HECH QACHON QO'SHILMAYDI (TZ 3.16
 * qabul mezoni: «tuzilma sxemasi hammaga ochiq — ish haqi va baho
 * yo'q»). Server ham ularni bermaydi.
 */
import { useState } from "react";
import { ArrowDown, CheckCircle2, ClipboardList, Network, User as UserIcon, Users } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { OrgNode } from "@/lib/api/types";
import { useOrgAcknowledge, useOrgChart, useOrgMyPlace } from "@/lib/queries";

/** Yo'riqnomaning bitta ro'yxat bo'limi. */
function Bolim({ sarlavha, bandlar }: { sarlavha: string; bandlar: string[] }) {
  if (!bandlar.length) return null;
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-slate-600">{sarlavha}</div>
      <ul className="list-disc space-y-0.5 pl-5">
        {bandlar.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Daraxt — ichma-ich `<ul>`.
 *
 * ⚠️ OG'IR SXEMA KUTUBXONASI OLINMADI (TZ: 20-30 tugun). Ichma-ich
 * ro'yxat kichik ekranda o'zidan o'zi o'qiladigan bo'lib qoladi,
 * ya'ni alohida mobil ko'rinish yozish shart emas.
 */
function Daraxt({ nodes, parentId }: { nodes: OrgNode[]; parentId: number | null }) {
  const bolalar = nodes.filter((n) => n.parent_id === parentId);
  if (!bolalar.length) return null;
  return (
    <ul className="space-y-1 border-l pl-4">
      {bolalar.map((n) => (
        <li key={n.id}>
          <span className="font-medium">{n.name}</span>
          <span className="text-xs text-slate-600">
            {" · "}
            {n.employees} xodim
            {n.units ? ` / ${n.units} o'rin` : ""}
          </span>
          <Daraxt nodes={nodes} parentId={n.id} />
        </li>
      ))}
    </ul>
  );
}

export default function MyPlace() {
  const { data, isLoading } = useOrgMyPlace();
  const [sxemaOchiq, setSxemaOchiq] = useState(false);
  //  Sxema FAQAT ochilganda so'raladi — kabinet birinchi yuklanishida
  //  ortiqcha so'rov bo'lmasin (Passenger'da konkurentlik = 1).
  const { data: sxema, isLoading: sxemaYuklanmoqda } = useOrgChart({
    enabled: sxemaOchiq,
  });
  const tanishdim = useOrgAcknowledge();

  const y = data?.description ?? null;
  const tanishuv = data?.acknowledgement ?? null;

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
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Kuzatiladigan ko'rsatkichlar ── */}
      {!!data?.metrics.length && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Kuzatiladigan ko'rsatkichlarim</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {data.metrics.map((m) => (
                <li key={m.key}>{m.label}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* ── Lavozim yo'riqnomasi ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList className="h-4 w-4" />
            Lavozim yo'riqnomam
            {y && (
              <span className="text-xs font-normal text-slate-600">
                v{y.version} · {y.effective_from} dan
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !y ? (
            <p className="text-sm text-amber-700">
              ⚠️ Lavozimingiz uchun yo'riqnoma hali kiritilmagan.
            </p>
          ) : (
            <div className="space-y-3 text-sm">
              {y.purpose && <p className="italic text-slate-700">{y.purpose}</p>}
              <Bolim sarlavha="Vazifalarim" bandlar={y.duties} />
              <Bolim sarlavha="Huquqlarim" bandlar={y.rights} />
              <Bolim sarlavha="Javobgarligim" bandlar={y.responsibility} />
              <Bolim sarlavha="Talablar" bandlar={y.requirements} />

              {/* ── «Tanishdim» (S-20 qaydi) ── */}
              {tanishuv?.acknowledged ? (
                <p className="flex items-center gap-1.5 text-sm text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  Siz bu yo'riqnoma bilan tanishgansiz
                  {tanishuv.acknowledged_at
                    ? ` (${tanishuv.acknowledged_at.slice(0, 10)})`
                    : ""}
                </p>
              ) : (
                <div className="space-y-1.5 border-t pt-3">
                  <p className="text-xs text-slate-600">
                    Yo'riqnomani o'qib chiqqaningizni tasdiqlang. Tasdiq
                    VERSIYA bilan yoziladi — yo'riqnoma yangilansa qaytadan
                    so'raladi.
                  </p>
                  <Button
                    size="sm"
                    onClick={() => tanishdim.mutate(undefined)}
                    disabled={tanishdim.isPending}
                  >
                    ✅ Tanishdim
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Butun tuzilma (TZ 3.16: sxema hammaga ochiq) ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between gap-2 text-base">
            <span>Kompaniya tuzilmasi</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSxemaOchiq((v) => !v)}
            >
              {sxemaOchiq ? "Yopish" : "Ko'rish"}
            </Button>
          </CardTitle>
        </CardHeader>
        {sxemaOchiq && (
          <CardContent>
            {sxemaYuklanmoqda ? (
              <Skeleton className="h-40 w-full" />
            ) : !sxema?.nodes.length ? (
              <div className="text-sm text-slate-600">
                Tuzilma hali kiritilmagan.
              </div>
            ) : (
              <div className="overflow-x-auto text-sm">
                <Daraxt nodes={sxema.nodes} parentId={null} />
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
