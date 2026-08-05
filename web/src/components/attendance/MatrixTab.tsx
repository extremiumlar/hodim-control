/**
 * «Oylik jadval» tabi — davomat matritsasi (UX-C, HR ning asosiy quroli).
 *
 * Qatorlar — xodimlar, ustunlar — kunlar; butun oy BITTA so'rovda
 * (`GET /attendance/matrix`). 300-qatorlik flat ro'yxat o'rniga oylik manzara
 * bitta qarashda: kim qachon kechikkan, kim kelmagan, qaysi kun sababli.
 *
 * O'zaro ta'sir: katak bosilsa — kun tafsiloti dialogi (+ Tahrirlash);
 * ism bosilsa — xodim paneli (Sheet). «Yozuvlar» xom ro'yxati pastda,
 * yig'iq holda qoladi (kerak bo'lganda ochiladi).
 */
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Pencil } from "lucide-react";
import EditAttendanceDialog, {
  type EditPreset,
} from "@/components/attendance/EditAttendanceDialog";
import EmployeeDrawer from "@/components/attendance/EmployeeDrawer";
import { CellDetail } from "@/components/attendance/MonthCalendar";
import MonthNav, { currentMonthKey } from "@/components/attendance/MonthNav";
import ReadinessSection from "@/components/attendance/ReadinessSection";
import RecordsSection from "@/components/attendance/RecordsSection";
import { LEGEND, MATRIX_CELL_CLS, STATUS_LABELS } from "@/components/attendance/cellStyles";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { type MatrixCell, type MatrixEmployee } from "@/lib/api";
import { useAttendanceMatrix, useAttendanceReadiness } from "@/lib/queries";
import { cn } from "@/lib/utils";

const WD_LETTERS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function wdIndex(iso: string): number {
  return (new Date(iso + "T00:00:00").getDay() + 6) % 7;
}

/** Bitta matritsa katagi — 26px kvadrat, holat rangi + qisqa mazmun. */
function Cell({ cell, onClick }: { cell: MatrixCell; onClick: () => void }) {
  const titleParts = [STATUS_LABELS[cell.status]];
  if (cell.check_in) titleParts.push(`${cell.check_in} → ${cell.check_out ?? "—"}`);
  if (cell.late_minutes > 0) titleParts.push(`+${cell.late_minutes} daq`);
  if (cell.flags.length) titleParts.push("⚠");

  return (
    <button
      type="button"
      onClick={onClick}
      title={titleParts.join(" · ")}
      className={cn(
        "relative mx-auto flex h-[26px] w-[26px] items-center justify-center overflow-hidden rounded-md text-[10px] font-bold tabular-nums transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-primary",
        MATRIX_CELL_CLS[cell.status]
      )}
    >
      {cell.status === "present" && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
      {cell.status === "late" && (cell.late_minutes > 99 ? "99" : cell.late_minutes)}
      {cell.status === "absent" && "✕"}
      {cell.status === "excused" && "S"}
      {cell.status === "pending" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />
      )}
      {/* Burchak belgisi: avtomatik yopilgan / qo'lda tuzatilgan kun */}
      {cell.flags.length > 0 && cell.status !== "future" && (
        <span className="absolute right-0 top-0 h-0 w-0 border-l-[7px] border-t-[7px] border-l-transparent border-t-amber-700" />
      )}
    </button>
  );
}

export default function MatrixTab({
  active,
  canEdit,
  isDasturchi,
}: {
  active: boolean;
  canEdit: boolean;
  isDasturchi: boolean;
}) {
  const [month, setMonth] = useState(currentMonthKey());
  const [drawerEmp, setDrawerEmp] = useState<MatrixEmployee | null>(null);
  const [cellDialog, setCellDialog] = useState<{ emp: MatrixEmployee; cell: MatrixCell } | null>(
    null
  );
  const [editPreset, setEditPreset] = useState<EditPreset | null>(null);
  const [readinessOpen, setReadinessOpen] = useState(false);
  const [recordsOpen, setRecordsOpen] = useState(false);

  const matrixQuery = useAttendanceMatrix(month, undefined, active);
  const data = matrixQuery.data;

  // Tayyorlik banneri — tanlangan oy davri bilan (yig'iq, faqat muammo soni).
  const [y, m] = month.split("-").map(Number);
  const monthStart = `${month}-01`;
  const monthEnd = `${month}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
  const readinessQuery = useAttendanceReadiness(
    { date_from: monthStart, date_to: monthEnd },
    active
  );
  const readiness = readinessQuery.data;
  const issueCount = readiness
    ? readiness.no_schedule.length +
      readiness.open_checkouts.length +
      readiness.auto_closed.length +
      readiness.pending_excused.length +
      readiness.no_face.length
    : 0;

  const dayHeaders = useMemo(
    () =>
      (data?.days ?? []).map((d) => ({
        iso: d,
        num: Number(d.slice(8, 10)),
        wd: wdIndex(d),
        isToday: d === data?.today,
      })),
    [data]
  );

  return (
    <div className="space-y-4">
      {/* Tayyorlik banneri — muammo bo'lsagina */}
      {readiness && !readiness.ok && (
        <div className="rounded-lg border border-amber-200 bg-amber-50">
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-amber-800"
            onClick={() => setReadinessOpen((o) => !o)}
          >
            {readinessOpen ? (
              <ChevronDown className="h-4 w-4 shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0" />
            )}
            ⚠️ <b>{issueCount} muammo</b> — bu oy hisobi uchun ma'lumot hali to'liq tayyor emas
            (bosib ko'ring)
          </button>
          {readinessOpen && (
            <div className="border-t border-amber-200 p-3">
              <ReadinessSection dateFrom={monthStart} dateTo={monthEnd} />
            </div>
          )}
        </div>
      )}

      {/* Oy tanlagich + legend */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthNav month={month} onChange={setMonth} />
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          {LEGEND.map((l) => (
            <span key={l.status} className="inline-flex items-center gap-1.5">
              <span className={cn("h-3 w-3 rounded", MATRIX_CELL_CLS[l.status])} />
              {l.label}
            </span>
          ))}
        </div>
      </div>

      {/* Matritsa */}
      {matrixQuery.isLoading ? (
        <Skeleton className="h-72 w-full rounded-xl" />
      ) : matrixQuery.error ? (
        <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {matrixQuery.error.message}
          <Button variant="outline" size="sm" onClick={() => matrixQuery.refetch()}>
            Qayta urinish
          </Button>
        </div>
      ) : !data || data.employees.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400">
          Bu oyda ko'rsatadigan xodim yo'q.
        </div>
      ) : (
        <div
          className={cn(
            "overflow-x-auto rounded-xl border border-slate-200 bg-white transition-opacity",
            matrixQuery.isPlaceholderData && "opacity-60"
          )}
        >
          <table className="w-full border-separate border-spacing-0 text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 z-[2] min-w-[130px] border-b border-r border-slate-200 bg-slate-50 px-3 py-1.5 text-left font-semibold text-slate-600">
                  Xodim
                </th>
                {dayHeaders.map((d) => (
                  <th
                    key={d.iso}
                    className={cn(
                      "min-w-[30px] border-b border-slate-200 px-0.5 py-1 text-center font-semibold tabular-nums",
                      d.wd >= 5 ? "text-rose-400" : "text-slate-500",
                      d.isToday && "bg-blue-50"
                    )}
                  >
                    {d.num}
                    <span className="block text-[9px] font-medium text-slate-400">
                      {WD_LETTERS[d.wd]}
                    </span>
                  </th>
                ))}
                <th className="border-b border-l border-slate-200 px-2 py-1 text-center font-semibold text-slate-500">
                  Kelgan
                </th>
                <th className="border-b border-slate-200 px-2 py-1 text-center font-semibold text-slate-500">
                  Kech
                </th>
                <th className="border-b border-slate-200 px-2 py-1 text-center font-semibold text-slate-500">
                  Yo'q
                </th>
                <th className="border-b border-slate-200 px-2 py-1 text-center font-semibold text-slate-500">
                  Soat
                </th>
              </tr>
            </thead>
            <tbody>
              {data.employees.map((emp) => (
                <tr key={emp.user_id}>
                  <td className="sticky left-0 z-[1] border-b border-r border-slate-100 bg-white px-1 py-0.5">
                    <button
                      type="button"
                      className="w-full truncate rounded px-2 py-1 text-left text-[13px] font-medium hover:bg-slate-50 hover:text-primary"
                      onClick={() => setDrawerEmp(emp)}
                      title="Xodim panelini ochish"
                    >
                      {emp.full_name}
                    </button>
                  </td>
                  {emp.cells.map((c) => (
                    <td
                      key={c.date}
                      className={cn(
                        "border-b border-slate-100 px-0.5 py-1",
                        c.date === data.today && "bg-blue-50"
                      )}
                    >
                      <Cell cell={c} onClick={() => setCellDialog({ emp, cell: c })} />
                    </td>
                  ))}
                  <td className="border-b border-l border-slate-100 px-2 text-center font-semibold tabular-nums">
                    {emp.totals.present_days}
                  </td>
                  <td
                    className={cn(
                      "border-b border-slate-100 px-2 text-center font-semibold tabular-nums whitespace-nowrap",
                      emp.totals.late_count > 0 ? "text-rose-600" : "text-slate-400"
                    )}
                  >
                    {emp.totals.late_count > 0
                      ? `${emp.totals.late_count}/${emp.totals.late_minutes}d`
                      : "—"}
                  </td>
                  <td
                    className={cn(
                      "border-b border-slate-100 px-2 text-center font-semibold tabular-nums",
                      emp.totals.absent_days > 0 ? "text-rose-600" : "text-slate-400"
                    )}
                  >
                    {emp.totals.absent_days || "—"}
                  </td>
                  <td className="border-b border-slate-100 px-2 text-center font-semibold tabular-nums">
                    {emp.totals.worked_hours}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Xom yozuvlar — yig'iq bo'lim (kerak bo'lganda ochiladi) */}
      <div className="rounded-xl border border-slate-200 bg-white">
        <button
          type="button"
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-slate-600"
          onClick={() => setRecordsOpen((o) => !o)}
        >
          {recordsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Yozuvlar ro'yxati (xom qatorlar, qidiruv/filtr bilan)
        </button>
        {recordsOpen && (
          <div className="border-t border-slate-100 p-4">
            <RecordsSection canEdit={canEdit} isDasturchi={isDasturchi} />
          </div>
        )}
      </div>

      {/* Katak tafsiloti dialogi */}
      <Dialog open={cellDialog !== null} onOpenChange={(o) => !o && setCellDialog(null)}>
        <DialogContent className="max-w-sm">
          {cellDialog && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center justify-between gap-3 pr-6">
                  <span>
                    {cellDialog.emp.full_name} —{" "}
                    {Number(cellDialog.cell.date.slice(8, 10))}-
                    {Number(cellDialog.cell.date.slice(5, 7))}
                  </span>
                  <StatusBadge kind="attendance" status={cellDialog.cell.status} />
                </DialogTitle>
              </DialogHeader>
              <CellDetail cell={cellDialog.cell} />
              {canEdit && cellDialog.cell.status !== "future" && (
                <Button
                  onClick={() => {
                    setEditPreset({
                      userId: cellDialog.emp.user_id,
                      userName: cellDialog.emp.full_name,
                      date: cellDialog.cell.date,
                      checkIn: cellDialog.cell.check_in,
                      checkOut: cellDialog.cell.check_out,
                      note: cellDialog.cell.note,
                    });
                    setCellDialog(null);
                  }}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  Tahrirlash
                </Button>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Katakdan ochilgan tahrirlash — saqlangach matritsa avtomatik yangilanadi
          (mutation ["attendance"] kalitini invalidatsiya qiladi). */}
      {canEdit && (
        <EditAttendanceDialog
          open={editPreset !== null}
          row={null}
          preset={editPreset}
          onClose={() => setEditPreset(null)}
          silent={isDasturchi}
        />
      )}

      <EmployeeDrawer employee={drawerEmp} month={month} onClose={() => setDrawerEmp(null)} />
    </div>
  );
}
