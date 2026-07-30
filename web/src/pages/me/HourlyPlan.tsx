/**
 * Xodim kabineti — «Bugungi rejam» (soatma-soat reja vs haqiqiy natija).
 *
 * Botdagi «📋 Bugungi rejam» bilan bir xil ma'lumot: bot
 * `/hourly-plan/{tg}/me` ni, bu sahifa `/hourly-plan/me` ni chaqiradi,
 * ikkalasi ham `build_plan(db, user, now)` ga boradi.
 *
 * Javobdagi `text` maydoni — botga tayyor HTML. Bu sahifa uni ATAYLAB
 * ishlatmaydi: strukturali maydonlardan (`cumulative_target`, `actual`,
 * `delta`, `this_hour_target`) o'zi chizadi, shunda progress ko'rinadi va
 * matn bloki mobil ekranga tiqilib qolmaydi. Raqamlar aynan bir xil.
 *
 * `hourly_plan_enabled` bilan to'silmaydi — u faqat avtomatik push
 * eslatmasini boshqaradi (api/config.py).
 */
import { AlertCircle, Clock, Moon, UtensilsCrossed } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyHourlyPlan } from "@/lib/queries";
import type { HourlyMetricStatus, HourlyPlan } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Yuqoridagi holat chizig'i: dam olish / tushlik / ish boshlanmagan / tugagan. */
function StatusStrip({ plan }: { plan: HourlyPlan }) {
  const base = "flex items-center gap-2 rounded-xl border p-3 text-sm";

  if (!plan.is_working) {
    return (
      <div className={cn(base, "border-slate-200 bg-white text-slate-600")}>
        <Moon className="h-4 w-4 shrink-0" />
        Bugun dam olish kuni (ish jadvali bo'yicha).
      </div>
    );
  }
  if (plan.in_lunch) {
    return (
      <div className={cn(base, "border-amber-200 bg-amber-50 text-amber-800")}>
        <UtensilsCrossed className="h-4 w-4 shrink-0" />
        Hozir tushlik vaqti (13:00–14:00).
      </div>
    );
  }
  return (
    <div className={cn(base, "border-slate-200 bg-white text-slate-600")}>
      <Clock className="h-4 w-4 shrink-0" />
      <span>
        Ish vaqti {plan.start_time}–{plan.end_time}
        {plan.now && <span className="text-slate-400"> · hozir {plan.now}</span>}
      </span>
    </div>
  );
}

function MetricCard({ m }: { m: HourlyMetricStatus }) {
  // Progress "shu paytgacha kerak" ga nisbatan — kunlik normaga emas. Xodim
  // uchun muhim savol "hozir orqadamanmi?", "kun oxirigacha qanchami?" emas.
  const target = m.cumulative_target;
  const pct = target > 0 ? Math.min(100, Math.round((m.actual / target) * 100)) : m.actual > 0 ? 100 : 0;
  const ahead = m.delta >= 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-sm font-medium">{m.label}</span>
        <span className="shrink-0 text-sm tabular-nums">
          <span className="text-lg font-bold">{m.actual}</span>
          <span className="text-slate-400"> / {target}</span>
        </span>
      </div>

      {m.tracked ? (
        <>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn("h-full rounded-full transition-all", ahead ? "bg-emerald-500" : "bg-rose-400")}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
            <span className={ahead ? "text-emerald-600" : "text-rose-600"}>
              {m.delta === 0
                ? "Rejada"
                : ahead
                  ? `${m.delta} ta oldinda`
                  : `${Math.abs(m.delta)} ta orqada`}
            </span>
            <span className="text-slate-400">
              Bu soatda ~{m.this_hour_target} ta · kunlik {m.effective_norm}
            </span>
          </div>
        </>
      ) : (
        // tracked=false — CRM bog'lanmagan, actual doim 0 bo'ladi va
        // "orqada" deb ko'rsatish yolg'on bo'lardi (bot ham shu farqni aytadi)
        <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-600">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          Bu ko'rsatkich hozircha kuzatilmayapti (CRM bog'lanmagan)
        </div>
      )}
    </div>
  );
}

export default function HourlyPlanPage() {
  const { data, isLoading, isError } = useMyHourlyPlan();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-12 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Rejani yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <StatusStrip plan={data} />

      {data.is_working && !data.metrics.length && (
        // Botdagi bilan bir xil matn (hourly_plan.py: build_plan)
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-600">
          Sizga hali kunlik norma belgilanmagan — rahbaringizga murojaat qiling.
        </div>
      )}

      {data.metrics.map((m) => (
        <MetricCard key={m.key} m={m} />
      ))}

      {data.is_working && !!data.metrics.length && (
        <p className="px-1 text-xs text-slate-400">
          «Shu paytgacha kerak» ish vaqtingizga moslashib hisoblanadi — qisqa
          kunda kunlik norma ham kamayadi.
        </p>
      )}
    </div>
  );
}
