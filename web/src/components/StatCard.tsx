import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** Ko'rsatkich kartasi: raqam + yorliq + ikonka + ixtiyoriy trend (% o'zgarish). */
export default function StatCard({
  label,
  value,
  icon: Icon,
  trend,
  hint,
  warn = false,
}: {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  trend?: number | null; // % o'zgarish (masalan +12 yoki -5); null/undefined — ko'rsatilmaydi
  hint?: string;
  warn?: boolean; // qiymatni qizil qilib urg'ulash (masalan kechikkanlar > 0)
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-xs text-slate-500">{label}</div>
          <div className={cn("mt-1 text-2xl font-semibold", warn ? "text-rose-600" : "text-slate-800")}>
            {value}
            {trend != null && (
              <span
                className={cn(
                  "ml-2 align-middle rounded px-1.5 py-0.5 text-xs font-medium",
                  trend > 0
                    ? "bg-emerald-50 text-emerald-700"
                    : trend < 0
                      ? "bg-rose-50 text-rose-700"
                      : "bg-slate-100 text-slate-600"
                )}
              >
                {trend > 0 ? "+" : ""}
                {trend}%
              </span>
            )}
          </div>
          {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
        </div>
        {Icon && (
          <div className="rounded-lg bg-primary/10 p-2 text-primary">
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
    </div>
  );
}
