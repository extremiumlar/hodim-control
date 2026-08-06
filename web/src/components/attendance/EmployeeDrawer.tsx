/**
 * Xodim paneli — matritsada ism bosilganda o'ngdan ochiladigan Sheet (UX-C).
 *
 * Ma'lumot ALLAQACHON yuklangan matritsadan keladi (qo'shimcha so'rov yo'q):
 * oy statlari + kalendar + kun tafsiloti + profil havolasi.
 *
 * UX2-A15: panel endi boshi berk ko'cha emas — pastda AMALLAR qatori:
 * tanlangan kunni tuzatish, ish jadvalini sozlash, profil. Kalendarda kun
 * tanlanganda «Tuzatish» faollashadi (kontekst yo'qolmaydi).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarCog, ExternalLink, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { CellDetail, MonthCalendar } from "@/components/attendance/MonthCalendar";
import { monthLabel } from "@/components/attendance/MonthNav";
import type { MatrixCell, MatrixEmployee } from "@/lib/api";

function Totals({ emp }: { emp: MatrixEmployee }) {
  const t = emp.totals;
  const items: { label: string; value: string; warn?: boolean }[] = [
    { label: "Kelgan", value: `${t.present_days} kun` },
    {
      label: "Kechikish",
      value: t.late_count ? `${t.late_count} marta · ${t.late_minutes} daq` : "yo'q",
      warn: t.late_count > 0,
    },
    { label: "Kelmagan", value: `${t.absent_days} kun`, warn: t.absent_days > 0 },
    { label: "Ishlangan", value: `${t.worked_hours} soat` },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map((i) => (
        <div key={i.label} className="rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-[11px] text-slate-500">{i.label}</div>
          <div className={"text-sm font-semibold tabular-nums " + (i.warn ? "text-rose-600" : "")}>
            {i.value}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function EmployeeDrawer({
  employee,
  month,
  onClose,
  onEditDay,
}: {
  employee: MatrixEmployee | null;
  month: string;
  onClose: () => void;
  /** Tanlangan kunni tuzatish (EditAttendanceDialog preset) — canEdit bo'lsagina. */
  onEditDay?: (emp: MatrixEmployee, cell: MatrixCell) => void;
}) {
  const [selected, setSelected] = useState<MatrixCell | null>(null);

  return (
    <Sheet
      open={employee !== null}
      onOpenChange={(open) => {
        if (!open) {
          setSelected(null);
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        {employee && (
          <div className="space-y-4">
            <div>
              <SheetTitle className="text-lg">{employee.full_name.trim()}</SheetTitle>
              <div className="text-sm text-slate-500">{monthLabel(month)}</div>
            </div>

            <Totals emp={employee} />

            <MonthCalendar
              cells={employee.cells}
              selected={selected?.date ?? null}
              onSelect={(c) => setSelected(selected?.date === c.date ? null : c)}
            />
            {selected && <CellDetail cell={selected} />}

            {/* A15: amallar qatori */}
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              {onEditDay && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!selected || selected.status === "future"}
                  title={
                    selected
                      ? "Tanlangan kunni tuzatish"
                      : "Avval kalendardan kunni tanlang"
                  }
                  onClick={() => selected && onEditDay(employee, selected)}
                >
                  <Pencil className="mr-1.5 h-3.5 w-3.5" />
                  {selected
                    ? `${Number(selected.date.slice(8, 10))}-kunni tuzatish`
                    : "Kunni tuzatish"}
                </Button>
              )}
              <Button size="sm" variant="outline" asChild>
                <Link to={`/work-schedule?tab=bitta&user=${employee.user_id}`}>
                  <CalendarCog className="mr-1.5 h-3.5 w-3.5" />
                  Ish jadvali
                </Link>
              </Button>
              <Button size="sm" variant="outline" asChild>
                <Link to={`/employees/${employee.user_id}`}>
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                  Profil
                </Link>
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
