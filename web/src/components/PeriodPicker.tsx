import { format, startOfMonth, subDays } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Davr tanlagichlar — Attendance, Statistics, Reports, AuditLogs bitta
 * komponentdan foydalanadi:
 *  - DateRangePicker: "dan/gacha" + tez tanlovlar (7 kun, 30 kun, Shu oy)
 *  - MonthPicker: oy tanlagich (kelajak oylar bloklangan)
 */

const iso = (d: Date) => format(d, "yyyy-MM-dd");

const PRESETS: { label: string; range: () => { from: string; to: string } }[] = [
  { label: "7 kun", range: () => ({ from: iso(subDays(new Date(), 6)), to: iso(new Date()) }) },
  { label: "30 kun", range: () => ({ from: iso(subDays(new Date(), 29)), to: iso(new Date()) }) },
  { label: "Shu oy", range: () => ({ from: iso(startOfMonth(new Date())), to: iso(new Date()) }) },
];

export function DateRangePicker({
  from,
  to,
  onChange,
  withPresets = true,
  className,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  withPresets?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Input
        type="date"
        value={from}
        max={to || undefined}
        onChange={(e) => onChange(e.target.value, to)}
        className="w-auto"
      />
      <span className="text-slate-400">—</span>
      <Input
        type="date"
        value={to}
        min={from || undefined}
        onChange={(e) => onChange(from, e.target.value)}
        className="w-auto"
      />
      {withPresets && (
        <div className="flex gap-1">
          {PRESETS.map((p) => {
            const r = p.range();
            const active = r.from === from && r.to === to;
            return (
              <Button
                key={p.label}
                type="button"
                size="sm"
                variant={active ? "default" : "ghost"}
                onClick={() => onChange(r.from, r.to)}
              >
                {p.label}
              </Button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function currentMonthKey(): string {
  return format(new Date(), "yyyy-MM");
}

export function MonthPicker({
  value,
  onChange,
  className,
}: {
  value: string; // "YYYY-MM"
  onChange: (month: string) => void;
  className?: string;
}) {
  return (
    <Input
      type="month"
      value={value}
      max={currentMonthKey()}
      onChange={(e) => onChange(e.target.value || currentMonthKey())}
      className={cn("w-auto", className)}
    />
  );
}
