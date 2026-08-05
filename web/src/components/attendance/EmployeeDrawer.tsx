/**
 * Xodim paneli — matritsada ism bosilganda o'ngdan ochiladigan Sheet (UX-C).
 *
 * Ma'lumot ALLAQACHON yuklangan matritsadan keladi (qo'shimcha so'rov yo'q):
 * oy statlari + kalendar + kun tafsiloti + profil havolasi.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
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
}: {
  employee: MatrixEmployee | null;
  month: string;
  onClose: () => void;
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
              <SheetTitle className="text-lg">{employee.full_name}</SheetTitle>
              <div className="text-sm text-slate-500">{monthLabel(month)}</div>
            </div>

            <Totals emp={employee} />

            <MonthCalendar
              cells={employee.cells}
              selected={selected?.date ?? null}
              onSelect={(c) => setSelected(selected?.date === c.date ? null : c)}
            />
            {selected && <CellDetail cell={selected} />}

            <Link
              to={`/employees/${employee.user_id}`}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              Xodim profiliga o'tish
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
