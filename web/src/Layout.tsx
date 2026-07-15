import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
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
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Target,
  TrendingUp,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "./lib/auth";
import { cn } from "./lib/utils";
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
  onlyPositionsManager?: boolean; // faqat boss/dasturchi
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
    title: "Ma'muriyat",
    items: [
      { to: "/users", label: "Foydalanuvchilar", icon: Users },
      { to: "/positions", label: "Lavozimlar", icon: Briefcase, onlyPositionsManager: true },
      { to: "/audit-logs", label: "Audit", icon: ScrollText },
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
  return found?.label ?? "Xodimlar KPI/Bonus";
}

function SidebarLink({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          collapsed && "justify-center px-2",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{item.label}</span>}
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
  onNavigate,
}: {
  collapsed: boolean;
  canManagePositions: boolean;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((i) => !i.onlyPositionsManager || canManagePositions);
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
                  <SidebarLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
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

export default function Layout() {
  const { user } = useAuth();
  const location = useLocation();
  const isManager = ["hr", "rop", "boss", "dasturchi"].includes(user?.role ?? "");
  const canManagePositions = user?.role === "boss" || user?.role === "dasturchi";

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("sidebar_collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  // employee — sidebar shart emas: faqat oddiy header (u faqat check-in ko'radi)
  if (!isManager) {
    return (
      <div className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
            <span className="text-lg font-semibold">Xodimlar KPI/Bonus</span>
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto max-w-2xl px-4 py-6">
          <Outlet />
        </main>
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
            {!collapsed && <span className="truncate font-semibold">Xodimlar KPI/Bonus</span>}
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
          <SidebarNav collapsed={collapsed} canManagePositions={canManagePositions} />
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
                  Xodimlar KPI/Bonus
                </SheetTitle>
                <div className="h-[calc(100vh-3.5rem)]">
                  <SidebarNav
                    collapsed={false}
                    canManagePositions={canManagePositions}
                    onNavigate={() => setMobileOpen(false)}
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
