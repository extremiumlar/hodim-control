import { FormEvent, useState } from "react";
import { api } from "../lib/api";
import { toLocalDateString } from "../lib/date";

function firstDayOfMonth(): string {
  const now = new Date();
  return toLocalDateString(new Date(now.getFullYear(), now.getMonth(), 1));
}

export default function Reports() {
  const [dateFrom, setDateFrom] = useState(firstDayOfMonth());
  const [dateTo, setDateTo] = useState(toLocalDateString(new Date()));
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setDownloading(true);
    setError(null);
    try {
      await api.downloadReportExport(dateFrom, dateTo);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklab olishda xatolik");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-5 max-w-lg">
      <h2 className="font-semibold mb-4">Hisobot eksporti (.xlsx)</h2>
      <p className="text-sm text-slate-500 mb-4">
        Tanlangan davr bo'yicha har bir xodim uchun suhbatlar, tashriflar, vazifalar, sababli kunlar va
        (agar davr aniq bitta oyni qamrab olsa) bonus summasi Excel faylga eksport qilinadi.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">Boshlanish sanasi</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              required
              className="w-full border rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Tugash sanasi</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              required
              className="w-full border rounded px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={downloading}
          className="bg-indigo-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {downloading ? "Tayyorlanmoqda..." : "Excel yuklab olish"}
        </button>
      </form>
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
    </div>
  );
}
