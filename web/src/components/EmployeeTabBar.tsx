/**
 * Xodim uchun pastdagi tab-bar.
 *
 * NEGA PASTDA: telefonni bir qo'lda ushlab turganda barmoq ekranning pastiga
 * yetadi, yuqorisiga yetmaydi. Rahbarlar desktopda ishlaydi — ularda sidebar
 * qoladi (Layout.tsx).
 *
 * `pb-[env(safe-area-inset-bottom)]` — iPhone'dagi "home indicator" chizig'i
 * tab'lar ustiga tushmasligi uchun (PWA'da bosh ekrandan ochilganda ayniqsa
 * sezilarli).
 */
import { NavLink } from "react-router-dom";
import { MoreHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EmployeeSection } from "@/lib/employeeNav";

export default function EmployeeTabBar({
  tabs,
  hasMore,
}: {
  tabs: EmployeeSection[];
  hasMore: boolean;
}) {
  const count = tabs.length + (hasMore ? 1 : 0);
  if (count <= 1) return null;

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)]"
      aria-label="Asosiy bo'limlar"
    >
      <div className="mx-auto flex max-w-2xl">
        {tabs.map((s) => (
          <TabLink key={s.key} to={s.to} label={s.label} icon={<s.icon className="h-5 w-5" />} />
        ))}
        {hasMore && (
          <TabLink to="/me/more" label="Yana" icon={<MoreHorizontal className="h-5 w-5" />} />
        )}
      </div>
    </nav>
  );
}

function TabLink({ to, label, icon }: { to: string; label: string; icon: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          // min-h-[56px] — barmoq uchun minimal tegish maydoni (44px'dan katta)
          "flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 px-1 py-2 text-[11px] font-medium",
          isActive ? "text-primary" : "text-slate-500"
        )
      }
    >
      {icon}
      {/* Uzun nomlar ("Lidlar statistikasi") tab'ni buzmasligi uchun bir qatorda kesiladi */}
      <span className="w-full truncate text-center leading-tight">{label}</span>
    </NavLink>
  );
}
