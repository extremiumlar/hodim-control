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
const Payroll = lazy(() => import("./pages/Payroll"));
const PayrollSettings = lazy(() => import("./pages/PayrollSettings"));
const Overtime = lazy(() => import("./pages/Overtime"));
const AdminOverride = lazy(() => import("./pages/AdminOverride"));
const WorkLog = lazy(() => import("./pages/WorkLog"));

// Xodim kabineti. Bo'limlarning KO'RINISH shartlari lib/employeeNav.ts da —
// bot menyusi (bot/keyboards.py: main_menu) bilan aynan bir xil.
// Bosqich 4 tugadi: barcha bo'limlar haqiqiy sahifaga ulangan, vaqtinchalik
// "Tez orada" placeholder'i endi kerak emas va olib tashlandi.
const MeMore = lazy(() => import("./pages/me/More"));
const MeSchedule = lazy(() => import("./pages/me/Schedule"));
const MePayroll = lazy(() => import("./pages/me/Payroll"));
const MeNorm = lazy(() => import("./pages/me/Norm"));
const MeTasks = lazy(() => import("./pages/me/Tasks"));
const MeHourlyPlan = lazy(() => import("./pages/me/HourlyPlan"));
const MeStats = lazy(() => import("./pages/me/Stats"));
const MeKpi = lazy(() => import("./pages/me/Kpi"));
const MeExcused = lazy(() => import("./pages/me/Excused"));
const MeWorkLog = lazy(() => import("./pages/me/WorkLog"));

const MANAGER_ROLES = ["hr", "rop", "boss", "dasturchi"];
// Payroll sozlash/hisoblash — ROP'da yo'q (9-bo'lim, savol 8, QAROR):
// maosh sozlamalari/hisob-kitobi faqat HR/Boshliq/Dasturchi qo'lida.
const PAYROLL_MANAGE_ROLES = ["hr", "boss", "dasturchi"];

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

// Davomat sahifasi: rahbarlar + Dasturchi SHAXSAN davomat tuzatish huquqini
// bergan odamlar. Oddiy xodimga huquq berilgan bo'lsa, u ham shu sahifaga
// kira olishi kerak — aks holda huquq bor, lekin ishlatadigan joyi yo'q.
function AttendanceRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (!isManager(user?.role) && !user?.can_edit_attendance) {
    return <Navigate to="/check-in" replace />;
  }
  return children;
}

// Payroll sozlash/hisoblash sahifalari: ROP ham "rahbar", lekin bu yerga kira
// olmaydi — payslip ro'yxatini o'z jamoasi uchun /payroll'da ko'radi.
function PayrollManageRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (!PAYROLL_MANAGE_ROLES.includes(user?.role ?? "")) return <Navigate to="/payroll" replace />;
  return children;
}

// Payroll SOZLAMALARI sahifasi: rahbarlar + Dasturchi/Boshliq shaxsan
// «kechikish normasi» huquqini bergan odamlar (masalan ROP). Sahifaning
// o'zi jarima qoidasidan tashqari narsalarni ham ko'rsatishi mumkin, lekin
// backend har bir endpointni alohida qo'riqlaydi: bayroq FAQAT
// `/payroll/policies` ni ochadi, hisoblash/tasdiqlashni EMAS.
function FinePolicyRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  const allowed =
    PAYROLL_MANAGE_ROLES.includes(user?.role ?? "") || !!user?.can_edit_fine_policy;
  if (!allowed) return <Navigate to="/payroll" replace />;
  return children;
}

// Dasturchi rejimi (super-admin, OYLIK_JARIMA_REJASI.md 11-bo'lim) — FAQAT
// dasturchi, Boshliq HAM kirmaydi (u override tarixini /audit-logs orqali
// emas, hozircha faqat backenddan ko'radi — 11.6-band).
// E'TIBOR: yo'l ataylab "/dasturchi" — "/admin" band (vite.config.ts'dagi
// eski verifix/Django admin redirekti "/admin"ni "/attendance"ga
// yo'naltiradi, server darajasida, React Router ko'rishidan OLDIN).
function DasturchiRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (user?.role !== "dasturchi") return <Navigate to="/" replace />;
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
        {/* Mobil ilova (WebView) — davomat sahifasi Layout'SIZ: ilovaning o'z
            navigatsiyasi bor, sidebar/header ikki marta ko'rinmasligi kerak.
            JWT'ni ilova WebView'ga localStorage["access_token"] sifatida
            inject qiladi (mobile/app/checkin.tsx). Face ID kodi web bilan
            aynan bir xil qoladi — descriptorlar mos, xodimlar yuzini
            qaytadan ro'yxatdan o'tkazmaydi (MOBIL_ILOVA_REJASI.md 4.2). */}
        <Route
          path="/embed/check-in"
          element={
            <ProtectedRoute>
              {/* UX2-MC6: Layout'siz marshrutda chekka yo'q edi — kartalar
                  telefon chetiga yopishib turardi (/view bo'limlari chekkali,
                  eng muhim ekran esa chekkasi yo'q bo'lib qolgan edi). */}
              <div className="px-4 py-4">
                <CheckIn />
              </div>
            </ProtectedRoute>
          }
        />
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

          {/* ── Xodim kabineti ──
              ManagerRoute'ga O'RALMAYDI: bu sahifalar xodim uchun. Rahbar ham
              kira oladi (u ham o'z jadvalini/oyligini ko'radi — bot ham
              shunday: BTN_SCHEDULE va BTN_PAYROLL rahbarlarda ham bor).
              Har bir endpoint tokendan `current_user` oladi, ya'ni kim
              kirsa o'zining ma'lumotini ko'radi. */}
          <Route path="me/more" element={<MeMore />} />
          <Route path="me/schedule" element={<MeSchedule />} />
          <Route path="me/payroll" element={<MePayroll />} />
          <Route path="me/stats" element={<MeStats />} />
          <Route path="me/tasks" element={<MeTasks />} />
          <Route path="me/norm" element={<MeNorm />} />
          <Route path="me/hourly-plan" element={<MeHourlyPlan />} />
          <Route path="me/kpi" element={<MeKpi />} />
          {/* LeadStats sahifasi ALLAQACHON ikkala holatni biladi: `isManager`
              bayrog'i bo'yicha tashkilot yoki shaxsiy ko'rinishni chizadi va
              hooklar `/stats/web/lead-stages/me` ga boradi. Backend ham tayyor
              (`_can_view_lead_stats` sotuv xodimlariga ruxsat beradi). Ya'ni
              bu yerda yangi sahifa emas — faqat xodimga yo'l ochiladi. */}
          <Route path="me/lead-stats" element={<LeadStats />} />
          <Route path="me/excused" element={<MeExcused />} />
          <Route path="me/work-log" element={<MeWorkLog />} />
          <Route path="attendance" element={<AttendanceRoute><Attendance /></AttendanceRoute>} />
          <Route path="offices" element={<ManagerRoute><Offices /></ManagerRoute>} />
          <Route path="users" element={<ManagerRoute><Users /></ManagerRoute>} />
          <Route path="excused-days" element={<ManagerRoute><ExcusedDays /></ManagerRoute>} />
          <Route path="norms" element={<ManagerRoute><Norms /></ManagerRoute>} />
          <Route path="lead-stats" element={<ManagerRoute><LeadStats /></ManagerRoute>} />
          <Route path="statistics" element={<ManagerRoute><Statistics /></ManagerRoute>} />
          <Route path="work-schedule" element={<ManagerRoute><WorkSchedule /></ManagerRoute>} />
          {/* Ish kundaligi — ROP ham kiradi (backend uni o'z jamoasi bilan
              cheklaydi: work_log.py VIEW_ROLES + manager_id filtri). */}
          <Route path="work-log" element={<ManagerRoute><WorkLog /></ManagerRoute>} />
          <Route path="employees/:id" element={<ManagerRoute><EmployeeProfile /></ManagerRoute>} />
          <Route path="reports" element={<ManagerRoute><Reports /></ManagerRoute>} />
          <Route path="audit-logs" element={<ManagerRoute><AuditLogs /></ManagerRoute>} />
          <Route path="positions" element={<ManagerRoute><Positions /></ManagerRoute>} />
          <Route path="payroll" element={<ManagerRoute><Payroll /></ManagerRoute>} />
          <Route
            path="payroll/settings"
            element={<FinePolicyRoute><PayrollSettings /></FinePolicyRoute>}
          />
          <Route path="overtime" element={<PayrollManageRoute><Overtime /></PayrollManageRoute>} />
          <Route path="dasturchi" element={<DasturchiRoute><AdminOverride /></DasturchiRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
