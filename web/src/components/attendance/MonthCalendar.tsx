/**
 * Oylik kalendar — bitta xodimning bir oyi, 7 ustunli to'r (UX-C/D).
 *
 * UCH joyda ishlatiladi: rahbar matritsasidagi xodim paneli (drawer), xodim
 * profili sahifasi va xodimning o'z «Oylik davomatim» kartasi. BITTA komponent —
 * rang tili va kun tafsiloti hamma joyda bir xil bo'lishi uchun.
 *
 * 360px ekranga gorizontal skrollsiz sig'adi (aspect-square kataklar, gap-1).
 */
import { cn } from "@/lib/utils";
import type { MatrixCell } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { CALENDAR_DAY_CLS, FLAG_LABELS } from "@/components/attendance/cellStyles";

const WEEKDAYS_SHORT = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function weekdayIndex(iso: string): number {
  // Date.getDay(): 0=Yak ... 6=Sh -> bizga 0=Du ... 6=Ya kerak.
  return (new Date(iso + "T00:00:00").getDay() + 6) % 7;
}

export function MonthCalendar({
  cells,
  selected,
  onSelect,
}: {
  cells: MatrixCell[];
  selected?: string | null;
  onSelect?: (cell: MatrixCell) => void;
}) {
  if (!cells.length) return null;
  const leadingBlanks = weekdayIndex(cells[0].date);

  return (
    <div className="grid grid-cols-7 gap-1">
      {WEEKDAYS_SHORT.map((w, i) => (
        <div
          key={w}
          className={cn(
            "text-center text-[10px] font-semibold",
            i >= 5 ? "text-rose-400" : "text-slate-400"
          )}
        >
          {w}
        </div>
      ))}
      {Array.from({ length: leadingBlanks }).map((_, i) => (
        <div key={`b${i}`} />
      ))}
      {cells.map((c) => {
        const dayNum = Number(c.date.slice(8, 10));
        return (
          <button
            key={c.date}
            type="button"
            onClick={() => onSelect?.(c)}
            className={cn(
              "aspect-square rounded-lg text-xs font-semibold tabular-nums transition-shadow",
              CALENDAR_DAY_CLS[c.status],
              onSelect && "cursor-pointer hover:shadow",
              selected === c.date && "ring-2 ring-primary ring-offset-1"
            )}
            title={c.status === "late" ? `+${c.late_minutes} daqiqa kechikkan` : undefined}
          >
            {dayNum}
          </button>
        );
      })}
    </div>
  );
}

/** Tanlangan kun tafsiloti — kalendar ostida ko'rsatiladigan qatorlar. */
export function CellDetail({ cell }: { cell: MatrixCell }) {
  const [, m, d] = cell.date.split("-");
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
      <div className="mb-1.5 flex items-center justify-between">
        <b>
          {d}.{m}
        </b>
        <StatusBadge kind="attendance" status={cell.status} />
      </div>
      <div className="space-y-0.5 text-slate-600">
        {(cell.check_in || cell.check_out) && (
          <div className="tabular-nums">
            {cell.check_in ?? "—"} → {cell.check_out ?? "—"}
            {cell.worked_minutes > 0 && (
              <span className="ml-2 text-slate-400">
                {Math.round((cell.worked_minutes / 60) * 10) / 10} soat
              </span>
            )}
          </div>
        )}
        {cell.late_minutes > 0 && (
          <div className="text-rose-600">Kechikish: {cell.late_minutes} daqiqa</div>
        )}
        {cell.schedule_start && (
          <div className="text-xs text-slate-400">
            Jadval: {cell.schedule_start}–{cell.schedule_end}
          </div>
        )}
        {cell.note && <div className="text-xs text-slate-500">Izoh: {cell.note}</div>}
        {cell.flags.map((f) => (
          <div key={f} className="text-xs text-amber-700">
            ⚠ {FLAG_LABELS[f] ?? f}
          </div>
        ))}
      </div>
    </div>
  );
}
