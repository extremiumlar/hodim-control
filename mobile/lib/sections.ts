/**
 * Xodim kabineti bo'limlari — ilova uchun.
 *
 * ⚠️ DIQQAT: ko'rinish shartlari `web/src/lib/employeeNav.ts` va
 * `bot/keyboards.py: main_menu` bilan AYNAN bir xil bo'lishi SHART. Aks holda
 * bitta xodim botda bir menyu, saytda ikkinchi, ilovada uchinchi menyu ko'radi.
 * Uchtasidan biri o'zgarsa — qolgan ikkitasi ham o'zgaradi.
 *
 * (Bu uchinchi nusxa. Uni yo'qotishning to'g'ri yo'li — serverdan
 * `GET /me/sections` qaytarish, ya'ni bot bilan bitta manbadan. Hozircha
 * ilovaning tayllari eskirib qolgani uchun shu ro'yxat to'g'rilandi;
 * endpointga o'tish alohida ish.)
 */
import type { UserOut } from "./api";

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

export interface Section {
  key: string;
  title: string;
  emoji: string;
  /**
   * Ilova ochadigan yo'l. `/checkin` — nativ ekran (kamera/GPS ruxsati
   * kerak), qolganlari saytning sahifasi (`/view?path=...`).
   */
  webPath?: string;
  nativeRoute?: string;
  visible: (ctx: NavContext) => boolean;
}

interface NavContext {
  role: string;
  isManager: boolean;
  flags: Record<string, boolean>;
  metrics: string[];
  hasSalesMetric: boolean;
  hasTrackableMetric: boolean;
}

function buildContext(user: UserOut): NavContext {
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
  };
}

/** Tartib — muhimlik bo'yicha (web'dagi EMPLOYEE_SECTIONS bilan bir xil). */
const SECTIONS: Section[] = [
  {
    key: "checkin",
    title: "Davomat (Keldim/Ketdim)",
    emoji: "🕐",
    nativeRoute: "/checkin",
    visible: () => true,
  },
  { key: "schedule", title: "Ish jadvali", emoji: "🗓", webPath: "/me/schedule", visible: () => true },
  {
    key: "payroll",
    title: "Mening oyligim",
    emoji: "💵",
    webPath: "/me/payroll",
    // bot: flags.payroll va role != "boss" (Boshliqda oylik kuzatilmaydi)
    visible: (c) => !!c.flags.payroll && c.role !== "boss",
  },
  { key: "stats", title: "Statistikam", emoji: "📈", webPath: "/me/stats", visible: () => true },
  {
    key: "tasks",
    title: "Vazifalarim",
    emoji: "📋",
    webPath: "/me/tasks",
    visible: (c) => !!c.flags.tasks,
  },
  {
    key: "norm",
    title: "Bugungi normam",
    emoji: "📊",
    webPath: "/me/norm",
    visible: (c) => !!c.flags.norm,
  },
  {
    key: "hourly",
    title: "Bugungi rejam",
    emoji: "🕒",
    webPath: "/me/hourly-plan",
    // bot: rahbar EMAS va kuzatiladigan metrikasi bor
    visible: (c) => !c.isManager && c.hasTrackableMetric,
  },
  {
    key: "kpi",
    title: "Oylik KPI'm",
    emoji: "💰",
    webPath: "/me/kpi",
    visible: (c) => !!c.flags.kpi,
  },
  {
    key: "leads",
    title: "Lidlar statistikasi",
    emoji: "🧲",
    webPath: "/me/lead-stats",
    // bot: show_lead_stats va rahbar EMAS
    visible: (c) => !c.isManager && c.hasSalesMetric,
  },
  {
    key: "excused",
    title: "Sababli kun so'rash",
    emoji: "🙋",
    webPath: "/me/excused",
    visible: (c) => !!c.flags.excused,
  },
];

/** Shu xodimga ko'rinadigan bo'limlar, muhimlik tartibida. */
export function visibleSections(user: UserOut | null): Section[] {
  if (!user) return [];
  const ctx = buildContext(user);
  return SECTIONS.filter((s) => s.visible(ctx));
}
