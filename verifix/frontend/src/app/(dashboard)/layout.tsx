"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { isAuthenticated } from "@/lib/api";
import { useMe } from "@/lib/useMe";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { me } = useMe();

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [router]);

  // Sahifa o'zgarganda mobile sidebar yopilsin
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  // Joriy sahifa nomi
  const titles: Record<string, string> = {
    "/dashboard": "Bosh sahifa",
    "/face-register": "Face ID",
    "/tasks": "Vazifalar",
    "/attendance": "Davomat",
    "/leaves": "Ta'til",
    "/payroll": "Oylik",
    "/admin": "Admin panel",
    "/employees": "Hodimlar",
  };
  const pageTitle =
    Object.keys(titles).find((k) => pathname.startsWith(k)) || "/dashboard";

  return (
    <div className="flex h-screen">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile top bar */}
        <header className="lg:hidden flex items-center justify-between bg-white border-b border-slate-200 px-4 py-3 sticky top-0 z-20">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 text-slate-700 hover:bg-slate-100 rounded-lg"
            aria-label="Menyu ochish"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-primary-600 flex items-center justify-center text-white font-bold text-sm">H</div>
            <div className="font-semibold text-sm">{titles[pageTitle] || "Hodim CRM"}</div>
          </div>

          {me && (
            <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-sm font-semibold">
              {(me.full_name || me.username || "?").charAt(0).toUpperCase()}
            </div>
          )}
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto p-4 lg:p-6">{children}</div>
        </div>
      </main>
    </div>
  );
}
