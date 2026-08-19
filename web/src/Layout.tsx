import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
  Banknote,
  Briefcase,
  CalendarCheck,
  CalendarX,
  ChevronDown,
  Clock,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  NotebookPen,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  Clapperboard,
  Filter,
  ScrollText,
  Settings,
  ShieldAlert,
  Target,
  TimerReset,
  TrendingUp,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "./lib/auth";
import { useAppeals, useExcusedDays, useExplanations, useMySections, useRequests } from "./lib/queries";
import { cn } from "./lib/utils";
import { BRAND_NAME } from "./lib/brand";
import { sectionTitle, splitSections } from "./lib/employeeNav";
import { sectionIcon } from "./lib/sectionIcons";
import type { MeSection } from "./lib/api/types";
import EmployeeTabBar from "@/components/EmployeeTabBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const ROLE_LABELS: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
  dasturchi: "Dasturchi",
};

/**
 * Menyu bandi — SERVERDAN keladi (`GET /me/sections`, TZ 2.6 / S-05).
 *
 * Ilgari bu yerda `NAV_GROUPS` qattiq yozilgan ro'yxat bor edi va AYNAN
 * shu ro'yxat bot hamda xodim kabinetida ham takrorlanardi. Endi manba
 * bitta: `api/services/sections.py`. Serverda bo'lim qo'shilsa, bu yerda
 * kod O'ZGARMASDAN paydo bo'ladi.
 */
interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

/** Serverdan kelgan tekis ro'yxatni yon panel guruhlariga yig'adi.
 *  Tartib `order` bo'yicha (server allaqachon tartiblab yuboradi), guruh
 *  esa BIRINCHI uchragan joyida paydo bo'ladi — ya'ni guruhlar tartibi ham
 *  serverda hal qilinadi. */
function toGroups(sections: MeSection[]): { groups: NavGroup[]; loose: NavItem[] } {
  const groups: NavGroup[] = [];
  const loose: NavItem[] = [];
  for (const s of sections) {
    const item: NavItem = {
      to: s.path,
      label: s.label,
      icon: sectionIcon(s.icon),
      end: s.exact || undefined,
    };
    if (!s.group) {
      loose.push(item);
      continue;
    }
    const found = groups.find((g) => g.title === s.group);
    if (found) found.items.push(item);
    else groups.push({ title: s.group, items: [item] });
  }
  return { groups, loose };
}

// Joriy sahifa sarlavhasi (yuqori panel uchun). Manba — o'sha serverdan
// kelgan ro'yxat: sarlavha va menyu bandi bir xil nomni ko'rsatsin.
function pageTitle(pathname: string, sections: MeSection[]): string {
  if (pathname === "/") return "Bosh sahifa";
  if (pathname.startsWith("/employees/")) return "Xodim profili";
  const found = sections
    .filter((s) => s.path !== "/")
    .sort((a, b) => b.path.length - a.path.length)
    .find((s) => pathname === s.path || pathname.startsWith(s.path + "/"));
  return found?.label ?? BRAND_NAME;
}

function SidebarLink({
  item,
  collapsed,
  onNavigate,
  badge = 0,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
  /** UX-G1: kutilayotgan ishlar soni (masalan sababli kun so'rovlari). */
  badge?: number;
}) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          collapsed && "justify-center px-2",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {badge > 0 &&
        (collapsed ? (
          // Yig'iq sidebar'da joy yo'q — kichik nuqta yetadi.
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-amber-500" />
        ) : (
          <span className="ml-auto rounded-full bg-amber-100 px-1.5 py-0.5 text-[11px] font-bold leading-none text-amber-700">
            {badge}
          </span>
        ))}
    </NavLink>
  );
  if (!collapsed) return link;
  return (
    <Tooltip delayDuration={0}>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

function SidebarNav({
  collapsed,
  sections,
  onNavigate,
  badges = {},
}: {
  collapsed: boolean;
  /** `GET /me/sections` javobi — server allaqachon FILTRLAB va tartiblab
   *  yuborgan. Mijozda rol sharti YO'Q (S-05 qabul mezoni). */
  sections: MeSection[];
  onNavigate?: () => void;
  /** UX-G1: yo'l -> kutilayotgan ishlar soni. */
  badges?: Record<string, number>;
}) {
  const { groups, loose } = toGroups(sections);
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
        {groups.map((group) => {
          const items = group.items;
          if (!items.length) return null;
          return (
            <div key={group.title}>
              {!collapsed && (
                <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  {group.title}
                </div>
              )}
              <div className="space-y-0.5">
                {items.map((item) => (
                  <SidebarLink
                    key={item.to}
                    item={item}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                    badge={badges[item.to] ?? 0}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </nav>
      {loose.length > 0 && (
        <div className="px-2 pb-3">
          <Separator className="mb-3" />
          {loose.map((item) => (
            <SidebarLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-2 px-2">
          <span className="max-w-[160px] truncate text-sm font-medium">{user?.full_name}</span>
          <Badge variant="secondary">{ROLE_LABELS[user?.role ?? ""] ?? user?.role}</Badge>
          <ChevronDown className="h-4 w-4 text-slate-400" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel className="font-normal">
          <div className="text-sm font-medium">{user?.full_name}</div>
          <div className="text-xs text-muted-foreground">
            {ROLE_LABELS[user?.role ?? ""] ?? user?.role}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} className="text-rose-600 focus:text-rose-600">
          <LogOut className="mr-2 h-4 w-4" />
          Chiqish
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Mobil ilova sahifani WebView'da ochganda URL'ga `?embed=1` qo'shadi —
 * ilovada O'Z yuqori paneli va tayl navigatsiyasi bor, sayt qobig'i (header,
 * tab-bar yoki sidebar) ikkinchi marta ko'rinmasligi kerak.
 *
 * NEGA query parametr, alohida `/embed/...` marshrutlari emas: aks holda
 * `App.tsx`dagi butun marshrut ro'yxatini ikki marta e'lon qilish kerak
 * bo'lardi va yangi sahifa qo'shilganda biri unutilib qolardi.
 *
 * `sessionStorage` — sahifa ichida navigatsiya bo'lsa (masalan «Yana»
 * ro'yxatidagi havola) parametr yo'qolib qobiq qaytib chiqmasin.
 */
function useEmbedded(search: string): boolean {
  const fromQuery = new URLSearchParams(search).get("embed") === "1";
  if (fromQuery) sessionStorage.setItem("embed_mode", "1");
  return fromQuery || sessionStorage.getItem("embed_mode") === "1";
}

export default function Layout() {
  const { user } = useAuth();
  const location = useLocation();
  const embedded = useEmbedded(location.search);
  // Menyu SERVERDAN (TZ 2.6 / S-05). Qattiq yozilgan rol shartlari olib
  // tashlandi — ular endi `api/services/sections.py` da, YAGONA joyda.
  const sectionsQuery = useMySections();
  const sections = sectionsQuery.data ?? [];
  // Rozetka (badge) so'rovlarini kimga yuborish — buni ham SHU ro'yxatdan
  // aniqlaymiz, roldan emas. Aks holda mijozda yana rol sharti paydo
  // bo'lardi va S-05 ning maqsadi buzilardi: bo'lim ko'rinmasa, unga tegishli
  // so'rov ham yuborilmasligi kerak.
  const hasSection = (path: string) => sections.some((x) => x.path === path);
  const isManager = sections.some((x) => x.audience === "manager");
  const canManagePayroll = hasSection("/appeals");

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);

  // UX-G1: «Sababli kunlar» bandida kutilayotgan ishlar soni — HR sahifaga
  // kirmasa ham so'rov kelganini sezsin. Faqat rahbarda so'raladi (enabled);
  // 60s staleTime — sidebar har renderda so'rov yubormaydi.
  const pendingExcused = useExcusedDays("pending", isManager);
  const answeredExplanations = useExplanations("answered", isManager);
  const excusedBadge =
    (pendingExcused.data?.length ?? 0) + (answeredExplanations.data?.length ?? 0);
  // Murojaatlar badge'i: hali qaror chiqarilmagan («yangi») murojaatlar.
  // `in_review` sanalmaydi — u allaqachon qo'lga olingan.
  const pendingAppeals = useAppeals({ status_filter: "pending" }, canManagePayroll);
  const pendingRequests = useRequests({ status_filter: "pending" }, canManagePayroll);
  const navBadges = {
    "/excused-days": excusedBadge,
    "/appeals": pendingAppeals.data?.length ?? 0,
    "/requests": pendingRequests.data?.length ?? 0,
  };

  useEffect(() => {
    localStorage.setItem("sidebar_collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  // ── Mobil ilova (WebView): qobiqsiz ──
  // Roldan QAT'I NAZAR: ilova sahifani o'z paneli ichida ko'rsatadi, ya'ni
  // rahbar ham ilovadan ochsa sidebar kerak emas.
  if (embedded) {
    return (
      <div className="min-h-screen bg-slate-50">
        <main className="mx-auto max-w-2xl px-4 py-5">
          <Outlet />
        </main>
      </div>
    );
  }

  // ── Xodim qobig'i: pastdagi tab-bar ──
  // Ilgari bu yerda navigatsiya UMUMAN yo'q edi (faqat sarlavha + "Chiqish"),
  // chunki xodim bitta sahifani — /check-in — ko'rardi. Endi kabinet bor,
  // shuning uchun tab-bar kerak. Sidebar EMAS: telefonni bir qo'lda ushlab
  // turganda barmoq ekran pastiga yetadi, yuqorisiga yetmaydi.
  if (!isManager) {
    const { tabs, more } = splitSections(sections);
    const title = sectionTitle(location.pathname, sections) ?? BRAND_NAME;
    return (
      <div className="min-h-screen bg-slate-50">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
            <span className="truncate text-lg font-semibold">{title}</span>
            <UserMenu />
          </div>
        </header>
        {/* pb-24 — kontent tab-bar ostiga kirib ketmasligi uchun */}
        <main className="mx-auto max-w-2xl px-4 py-5 pb-24">
          <Outlet />
        </main>
        <EmployeeTabBar tabs={tabs} hasMore={more.length > 0} />
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="min-h-screen lg:flex">
        {/* Desktop sidebar */}
        <aside
          className={cn(
            "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-slate-200 bg-white lg:flex",
            collapsed ? "w-14" : "w-60"
          )}
        >
          <div
            className={cn(
              "flex h-14 items-center border-b border-slate-200 px-4",
              collapsed && "justify-center px-2"
            )}
          >
            {!collapsed && <span className="truncate font-semibold">{BRAND_NAME}</span>}
            <Button
              variant="ghost"
              size="icon"
              className={cn("h-8 w-8 text-slate-400", !collapsed && "ml-auto")}
              onClick={() => setCollapsed((c) => !c)}
              title={collapsed ? "Menyuni yoyish" : "Menyuni yig'ish"}
            >
              {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </Button>
          </div>
          <SidebarNav collapsed={collapsed} sections={sections} badges={navBadges} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Yuqori panel */}
          <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-slate-200 bg-white px-4">
            {/* Mobil: hamburger + drawer */}
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-64 p-0">
                <SheetTitle className="flex h-14 items-center border-b border-slate-200 px-4 text-base font-semibold">
                  {BRAND_NAME}
                </SheetTitle>
                <div className="h-[calc(100vh-3.5rem)]">
                  <SidebarNav
                    collapsed={false}
                    sections={sections}
                    onNavigate={() => setMobileOpen(false)}
                    badges={navBadges}
                  />
                </div>
              </SheetContent>
            </Sheet>

            <h1 className="truncate text-base font-semibold">{pageTitle(location.pathname, sections)}</h1>
            <div className="ml-auto">
              <UserMenu />
            </div>
          </header>

          <main className="min-w-0 flex-1 px-4 py-6">
            <div className="mx-auto max-w-6xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
