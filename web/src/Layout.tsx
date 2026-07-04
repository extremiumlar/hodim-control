import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./lib/auth";

const ROLE_LABELS: Record<string, string> = {
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
  dasturchi: "Dasturchi",
};

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-200"
  }`;

export default function Layout() {
  const { user, logout } = useAuth();
  const canManagePositions = user?.role === "boss" || user?.role === "dasturchi";

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-lg">Xodimlar KPI/Bonus</span>
            <nav className="flex gap-1 ml-6">
              <NavLink to="/" end className={navLinkClass}>
                Bosh sahifa
              </NavLink>
              <NavLink to="/excused-days" className={navLinkClass}>
                Sababli kunlar
              </NavLink>
              <NavLink to="/norms" className={navLinkClass}>
                Normalar
              </NavLink>
              <NavLink to="/users" className={navLinkClass}>
                Foydalanuvchilar
              </NavLink>
              {canManagePositions && (
                <NavLink to="/positions" className={navLinkClass}>
                  Lavozimlar
                </NavLink>
              )}
              <NavLink to="/reports" className={navLinkClass}>
                Hisobotlar
              </NavLink>
              <NavLink to="/audit-logs" className={navLinkClass}>
                Audit
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              {user?.full_name} ({ROLE_LABELS[user?.role ?? ""] ?? user?.role})
            </span>
            <button onClick={logout} className="text-indigo-600 hover:underline">
              Chiqish
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
