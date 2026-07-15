import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import Layout from "./Layout";

// Route-level code-splitting: har bir sahifa alohida chunk bo'lib, faqat
// ochilganda yuklanadi. Ayniqsa muhim: recharts (EmployeeProfile) va
// @vladmandic/face-api (CheckIn) katta kutubxonalar — asosiy bundle'ga kirmaydi.
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Users = lazy(() => import("./pages/Users"));
const ExcusedDays = lazy(() => import("./pages/ExcusedDays"));
const Norms = lazy(() => import("./pages/Norms"));
const EmployeeProfile = lazy(() => import("./pages/EmployeeProfile"));
const Reports = lazy(() => import("./pages/Reports"));
const AuditLogs = lazy(() => import("./pages/AuditLogs"));
const Positions = lazy(() => import("./pages/Positions"));
const LeadStats = lazy(() => import("./pages/LeadStats"));
const Statistics = lazy(() => import("./pages/Statistics"));
const WorkSchedule = lazy(() => import("./pages/WorkSchedule"));
const Attendance = lazy(() => import("./pages/Attendance"));
const Offices = lazy(() => import("./pages/Offices"));
const CheckIn = lazy(() => import("./pages/CheckIn"));

const MANAGER_ROLES = ["hr", "rop", "boss", "dasturchi"];

function isManager(role?: string): boolean {
  return !!role && MANAGER_ROLES.includes(role);
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center p-12">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
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
    <Suspense fallback={<PageLoader />}>
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
    </Suspense>
  );
}
