import { useEffect, useState } from "react";
import { format } from "date-fns";
import { CalendarDays, Home, Magnet, Phone } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { currentMonthKey, MonthPicker } from "@/components/PeriodPicker";
import StatCard from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLeadStageDay, useLeadStageMonth } from "@/lib/queries";

const MANAGER_ROLES = ["hr", "rop", "boss", "dasturchi"];

const MONTH_NAMES = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];

function monthTitle(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  return `${MONTH_NAMES[m - 1] ?? monthKey} ${y}`;
}

function formatDay(iso: string): string {
  return format(new Date(iso + "T00:00:00"), "dd.MM");
}

function LastUpdated({ iso }: { iso: string | null }) {
  if (!iso) {
    return <p className="mt-3 text-xs text-slate-400">Ma'lumot hali yig'ilmagan.</p>;
  }
  return (
    <p className="mt-3 text-xs text-slate-400">
      🕐 Oxirgi yangilanish: {format(new Date(iso + "Z"), "dd.MM, HH:mm")} (fon rejimida, taxminan
      har 30 daqiqada)
    </p>
  );
}

export default function LeadStats() {
  const { user } = useAuth();
  const isManager = MANAGER_ROLES.includes(user?.role ?? "");
  const [month, setMonth] = useState(currentMonthKey());
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedOperator, setSelectedOperator] = useState<number | null>(null);

  const monthQuery = useLeadStageMonth(month, isManager);
  const monthData = monthQuery.data;

  // Oy ma'lumoti kelganda oxirgi kunni avtomatik tanlaymiz
  useEffect(() => {
    if (monthData) {
      const lastDay = monthData.days.length ? monthData.days[monthData.days.length - 1].date : null;
      setSelectedDay(lastDay);
      setSelectedOperator(null);
    }
  }, [monthData]);

  const dayQuery = useLeadStageDay(selectedDay, selectedOperator ?? undefined, isManager);
  const dayData = dayQuery.data ?? null;

  if (monthQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[86px] rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  if (monthQuery.error) {
    const status = monthQuery.error instanceof ApiError ? monthQuery.error.status : 0;
    return (
      <div className="rounded-lg bg-white p-6 text-slate-600 shadow">
        {status === 403
          ? "Bu bo'lim uchun ruxsatingiz yo'q."
          : status === 400
            ? "CRM operator ID'ingiz sozlanmagan — rahbaringizga murojaat qiling."
            : "Ma'lumotni yuklashda xatolik."}
      </div>
    );
  }

  if (!monthData) return null;

  return (
    <div className="space-y-4">
      <PageHeader title={`🧲 Lidlar statistikasi — ${monthTitle(monthData.month)}`}>
        <MonthPicker value={month} onChange={setMonth} />
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Gaplashilgan lidlar" value={monthData.calls} icon={Phone} />
        <StatCard label="Ishlangan lidlar" value={monthData.total} icon={Magnet} />
        <StatCard label="Tashriflar" value={monthData.visits} icon={Home} />
        <StatCard label="Ma'lumotli kunlar" value={monthData.days.length} icon={CalendarDays} />
      </div>

      {monthData.days.length === 0 ? (
        <div className="rounded-lg bg-white p-6 text-slate-500 shadow">
          Bu oy uchun hali ma'lumot yo'q.
        </div>
      ) : (
        <div className={cn("grid grid-cols-1 gap-4", isManager ? "md:grid-cols-3" : "md:grid-cols-2")}>
          {/* Kunlar ro'yxati */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm text-slate-600">Kunlar</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[28rem] space-y-1 overflow-auto">
                {[...monthData.days].reverse().map((d) => (
                  <button
                    key={d.date}
                    onClick={() => {
                      setSelectedDay(d.date);
                      setSelectedOperator(null);
                    }}
                    className={cn(
                      "flex w-full items-center justify-between rounded px-3 py-2 text-sm",
                      selectedDay === d.date ? "bg-primary text-primary-foreground" : "hover:bg-slate-100"
                    )}
                  >
                    <span>{formatDay(d.date)}</span>
                    <span className={selectedDay === d.date ? "text-indigo-100" : "text-slate-500"}>
                      {d.calls} gaplashildi · {d.total} lid
                    </span>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Kun tafsiloti: bosqichlar */}
          <Card>
            <CardContent className="pt-6">
              {dayQuery.isLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : dayData ? (
                <>
                  <h3 className="mb-1 text-sm font-medium text-slate-600">
                    {dayData.responsible_id != null ? dayData.responsible_name : "Barcha operatorlar"} —{" "}
                    {formatDay(dayData.date)}
                  </h3>
                  <div className="mb-3 space-y-0.5 text-sm text-slate-500">
                    <div>
                      📞 Gaplashilgan: <b>{dayData.calls}</b> (kiruvchi {dayData.calls_in}, chiquvchi{" "}
                      {dayData.calls_out})
                    </div>
                    <div>
                      🧲 Ishlangan lidlar: <b>{dayData.total}</b> · Tashrif: <b>{dayData.visits}</b>
                    </div>
                  </div>
                  <div className="space-y-1">
                    {dayData.stages.length === 0 ? (
                      <p className="text-sm text-slate-400">Ma'lumot yo'q.</p>
                    ) : (
                      dayData.stages.map((s) => (
                        <div
                          key={s.stage_name}
                          className="flex justify-between border-b border-slate-100 py-1 text-sm"
                        >
                          <span>{s.stage_name}</span>
                          <span className="font-medium">{s.count}</span>
                        </div>
                      ))
                    )}
                  </div>
                  {selectedOperator != null && (
                    <Button
                      variant="link"
                      size="sm"
                      className="mt-3 h-auto p-0"
                      onClick={() => setSelectedOperator(null)}
                    >
                      ← Barcha operatorlar
                    </Button>
                  )}
                  <LastUpdated iso={dayData.last_updated} />
                </>
              ) : (
                <p className="text-sm text-slate-400">Kun tanlang.</p>
              )}
            </CardContent>
          </Card>

          {/* Operatorlar — faqat rahbarlar uchun */}
          {isManager && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm text-slate-600">Operatorlar</CardTitle>
              </CardHeader>
              <CardContent>
                {dayData && dayData.operators.length > 0 ? (
                  <div className="max-h-[28rem] space-y-1 overflow-auto">
                    {dayData.operators.map((op) => (
                      <button
                        key={op.responsible_id}
                        onClick={() => setSelectedOperator(op.responsible_id)}
                        className={cn(
                          "flex w-full items-center justify-between rounded px-3 py-2 text-sm",
                          selectedOperator === op.responsible_id
                            ? "bg-primary text-primary-foreground"
                            : "hover:bg-slate-100"
                        )}
                      >
                        <span className="mr-2 truncate">{op.responsible_name}</span>
                        <span
                          className={cn(
                            "whitespace-nowrap",
                            selectedOperator === op.responsible_id ? "text-indigo-100" : "text-slate-500"
                          )}
                        >
                          📞{op.calls} · 🧲{op.total}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400">
                    {selectedOperator != null ? "Bitta operator ko'rinishi." : "Kun tanlang."}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
