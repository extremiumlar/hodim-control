import { useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  OperatorSummary,
  StatsOverview,
  StatsSeriesPoint,
} from "../lib/api";

const PERIOD_LABELS: Record<string, string> = {
  today: "Bugun",
  week: "Oxirgi 7 kun",
  month: "Oxirgi 30 kun",
};

function fmtTalk(sec: number): string {
  const minutes = Math.floor(sec / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}s ${m}d` : `${m}d`;
}

function fmtDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

function pctBadge(pct: number | null) {
  if (pct == null) return null;
  const positive = pct > 0;
  const cls = positive
    ? "text-emerald-700 bg-emerald-50"
    : pct < 0
      ? "text-rose-700 bg-rose-50"
      : "text-slate-600 bg-slate-100";
  return (
    <span className={`ml-1 px-1.5 py-0.5 rounded text-xs font-medium ${cls}`}>
      {positive ? "+" : ""}
      {pct}%
    </span>
  );
}

// --- Sof SVG trend grafigi (tashqi kutubxonasiz) ---
// Bir nechta seriya bitta o'qda; talk_sec kabi boshqa masshtabdagi seriya
// alohida chizilmaydi — chaqiruvchi uni daqiqaga o'girib alohida chart beradi.

interface ChartSeries {
  key: keyof StatsSeriesPoint;
  label: string;
  color: string;
  transform?: (v: number) => number;
}

function TrendChart({
  points,
  series,
  height = 200,
}: {
  points: StatsSeriesPoint[];
  series: ChartSeries[];
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 720; // viewBox kengligi — konteynerga responsive cho'ziladi
  const pad = { top: 12, right: 12, bottom: 22, left: 36 };

  const values = useMemo(() => {
    return points.map((p) =>
      series.map((s) => {
        const raw = Number(p[s.key] ?? 0);
        return s.transform ? s.transform(raw) : raw;
      })
    );
  }, [points, series]);

  const maxY = Math.max(1, ...values.flat());
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const stepX = points.length > 1 ? innerW / (points.length - 1) : innerW;

  const x = (i: number) => pad.left + i * stepX;
  const y = (v: number) => pad.top + innerH - (v / maxY) * innerH;

  // Y o'qi uchun 4 ta yumaloq bo'linma
  const ticks = useMemo(() => {
    const t: number[] = [];
    for (let i = 0; i <= 3; i++) t.push(Math.round((maxY / 3) * i));
    return [...new Set(t)];
  }, [maxY]);

  if (!points.length) {
    return <p className="text-sm text-slate-400 py-8 text-center">Ma'lumot yo'q.</p>;
  }

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
      >
        {/* Gorizontal to'r chiziqlari */}
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(t)}
              y2={y(t)}
              stroke="#e2e8f0"
              strokeWidth={1}
            />
            <text x={pad.left - 6} y={y(t) + 4} textAnchor="end" fontSize={10} fill="#94a3b8">
              {t}
            </text>
          </g>
        ))}

        {/* Sana yorliqlari — har ~5 kunda bitta (zichlikka qarab) */}
        {points.map((p, i) => {
          const every = Math.max(1, Math.ceil(points.length / 8));
          if (i % every !== 0 && i !== points.length - 1) return null;
          return (
            <text
              key={p.date}
              x={x(i)}
              y={height - 6}
              textAnchor="middle"
              fontSize={10}
              fill="#94a3b8"
            >
              {fmtDay(p.date)}
            </text>
          );
        })}

        {/* Seriya chiziqlari */}
        {series.map((s, si) => {
          const d = points
            .map((_, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(values[i][si]).toFixed(1)}`)
            .join(" ");
          return <path key={s.key as string} d={d} fill="none" stroke={s.color} strokeWidth={2} />;
        })}

        {/* Hover: vertikal chiziq + nuqtalar */}
        {hover != null && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={pad.top}
              y2={pad.top + innerH}
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            {series.map((s, si) => (
              <circle
                key={s.key as string}
                cx={x(hover)}
                cy={y(values[hover][si])}
                r={3.5}
                fill={s.color}
              />
            ))}
          </g>
        )}

        {/* Hoverni ushlash uchun ko'rinmas kengaytirilgan zonalar */}
        {points.map((_, i) => (
          <rect
            key={i}
            x={x(i) - stepX / 2}
            y={0}
            width={stepX}
            height={height}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>

      {/* Legend + hover qiymatlari */}
      <div className="flex flex-wrap items-center gap-4 mt-1 text-xs text-slate-600">
        {series.map((s, si) => (
          <span key={s.key as string} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-0.5 rounded" style={{ background: s.color }} />
            {s.label}
            {hover != null && (
              <b className="text-slate-800">{values[hover][si]}</b>
            )}
          </span>
        ))}
        {hover != null && (
          <span className="text-slate-400">{fmtDay(points[hover].date)}</span>
        )}
      </div>
    </div>
  );
}

const REASON_CATEGORY_LABELS: Record<string, string> = {
  no_answer: "Mijoz ko'tarmadi",
  no_base: "Lid/baza tugadi",
  tech: "Texnik muammo",
  meeting: "Yig'ilish/band",
  other: "Boshqa",
};

export default function Statistics() {
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [summary, setSummary] = useState<OperatorSummary | null>(null);
  const [period, setPeriod] = useState<string>("week");
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .statsOverview(30)
      .then(setOverview)
      .catch((e) => {
        const status = e instanceof ApiError ? e.status : 0;
        setError(status === 403 ? "Bu bo'lim faqat rahbarlar uchun." : "Yuklashda xatolik.");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setSummaryLoading(true);
    api
      .operatorSummary(period)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setSummaryLoading(false));
  }, [period]);

  if (loading) return <div className="p-8 text-center text-slate-500">Yuklanmoqda...</div>;
  if (error) return <div className="bg-white rounded-lg shadow p-6 text-slate-600">{error}</div>;
  if (!overview) return null;

  const last = overview.series[overview.series.length - 1];
  const totals30 = overview.series.reduce(
    (acc, p) => ({
      calls: acc.calls + p.calls,
      talk: acc.talk + p.talk_sec,
      leads: acc.leads + p.leads,
      visits: acc.visits + p.visits,
    }),
    { calls: 0, talk: 0, leads: 0, visits: 0 }
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold">📊 Statistika</h2>
        <span className="text-xs text-slate-400">
          {fmtDay(overview.date_from)} – {fmtDay(overview.date_to)} · ma'lumot fon snapshotlaridan
        </span>
      </div>

      {/* Yuqori kartalar — 30 kunlik jami */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">📞 Qo'ng'iroqlar (30 kun)</div>
          <div className="text-2xl font-semibold">{totals30.calls}</div>
          <div className="text-xs text-slate-400 mt-0.5">bugun: {last?.calls ?? 0}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">🗣 Gaplashgan vaqt (30 kun)</div>
          <div className="text-2xl font-semibold">{fmtTalk(totals30.talk)}</div>
          <div className="text-xs text-slate-400 mt-0.5">bugun: {fmtTalk(last?.talk_sec ?? 0)}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">🧲 Ishlangan lidlar (30 kun)</div>
          <div className="text-2xl font-semibold">{totals30.leads}</div>
          <div className="text-xs text-slate-400 mt-0.5">bugun: {last?.leads ?? 0}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-xs text-slate-500">🏠 Tashriflar (30 kun)</div>
          <div className="text-2xl font-semibold">{totals30.visits}</div>
          <div className="text-xs text-slate-400 mt-0.5">bugun: {last?.visits ?? 0}</div>
        </div>
      </div>

      {/* Trend grafigi — sonlar */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-medium text-sm text-slate-600 mb-2">Kunlik trend (30 kun)</h3>
        <TrendChart
          points={overview.series}
          series={[
            { key: "calls", label: "Qo'ng'iroq", color: "#6366f1" },
            { key: "leads", label: "Lid", color: "#10b981" },
            { key: "visits", label: "Tashrif", color: "#f59e0b" },
          ]}
        />
      </div>

      {/* Trend grafigi — gaplashgan vaqt (daqiqa) */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-medium text-sm text-slate-600 mb-2">Gaplashgan vaqt, daqiqa (30 kun)</h3>
        <TrendChart
          height={140}
          points={overview.series}
          series={[
            {
              key: "talk_sec",
              label: "Daqiqa",
              color: "#0ea5e9",
              transform: (v) => Math.round(v / 60),
            },
          ]}
        />
      </div>

      {/* Operator kesimi */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <h3 className="font-medium text-sm text-slate-600">Operator kesimi</h3>
          <div className="flex gap-1">
            {Object.entries(PERIOD_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setPeriod(key)}
                className={`px-3 py-1.5 rounded text-sm ${
                  period === key ? "bg-indigo-600 text-white" : "hover:bg-slate-100 text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {summaryLoading ? (
          <p className="text-sm text-slate-400 py-4 text-center">Yuklanmoqda...</p>
        ) : !summary || summary.operators.length === 0 ? (
          <p className="text-sm text-slate-400 py-4 text-center">Bu davr uchun ma'lumot yo'q.</p>
        ) : (
          <>
            <p className="text-xs text-slate-400 mb-2">
              {fmtDay(summary.date_from)} – {fmtDay(summary.date_to)} · % — oldingi teng davrga
              ({fmtDay(summary.prev_from)} – {fmtDay(summary.prev_to)}) nisbatan
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b">
                    <th className="py-2 pr-3">Xodim</th>
                    <th className="py-2 pr-3">📞 Qo'ng'iroq</th>
                    <th className="py-2 pr-3">🗣 Gaplashgan</th>
                    <th className="py-2 pr-3">🧲 Lid</th>
                    <th className="py-2 pr-3">🏠 Tashrif</th>
                    <th className="py-2">✅ Vazifa</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.operators.map((op) => (
                    <tr key={op.responsible_id} className="border-b border-slate-100">
                      <td className="py-2 pr-3">
                        {op.name}
                        {!op.is_system_user && (
                          <span
                            className="ml-1 text-xs text-slate-400"
                            title="Tizim foydalanuvchisiga bog'lanmagan (CRM ID)"
                          >
                            ⚠
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        <b>{op.calls}</b>
                        {pctBadge(op.calls_pct)}
                      </td>
                      <td className="py-2 pr-3">{op.talk_sec ? fmtTalk(op.talk_sec) : "—"}</td>
                      <td className="py-2 pr-3">{op.leads}</td>
                      <td className="py-2 pr-3">{op.visits}</td>
                      <td className="py-2">
                        {op.tasks_total != null ? `${op.tasks_done}/${op.tasks_total}` : "—"}
                      </td>
                    </tr>
                  ))}
                  <tr className="font-medium">
                    <td className="py-2 pr-3">Jami</td>
                    <td className="py-2 pr-3">
                      {summary.totals.calls}
                      {pctBadge(summary.totals.calls_pct)}
                    </td>
                    <td className="py-2 pr-3">{fmtTalk(summary.totals.talk_sec)}</td>
                    <td className="py-2 pr-3">{summary.totals.leads}</td>
                    <td className="py-2 pr-3">{summary.totals.visits}</td>
                    <td className="py-2" />
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* Sabablar — oxirgi 7 kun */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-medium text-sm text-slate-600 mb-3">
          Orqada qolish sabablari (oxirgi 7 kun)
        </h3>
        {overview.reasons.length === 0 ? (
          <p className="text-sm text-slate-400">Bu davrda sabab so'ralmagan.</p>
        ) : (
          <div className="space-y-2">
            {overview.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-3 text-sm border-b border-slate-100 pb-2">
                <span className="text-slate-400 whitespace-nowrap">
                  {fmtDay(r.date)} {String(r.hour).padStart(2, "0")}:00
                </span>
                <span className="font-medium whitespace-nowrap">{r.user_name}</span>
                <span className="flex-1">
                  {r.reason ?? <i className="text-slate-400">Javob yozilmagan</i>}
                  {r.ai_category &&
                    r.reason &&
                    (REASON_CATEGORY_LABELS[r.ai_category] ?? r.ai_category) !== r.reason && (
                      <span className="text-slate-400">
                        {" "}· {REASON_CATEGORY_LABELS[r.ai_category] ?? r.ai_category}
                      </span>
                    )}
                  {r.raw_text && <span className="block text-xs text-slate-400 mt-0.5">«{r.raw_text}»</span>}
                </span>
                {r.verified === false && (
                  <span
                    className="px-1.5 py-0.5 rounded text-xs bg-rose-50 text-rose-700 whitespace-nowrap"
                    title={r.verify_note ?? ""}
                  >
                    ⚠ mos kelmadi
                  </span>
                )}
                {r.verified === true && (
                  <span
                    className="px-1.5 py-0.5 rounded text-xs bg-emerald-50 text-emerald-700 whitespace-nowrap"
                    title={r.verify_note ?? ""}
                  >
                    ✓ tasdiqlandi
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
