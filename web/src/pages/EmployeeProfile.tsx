import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, Bonus, DailyResult, User } from "../lib/api";

const SOURCE_LABELS: Record<string, string> = { crm: "CRM", manual: "Qo'lda" };

export default function EmployeeProfile() {
  const { id } = useParams<{ id: string }>();
  const userId = Number(id);

  const [employee, setEmployee] = useState<User | null>(null);
  const [results, setResults] = useState<DailyResult[]>([]);
  const [bonuses, setBonuses] = useState<Bonus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedBonus, setExpandedBonus] = useState<number | null>(null);

  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [conversations, setConversations] = useState("");
  const [visits, setVisits] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [emp, resultList, bonusList] = await Promise.all([
        api.getUser(userId),
        api.listDailyResults(userId),
        api.listBonuses(userId),
      ]);
      setEmployee(emp);
      setResults(resultList);
      setBonuses(bonusList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const conversationsCount = Number(conversations);
    const visitsCount = Number(visits);
    if (
      !Number.isInteger(conversationsCount) ||
      conversationsCount < 0 ||
      !Number.isInteger(visitsCount) ||
      visitsCount < 0
    ) {
      setError("Suhbatlar va tashriflar soni manfiy bo'lmagan butun son bo'lishi kerak");
      return;
    }

    setSubmitting(true);
    try {
      await api.createManualDailyResult({
        user_id: userId,
        date,
        conversations_count: conversationsCount,
        visits_count: visitsCount,
      });
      setConversations("");
      setVisits("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saqlashda xatolik");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <p className="text-sm text-slate-500">Yuklanmoqda...</p>;

  const chartData = [...results]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((r) => ({ date: r.date.slice(5), suhbat: r.conversations_count, tashrif: r.visits_count }));

  return (
    <div className="space-y-6">
      <div>
        <Link to="/norms" className="text-indigo-600 text-sm hover:underline">
          ← Orqaga
        </Link>
        <h1 className="text-xl font-semibold mt-1">{employee?.full_name}</h1>
        <p className="text-sm text-slate-500">Xodim profili</p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
          <h2 className="font-semibold mb-4">Kunlik natijani qo'lda kiritish</h2>
          <p className="text-xs text-slate-400 mb-3">
            CRM ulanmagan bo'lsa yoki tuzatish kerak bo'lsa shu yerdan kiriting.
          </p>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-sm text-slate-600 mb-1">Sana</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
                className="w-full border rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-600 mb-1">Suhbatlar soni</label>
              <input
                type="number"
                value={conversations}
                onChange={(e) => setConversations(e.target.value)}
                required
                className="w-full border rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-600 mb-1">Tashriflar soni</label>
              <input
                type="number"
                value={visits}
                onChange={(e) => setVisits(e.target.value)}
                required
                className="w-full border rounded px-3 py-2 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting ? "Saqlanmoqda..." : "Saqlash"}
            </button>
          </form>
        </div>

        <div className="md:col-span-2 space-y-6">
          <div className="bg-white rounded-lg shadow p-5">
            <h2 className="font-semibold mb-4">Tendensiya</h2>
            {chartData.length === 0 ? (
              <p className="text-sm text-slate-500">Grafik uchun hali ma'lumot yo'q.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" fontSize={12} />
                  <YAxis fontSize={12} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="suhbat" name="Suhbatlar" stroke="#4f46e5" strokeWidth={2} />
                  <Line type="monotone" dataKey="tashrif" name="Tashriflar" stroke="#16a34a" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="bg-white rounded-lg shadow p-5">
            <h2 className="font-semibold mb-4">Kunlik natijalar tarixi</h2>
            {results.length === 0 ? (
              <p className="text-sm text-slate-500">Hozircha ma'lumot yo'q.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Sana</th>
                    <th className="py-2">Suhbatlar</th>
                    <th className="py-2">Tashriflar</th>
                    <th className="py-2">Manba</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.id} className="border-b last:border-0">
                      <td className="py-2">{r.date}</td>
                      <td className="py-2">{r.conversations_count}</td>
                      <td className="py-2">{r.visits_count}</td>
                      <td className="py-2">{SOURCE_LABELS[r.source] ?? r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="bg-white rounded-lg shadow p-5">
            <h2 className="font-semibold mb-4">Bonus tarixi</h2>
            {bonuses.length === 0 ? (
              <p className="text-sm text-slate-500">Hali bonus hisoblanmagan.</p>
            ) : (
              <div className="space-y-2">
                {bonuses.map((b) => (
                  <div key={b.id} className="border rounded">
                    <button
                      onClick={() => setExpandedBonus(expandedBonus === b.id ? null : b.id)}
                      className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-slate-50"
                    >
                      <span>
                        {b.period} — <span className="font-medium">{b.amount.toLocaleString()} so'm</span>
                      </span>
                      <span className="text-slate-400 text-xs">
                        {expandedBonus === b.id ? "yopish ▲" : "tafsilot ▼"}
                      </span>
                    </button>
                    {expandedBonus === b.id && b.breakdown && (
                      <div className="px-3 pb-3 text-xs text-slate-600 space-y-1">
                        {Object.entries(b.breakdown).map(([key, value]) => (
                          <div key={key} className="flex justify-between border-b border-dashed py-1">
                            <span className="text-slate-400">{key}</span>
                            <span>{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
