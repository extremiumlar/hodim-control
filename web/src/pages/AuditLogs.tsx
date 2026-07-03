import { useEffect, useRef, useState } from "react";
import { api, AuditLog } from "../lib/api";

const ACTION_LABELS: Record<string, string> = {
  user_created: "Foydalanuvchi qo'shildi",
  norm_changed: "Norma o'zgartirildi",
  excused_day_decided: "Sababli kun bo'yicha qaror",
  task_created: "Vazifa berildi",
  task_completed: "Vazifa bajarildi",
  mobilograf_confirmed: "Mobilograf tasdiqlandi",
  mobilograf_unconfirmed: "Mobilograf tasdig'i bekor qilindi",
  bonus_calculated: "Bonus hisoblandi",
};

function formatValue(value: Record<string, unknown> | null): string {
  if (!value) return "—";
  return Object.entries(value)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const latestRequestId = useRef(0);

  const load = async () => {
    const requestId = ++latestRequestId.current;
    setLoading(true);
    try {
      const logs = await api.listAuditLogs({
        action: action || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      if (requestId !== latestRequestId.current) return; // yangiroq so'rov allaqachon boshlangan
      setLogs(logs);
    } catch (e) {
      if (requestId !== latestRequestId.current) return;
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      if (requestId === latestRequestId.current) setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, dateFrom, dateTo]);

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 className="font-semibold">Audit jurnali</h2>
        <div className="flex gap-2">
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm"
          >
            <option value="">Barcha harakatlar</option>
            {Object.entries(ACTION_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {loading ? (
        <p className="text-sm text-slate-500">Yuklanmoqda...</p>
      ) : logs.length === 0 ? (
        <p className="text-sm text-slate-500">Yozuvlar topilmadi.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b">
              <th className="py-2">Vaqt</th>
              <th className="py-2">Harakat</th>
              <th className="py-2">Kim</th>
              <th className="py-2">Kimga</th>
              <th className="py-2">O'zgarish</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-b last:border-0 align-top">
                <td className="py-2 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                <td className="py-2">{ACTION_LABELS[log.action] ?? log.action}</td>
                <td className="py-2">{log.actor_name ?? "tizim"}</td>
                <td className="py-2">{log.target_name ?? "—"}</td>
                <td className="py-2 text-xs text-slate-500">
                  <div>oldin: {formatValue(log.before)}</div>
                  <div>keyin: {formatValue(log.after)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
