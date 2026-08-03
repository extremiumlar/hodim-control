/**
 * Xodim kabineti bo'limlari — YAGONA manba.
 *
 * DIQQAT: ko'rinish shartlari `bot/keyboards.py: main_menu` bilan AYNAN bir xil
 * bo'lishi shart. Aks holda bitta xodim botda bir menyu, web'da boshqa menyu
 * ko'radi va "menda bu tugma yo'q" degan chalkashlik chiqadi. Botda shart
 * o'zgarsa — shu fayl ham o'zgaradi.
 *
 * Marshrutlar ataylab `/me/...` prefiksi bilan: `/payroll`, `/work-schedule`,
 * `/lead-stats`, `/statistics` allaqachon RAHBAR sahifalari (App.tsx), ular
 * bilan to'qnashmasligi kerak. Prefiks API konventsiyasini ham takrorlaydi
 * (`/me/late-status` va h.k.).
 */
import {
  BarChart3,
  Banknote,
  CalendarX,
  Clock,
  ClipboardList,
  ListTodo,
  Target,
  TrendingUp,
  PencilLine,
  UserCheck,
  type LucideIcon,
} from "lucide-react";

import type { User } from "./api/types";

/** bot/keyboards.py: DEFAULT_MENU_FLAGS — lavozim yo'q bo'lsa hammasi ko'rinadi. */
const DEFAULT_MENU_FLAGS: Record<string, boolean> = {
  tasks: true,
  norm: true,
  kpi: true,
  excused: true,
  payroll: true,
};

/** bot/keyboards.py: metrics_for() defaulti — lavozim biriktirilmagan xodim. */
const DEFAULT_METRICS = ["suhbat", "tashrif"];
const SALES_METRICS = ["suhbat", "tashrif"];
const TRACKABLE_METRICS = ["suhbat", "tashrif", "oddiy_video", "dumaloq_video"];

const MANAGER_ROLES = ["hr", "rop", "boss", "dasturchi"];

export interface EmployeeSection {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
  /** false qaytarsa bo'lim umuman ko'rinmaydi (bot bilan bir xil). */
  visible: (ctx: NavContext) => boolean;
}

interface NavContext {
  role: string;
  isManager: boolean;
  flags: Record<string, boolean>;
  metrics: string[];
  hasSalesMetric: boolean;
  hasTrackableMetric: boolean;
  /** Dasturchi shaxsan bergan davomat tuzatish huquqi. */
  canEditAttendance: boolean;
}

function buildContext(user: User): NavContext {
  const flags = { ...DEFAULT_MENU_FLAGS, ...(user.position?.menu_flags ?? {}) };
  // `metrics === null` (lavozim yo'q) → default; `[]` (ataylab bo'sh) → bo'sh.
  // Bot ham shu farqni saqlaydi, shuning uchun `??` ishlatiladi, `||` emas.
  const metrics = user.position?.metrics ?? DEFAULT_METRICS;
  return {
    role: user.role,
    isManager: MANAGER_ROLES.includes(user.role),
    flags,
    metrics,
    hasSalesMetric: metrics.some((m) => SALES_METRICS.includes(m)),
    hasTrackableMetric: metrics.some((m) => TRACKABLE_METRICS.includes(m)),
    canEditAttendance: !!user.can_edit_attendance,
  };
}

/**
 * Tartib MUHIM: tab-barga shu ro'yxatdan birinchi 4 tasi (ko'rinadiganlari)
 * tushadi, qolgani «Yana» sahifasiga o'tadi. Ya'ni bu ro'yxat — muhimlik
 * tartibi.
 */
export const EMPLOYEE_SECTIONS: EmployeeSection[] = [
  {
    key: "checkin",
    label: "Davomat",
    to: "/check-in",
    icon: UserCheck,
    visible: () => true,
  },
  {
    // Dasturchi shaxsan huquq bergan xodim uchun — boshqalarning keldi/ketdi
    // vaqtini tuzatish sahifasi. Rahbarlarga bu yerda kerak emas: ular
    // sidebar orqali kiradi (bu ro'yxat faqat xodim qobig'i uchun).
    key: "attendance-edit",
    label: "Davomat tuzatish",
    to: "/attendance",
    icon: PencilLine,
    visible: (ctx) => ctx.canEditAttendance,
  },
  {
    key: "schedule",
    label: "Ish jadvali",
    to: "/me/schedule",
    icon: Clock,
    visible: () => true,
  },
  {
    key: "payroll",
    label: "Mening oyligim",
    to: "/me/payroll",
    icon: Banknote,
    // bot: flags.payroll va role != "boss" (Boshliqda oylik kuzatilmaydi)
    visible: (c) => !!c.flags.payroll && c.role !== "boss",
  },
  {
    key: "stats",
    label: "Statistikam",
    to: "/me/stats",
    icon: BarChart3,
    // bot: har doim ko'rinadi
    visible: () => true,
  },
  {
    key: "tasks",
    label: "Vazifalarim",
    to: "/me/tasks",
    icon: ListTodo,
    visible: (c) => !!c.flags.tasks,
  },
  {
    key: "norm",
    label: "Bugungi normam",
    to: "/me/norm",
    icon: Target,
    visible: (c) => !!c.flags.norm,
  },
  {
    key: "hourly",
    label: "Bugungi rejam",
    to: "/me/hourly-plan",
    icon: ClipboardList,
    // bot: rahbar EMAS va kuzatiladigan metrikasi bor
    visible: (c) => !c.isManager && c.hasTrackableMetric,
  },
  {
    key: "kpi",
    label: "Oylik KPI'm",
    to: "/me/kpi",
    icon: TrendingUp,
    visible: (c) => !!c.flags.kpi,
  },
  {
    key: "leads",
    label: "Lidlar statistikasi",
    to: "/me/lead-stats",
    icon: TrendingUp,
    // bot: show_lead_stats va rahbar EMAS
    visible: (c) => !c.isManager && c.hasSalesMetric,
  },
  {
    key: "excused",
    label: "Sababli kun so'rash",
    to: "/me/excused",
    icon: CalendarX,
    visible: (c) => !!c.flags.excused,
  },
];

/** Shu xodimga ko'rinadigan bo'limlar, muhimlik tartibida. */
export function visibleSections(user: User | null): EmployeeSection[] {
  if (!user) return [];
  const ctx = buildContext(user);
  return EMPLOYEE_SECTIONS.filter((s) => s.visible(ctx));
}

/** Tab-barga nechta bo'lim sig'adi (5-slot «Yana» uchun band). */
export const MAX_TABS = 4;

/**
 * Tab-bar va «Yana» sahifasi uchun bo'linish. Flaglar tufayli ko'rinadigan
 * bo'lim 4 tadan kam bo'lsa, «Yana» umuman kerak emas.
 */
export function splitSections(user: User | null): {
  tabs: EmployeeSection[];
  more: EmployeeSection[];
} {
  const all = visibleSections(user);
  if (all.length <= MAX_TABS + 1) return { tabs: all, more: [] };
  return { tabs: all.slice(0, MAX_TABS), more: all.slice(MAX_TABS) };
}

/** Sahifa sarlavhasi (yuqori panel uchun). */
export function sectionTitle(pathname: string): string | null {
  const found = EMPLOYEE_SECTIONS.filter((s) => s.to !== "/")
    .sort((a, b) => b.to.length - a.to.length)
    .find((s) => pathname === s.to || pathname.startsWith(s.to + "/"));
  if (found) return found.label;
  if (pathname === "/me/more") return "Yana";
  return null;
}
