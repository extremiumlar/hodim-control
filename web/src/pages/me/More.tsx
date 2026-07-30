/**
 * «Yana» — tab-barga sig'magan bo'limlar ro'yxati.
 *
 * Tab-bar 4 ta bo'limni ko'rsatadi (barmoq yetadigan joyda eng kerakli
 * to'rttasi), qolgani shu sahifada. Ro'yxat `employeeNav.ts` dagi tartibdan
 * keladi — u bilan bot menyusi bir xil bo'lishi kerak.
 */
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { useAuth } from "@/lib/auth";
import { splitSections } from "@/lib/employeeNav";

export default function More() {
  const { user } = useAuth();
  const { more } = splitSections(user);

  if (!more.length) {
    return (
      <p className="p-4 text-center text-sm text-slate-500">
        Barcha bo'limlar pastdagi menyuda.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      {more.map((s, i) => (
        <Link
          key={s.key}
          to={s.to}
          className={
            // min-h-[56px] — barmoq uchun qulay tegish maydoni
            "flex min-h-[56px] items-center gap-3 px-4 py-3 active:bg-slate-50" +
            (i > 0 ? " border-t border-slate-100" : "")
          }
        >
          <s.icon className="h-5 w-5 shrink-0 text-slate-400" />
          <span className="flex-1 text-sm font-medium">{s.label}</span>
          <ChevronRight className="h-4 w-4 shrink-0 text-slate-300" />
        </Link>
      ))}
    </div>
  );
}
