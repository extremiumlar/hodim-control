import SetupStatusCard from "@/components/SetupStatusCard";
import DashboardStatCards from "@/components/dashboard/DashboardStatCards";
import TaskForm from "@/components/dashboard/TaskForm";
import TaskList from "@/components/dashboard/TaskList";
import { useAuth } from "@/lib/auth";

export default function Dashboard() {
  const { user } = useAuth();
  // Endpoint faqat HR/Boshliq/Dasturchi uchun ochiq — boshqa rolda so'rov
  // yubormaymiz (403 va konsolda keraksiz xato bo'lardi).
  const canSeeSetup = ["hr", "boss", "dasturchi"].includes(user?.role ?? "");

  return (
    <div className="space-y-6">
      {/* Eng tepada ATAYLAB: sozlanmagan modul topilsa, u boshqa raqamlarni
          ham noto'g'ri qiladi — avval shuni ko'rsin. */}
      <SetupStatusCard enabled={canSeeSetup} />
      <DashboardStatCards />
      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-1">
          <TaskForm />
        </div>
        <div className="md:col-span-2">
          <TaskList />
        </div>
      </div>
    </div>
  );
}
