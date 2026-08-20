/**
 * «Sinov muddati» — HR paneli (TZ 3.24 / S-24).
 *
 * ⚠️ Ro'yxat DOIM ko'rinadi — eslatma o'tkazib yuborilgan bo'lsa ham.
 * Eslatmaning o'zi S-12 (`deadlines`) orqali boradi, bu esa qaror
 * kutayotganlarni ko'z oldida ushlab turadi.
 *
 * ⚠️ Yangi jadval yo'q: ro'yxat `hire_date` + sinov muddatidan
 * HISOBLANADI. Muddat manbai har qatorda ko'rsatiladi — HR «nega bu
 * sana?» deb so'ramasin.
 */
import { AlertTriangle, CheckCircle2, FileWarning, Package, UserCheck } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useProbation, useProbationSummary } from "@/lib/queries";

export default function Probation() {
  const { data, isLoading } = useProbation();
  const { data: sum } = useProbationSummary();

  return (
    <div className="space-y-4">
      <PageHeader title="Sinov muddati" />

      {sum && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border bg-white p-3">
            <div className="text-xs text-slate-600">Sinovda</div>
            <div className="text-2xl font-semibold">{sum.total}</div>
          </div>
          <div
            className={`rounded-lg border p-3 ${
              sum.ending_soon > 0 ? "border-amber-200 bg-amber-50" : "bg-white"
            }`}
          >
            <div className="text-xs text-slate-600">7 kun ichida tugaydi</div>
            <div className="text-2xl font-semibold text-amber-800">{sum.ending_soon}</div>
          </div>
          <div
            className={`rounded-lg border p-3 ${
              sum.overdue > 0 ? "border-rose-200 bg-rose-50" : "bg-white"
            }`}
          >
            <div className="text-xs text-slate-600">Muddati o'tgan</div>
            <div className="text-2xl font-semibold text-rose-800">{sum.overdue}</div>
          </div>
        </div>
      )}

      {sum && (
        <p className="text-xs text-slate-500">
          Umumiy sinov muddati: <b>{sum.default_days} kun</b> (Muddatlar
          bo'limidagi sozlama). Ish taklifi orqali kelgan xodimda o'sha
          taklifdagi muddat ishlatiladi.
        </p>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <UserCheck className="h-4 w-4" />
            Xodimlar
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hozir sinov muddatida xodim yo'q.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((p) => (
                <li key={p.user_id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                  <span
                    className={`w-28 shrink-0 rounded px-1.5 py-0.5 text-center text-xs ${
                      p.is_overdue
                        ? "bg-rose-100 text-rose-800"
                        : p.days_left <= 7
                          ? "bg-amber-100 text-amber-900"
                          : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {p.is_overdue
                      ? `${Math.abs(p.days_left)} kun o'tdi`
                      : p.days_left === 0
                        ? "bugun tugaydi"
                        : `${p.days_left} kun qoldi`}
                  </span>
                  <span className="min-w-[140px] flex-1">
                    <span className="block truncate font-medium">{p.full_name}</span>
                    <span className="block text-xs text-slate-600">
                      {p.position_name ?? "lavozimsiz"} · {p.hire_date} → {p.ends_at}
                    </span>
                  </span>

                  {/* Onboarding belgilarini MAVJUD modullardan yig'amiz —
                      3.2 tayyor bo'lgach o'sha yerdan keladi. */}
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    {p.has_contract ? (
                      <span className="flex items-center gap-1 text-emerald-700">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        shartnoma
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-rose-700">
                        <FileWarning className="h-3.5 w-3.5" />
                        shartnoma yo'q
                      </span>
                    )}
                    {p.assets_missing > 0 && (
                      <span className="flex items-center gap-1 text-amber-800">
                        <Package className="h-3.5 w-3.5" />
                        {p.assets_missing} buyum
                      </span>
                    )}
                    {p.acks_pending > 0 && (
                      <span className="flex items-center gap-1 text-amber-800">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        {p.acks_pending} tanishuv
                      </span>
                    )}
                  </span>

                  <span className="shrink-0 text-xs text-slate-400" title="Muddat manbai">
                    {p.source}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
