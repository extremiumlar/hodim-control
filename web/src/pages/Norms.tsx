import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, TeamNormRow } from "../lib/api";

export default function Norms() {
  const [rows, setRows] = useState<TeamNormRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, { suhbat: string; tashrif: string }>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.teamNorms();
      setRows(data);
      const nextDrafts: Record<number, { suhbat: string; tashrif: string }> = {};
      data.forEach((row) => {
        nextDrafts[row.user_id] = {
          suhbat: row.suhbat?.toString() ?? "",
          tashrif: row.tashrif?.toString() ?? "",
        };
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

  const saveMetric = async (userId: number, metric: "suhbat" | "tashrif") => {
    const raw = drafts[userId]?.[metric] ?? "";
    const value = Number(raw);
    if (!raw || Number.isNaN(value)) {
      setError("Qiymat butun son bo'lishi kerak");
      return;
    }
    setSavingKey(`${userId}:${metric}`);
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
      <h2 className="font-semibold mb-4">Xodimlar normalari</h2>
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
              <th className="py-2">Suhbatlar normasi</th>
              <th className="py-2">Tashriflar normasi</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.user_id} className="border-b last:border-0">
                <td className="py-2">
                  <Link to={`/employees/${row.user_id}`} className="text-indigo-600 hover:underline">
                    {row.full_name}
                  </Link>
                </td>
                {(["suhbat", "tashrif"] as const).map((metric) => (
                  <td key={metric} className="py-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={drafts[row.user_id]?.[metric] ?? ""}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [row.user_id]: { ...prev[row.user_id], [metric]: e.target.value },
                          }))
                        }
                        className="w-24 border rounded px-2 py-1"
                      />
                      <button
                        onClick={() => saveMetric(row.user_id, metric)}
                        disabled={savingKey === `${row.user_id}:${metric}`}
                        className="text-indigo-600 hover:underline text-xs disabled:opacity-50"
                      >
                        Saqlash
                      </button>
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
