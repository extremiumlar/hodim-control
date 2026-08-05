/**
 * Matritsa/kalendar kataklarining YAGONA rang tili (UX-C).
 *
 * Uch iste'molchi bor: rahbar matritsasi, xodim paneli (drawer) kalendari va
 * xodimning o'z «Oylik davomatim» kalendari (UX-D). Ranglar bir joyda
 * turmasa, rahbar bilan xodim bitta kunni ikki xil rangda ko'rardi.
 */
import type { MatrixCellStatus } from "@/lib/api";

/** Matritsaning zich (28px) kataklari uchun to'liq-rang variantlar. */
export const MATRIX_CELL_CLS: Record<MatrixCellStatus, string> = {
  present: "bg-emerald-500",
  late: "bg-amber-400 text-amber-950",
  absent: "bg-rose-500 text-white",
  excused: "bg-sky-400 text-white",
  weekend: "bg-slate-100",
  pending: "bg-slate-200",
  future: "border border-dashed border-slate-200 bg-transparent",
};

/** Kalendar (katta, raqamli) kataklari uchun yumshoq variantlar. */
export const CALENDAR_DAY_CLS: Record<MatrixCellStatus, string> = {
  present: "bg-emerald-100 text-emerald-700",
  late: "bg-amber-100 text-amber-700",
  absent: "bg-rose-100 text-rose-700",
  excused: "bg-sky-100 text-sky-700",
  weekend: "bg-slate-100 text-slate-400",
  pending: "bg-slate-100 text-slate-500",
  future: "text-slate-300",
};

export const STATUS_LABELS: Record<MatrixCellStatus, string> = {
  present: "Keldi",
  late: "Kechikdi",
  absent: "Kelmadi",
  excused: "Sababli",
  weekend: "Dam olish",
  pending: "Kutilmoqda",
  future: "Kelajak",
};

export const FLAG_LABELS: Record<string, string> = {
  auto_closed: "Avtomatik yopilgan («Ketdim» bosilmagan) — ishlangan vaqt taxminiy",
  manual: "Qo'lda tuzatilgan (HR/Boshliq)",
  no_checkout: "«Ketdim» bosilmagan — kun ochiq qolgan",
};

/** Legend uchun tartiblangan ro'yxat (future ko'rsatilmaydi — o'z-o'zidan ayon). */
export const LEGEND: { status: MatrixCellStatus; label: string }[] = [
  { status: "present", label: "Keldi" },
  { status: "late", label: "Kechikdi (daq)" },
  { status: "absent", label: "Kelmadi" },
  { status: "excused", label: "Sababli" },
  { status: "weekend", label: "Dam" },
  { status: "pending", label: "Kutilmoqda" },
];
