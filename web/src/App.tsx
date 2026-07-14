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

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8 text-center">Yuklanmoqda...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
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
        <Route index element={<Dashboard />} />
        <Route path="users" element={<Users />} />
        <Route path="excused-days" element={<ExcusedDays />} />
        <Route path="norms" element={<Norms />} />
        <Route path="lead-stats" element={<LeadStats />} />
        <Route path="statistics" element={<Statistics />} />
        <Route path="work-schedule" element={<WorkSchedule />} />
        <Route path="employees/:id" element={<EmployeeProfile />} />
        <Route path="reports" element={<Reports />} />
        <Route path="audit-logs" element={<AuditLogs />} />
        <Route path="positions" element={<Positions />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
