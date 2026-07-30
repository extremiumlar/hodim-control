/**
 * Xodim kabineti — «Bugungi normam».
 *
 * Botdagi «📊 Bugungi normam» bilan bir xil ma'lumot: bot
 * `/daily-results/today/{tg}` ni, bu sahifa `/daily-results/me/today` ni
 * chaqiradi, ikkalasi ham `_today_result_for_user(db, user)` ga boradi.
 *
 * Botdagi qoidalar saqlangan (bot/handlers/menu.py: show_norm):
 *  - faqat NORMA BELGILANGAN ko'rsatkichlar ko'rsatiladi (`norm !== null`)
 *  - birortasida norma bo'lmasa — "Sizga hali norma belgilanmagan" xabari
 *
 * Web botdan bitta narsada ustun: matn qatori o'rniga PROGRESS ko'rinadi —
 * xodim "70 dan 12 tasi" ni o'qimasdan, bir qarashda holatini ko'radi.
 * Raqamlar esa aynan bir xil.
 */
import { AlertCircle, Target } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyTodayResult } from "@/lib/queries";
import type { MetricProgressRow } from "@/lib/api";
import { cn } from "@/lib/utils";

function MetricCard({ m }: { m: MetricProgressRow }) {
  const norm = m.norm ?? 0;
  const pct = norm > 0 ? Math.min(100, Math.round((m.value / norm) * 100)) : 0;
  const done = norm > 0 && m.value >= norm;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-sm font-medium">{m.label}</span>
        <span className="shrink-0 text-sm tabular-nums">
          <span className={cn("text-lg font-bold", done ? "text-emerald-600" : "text-slate-900")}>
            {m.value}
          </span>
          <span className="text-slate-400"> / {norm}</span>
        </span>
      </div>

      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            done ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-slate-400"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-2 text-xs">
        <span className={cn(done ? "text-emerald-600" : "text-slate-400")}>
          {done ? "Norma bajarildi ✅" : `${pct}%`}
        </span>
        {/* tracked=false — CRM bog'lanmagan, qiymat DOIM 0 bo'ladi. Busiz xodim
            "ishlayapman-u, nega 0?" deb o'ylardi. Bot bu farqni ko'rsatmaydi. */}
        {!m.tracked && (
          <span className="flex items-center gap-1 text-amber-600">
            <AlertCircle className="h-3.5 w-3.5" />
            CRM bog'lanmagan
          </span>
        )}
      </div>
    </div>
  );
}

export default function Norm() {
  const { data, isLoading, isError } = useMyTodayResult();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Ma'lumotni yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  // Botdagi bilan bir xil filtr: normasi yo'q ko'rsatkich ko'rsatilmaydi
  const withNorm = data.metrics.filter((m) => m.norm !== null);

  if (!withNorm.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Target className="mx-auto mb-3 h-8 w-8 text-slate-300" />
        <p className="text-sm text-slate-600">
          Sizga hali norma belgilanmagan — rahbaringiz bilan bog'laning.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {withNorm.map((m) => (
        <MetricCard key={m.key} m={m} />
      ))}
      <p className="px-1 text-xs text-slate-400">
        Normani rahbaringiz belgilaydi. Qiymatlar CRM'dan avtomatik yangilanadi.
      </p>
    </div>
  );
}
