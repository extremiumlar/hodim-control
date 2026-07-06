import { useEffect, useState } from "react";
import { api, ApiError, LeadStageDay, LeadStageMonth } from "../lib/api";

const MONTH_NAMES = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];

function monthTitle(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  return `${MONTH_NAMES[m - 1] ?? monthKey} ${y}`;
}

function currentMonthKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatDay(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function LastUpdated({ iso }: { iso: string | null }) {
  if (!iso) {
    return <p className="text-xs text-slate-400 mt-3">Ma'lumot hali yig'ilmagan.</p>;
  }
  const dt = new Date(iso + "Z");
  return (
    <p className="text-xs text-slate-400 mt-3">
      🕐 Oxirgi yangilanish: {dt.toLocaleString("uz", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
      {" "}(fon rejimida, taxminan har 30 daqiqada)
    </p>
  );
}

export default function LeadStats() {
  const [month, setMonth] = useState(currentMonthKey());
  const [monthData, setMonthData] = useState<LeadStageMonth | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [dayData, setDayData] = useState<LeadStageDay | null>(null);
  const [selectedOperator, setSelectedOperator] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Oylik ma'lumot
  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .leadStageMonth(month)
      .then((data) => {
        setMonthData(data);
        // Standart: eng so'nggi kunni ochamiz
        const lastDay = data.days.length ? data.days[data.days.length - 1].date : null;
        setSelectedDay(lastDay);
        setSelectedOperator(null);
      })
      .catch((e) => {
        setError(e instanceof ApiError && e.status === 403 ? "Bu bo'lim uchun ruxsatingiz yo'q." : "Ma'lumotni yuklashda xatolik.");
        setMonthData(null);
      })
      .finally(() => setLoading(false));
  }, [month]);

  // Kunlik ma'lumot (kun yoki operator o'zgarganda)
  useEffect(() => {
    if (!selectedDay) {
      setDayData(null);
      return;
    }
    api
      .leadStageDay(selectedDay, selectedOperator ?? undefined)
      .then(setDayData)
      .catch(() => setDayData(null));
  }, [selectedDay, selectedOperator]);

  if (loading) return <div className="p-8 text-center text-slate-500">Yuklanmoqda...</div>;
  if (error) return <div className="bg-white rounded-lg shadow p-6 text-slate-600">{error}</div>;
  if (!monthData) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold">🧲 Lidlar statistikasi — {monthTitle(monthData.month)}</h2>
        <input
          type="month"
          value={month}
          max={currentMonthKey()}
          onChange={(e) => setMonth(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm"
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">📞 Gaplashilgan lidlar</div>
          <div className="text-2xl font-semibold">{monthData.calls}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">🧲 Ishlangan lidlar</div>
          <div className="text-2xl font-semibold">{monthData.total}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">Tashriflar</div>
          <div className="text-2xl font-semibold">{monthData.visits}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">Ma'lumotli kunlar</div>
          <div className="text-2xl font-semibold">{monthData.days.length}</div>
        </div>
      </div>

      {monthData.days.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-6 text-slate-500">Bu oy uchun hali ma'lumot yo'q.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Kunlar ro'yxati */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-medium text-sm text-slate-600 mb-3">Kunlar</h3>
            <div className="space-y-1 max-h-[28rem] overflow-auto">
              {[...monthData.days].reverse().map((d) => (
                <button
                  key={d.date}
                  onClick={() => {
                    setSelectedDay(d.date);
                    setSelectedOperator(null);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded text-sm ${
                    selectedDay === d.date ? "bg-indigo-600 text-white" : "hover:bg-slate-100"
                  }`}
                >
                  <span>{formatDay(d.date)}</span>
                  <span className={selectedDay === d.date ? "text-indigo-100" : "text-slate-500"}>
                    {d.calls} gaplashildi · {d.total} lid
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Kun tafsiloti: bosqichlar */}
          <div className="bg-white rounded-lg shadow p-4">
            {dayData ? (
              <>
                <h3 className="font-medium text-sm text-slate-600 mb-1">
                  {dayData.responsible_id != null
                    ? dayData.responsible_name
                    : "Barcha operatorlar"}{" "}
                  — {formatDay(dayData.date)}
                </h3>
                <div className="text-sm text-slate-500 mb-3 space-y-0.5">
                  <div>📞 Gaplashilgan: <b>{dayData.calls}</b> (kiruvchi {dayData.calls_in}, chiquvchi {dayData.calls_out})</div>
                  <div>🧲 Ishlangan lidlar: <b>{dayData.total}</b> · Tashrif: <b>{dayData.visits}</b></div>
                </div>
                <div className="space-y-1">
                  {dayData.stages.length === 0 ? (
                    <p className="text-sm text-slate-400">Ma'lumot yo'q.</p>
                  ) : (
                    dayData.stages.map((s) => (
                      <div key={s.stage_name} className="flex justify-between text-sm py-1 border-b border-slate-100">
                        <span>{s.stage_name}</span>
                        <span className="font-medium">{s.count}</span>
                      </div>
                    ))
                  )}
                </div>
                {selectedOperator != null && (
                  <button
                    onClick={() => setSelectedOperator(null)}
                    className="mt-3 text-sm text-indigo-600 hover:underline"
                  >
                    ← Barcha operatorlar
                  </button>
                )}
                <LastUpdated iso={dayData.last_updated} />
              </>
            ) : (
              <p className="text-sm text-slate-400">Kun tanlang.</p>
            )}
          </div>

          {/* Operatorlar */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-medium text-sm text-slate-600 mb-3">Operatorlar</h3>
            {dayData && dayData.operators.length > 0 ? (
              <div className="space-y-1 max-h-[28rem] overflow-auto">
                {dayData.operators.map((op) => (
                  <button
                    key={op.responsible_id}
                    onClick={() => setSelectedOperator(op.responsible_id)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded text-sm ${
                      selectedOperator === op.responsible_id ? "bg-indigo-600 text-white" : "hover:bg-slate-100"
                    }`}
                  >
                    <span className="truncate mr-2">{op.responsible_name}</span>
                    <span className={`whitespace-nowrap ${selectedOperator === op.responsible_id ? "text-indigo-100" : "text-slate-500"}`}>
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
          </div>
        </div>
      )}
    </div>
  );
}
