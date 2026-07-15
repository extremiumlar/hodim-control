import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import Layout from "./Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import ExcusedDays from "./pages/ExcusedDays";
import Norms from "./pages/Norms";
import EmployeeProfile from "./pages/EmployeeProfile";
import Reports from "./pages/Reports";
import AuditLogs from "./pages/AuditLogs";
import Positions from "./pages/Positions";
import LeadStats from "./pages/LeadStats";
import Statistics from "./pages/Statistics";
import WorkSchedule from "./pages/WorkSchedule";
import Attendance from "./pages/Attendance";
import Offices from "./pages/Offices";
import CheckIn from "./pages/CheckIn";

const MANAGER_ROLES = ["hr", "rop", "boss", "dasturchi"];

function isManager(role?: string): boolean {
  return !!role && MANAGER_ROLES.includes(role);
}

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8 text-center">Yuklanmoqda...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

// Rahbar sahifalari: xodim (employee) kirsa o'z davomat sahifasiga yo'naltiriladi.
function ManagerRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (!isManager(user?.role)) return <Navigate to="/check-in" replace />;
  return children;
}

// Bosh sahifa: rahbar → boshqaruv paneli; xodim → o'z davomati (Face ID check-in).
function HomeIndex() {
  const { user } = useAuth();
  return isManager(user?.role) ? <Dashboard /> : <Navigate to="/check-in" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeIndex />} />
        <Route path="check-in" element={<CheckIn />} />
        <Route path="attendance" element={<ManagerRoute><Attendance /></ManagerRoute>} />
        <Route path="offices" element={<ManagerRoute><Offices /></ManagerRoute>} />
        <Route path="users" element={<ManagerRoute><Users /></ManagerRoute>} />
        <Route path="excused-days" element={<ManagerRoute><ExcusedDays /></ManagerRoute>} />
        <Route path="norms" element={<ManagerRoute><Norms /></ManagerRoute>} />
        <Route path="lead-stats" element={<ManagerRoute><LeadStats /></ManagerRoute>} />
        <Route path="statistics" element={<ManagerRoute><Statistics /></ManagerRoute>} />
        <Route path="work-schedule" element={<ManagerRoute><WorkSchedule /></ManagerRoute>} />
        <Route path="employees/:id" element={<ManagerRoute><EmployeeProfile /></ManagerRoute>} />
        <Route path="reports" element={<ManagerRoute><Reports /></ManagerRoute>} />
        <Route path="audit-logs" element={<ManagerRoute><AuditLogs /></ManagerRoute>} />
        <Route path="positions" element={<ManagerRoute><Positions /></ManagerRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
