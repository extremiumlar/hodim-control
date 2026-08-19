/**
 * Xodim kabineti bo'limlari — endi SERVERDAN (`GET /me/sections`, TZ 2.6 / S-05).
 *
 * ILGARI bu faylda to'liq ro'yxat qattiq yozilgan edi va uning boshida
 * shunday ogohlantirish turardi: «ko'rinish shartlari `bot/keyboards.py`
 * bilan AYNAN bir xil bo'lishi shart». Ya'ni muvofiqlik INSON e'tiboriga
 * qolgan edi — bitta shart unutilsa xodim botda bir menyu, saytda
 * boshqasini ko'rardi.
 *
 * Endi ro'yxat ham, ko'rinish shartlari ham `api/services/sections.py` da.
 * Bu fayl — faqat KO'RINISH yordamchisi: tab-bar/«Yana» bo'linishi va
 * sarlavha.
 */
import type { LucideIcon } from "lucide-react";

import type { MeSection } from "./api/types";
import { sectionIcon } from "./sectionIcons";

export interface EmployeeSection {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
}

/** Serverdan kelgan bandni mijoz ko'rinishiga o'giradi. */
export function toEmployeeSection(s: MeSection): EmployeeSection {
  return { key: s.key, label: s.label, to: s.path, icon: sectionIcon(s.icon) };
}

/** Tab-barga nechta bo'lim sig'adi (5-slot «Yana» uchun band). */
export const MAX_TABS = 4;

/**
 * Tab-bar va «Yana» sahifasi uchun bo'linish. Ko'rinadigan bo'lim 4 tadan
 * kam bo'lsa «Yana» umuman kerak emas.
 *
 * Tartib — serverdagi `order`, ya'ni MUHIMLIK tartibi (birinchi to'rttasi
 * tab-barga tushadi).
 */
export function splitSections(sections: MeSection[]): {
  tabs: EmployeeSection[];
  more: EmployeeSection[];
} {
  const all = sections.filter((s) => s.audience === "employee").map(toEmployeeSection);
  if (all.length <= MAX_TABS + 1) return { tabs: all, more: [] };
  return { tabs: all.slice(0, MAX_TABS), more: all.slice(MAX_TABS) };
}

/** Sahifa sarlavhasi (yuqori panel uchun). */
export function sectionTitle(pathname: string, sections: MeSection[]): string | null {
  const found = sections
    .filter((s) => s.path !== "/")
    .sort((a, b) => b.path.length - a.path.length)
    .find((s) => pathname === s.path || pathname.startsWith(s.path + "/"));
  if (found) return found.label;
  if (pathname === "/me/more") return "Yana";
  return null;
}
