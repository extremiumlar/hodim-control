import { useCallback, useEffect, useState } from "react";
import {
  api,
  Attendance as AttendanceRow,
  AttendanceDashboard,
  EmployeeAttendanceSummary,
} from "../lib/api";

const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  present: { text: "Keldi", cls: "bg-emerald-100 text-emerald-700" },
  late: { text: "Kechikdi", cls: "bg-rose-100 text-rose-700" },
  absent: { text: "Kelmadi", cls: "bg-slate-200 text-slate-600" },
  weekend: { text: "Dam olish", cls: "bg-blue-100 text-blue-700" },
};

// Backend naive-UTC — "Z" qo'shib mahalliy vaqtga o'giramiz.
function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const norm = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`;
  return new Date(norm).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function Attendance() {
  const [dash, setDash] = useState<AttendanceDashboard | null>(null);
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [summary, setSummary] = useState<EmployeeAttendanceSummary[]>([]);
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(7));
  const [dateTo, setDateTo] = useState(isoDaysAgo(0));
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [d, r, s] = await Promise.all([
        api.attendanceDashboard(),
        api.listAttendance({ date_from: dateFrom, date_to: dateTo }),
        api.attendanceEmployeeSummary(30),
      ]);
      setDash(d);
      setRows(r);
      setSummary(s);
    } catch (e: any) {
      setError(e.message || "Yuklashda xatolik");
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const s = dash?.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Davomat (kelib-ketish)</h1>
        <button onClick={load} className="text-sm text-indigo-600 hover:underline">
          Yangilash
        </button>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg px-3 py-2 text-sm">{error}</div>
      )}

      {/* Bugungi xulosa kartalari */}
      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { label: "Bugun ishlashi kerak", value: s.working_today },
            { label: "Keldi", value: s.checked_in_today },
            { label: "Hozir ofisda", value: s.present_now },
            { label: "Kechikdi", value: s.late_today, warn: s.late_today > 0 },
            { label: "Ketdi", value: s.left_today },
            { label: "Kelmagan", value: s.not_checked_in, warn: s.not_checked_in > 0 },
            { label: "Oy: ishlangan soat", value: s.month_worked_hours },
          ].map((c) => (
            <div key={c.label} className="bg-white border border-slate-200 rounded-xl p-3">
              <div className="text-xs text-slate-500">{c.label}</div>
              <div className={`text-2xl font-bold ${c.warn ? "text-rose-600" : "text-slate-800"}`}>{c.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Hozir ofisda */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="font-semibold mb-3">Hozir ofisda ({dash?.in_office.length ?? 0})</h2>
          {dash && dash.in_office.length === 0 && <div className="text-sm text-slate-400">Hech kim yo'q</div>}
          <ul className="space-y-2">
            {dash?.in_office.map((p, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span>{p.user_name}</span>
                <span className="text-slate-500">
                  {fmtTime(p.check_in_time)}
                  {p.late_minutes > 0 && <span className="text-rose-600 ml-2">+{p.late_minutes} daq</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* So'nggi harakatlar */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="font-semibold mb-3">Bugungi harakatlar</h2>
          {dash && dash.recent.length === 0 && <div className="text-sm text-slate-400">Hali yozuv yo'q</div>}
          <ul className="space-y-2">
            {dash?.recent.map((p, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span>{p.user_name}</span>
                <span className="text-slate-500">
                  {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)}
                  <span
                    className={`ml-2 px-2 py-0.5 rounded-full text-xs ${STATUS_LABELS[p.status]?.cls ?? "bg-slate-100"}`}
                  >
                    {STATUS_LABELS[p.status]?.text ?? p.status}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* 30 kunlik xodim xulosasi */}
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <h2 className="font-semibold mb-3">Xodimlar bo'yicha (oxirgi 30 kun)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="py-2 pr-3">Xodim</th>
                <th className="py-2 pr-3">Kelgan kun</th>
                <th className="py-2 pr-3">Kechikish (marta)</th>
                <th className="py-2 pr-3">Kechikish (daq)</th>
                <th className="py-2 pr-3">Erta ketish (daq)</th>
                <th className="py-2">Ishlangan (soat)</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((r) => (
                <tr key={r.user_id} className="border-b border-slate-50">
                  <td className="py-2 pr-3 font-medium">{r.full_name}</td>
                  <td className="py-2 pr-3">{r.present_days}</td>
                  <td className={`py-2 pr-3 ${r.late_count > 0 ? "text-rose-600" : ""}`}>{r.late_count}</td>
                  <td className={`py-2 pr-3 ${r.late_minutes > 0 ? "text-rose-600" : ""}`}>{r.late_minutes}</td>
                  <td className="py-2 pr-3">{r.early_minutes}</td>
                  <td className="py-2">{Math.round((r.worked_minutes / 60) * 10) / 10}</td>
                </tr>
              ))}
              {summary.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-slate-400">
                    Hali davomat yozuvlari yo'q
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Yozuvlar jadvali (sana oralig'i bilan) */}
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h2 className="font-semibold">Yozuvlar</h2>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border border-slate-300 rounded-md px-2 py-1 text-sm"
          />
          <span className="text-slate-400">—</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border border-slate-300 rounded-md px-2 py-1 text-sm"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="py-2 pr-3">Sana</th>
                <th className="py-2 pr-3">Xodim</th>
                <th className="py-2 pr-3">Keldim</th>
                <th className="py-2 pr-3">Ketdim</th>
                <th className="py-2 pr-3">Kechikish</th>
                <th className="py-2 pr-3">Ishlangan</th>
                <th className="py-2">Holat</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-50">
                  <td className="py-2 pr-3">{r.date}</td>
                  <td className="py-2 pr-3 font-medium">{r.user_full_name}</td>
                  <td className="py-2 pr-3">{fmtTime(r.check_in_time)}</td>
                  <td className="py-2 pr-3">{fmtTime(r.check_out_time)}</td>
                  <td className={`py-2 pr-3 ${r.late_minutes > 0 ? "text-rose-600" : ""}`}>
                    {r.late_minutes > 0 ? `${r.late_minutes} daq` : "—"}
                  </td>
                  <td className="py-2 pr-3">
                    {r.worked_minutes > 0 ? `${Math.round((r.worked_minutes / 60) * 10) / 10} soat` : "—"}
                  </td>
                  <td className="py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_LABELS[r.status]?.cls ?? "bg-slate-100"}`}>
                      {STATUS_LABELS[r.status]?.text ?? r.status}
                    </span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-slate-400">
                    Tanlangan oraliqda yozuv yo'q
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
