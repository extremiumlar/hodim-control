"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { useRouter } from "next/navigation";
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, Title, Tooltip, Legend, ArcElement, Filler,
} from "chart.js";
import { Bar, Line, Doughnut } from "react-chartjs-2";
import {
  UsersIcon, UserCheckIcon, ClockIcon, AlertIcon,
  ChartIcon, DoorIcon, HourglassIcon, BriefcaseIcon,
  BellIcon, TrophyIcon, TrendingIcon,
} from "@/components/icons";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend, ArcElement, Filler);

const fetcher = (url: string) => api.get(url).then((r) => r.data);

function timeStr(t?: string) {
  return t ? new Date(t).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—";
}
function fullName(u: any) {
  return `${u.user__first_name || ""} ${u.user__last_name || ""}`.trim() || u.user__username;
}

// KPI karta komponenti
function StatCard({ label, value, sub, color, Icon }: any) {
  return (
    <div className="card flex items-center gap-4 hover:shadow-md transition-shadow">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${color}`}>
        <Icon className="w-6 h-6" />
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-bold leading-tight">{value}</div>
        <div className="text-xs text-slate-500 truncate">{label}</div>
        {sub && <div className="text-xs text-slate-400">{sub}</div>}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const { me, isHR, isLoading } = useMe();
  const [days, setDays] = useState(30);

  const { data: dash } = useSWR("/attendance/dashboard/", fetcher, { refreshInterval: 15000 });
  const { data: stats } = useSWR(`/attendance/stats/?days=${days}`, fetcher);
  const { data: empSummary } = useSWR(`/attendance/employee-summary/?days=${days}`, fetcher);

  useEffect(() => {
    if (!isLoading && me && !isHR) router.replace("/dashboard");
  }, [isLoading, me, isHR, router]);

  if (!isHR) return null;

  const s = dash?.summary || {};
  const byDay = stats?.by_day || [];
  const lateTop = stats?.late_top || [];
  const workedTop = stats?.worked_top || [];

  const lineData = {
    labels: byDay.map((d: any) => d.date?.slice(5)),
    datasets: [
      { label: "Keldi", data: byDay.map((d: any) => d.present), borderColor: "#10b981", backgroundColor: "rgba(16,185,129,.15)", fill: true, tension: 0.35 },
      { label: "Kechikdi", data: byDay.map((d: any) => d.late), borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,.12)", fill: true, tension: 0.35 },
    ],
  };
  const lateBar = {
    labels: lateTop.map(fullName),
    datasets: [{ label: "Kechikish (daq)", data: lateTop.map((u: any) => u.late_total_min || 0), backgroundColor: "#ef4444", borderRadius: 6 }],
  };
  const workedBar = {
    labels: workedTop.map(fullName),
    datasets: [{ label: "Ishlangan (soat)", data: workedTop.map((u: any) => Math.round((u.worked || 0) / 60)), backgroundColor: "#3b82f6", borderRadius: 6 }],
  };
  const doughnut = {
    labels: ["Ofisda", "Ketgan", "Kelmagan", "Ta'tilda"],
    datasets: [{
      data: [s.present_now || 0, s.left_today || 0, s.not_checked_in || 0, s.on_leave || 0],
      backgroundColor: ["#10b981", "#3b82f6", "#ef4444", "#f59e0b"],
      borderWidth: 0,
    }],
  };

  const noLegend = { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } } } };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Boshqaruv paneli</h1>
          <p className="text-slate-500 text-sm">
            {dash?.today && new Date(dash.today).toLocaleDateString("uz-UZ", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs text-emerald-600">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> Real vaqt
          </span>
          <select className="input !w-auto text-sm py-1.5" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7 kun</option>
            <option value={30}>30 kun</option>
            <option value={90}>90 kun</option>
          </select>
        </div>
      </div>

      {/* KPI kartalar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard Icon={UsersIcon} color="bg-slate-100 text-slate-600" label="Jami hodimlar" value={s.total_employees ?? "—"} />
        <StatCard Icon={UserCheckIcon} color="bg-emerald-100 text-emerald-600" label="Hozir ofisda" value={s.present_now ?? "—"} sub={`Bugun kelgan: ${s.checked_in_today ?? 0}`} />
        <StatCard Icon={ClockIcon} color="bg-amber-100 text-amber-600" label="Bugun kechikkan" value={s.late_today ?? "—"} />
        <StatCard Icon={AlertIcon} color="bg-rose-100 text-rose-600" label="Kelmagan" value={s.not_checked_in ?? "—"} sub={`Ta'tilda: ${s.on_leave ?? 0}`} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard Icon={ChartIcon} color="bg-blue-100 text-blue-600" label="Davomat (oy)" value={`${s.attendance_rate ?? 0}%`} />
        <StatCard Icon={DoorIcon} color="bg-indigo-100 text-indigo-600" label="Bugun ketgan" value={s.left_today ?? "—"} />
        <StatCard Icon={HourglassIcon} color="bg-rose-100 text-rose-600" label="Kechikish (oy)" value={`${s.month_late_minutes ?? 0} daq`} />
        <StatCard Icon={BriefcaseIcon} color="bg-emerald-100 text-emerald-600" label="Ishlangan (oy)" value={`${s.month_worked_hours ?? 0} soat`} />
      </div>

      {/* Live + Recent */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Hozir ofisda */}
        <div className="card lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold flex items-center gap-2">
              <UserCheckIcon className="w-5 h-5 text-emerald-600" />
              Hozir ofisda ({dash?.in_office?.length || 0})
            </h2>
          </div>
          <div className="overflow-y-auto max-h-80">
            <table className="w-full text-sm">
              <thead className="text-slate-500 sticky top-0 bg-white">
                <tr className="border-b">
                  <th className="text-left py-2">Hodim</th>
                  <th className="text-left py-2">Bo'lim</th>
                  <th className="text-left py-2">Kelgan</th>
                  <th className="text-left py-2">Holat</th>
                </tr>
              </thead>
              <tbody>
                {dash?.in_office?.map((a: any) => (
                  <tr key={a.id} className="border-b last:border-0">
                    <td className="py-2 font-medium">{a.user_name}</td>
                    <td className="text-slate-500">{a.department || "—"}</td>
                    <td>{timeStr(a.check_in_time)}</td>
                    <td>{a.late_minutes > 0
                      ? <span className="badge-yellow">{a.late_minutes} daq kech</span>
                      : <span className="badge-green">Vaqtida</span>}</td>
                  </tr>
                ))}
                {!dash?.in_office?.length && (
                  <tr><td colSpan={4} className="py-8 text-center text-slate-400">Hozir ofisda hech kim yo'q</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Holat doirasi */}
        <div className="card">
          <h2 className="font-semibold mb-3">Bugungi holat</h2>
          <Doughnut data={doughnut} options={{ plugins: { legend: { position: "bottom", labels: { padding: 12, font: { size: 11 } } } }, cutout: "62%" }} />
        </div>
      </div>

      {/* So'nggi harakatlar */}
      <div className="card">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <BellIcon className="w-5 h-5 text-primary-600" />
          Bugungi so'nggi check-in'lar
        </h2>
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {dash?.recent?.map((a: any) => (
            <div key={a.id} className="flex items-center justify-between border border-slate-100 rounded-lg px-3 py-2">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-sm font-semibold">
                  {(a.user_name || "?").charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="font-medium text-sm">{a.user_name}</div>
                  <div className="text-xs text-slate-400">{a.department || "—"}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm">{timeStr(a.check_in_time)}{a.check_out_time && ` → ${timeStr(a.check_out_time)}`}</div>
                {a.late_minutes > 0
                  ? <span className="badge-yellow">{a.late_minutes} daq kech</span>
                  : <span className="badge-green">Vaqtida</span>}
              </div>
            </div>
          ))}
          {!dash?.recent?.length && <div className="py-8 text-center text-slate-400 text-sm">Bugun hali check-in yo'q</div>}
        </div>
      </div>

      {/* Grafiklar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <TrendingIcon className="w-5 h-5 text-primary-600" />
            {days} kunlik davomat dinamikasi
          </h2>
          <Line data={lineData} options={{ plugins: { legend: { position: "bottom" } }, scales: { x: { grid: { display: false } } } }} />
        </div>
        <div className="card">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <TrophyIcon className="w-5 h-5 text-amber-500" />
            Eng ko'p ishlaganlar (soat)
          </h2>
          <Bar data={workedBar} options={{ indexAxis: "y" as const, ...noLegend }} />
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <AlertIcon className="w-5 h-5 text-rose-500" />
          Eng ko'p kechikadiganlar (daqiqa)
        </h2>
        <Bar data={lateBar} options={noLegend} height={80} />
      </div>

      {/* Hodimlar jadvali */}
      <div className="card">
        <h2 className="font-semibold mb-3">Hodimlar bo'yicha hisobot ({days} kun)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-slate-500 border-b">
              <tr>
                <th className="text-left py-2">Hodim</th>
                <th className="text-left py-2">Bo'lim</th>
                <th className="text-right py-2">Kelgan kun</th>
                <th className="text-right py-2">Kechikish</th>
                <th className="text-right py-2">Kech (daq)</th>
                <th className="text-right py-2">Erta (daq)</th>
                <th className="text-right py-2">Ishlangan</th>
              </tr>
            </thead>
            <tbody>
              {empSummary?.map((r: any) => (
                <tr key={r.user__id} className="border-b last:border-0 hover:bg-slate-50">
                  <td className="py-2 font-medium">{fullName(r)}</td>
                  <td className="text-slate-500">{r.user__department__name || "—"}</td>
                  <td className="text-right">{r.present_days}</td>
                  <td className="text-right">{r.late_count > 0 ? <span className="text-amber-600">{r.late_count}x</span> : "—"}</td>
                  <td className="text-right">{r.late_minutes || 0}</td>
                  <td className="text-right">{r.early_minutes || 0}</td>
                  <td className="text-right">{Math.round((r.worked_minutes || 0) / 60)} soat</td>
                </tr>
              ))}
              {!empSummary?.length && <tr><td colSpan={7} className="py-8 text-center text-slate-400">Ma'lumot yo'q</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
