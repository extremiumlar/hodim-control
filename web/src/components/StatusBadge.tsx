import { cn } from "@/lib/utils";

/**
 * Yagona status badge — davomat / vazifa / so'rov statuslari uchun bitta
 * rang xaritasi. "pending" ikki kontekstda har xil: vazifada ko'k
 * (jarayonda), so'rovda esa amber (qaror kutilmoqda) — shuning uchun kind.
 */
type Kind = "attendance" | "task" | "request";

const MAP: Record<Kind, Record<string, { text: string; cls: string }>> = {
  attendance: {
    present: { text: "Keldi", cls: "bg-emerald-100 text-emerald-700" },
    late: { text: "Kechikdi", cls: "bg-rose-100 text-rose-700" },
    absent: { text: "Kelmadi", cls: "bg-slate-200 text-slate-600" },
    weekend: { text: "Dam olish", cls: "bg-blue-100 text-blue-700" },
  },
  task: {
    pending: { text: "Kutilmoqda", cls: "bg-blue-100 text-blue-700" },
    done: { text: "Bajarildi", cls: "bg-emerald-100 text-emerald-700" },
    overdue: { text: "Muddati o'tgan", cls: "bg-rose-100 text-rose-700" },
    cancelled: { text: "Bekor qilingan", cls: "bg-slate-200 text-slate-600" },
  },
  request: {
    pending: { text: "Kutilmoqda", cls: "bg-amber-100 text-amber-700" },
    approved: { text: "Tasdiqlangan", cls: "bg-emerald-100 text-emerald-700" },
    rejected: { text: "Rad etilgan", cls: "bg-rose-100 text-rose-700" },
  },
};

export default function StatusBadge({
  kind,
  status,
  className,
}: {
  kind: Kind;
  status: string;
  className?: string;
}) {
  const entry = MAP[kind][status] ?? { text: status, cls: "bg-slate-100 text-slate-600" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        entry.cls,
        className
      )}
    >
      {entry.text}
    </span>
  );
}
