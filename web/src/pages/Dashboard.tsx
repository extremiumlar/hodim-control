import DashboardStatCards from "@/components/dashboard/DashboardStatCards";
import TaskForm from "@/components/dashboard/TaskForm";
import TaskList from "@/components/dashboard/TaskList";

export default function Dashboard() {
  return (
    <div className="space-y-6">
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
