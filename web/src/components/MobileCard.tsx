import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Jadval qatorining telefondagi ko'rinishi — "ustun nomi — qiymat" juftliklari.
 *
 * `DataTable`, `OperatorTable` va `CrmMappingSection` UCHALASI shu yerdan
 * foydalanadi: aks holda karta uslubi (chekka, ajratuvchi chiziq, yorliq rangi)
 * uch joyda ayri-ayri o'zgarib, telefonda uch xil ko'rinish paydo bo'lardi.
 */
export function MobileCard({
  children,
  className,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white px-4 py-2",
        onClick && "cursor-pointer active:bg-slate-50",
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

/**
 * Kartadagi bitta "yorliq — qiymat" juftligi. Yorliqsiz ustun (masalan amallar
 * tugmalari) yorliqsiz chiqadi va qiymat butun kenglikni oladi.
 */
export function MobileCardRow({ label, children }: { label?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-50 py-2 last:border-0">
      {label ? <span className="shrink-0 text-xs text-slate-500">{label}</span> : null}
      {/* `break-words` — qiymat bo'sh joysiz uzun satr bo'lishi mumkin (masalan
          Uysot identifikatori — email manzil). Usiz u satrga sig'may kartadan
          chiqib ketadi va butun sahifani gorizontal scrollga tushiradi. */}
      <span className={cn("min-w-0 break-words text-sm", label ? "text-right" : "flex-1")}>
        {children}
      </span>
    </div>
  );
}
