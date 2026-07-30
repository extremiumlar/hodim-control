/**
 * Xodim kabineti — «Statistikam».
 *
 * Botdagi «📈 Statistikam» bilan bir xil ma'lumot: bot `/stats/my/{tg}` ni,
 * bu sahifa `/stats/me` ni chaqiradi, ikkalasi ham `_my_stats_for_user` ga
 * boradi.
 *
 * Bot bo'limlarni FAQAT bo'sh bo'lmaganda ko'rsatadi (`if week_totals:`),
 * «Sababli kunlar» qatorini esa faqat 0 dan katta bo'lsa — shu qoidalar bu
 * yerda ham saqlangan.
 *
 * Metrika nomlari botdagi METRIC_MONTH_LABELS bilan bir xil, aks holda
 * xodim botda «Suhbatlar», web'da boshqa so'z ko'rib chalkashardi.
 */
import { CalendarCheck, ListChecks } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyStats } from "@/lib/queries";
import type { MetricProgressRow } from "@/lib/api";

// bot/handlers/stats.py: METRIC_MONTH_LABELS bilan bir xil
const METRIC_LABELS: Record<string, string> = {
  suhbat: "Suhbatlar",
  tashrif: "Tashriflar",
  oddiy_video: "Oddiy videolar",
  dumaloq_video: "Dumaloq videolar",
};

function TotalsCard({ title, totals }: { title: string; totals: Record<string, number> }) {
  const entries = Object.entries(totals);
  if (!entries.length) return null; // botdagi `if week_totals:` bilan bir xil

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </div>
      {entries.map(([key, total], i) => (
        <div
          key={key}
          className={
            "flex items-baseline justify-between gap-3 px-4 py-3" +
            (i > 0 ? " border-t border-slate-100" : "")
          }
        >
          <span className="text-sm text-slate-600">{METRIC_LABELS[key] ?? key}</span>
          <span className="shrink-0 text-base font-semibold tabular-nums">{total}</span>
        </div>
      ))}
    </div>
  );
}

function TodayCard({ rows }: { rows: MetricProgressRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Bugun
      </div>
      {rows.map((m, i) => (
        <div
          key={m.key}
          className={
            "flex items-baseline justify-between gap-3 px-4 py-3" +
            (i > 0 ? " border-t border-slate-100" : "")
          }
        >
          <span className="min-w-0 truncate text-sm text-slate-600">{m.label}</span>
          <span className="shrink-0 text-sm tabular-nums">
            <span className="text-base font-semibold">{m.value}</span>
            {/* Bot ham normani faqat belgilangan bo'lsa qo'shadi */}
            {m.norm !== null && <span className="text-slate-400"> / {m.norm}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function Stats() {
  const { data, isLoading, isError } = useMyStats();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Statistikani yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="px-1 text-xs text-slate-400">Davr: {data.period}</p>

      <TodayCard rows={data.today} />
      <TotalsCard title="Shu haftada jami" totals={data.week_totals} />
      <TotalsCard title="Shu oyda jami" totals={data.month_totals} />

      <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <ListChecks className="h-5 w-5 shrink-0 text-slate-400" />
        <span className="flex-1 text-sm text-slate-600">Vazifalar (shu oy)</span>
        <span className="shrink-0 text-base font-semibold tabular-nums">
          {data.tasks_done}
          <span className="text-slate-400"> / {data.tasks_total}</span>
        </span>
      </div>

      {/* Bot ham bu qatorni faqat 0 dan katta bo'lsa ko'rsatadi */}
      {data.excused_days > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
          <CalendarCheck className="h-5 w-5 shrink-0 text-slate-400" />
          <span className="flex-1 text-sm text-slate-600">Sababli kunlar</span>
          <span className="shrink-0 text-base font-semibold tabular-nums">
            {data.excused_days} kun
          </span>
        </div>
      )}
    </div>
  );
}
