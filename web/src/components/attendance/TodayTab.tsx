/**
 * «Bugun» tabi — jonli nazorat (UX-B).
 *
 * Rahbarning ertalabki asosiy savoli — «kim kelmadi?» — endi ISMLAR bilan,
 * jadval boshlanish vaqti va «Eslatish» tugmasi bilan (UX-A1/A5). Stat
 * kartalar 8 tadan 5 taga tushdi; «Keldi X/Y» progress chizig'i bilan.
 * Dashboard so'rovi faqat shu tab ochiq bo'lganda 30s'da yangilanib turadi.
 */
import { Bell, CalendarCheck, CalendarOff, Hourglass, UserX, Users } from "lucide-react";
import { toast } from "sonner";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendanceDashboard, useRemindAttendance } from "@/lib/queries";
import { fmtLocalTime as fmtTime } from "@/lib/utils";

export default function TodayTab({ active }: { active: boolean }) {
  const dashQuery = useAttendanceDashboard(active);
  const remind = useRemindAttendance();
  const dash = dashQuery.data;
  const s = dash?.summary;

  if (dashQuery.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[86px] rounded-xl" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (dashQuery.error) {
    // 4.8-band: xato ko'rsatilmasa rahbar "bugun hech narsa bo'lmagan" deb
    // tushunishi mumkin edi.
    return (
      <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        {dashQuery.error.message}
        <Button variant="outline" size="sm" onClick={() => dashQuery.refetch()}>
          Qayta urinish
        </Button>
      </div>
    );
  }

  if (!dash || !s) return null;

  const attendedPct = s.working_today > 0 ? Math.round((s.checked_in_today / s.working_today) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* Stat kartalar — 5 ta muhimi (UX-B: 8 -> 5) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {/* «Keldi X/Y» — progress bilan (StatCard'da meter yo'q, shu yerda kichik custom) */}
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-xs text-slate-500">Keldi</div>
              <div className="mt-1 text-2xl font-semibold text-slate-800">
                {s.checked_in_today}
                <span className="text-base font-medium text-slate-400">/{s.working_today}</span>
              </div>
            </div>
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <Users className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${Math.min(100, attendedPct)}%` }}
            />
          </div>
        </div>
        <StatCard label="Kechikdi" value={s.late_today} icon={Hourglass} warn={s.late_today > 0} />
        <StatCard label="Hozir ofisda" value={s.present_now} icon={CalendarCheck} />
        <StatCard
          label="Kelmagan"
          value={s.not_checked_in}
          icon={UserX}
          warn={s.not_checked_in > 0}
        />
        <StatCard label="Dam olishda" value={s.on_day_off} icon={CalendarOff} />
      </div>

      {/* Uch ustun: Kelmagan / Ofisda / Ketdi (UX-A1 ismlari bilan) */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              ❌ Kelmagan ({dash.not_come.length + dash.excused_today.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {dash.not_come.length === 0 && dash.excused_today.length === 0 ? (
              <div className="text-sm text-slate-400">Hamma keldi 🎉</div>
            ) : (
              <ul className="space-y-1">
                {dash.not_come.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between gap-2 border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <span className="min-w-0 truncate">
                      {p.full_name}
                      <span className="ml-1.5 text-xs tabular-nums text-slate-400">
                        · jadval {p.schedule_start}
                      </span>
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 shrink-0 border-indigo-200 bg-indigo-50 px-2 text-xs text-indigo-700 hover:bg-indigo-100"
                      disabled={remind.isPending}
                      title={
                        p.telegram_linked
                          ? "Bot orqali shaxsiy eslatma (kuniga ko'pi bilan 2 marta)"
                          : "Xodim Telegram botga ulanmagan — yetkazib bo'lmasligi mumkin"
                      }
                      onClick={() =>
                        remind.mutate(p.user_id, {
                          onSuccess: (r) =>
                            toast.success(
                              `${p.full_name}ga eslatma yuborildi (bugun ${r.sent_today}-marta).`
                            ),
                        })
                      }
                    >
                      <Bell className="mr-1 h-3 w-3" />
                      Eslatish
                    </Button>
                  </li>
                ))}
                {dash.excused_today.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between gap-2 border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <span className="min-w-0 truncate text-slate-500">{p.full_name}</span>
                    <StatusBadge kind="attendance" status="excused" />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">🏢 Ofisda ({dash.in_office.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {dash.in_office.length === 0 ? (
              <div className="text-sm text-slate-400">Hech kim yo'q</div>
            ) : (
              <ul className="space-y-1">
                {dash.in_office.map((p) => (
                  <li
                    key={`${p.user_name}-${p.check_in_time}`}
                    className="flex items-center justify-between border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <span className="min-w-0 truncate">{p.user_name}</span>
                    <span className="shrink-0 tabular-nums text-slate-500">
                      {fmtTime(p.check_in_time)}
                      {p.late_minutes > 0 && (
                        <span className="ml-1.5 font-semibold text-rose-600">+{p.late_minutes}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">🚪 Ketdi ({dash.left.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {dash.left.length === 0 ? (
              <div className="text-sm text-slate-400">Hali hech kim ketmadi</div>
            ) : (
              <ul className="space-y-1">
                {dash.left.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <span className="min-w-0 truncate">{p.full_name}</span>
                    <span className="shrink-0 tabular-nums text-xs text-slate-500">
                      {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)} ·{" "}
                      {Math.round((p.worked_minutes / 60) * 10) / 10} st
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bugun dam olishdagilar — faqat kimdir bo'lsa (bo'sh karta shovqin) */}
      {dash.on_day_off.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">🌙 Bugun dam olishda ({dash.on_day_off.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {dash.on_day_off.map((p) => (
                <span
                  key={p.user_id}
                  className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600"
                >
                  {p.full_name}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-400">
              Ish jadvali bo'yicha dam kuni — kechikish va jarima hisoblanmaydi.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Bugungi harakatlar lentasi */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Bugungi harakatlar</CardTitle>
        </CardHeader>
        <CardContent>
          {dash.recent.length === 0 ? (
            <div className="text-sm text-slate-400">Hali yozuv yo'q</div>
          ) : (
            <ul className="space-y-2">
              {dash.recent.map((p) => (
                <li
                  key={`${p.user_name}-${p.check_in_time}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span>{p.user_name}</span>
                  <span className="flex items-center gap-2 tabular-nums text-slate-500">
                    {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)}
                    <StatusBadge kind="attendance" status={p.status} />
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
