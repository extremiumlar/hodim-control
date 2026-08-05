/**
 * Oy tanlagich: ‹ Avgust 2026 › — matritsa, xodim profili va xodimning o'z
 * kalendari uchun bitta komponent.
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const UZ_MONTHS = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];

export function currentMonthKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return `${UZ_MONTHS[m - 1]} ${y}`;
}

export default function MonthNav({
  month,
  onChange,
  /** Kelajak oyga o'tishni bloklash (xodim kalendari uchun — unga kelajak kerak emas). */
  maxMonth,
}: {
  month: string;
  onChange: (m: string) => void;
  maxMonth?: string;
}) {
  const nextDisabled = maxMonth != null && shiftMonth(month, 1) > maxMonth;
  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-0.5">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => onChange(shiftMonth(month, -1))}
        aria-label="Oldingi oy"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="min-w-[120px] text-center text-sm font-semibold">{monthLabel(month)}</span>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => onChange(shiftMonth(month, 1))}
        disabled={nextDisabled}
        aria-label="Keyingi oy"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
