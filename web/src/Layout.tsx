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
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  NotebookPen,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
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
import { useAppeals, useExcusedDays, useExplanations } from "./lib/queries";
import { cn } from "./lib/utils";
import { BRAND_NAME } from "./lib/brand";
import { sectionTitle, splitSections } from "./lib/employeeNav";
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

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  onlyPositionsManager?: boolean; // faqat hr/boss/dasturchi
  onlyPayrollManager?: boolean; // faqat hr/boss/dasturchi (ROP'da yo'q)
  // hr/boss/dasturchi YOKI «kechikish normasi» huquqi shaxsan berilganlar.
  // `onlyPayrollManager` dan ATAYLAB alohida — u «Qo'shimcha ish»ni ham
  // yopadi, uni esa bayroq ochmaydi (backend 403 beradi).
  onlyFinePolicyEditor?: boolean;
  onlyDasturchi?: boolean; // faqat dasturchi (super-admin)
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: "Boshqaruv",
    items: [
      { to: "/", label: "Bosh sahifa", icon: LayoutDashboard, end: true },
      { to: "/statistics", label: "Statistika", icon: BarChart3 },
      { to: "/reports", label: "Hisobotlar", icon: FileSpreadsheet },
    ],
  },
  {
    title: "Davomat",
    items: [
      { to: "/attendance", label: "Davomat", icon: CalendarCheck },
      { to: "/excused-days", label: "Sababli kunlar", icon: CalendarX },
      { to: "/work-schedule", label: "Ish jadvali", icon: Clock },
      { to: "/work-log", label: "Ish kundaligi", icon: NotebookPen },
      { to: "/offices", label: "Ofislar", icon: MapPin },
    ],
  },
  {
    title: "Sotuv",
    items: [
      { to: "/lead-stats", label: "Lidlar", icon: TrendingUp },
      { to: "/norms", label: "Normalar", icon: Target },
    ],
  },
  {
    title: "Ish haqi",
    items: [
      { to: "/payroll", label: "Ish haqi", icon: Banknote },
      { to: "/overtime", label: "Qo'shimcha ish", icon: TimerReset, onlyPayrollManager: true },
      { to: "/payroll/settings", label: "Sozlamalar", icon: Settings, onlyFinePolicyEditor: true },
    ],
  },
  {
    title: "Ma'muriyat",
    items: [
      { to: "/users", label: "Foydalanuvchilar", icon: Users },
      // ROP'da yo'q — `onlyPayrollManager` bilan bir xil qamrov (hr/boss/
      // dasturchi), backend `appeals.py: MANAGE_ROLES` ham shunday.
      { to: "/appeals", label: "E'tiroz/Shikoyat", icon: Scale, onlyPayrollManager: true },
      { to: "/positions", label: "Lavozimlar", icon: Briefcase, onlyPositionsManager: true },
      { to: "/audit-logs", label: "Audit", icon: ScrollText },
      { to: "/dasturchi", label: "Dasturchi rejimi", icon: ShieldAlert, onlyDasturchi: true },
    ],
  },
];

const CHECK_IN_ITEM: NavItem = { to: "/check-in", label: "Mening davomatim", icon: UserCheck };

// Joriy sahifa sarlavhasi (yuqori panel uchun)
function pageTitle(pathname: string): string {
  if (pathname === "/") return "Bosh sahifa";
  if (pathname.startsWith("/employees/")) return "Xodim profili";
  const all = [...NAV_GROUPS.flatMap((g) => g.items), CHECK_IN_ITEM];
  const found = all
    .filter((i) => i.to !== "/")
    .sort((a, b) => b.to.length - a.to.length)
    .find((i) => pathname === i.to || pathname.startsWith(i.to + "/"));
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
  canManagePositions,
  canManagePayroll,
  canEditFinePolicy,
  isDasturchi,
  onNavigate,
  badges = {},
}: {
  collapsed: boolean;
  canManagePositions: boolean;
  canManagePayroll: boolean;
  canEditFinePolicy: boolean;
  isDasturchi: boolean;
  onNavigate?: () => void;
  /** UX-G1: yo'l -> kutilayotgan ishlar soni. */
  badges?: Record<string, number>;
}) {
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (i) =>
              (!i.onlyPositionsManager || canManagePositions) &&
              (!i.onlyPayrollManager || canManagePayroll) &&
              (!i.onlyFinePolicyEditor || canEditFinePolicy) &&
              (!i.onlyDasturchi || isDasturchi)
          );
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
      <div className="px-2 pb-3">
        <Separator className="mb-3" />
        <SidebarLink item={CHECK_IN_ITEM} collapsed={collapsed} onNavigate={onNavigate} />
      </div>
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
  const isManager = ["hr", "rop", "boss", "dasturchi"].includes(user?.role ?? "");
  const canManagePositions = ["hr", "boss", "dasturchi"].includes(user?.role ?? "");
  const canManagePayroll = ["hr", "boss", "dasturchi"].includes(user?.role ?? "");
  // ATAYLAB alohida: `canManagePayroll` «Qo'shimcha ish» havolasini ham
  // boshqaradi, uni esa bayroq OCHMAYDI (backend 403 beradi). Ikkalasini
  // bitta qilib qo'ysam, huquq egasi bosib bo'lmaydigan havolani ko'rardi.
  const canEditFinePolicy = canManagePayroll || !!user?.can_edit_fine_policy;
  const isDasturchi = user?.role === "dasturchi";

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
  const navBadges = {
    "/excused-days": excusedBadge,
    "/appeals": pendingAppeals.data?.length ?? 0,
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
    const { tabs, more } = splitSections(user);
    const title = sectionTitle(location.pathname) ?? BRAND_NAME;
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
          <SidebarNav
            collapsed={collapsed}
            canManagePositions={canManagePositions}
            canManagePayroll={canManagePayroll}
            canEditFinePolicy={canEditFinePolicy}
            isDasturchi={isDasturchi}
            badges={navBadges}
          />
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
                    canManagePositions={canManagePositions}
                    canManagePayroll={canManagePayroll}
                    canEditFinePolicy={canEditFinePolicy}
                    isDasturchi={isDasturchi}
                    onNavigate={() => setMobileOpen(false)}
                    badges={navBadges}
                  />
                </div>
              </SheetContent>
            </Sheet>

            <h1 className="truncate text-base font-semibold">{pageTitle(location.pathname)}</h1>
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
