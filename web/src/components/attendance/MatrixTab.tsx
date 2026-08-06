/**
 * «Oylik jadval» tabi — davomat matritsasi (UX-C, HR ning asosiy quroli).
 *
 * UX2-W2/W3 yangilanishi:
 *  - Telefonda (md dan kichik) 1200px jadval o'rniga XODIM KARTALARI — har
 *    kartada oy xulosasi + mini oy-chizig'i; bosilsa xodim paneli (Sheet).
 *  - Desktop jadvali joriy oyda BUGUNGI ustunga avto-aylanadi.
 *  - Katak dialogi endi holatga mos AMALLAR beradi: kelmagan kunga «Sababli
 *    qilish» (shu yerda, sabab bilan), bugungi kutilayotganga «Eslatish»,
 *    hammasi uchun «Tahrirlash». Kelajak/dam kataklari bosilmaydi.
 *  - Ism qidiruvi + «faqat muammoli» filtri + jami ustunlarini bosib saralash.
 *  - Tayyorlik banneri «13 muammo» o'rniga TOIFALAB gapiradi.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bell, ChevronDown, ChevronRight, Pencil } from "lucide-react";
import { toast } from "sonner";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { type MatrixCell, type MatrixEmployee } from "@/lib/api";
import {
  useAttendanceMatrix,
  useAttendanceReadiness,
  useRecordExcusedDayForUser,
  useRemindAttendance,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

const WD_LETTERS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];

function wdIndex(iso: string): number {
  return (new Date(iso + "T00:00:00").getDay() + 6) % 7;
}

const EXCUSE_PRESETS = ["Kasallik", "Oilaviy holat", "Ta'til", "Xizmat safari"];

/** Katak «bo'sh»mi — bosganda ko'rsatadigan hech narsasi yo'q. */
function isInert(cell: MatrixCell): boolean {
  return (
    (cell.status === "future" || cell.status === "weekend") &&
    !cell.check_in &&
    cell.flags.length === 0
  );
}

/** Bitta matritsa katagi — 26px kvadrat, holat rangi + qisqa mazmun. */
function Cell({ cell, onClick }: { cell: MatrixCell; onClick: () => void }) {
  const titleParts = [STATUS_LABELS[cell.status]];
  if (cell.check_in) titleParts.push(`${cell.check_in} → ${cell.check_out ?? "—"}`);
  if (cell.late_minutes > 0) titleParts.push(`+${cell.late_minutes} daq`);
  if (cell.flags.length) titleParts.push("⚠");
  const inert = isInert(cell);

  return (
    <button
      type="button"
      onClick={inert ? undefined : onClick}
      disabled={inert}
      title={titleParts.join(" · ")}
      className={cn(
        "relative mx-auto flex h-[26px] w-[26px] items-center justify-center overflow-hidden rounded-md text-[10px] font-bold tabular-nums focus-visible:ring-2 focus-visible:ring-primary",
        !inert && "transition-transform hover:scale-110",
        inert && "cursor-default",
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

type SortKey = "present" | "late" | "absent" | "worked";

export default function MatrixTab({
  active,
  canEdit,
  isDasturchi,
}: {
  active: boolean;
  canEdit: boolean;
  isDasturchi: boolean;
}) {
  // A8: oy URLda (?month=2026-07) — sahifa yangilansa/havola ulashilsa saqlanadi.
  const [searchParams, setSearchParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(searchParams.get("month") ?? "")
    ? (searchParams.get("month") as string)
    : currentMonthKey();
  const setMonth = (m: string) =>
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set("month", m);
      return p;
    });
  // A15: drawer endi ID saqlaydi — oy almashsa panel ma'lumoti ham yangilanadi
  // (ilgari bosilgan paytdagi obyekt muzlab qolardi).
  const [drawerId, setDrawerId] = useState<number | null>(null);
  const [cellDialog, setCellDialog] = useState<{ emp: MatrixEmployee; cell: MatrixCell } | null>(
    null
  );
  const [editPreset, setEditPreset] = useState<EditPreset | null>(null);
  // UX2-qoldiq #2: «Yozuv qo'shish» endi matritsa ustida ham — ilgari faqat
  // akkordeon ichida 9 bosish chuqurlikda edi.
  const [addOpen, setAddOpen] = useState(false);
  const [readinessOpen, setReadinessOpen] = useState(false);
  const [recordsOpen, setRecordsOpen] = useState(false);
  // A11: qidiruv/filtr/saralash
  const [q, setQ] = useState("");
  const [onlyProblem, setOnlyProblem] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  // A6: katak dialogidagi «Sababli qilish» mini-formasi
  const [excuseReason, setExcuseReason] = useState("");

  const matrixQuery = useAttendanceMatrix(month, undefined, active);
  const recordExcused = useRecordExcusedDayForUser();
  const remind = useRemindAttendance();
  const data = matrixQuery.data;
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // M1: joriy oyda bugungi ustun ko'rinishga avto-aylantiriladi (oy oxirida
  // rahbar har safar qo'lda 31 kunlik jadvalni surishi shart emas).
  useEffect(() => {
    if (!data?.today || !data.days.includes(data.today)) return;
    const th = scrollRef.current?.querySelector<HTMLElement>("[data-today-col]");
    th?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [data]);

  // Tayyorlik banneri — tanlangan oy davri bilan (yig'iq, faqat muammo soni).
  const [y, m] = month.split("-").map(Number);
  const monthStart = `${month}-01`;
  const monthEnd = `${month}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
  const readinessQuery = useAttendanceReadiness(
    { date_from: monthStart, date_to: monthEnd },
    active
  );
  const readiness = readinessQuery.data;
  // A7: «13 muammo» nima ekani tushunarsiz edi — endi TOIFALAB aytiladi.
  const issueParts = useMemo(() => {
    if (!readiness) return [] as string[];
    const parts: string[] = [];
    if (readiness.no_schedule.length) parts.push(`${readiness.no_schedule.length} xodimda jadval yo'q`);
    if (readiness.open_checkouts.length) parts.push(`${readiness.open_checkouts.length} kun yopilmagan`);
    if (readiness.auto_closed.length) parts.push(`${readiness.auto_closed.length} kun avto-yopilgan`);
    if (readiness.pending_excused.length) parts.push(`${readiness.pending_excused.length} sababli kutmoqda`);
    if (readiness.no_face.length) parts.push(`${readiness.no_face.length} xodimda yuz yo'q`);
    return parts;
  }, [readiness]);

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

  // A11: filtr + saralash (mijoz tomonida — ro'yxat kichik).
  const employees = useMemo(() => {
    let list = data?.employees ?? [];
    const query = q.trim().toLowerCase();
    if (query) list = list.filter((e) => e.full_name.toLowerCase().includes(query));
    if (onlyProblem)
      list = list.filter((e) => e.totals.late_count > 0 || e.totals.absent_days > 0);
    if (sortKey) {
      const val = (e: MatrixEmployee) =>
        sortKey === "present"
          ? e.totals.present_days
          : sortKey === "late"
            ? e.totals.late_minutes
            : sortKey === "absent"
              ? e.totals.absent_days
              : e.totals.worked_hours;
      list = [...list].sort((a, b) => val(b) - val(a));
    }
    return list;
  }, [data, q, onlyProblem, sortKey]);

  const drawerEmp = drawerId != null ? (data?.employees.find((e) => e.user_id === drawerId) ?? null) : null;

  function sortHeader(key: SortKey, label: string, hint: string) {
    return (
      <th
        className={cn(
          "cursor-pointer select-none border-b border-slate-200 px-2 py-1 text-center font-semibold text-slate-500 hover:text-primary",
          sortKey === key && "text-primary underline"
        )}
        title={`${hint} — saralash uchun bosing`}
        onClick={() => setSortKey((k) => (k === key ? null : key))}
      >
        {label}
      </th>
    );
  }

  function openExcuse(emp: MatrixEmployee, cell: MatrixCell) {
    const reason = excuseReason.trim();
    if (reason.length < 3) {
      toast.error("Sababni yozing (kamida 3 belgi).");
      return;
    }
    recordExcused.mutate(
      { user_id: emp.user_id, reason, date: cell.date },
      {
        onSuccess: () => {
          toast.success(`${emp.full_name.trim()} — ${cell.date} sababli deb belgilandi.`);
          setCellDialog(null);
          setExcuseReason("");
        },
      }
    );
  }

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
            <span>
              ⚠️ <b>{issueParts.join(" · ")}</b> — tafsilot uchun bosing
            </span>
          </button>
          {readinessOpen && (
            <div className="border-t border-amber-200 p-3">
              <ReadinessSection
                dateFrom={monthStart}
                dateTo={monthEnd}
                onFixDay={
                  canEdit
                    ? (it) =>
                        it.date &&
                        setEditPreset({
                          userId: it.user_id,
                          userName: it.full_name,
                          date: it.date,
                          checkIn: null,
                          checkOut: null,
                          note: null,
                        })
                    : undefined
                }
              />
            </div>
          )}
        </div>
      )}

      {/* Oy tanlagich + qidiruv + legend */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthNav month={month} onChange={setMonth} />
        {/* B18: legend telefonda joy yemasin — faqat md+ da ko'rinadi
            (mobil kartalarda holat matn bilan yoziladi). */}
        <div className="hidden flex-wrap items-center gap-3 text-xs text-slate-600 md:flex">
          {LEGEND.map((l) => (
            <span key={l.status} className="inline-flex items-center gap-1.5">
              <span className={cn("h-3 w-3 rounded", MATRIX_CELL_CLS[l.status])} />
              {l.label}
            </span>
          ))}
          {/* B2: bayroq belgisi ham legendda */}
          <span className="inline-flex items-center gap-1.5">
            <span className="relative h-3 w-3 rounded bg-slate-100">
              <span className="absolute right-0 top-0 h-0 w-0 border-l-[6px] border-t-[6px] border-l-transparent border-t-amber-700" />
            </span>
            Avto/qo'lda
          </span>
        </div>
      </div>

      {/* A11: qidiruv + muammoli filtri */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Xodim qidirish..."
          className="h-8 w-48"
        />
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={onlyProblem}
            onChange={(e) => setOnlyProblem(e.target.checked)}
            className="h-3.5 w-3.5 accent-rose-600"
          />
          Faqat muammoli (kechikkan/kelmagan)
        </label>
        {sortKey && (
          <button
            type="button"
            className="text-xs text-primary underline"
            onClick={() => setSortKey(null)}
          >
            saralashni tozalash
          </button>
        )}
        {canEdit && (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto h-8"
            onClick={() => setAddOpen(true)}
          >
            + Yozuv qo'shish
          </Button>
        )}
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
      ) : !data || employees.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400">
          {q || onlyProblem
            ? "Filtrga mos xodim topilmadi — qidiruvni tozalab ko'ring."
            : "Bu oyda ko'rsatadigan xodim yo'q."}
        </div>
      ) : (
        <>
          {/* A1: MOBIL ko'rinish — xodim kartalari (jadval telefonga sig'maydi).
              Kartani bosish — xodim paneli (7 ustunli kalendar u yerda). */}
          <div className="space-y-2 md:hidden">
            {employees.map((emp) => (
              <button
                key={emp.user_id}
                type="button"
                className={cn(
                  "w-full rounded-xl border border-slate-200 bg-white p-3 text-left transition-colors hover:border-primary/40",
                  matrixQuery.isPlaceholderData && "opacity-60"
                )}
                onClick={() => setDrawerId(emp.user_id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{emp.full_name.trim()}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  ✅ {emp.totals.present_days} kun
                  {emp.totals.late_count > 0 && (
                    <span className="text-amber-600">
                      {" "}· ⏱ {emp.totals.late_count} marta ({emp.totals.late_minutes} daq)
                    </span>
                  )}
                  {emp.totals.absent_days > 0 && (
                    <span className="text-rose-600"> · ✕ {emp.totals.absent_days} kun</span>
                  )}
                  {" "}· {emp.totals.worked_hours} soat
                </div>
                {/* Mini oy-chizig'i — oyning umumiy manzarasi bitta qarashda */}
                <div className="mt-2 flex flex-wrap gap-[3px]">
                  {emp.cells.map((c) => (
                    <span
                      key={c.date}
                      className={cn(
                        "h-2.5 w-2.5 rounded-[3px]",
                        MATRIX_CELL_CLS[c.status],
                        c.date === data.today && "ring-1 ring-blue-400 ring-offset-1"
                      )}
                    />
                  ))}
                </div>
              </button>
            ))}
          </div>

          {/* Desktop jadvali */}
          <div
            ref={scrollRef}
            className={cn(
              "hidden overflow-x-auto rounded-xl border border-slate-200 bg-white transition-opacity md:block",
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
                      {...(d.isToday ? { "data-today-col": true } : {})}
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
                  {sortHeader("present", "Kelgan", "Kelgan kunlar soni")}
                  {sortHeader("late", "Kech", "Kechikish: marta/jami daqiqa")}
                  {sortHeader("absent", "Yo'q", "Sababsiz kelmagan kunlar")}
                  {sortHeader("worked", "Soat", "Ishlangan soat (oy bo'yicha)")}
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <tr key={emp.user_id}>
                    <td className="sticky left-0 z-[1] border-b border-r border-slate-100 bg-white px-1 py-0.5">
                      <button
                        type="button"
                        className="w-full truncate rounded px-2 py-1 text-left text-[13px] font-medium hover:bg-slate-50 hover:text-primary"
                        onClick={() => setDrawerId(emp.user_id)}
                        title="Xodim panelini ochish"
                      >
                        {emp.full_name.trim()}
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
                      title={
                        emp.totals.late_count > 0
                          ? `${emp.totals.late_count} marta kechikkan, jami ${emp.totals.late_minutes} daqiqa`
                          : "Kechikish yo'q"
                      }
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
        </>
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

      {/* Katak tafsiloti dialogi — A6: holatga mos amallar */}
      <Dialog
        open={cellDialog !== null}
        onOpenChange={(o) => {
          if (!o) {
            setCellDialog(null);
            setExcuseReason("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          {cellDialog && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center justify-between gap-3 pr-6">
                  <span>
                    {cellDialog.emp.full_name.trim()} —{" "}
                    {Number(cellDialog.cell.date.slice(8, 10))}-
                    {Number(cellDialog.cell.date.slice(5, 7))}
                  </span>
                  <StatusBadge kind="attendance" status={cellDialog.cell.status} />
                </DialogTitle>
              </DialogHeader>
              <CellDetail cell={cellDialog.cell} />

              {/* A6: kelmagan kun uchun — sababli qilish (shu yerda) */}
              {canEdit && cellDialog.cell.status === "absent" && (
                <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
                  <div className="mb-2 text-xs font-medium text-sky-800">
                    Sababli kun deb belgilash:
                  </div>
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {EXCUSE_PRESETS.map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-xs transition-colors",
                          excuseReason === r
                            ? "border-sky-400 bg-sky-100 text-sky-800"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        )}
                        onClick={() => setExcuseReason(r)}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={excuseReason}
                      onChange={(e) => setExcuseReason(e.target.value)}
                      placeholder="Sabab..."
                      className="h-8 bg-white text-sm"
                    />
                    <Button
                      size="sm"
                      className="h-8 shrink-0 bg-sky-600 hover:bg-sky-700"
                      disabled={recordExcused.isPending}
                      onClick={() => openExcuse(cellDialog.emp, cellDialog.cell)}
                    >
                      Sababli
                    </Button>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {/* A6: bugungi «kutilmoqda» — eslatish mumkin */}
                {cellDialog.cell.status === "pending" && (
                  <Button
                    variant="outline"
                    className="border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                    disabled={remind.isPending}
                    onClick={() =>
                      remind.mutate(cellDialog.emp.user_id, {
                        onSuccess: (r) =>
                          toast.success(
                            `${cellDialog.emp.full_name.trim()}ga eslatma yuborildi (bugun ${r.sent_today}-marta).`
                          ),
                      })
                    }
                  >
                    <Bell className="mr-2 h-4 w-4" />
                    Eslatish
                  </Button>
                )}
                {canEdit && cellDialog.cell.status !== "future" && (
                  <Button
                    className="flex-1"
                    onClick={() => {
                      setEditPreset({
                        userId: cellDialog.emp.user_id,
                        userName: cellDialog.emp.full_name,
                        date: cellDialog.cell.date,
                        checkIn: cellDialog.cell.check_in,
                        checkOut: cellDialog.cell.check_out,
                        note: cellDialog.cell.note,
                        scheduleStart: cellDialog.cell.schedule_start,
                        scheduleEnd: cellDialog.cell.schedule_end,
                      });
                      setCellDialog(null);
                    }}
                  >
                    <Pencil className="mr-2 h-4 w-4" />
                    Tahrirlash
                  </Button>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Katakdan ochilgan tahrirlash — saqlangach matritsa avtomatik yangilanadi
          (mutation ["attendance"] kalitini invalidatsiya qiladi). */}
      {canEdit && (
        <EditAttendanceDialog
          open={editPreset !== null || addOpen}
          row={null}
          preset={editPreset}
          onClose={() => {
            setEditPreset(null);
            setAddOpen(false);
          }}
          silent={isDasturchi}
        />
      )}

      <EmployeeDrawer
        employee={drawerEmp}
        month={month}
        onClose={() => setDrawerId(null)}
        onEditDay={
          canEdit
            ? (emp, cell) => {
                setDrawerId(null);
                setEditPreset({
                  userId: emp.user_id,
                  userName: emp.full_name,
                  date: cell.date,
                  checkIn: cell.check_in,
                  checkOut: cell.check_out,
                  note: cell.note,
                  scheduleStart: cell.schedule_start,
                  scheduleEnd: cell.schedule_end,
                });
              }
            : undefined
        }
      />
    </div>
  );
}
