import { cn } from "@/lib/utils";

/**
 * Yagona status badge — davomat / vazifa / so'rov statuslari uchun bitta
 * rang xaritasi. "pending" ikki kontekstda har xil: vazifada ko'k
 * (jarayonda), so'rovda esa amber (qaror kutilmoqda) — shuning uchun kind.
 */
type Kind =
  | "attendance"
  | "task"
  | "request"
  | "payslip"
  | "overtime"
  | "appeal"
  | "advance"
  | "employee_request";

const MAP: Record<Kind, Record<string, { text: string; cls: string }>> = {
  attendance: {
    present: { text: "Keldi", cls: "bg-emerald-100 text-emerald-700" },
    late: { text: "Kechikdi", cls: "bg-rose-100 text-rose-700" },
    absent: { text: "Kelmadi", cls: "bg-slate-200 text-slate-600" },
    weekend: { text: "Dam olish", cls: "bg-blue-100 text-blue-700" },
    // 5.1-band statusi — sababli kunda kelgan/kelmagan (kechikish yozilmaydi).
    excused: { text: "Sababli", cls: "bg-sky-100 text-sky-700" },
    // UX-A2 virtual holatlari (matritsa kataklari uchun):
    pending: { text: "Kutilmoqda", cls: "bg-slate-100 text-slate-500" },
    future: { text: "Kelajak", cls: "bg-slate-100 text-slate-400" },
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
  payslip: {
    draft: { text: "Qoralama", cls: "bg-slate-200 text-slate-600" },
    calculated: { text: "Hisoblangan", cls: "bg-blue-100 text-blue-700" },
    approved: { text: "Tasdiqlangan", cls: "bg-emerald-100 text-emerald-700" },
    paid: { text: "To'langan", cls: "bg-emerald-100 text-emerald-700" },
  },
  overtime: {
    pending: { text: "Kutilmoqda", cls: "bg-amber-100 text-amber-700" },
    approved: { text: "Tasdiqlangan", cls: "bg-emerald-100 text-emerald-700" },
    rejected: { text: "Rad etilgan", cls: "bg-rose-100 text-rose-700" },
  },
  // Avans: holatlar `overtime` bilan bir xil, lekin matni boshqa — bu yerda
  // «tasdiqlangan» degani "pul oylikdan AYIRILADI", ya'ni HR uchun ma'nosi
  // teskari. Shuning uchun alohida tur (nusxa emas, aniqlik uchun).
  advance: {
    pending: { text: "Boshliq tasdig'i kutilmoqda", cls: "bg-amber-100 text-amber-700" },
    approved: { text: "Tasdiqlangan — oylikdan ayiriladi", cls: "bg-emerald-100 text-emerald-700" },
    rejected: { text: "Rad etilgan", cls: "bg-rose-100 text-rose-700" },
  },
  // E'tiroz/shikoyat: `request`dan farqli — oraliq «o'rganilmoqda» holati bor
  // va yakun ikki xil nomlanadi (e'tiroz qondiriladi, shikoyat hal qilinadi).
  // Ariza — `appeal` dan farqli: tasdiqlangach REAL yozuv yaratiladi,
  // shuning uchun «bekor qilingan» (revoked) alohida holat.
  employee_request: {
    pending: { text: "Yangi", cls: "bg-amber-100 text-amber-700" },
    manager_ok: { text: "Rahbar tasdiqladi", cls: "bg-blue-100 text-blue-700" },
    approved: { text: "Tasdiqlangan", cls: "bg-emerald-100 text-emerald-700" },
    rejected: { text: "Rad etilgan", cls: "bg-rose-100 text-rose-700" },
    cancelled: { text: "Qaytarib olingan", cls: "bg-slate-200 text-slate-600" },
    revoked: { text: "Bekor qilingan", cls: "bg-slate-200 text-slate-600" },
  },
  appeal: {
    pending: { text: "Yangi", cls: "bg-amber-100 text-amber-700" },
    in_review: { text: "O'rganilmoqda", cls: "bg-blue-100 text-blue-700" },
    accepted: { text: "Qondirildi", cls: "bg-emerald-100 text-emerald-700" },
    resolved: { text: "Hal qilindi", cls: "bg-emerald-100 text-emerald-700" },
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
