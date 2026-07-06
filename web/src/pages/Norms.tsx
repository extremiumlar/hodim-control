import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, TeamNormRow } from "../lib/api";

export default function Norms() {
  const [rows, setRows] = useState<TeamNormRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Kalit: `${userId}:${metricKey}` — har bir xodimning har bir ko'rsatkichi uchun qoralama
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.teamNorms();
      setRows(data);
      const nextDrafts: Record<string, string> = {};
      data.forEach((row) => {
        row.metrics.forEach((m) => {
          nextDrafts[`${row.user_id}:${m.key}`] = m.norm?.toString() ?? "";
        });
      });
      setDrafts(nextDrafts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveMetric = async (userId: number, metric: string) => {
    const draftKey = `${userId}:${metric}`;
    const raw = drafts[draftKey] ?? "";
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 0) {
      setError("Qiymat manfiy bo'lmagan butun son bo'lishi kerak");
      return;
    }
    setSavingKey(draftKey);
    setError(null);
    try {
      await api.updateNorm({ user_id: userId, metric_type: metric, value });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saqlashda xatolik");
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-5">
      <h2 className="font-semibold mb-1">Xodimlar normalari</h2>
      <p className="text-xs text-slate-400 mb-4">
        Ko'rsatkichlar har bir xodimning lavozimiga qarab belgilanadi ("Lavozimlar" bo'limida
        sozlanadi). Siz faqat o'zingiz boshqaradigan xodimlarning normalarini o'zgartira olasiz.
        "Bugungi" qiymat CRM (yoki qo'lda kiritilgan) ma'lumot asosida jonli ko'rsatiladi — shu
        orqali normani real vaqtda tekshirish mumkin.
      </p>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {loading ? (
        <p className="text-sm text-slate-500">Yuklanmoqda...</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500">Hozircha xodimlar yo'q.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b">
              <th className="py-2">Xodim</th>
              <th className="py-2">Lavozim</th>
              <th className="py-2">Normalar</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.user_id} className="border-b last:border-0 align-top">
                <td className="py-2">
                  <Link to={`/employees/${row.user_id}`} className="text-indigo-600 hover:underline">
                    {row.full_name}
                  </Link>
                </td>
                <td className="py-2 text-slate-500">{row.position_name ?? "—"}</td>
                <td className="py-2">
                  <div className="flex flex-wrap gap-4">
                    {row.metrics.map((m) => {
                      const draftKey = `${row.user_id}:${m.key}`;
                      const metNorm = m.norm !== null && m.value >= m.norm;
                      return (
                        <div key={m.key} className="flex items-center gap-2">
                          <span className="text-slate-500 text-xs">{m.label}:</span>
                          <span
                            className={`text-xs font-medium ${
                              m.norm === null ? "text-slate-400" : metNorm ? "text-emerald-600" : "text-amber-600"
                            }`}
                            title="Bugungi haqiqiy qiymat (CRM/qo'lda)"
                          >
                            {m.value}
                          </span>
                          <span className="text-slate-300">/</span>
                          {row.can_edit ? (
                            <>
                              <input
                                type="number"
                                value={drafts[draftKey] ?? ""}
                                onChange={(e) =>
                                  setDrafts((prev) => ({ ...prev, [draftKey]: e.target.value }))
                                }
                                className="w-20 border rounded px-2 py-1"
                              />
                              <button
                                onClick={() => saveMetric(row.user_id, m.key)}
                                disabled={savingKey === draftKey}
                                className="text-indigo-600 hover:underline text-xs disabled:opacity-50"
                              >
                                Saqlash
                              </button>
                            </>
                          ) : (
                            <span>{m.norm ?? "—"}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
