"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { logout } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { ICONS, LogoutIcon } from "@/components/icons";

const NAV = [
  { href: "/dashboard", label: "Bosh sahifa", icon: "home", role: "all" },
  { href: "/face-register", label: "Face ID", icon: "face", role: "all" },
  { href: "/tasks", label: "Vazifalar", icon: "task", role: "all" },
  { href: "/attendance", label: "Davomat", icon: "clock", role: "all" },
  { href: "/leaves", label: "Ta'til", icon: "leave", role: "all" },
  { href: "/payroll", label: "Oylik", icon: "money", role: "all" },
  { href: "/admin", label: "Admin panel", icon: "chart", role: "hr" },
  { href: "/employees", label: "Hodimlar", icon: "users", role: "hr" },
  { href: "/gps", label: "GPS aniqlash", icon: "location", role: "hr" },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const path = usePathname();
  const { me, isHR } = useMe();

  const roleLabel = me?.role === "admin" ? "Administrator" : me?.role === "hr" ? "HR / Manager" : "Hodim";

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={clsx(
          "fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-30 lg:hidden transition-opacity",
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
      />

      {/* Sidebar */}
      <aside
        className={clsx(
          "fixed lg:static inset-y-0 left-0 z-40 w-64 flex flex-col",
          "bg-white border-r border-slate-200",
          "transform transition-transform duration-200 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Logo */}
        <div className="px-5 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-primary-600/30">
              H
            </div>
            <div>
              <div className="font-bold leading-tight text-slate-800">Hodim CRM</div>
              <div className="text-[11px] text-slate-400 font-medium">Boshqaruv tizimi</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-slate-700 p-1 rounded-lg hover:bg-slate-100"
            aria-label="Yopish"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
          <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Menyu
          </div>
          {NAV.filter((n) => n.role === "all" || isHR).map((n) => {
            const active = path === n.href || path.startsWith(n.href + "/");
            const Icon = ICONS[n.icon];
            return (
              <Link
                key={n.href}
                href={n.href}
                onClick={onClose}
                className={clsx(
                  "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all relative",
                  active
                    ? "bg-primary-50 text-primary-700"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                )}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r-full bg-primary-600" />
                )}
                <Icon className={clsx("w-5 h-5 transition-colors", active ? "text-primary-600" : "text-slate-400 group-hover:text-slate-600")} />
                {n.label}
              </Link>
            );
          })}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-slate-100">
          {me && (
            <div className="flex items-center gap-3 px-2 py-2 mb-2">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary-100 to-primary-200 text-primary-700 flex items-center justify-center text-sm font-bold shrink-0">
                {(me.full_name || me.username || "?").charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="font-semibold text-sm text-slate-800 truncate">{me.full_name}</div>
                <div className="text-[11px] text-slate-400">{roleLabel}</div>
              </div>
            </div>
          )}
          <button
            onClick={logout}
            className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors"
          >
            <LogoutIcon className="w-4 h-4" />
            Chiqish
          </button>
        </div>
      </aside>
    </>
  );
}
