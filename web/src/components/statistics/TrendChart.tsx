import { useMemo, useState } from "react";
import { type StatsSeriesPoint } from "@/lib/api";

/**
 * Sof SVG trend grafigi (tashqi kutubxonasiz). Bir nechta seriya bitta o'qda;
 * talk_sec kabi boshqa masshtabdagi seriya alohida chizilmaydi — chaqiruvchi
 * uni daqiqaga o'girib alohida chart beradi.
 */

export interface ChartSeries {
  key: keyof StatsSeriesPoint;
  label: string;
  color: string;
  transform?: (v: number) => number;
}

function fmtDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

export default function TrendChart({
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
    return <p className="py-8 text-center text-sm text-slate-400">Ma'lumot yo'q.</p>;
  }

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" onMouseLeave={() => setHover(null)}>
        {/* Gorizontal to'r chiziqlari */}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="#e2e8f0" strokeWidth={1} />
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
            <text key={p.date} x={x(i)} y={height - 6} textAnchor="middle" fontSize={10} fill="#94a3b8">
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
              <circle key={s.key as string} cx={x(hover)} cy={y(values[hover][si])} r={3.5} fill={s.color} />
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
      <div className="mt-1 flex flex-wrap items-center gap-4 text-xs text-slate-600">
        {series.map((s, si) => (
          <span key={s.key as string} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} />
            {s.label}
            {hover != null && <b className="text-slate-800">{values[hover][si]}</b>}
          </span>
        ))}
        {hover != null && <span className="text-slate-400">{fmtDay(points[hover].date)}</span>}
      </div>
    </div>
  );
}
