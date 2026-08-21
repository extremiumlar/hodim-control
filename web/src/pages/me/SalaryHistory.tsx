/**
 * «Ish haqim tarixi» — xodim kabineti (TZ 3.25 / S-25).
 *
 * ⚠️ FAQAT O'ZINIKI. Endpoint (`/payroll/rates/me`) parametr qabul
 * qilmaydi — boshqa xodimning tarixini so'rash imkoniyati ham yo'q.
 *
 * ⚠️ ROP bu sahifani ko'rmaydi (TZ talabi): u ham xodim sifatida o'z
 * tarixini ko'radi, lekin jamoasinikini emas — bu ma'lumot
 * `PAYROLL_MANAGE_ROLES` bilan himoyalangan, u yerda ROP yo'q.
 */
import { TrendingDown, TrendingUp } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useMySalaryHistory, useSalaryReasons } from "@/lib/queries";

function pul(n: number): string {
  return `${Math.round(n).toLocaleString("ru-RU").replace(/ /g, " ")} so'm`;
}

export default function MeSalaryHistory() {
  const { data, isLoading } = useMySalaryHistory();
  const { data: reasons } = useSalaryReasons();
  const nomlar = Object.fromEntries((reasons ?? []).map((r) => [r.value, r.label]));

  return (
    <div className="space-y-4">
      <PageHeader title="Ish haqim tarixi" />

      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : !data?.length ? (
        <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
          Hali stavka kiritilmagan.
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {data.map((r, i) => {
            //  Ro'yxat eng yangisidan boshlanadi, ya'ni keyingi element —
            //  OLDINGI stavka.
            const oldingi = data[i + 1];
            const farq = oldingi ? r.amount - oldingi.amount : 0;
            return (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
                <span className="w-24 shrink-0 font-mono text-xs text-slate-600">
                  {r.effective_from}
                </span>
                <span className="min-w-[110px] font-medium">{pul(r.amount)}</span>
                {farq !== 0 && (
                  <span
                    className={`flex shrink-0 items-center gap-1 text-xs ${
                      farq > 0 ? "text-emerald-700" : "text-rose-700"
                    }`}
                  >
                    {farq > 0 ? (
                      <TrendingUp className="h-3.5 w-3.5" />
                    ) : (
                      <TrendingDown className="h-3.5 w-3.5" />
                    )}
                    {farq > 0 ? "+" : ""}
                    {pul(farq)}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-xs text-slate-600">
                  {/* S-25 dan OLDINGI qatorlarda sabab yo'q — soxta
                      qiymat qo'ymasdan «kiritilmagan» deb ko'rsatamiz. */}
                  {r.reason ? (nomlar[r.reason] ?? r.reason) : "sabab kiritilmagan"}
                  {r.note ? ` · ${r.note}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
