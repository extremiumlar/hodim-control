import { useEffect, useState } from "react";
import { api, ExcusedDay } from "../lib/api";

const STATUS_LABELS: Record<string, string> = {
  pending: "🕓 Kutilmoqda",
  approved: "✅ Tasdiqlangan",
  rejected: "❌ Rad etilgan",
};

export default function ExcusedDays() {
  const [items, setItems] = useState<ExcusedDay[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.listExcusedDays(statusFilter || undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">Sababli kunlar</h2>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm"
        >
          <option value="">Barchasi</option>
          <option value="pending">Kutilmoqda</option>
          <option value="approved">Tasdiqlangan</option>
          <option value="rejected">Rad etilgan</option>
        </select>
      </div>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {loading ? (
        <p className="text-sm text-slate-500">Yuklanmoqda...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">Ma'lumot topilmadi.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b">
              <th className="py-2">Xodim</th>
              <th className="py-2">Sana</th>
              <th className="py-2">Sabab</th>
              <th className="py-2">Holat</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-0">
                <td className="py-2">{item.user_full_name}</td>
                <td className="py-2">{item.date}</td>
                <td className="py-2">{item.reason}</td>
                <td className="py-2">{STATUS_LABELS[item.status] ?? item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="text-xs text-slate-400 mt-4">
        Qaror qabul qilish HR tomonidan Telegram bot orqali amalga oshiriladi. Bu sahifa faqat tarixni
        ko'rish uchun.
      </p>
    </div>
  );
}
