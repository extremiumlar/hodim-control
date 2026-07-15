import { useState } from "react";
import { Home, Magnet, MessageSquare, Phone } from "lucide-react";
import OperatorTable from "@/components/statistics/OperatorTable";
import ReasonsFeed from "@/components/statistics/ReasonsFeed";
import TrendChart from "@/components/statistics/TrendChart";
import PageHeader from "@/components/PageHeader";
import { currentMonthKey, MonthPicker } from "@/components/PeriodPicker";
import StatCard from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
import { useOperatorSummary, useStatsOverview } from "@/lib/queries";

const PERIOD_LABELS: Record<string, string> = {
  today: "Bugun",
  week: "Oxirgi 7 kun",
  month: "Oxirgi 30 kun",
};

const MONTH_NAMES = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];

function monthTitle(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  return `${MONTH_NAMES[m - 1] ?? monthKey} ${y}`;
}

function fmtTalk(sec: number): string {
  const minutes = Math.floor(sec / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}s ${m}d` : `${m}d`;
}

function fmtDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

export default function Statistics() {
  const [period, setPeriod] = useState<string>("week");
  // Joriy oy tanlangan bo'lsa — odatiy rejim (oxirgi 30 kun + davr tugmalari);
  // o'tgan oy tanlansa — o'sha kalendar oy ko'rsatiladi.
  const [month, setMonth] = useState<string>(currentMonthKey());
  const isPastMonth = month !== "" && month !== currentMonthKey();
  const monthParam = isPastMonth ? month : undefined;

  const overviewQuery = useStatsOverview(30, monthParam);
  const summaryQuery = useOperatorSummary(period, monthParam);

  const overview = overviewQuery.data;

  if (overviewQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[86px] rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (overviewQuery.error) {
    const status = overviewQuery.error instanceof ApiError ? overviewQuery.error.status : 0;
    return (
      <div className="rounded-lg bg-white p-6 text-slate-600 shadow">
        {status === 403 ? "Bu bo'lim faqat rahbarlar uchun." : "Yuklashda xatolik."}
      </div>
    );
  }

  if (!overview) return null;

  const rangeLabel = isPastMonth ? monthTitle(month) : "30 kun";
  const lastLabel = isPastMonth ? "oxirgi kun" : "bugun";
  const last = overview.series[overview.series.length - 1];
  const totals = overview.series.reduce(
    (acc, p) => ({
      calls: acc.calls + p.calls,
      talk: acc.talk + p.talk_sec,
      leads: acc.leads + p.leads,
      visits: acc.visits + p.visits,
    }),
    { calls: 0, talk: 0, leads: 0, visits: 0 }
  );

  return (
    <div className="space-y-4">
      <PageHeader title={`📊 Statistika${isPastMonth ? ` — ${monthTitle(month)}` : ""}`}>
        <MonthPicker value={month} onChange={setMonth} />
        {isPastMonth && (
          <Button variant="link" size="sm" onClick={() => setMonth(currentMonthKey())}>
            Joriy davrga qaytish
          </Button>
        )}
        <span className="text-xs text-slate-400">
          {fmtDay(overview.date_from)} – {fmtDay(overview.date_to)} · ma'lumot fon snapshotlaridan
        </span>
      </PageHeader>

      {/* Yuqori kartalar — davr jami */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={`Qo'ng'iroqlar (${rangeLabel})`}
          value={totals.calls}
          icon={Phone}
          hint={`${lastLabel}: ${last?.calls ?? 0}`}
        />
        <StatCard
          label={`Gaplashgan vaqt (${rangeLabel})`}
          value={fmtTalk(totals.talk)}
          icon={MessageSquare}
          hint={`${lastLabel}: ${fmtTalk(last?.talk_sec ?? 0)}`}
        />
        <StatCard
          label={`Ishlangan lidlar (${rangeLabel})`}
          value={totals.leads}
          icon={Magnet}
          hint={`${lastLabel}: ${last?.leads ?? 0}`}
        />
        <StatCard
          label={`Tashriflar (${rangeLabel})`}
          value={totals.visits}
          icon={Home}
          hint={`${lastLabel}: ${last?.visits ?? 0}`}
        />
      </div>

      {/* Trend grafigi — sonlar */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-600">Kunlik trend ({rangeLabel})</CardTitle>
        </CardHeader>
        <CardContent>
          <TrendChart
            points={overview.series}
            series={[
              { key: "calls", label: "Qo'ng'iroq", color: "#6366f1" },
              { key: "leads", label: "Lid", color: "#10b981" },
              { key: "visits", label: "Tashrif", color: "#f59e0b" },
            ]}
          />
        </CardContent>
      </Card>

      {/* Trend grafigi — gaplashgan vaqt (daqiqa) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-600">
            Gaplashgan vaqt, daqiqa ({rangeLabel})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TrendChart
            height={140}
            points={overview.series}
            series={[
              { key: "talk_sec", label: "Daqiqa", color: "#0ea5e9", transform: (v) => Math.round(v / 60) },
            ]}
          />
        </CardContent>
      </Card>

      {/* Operator kesimi */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm text-slate-600">
              Operator kesimi{isPastMonth ? ` — ${monthTitle(month)}` : ""}
            </CardTitle>
            {!isPastMonth && (
              <div className="flex gap-1">
                {Object.entries(PERIOD_LABELS).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setPeriod(key)}
                    className={cn(
                      "rounded px-3 py-1.5 text-sm",
                      period === key
                        ? "bg-primary text-primary-foreground"
                        : "text-slate-600 hover:bg-slate-100"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <OperatorTable summary={summaryQuery.data} isLoading={summaryQuery.isLoading} />
        </CardContent>
      </Card>

      {/* Sabablar */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-600">
            Orqada qolish sabablari ({isPastMonth ? monthTitle(month) : "oxirgi 7 kun"})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ReasonsFeed reasons={overview.reasons} />
        </CardContent>
      </Card>
    </div>
  );
}
