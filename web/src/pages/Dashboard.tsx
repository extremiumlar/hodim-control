import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Task, User } from "../lib/api";
import { useAuth } from "../lib/auth";

const STATUS_LABELS: Record<string, string> = {
  pending: "🕓 Kutilmoqda",
  done: "✅ Bajarildi",
  overdue: "⏰ Muddati o'tgan",
  cancelled: "🚫 Bekor qilingan",
};

const ROLE_LABELS: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
};

// Boshliq ROP/HR/xodimga, ROP va HR esa faqat xodimga vazifa bera oladi.
const ASSIGNABLE_ROLES: Record<string, string> = {
  boss: "employee,rop,hr",
  rop: "employee",
  hr: "employee",
};

export default function Dashboard() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [assignableUsers, setAssignableUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [assignedTo, setAssignedTo] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const roleFilter = user ? ASSIGNABLE_ROLES[user.role] ?? "employee" : "employee";
      const [taskList, userList] = await Promise.all([
        api.listTasks("today"),
        api.listUsers(roleFilter),
      ]);
      setTasks(taskList);
      setAssignableUsers(userList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      if (showSpinner) setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // MVP uchun real-vaqt sinxronizatsiya shart emas — 20 soniyada bir polling yetarli
    // (spetsifikatsiya 11-bo'lim, 6-band: WebSocket 4-bosqichdan tashqarida qoldirilgan).
    const interval = setInterval(() => load(false), 20000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!assignedTo || !title) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createTask({
        assigned_to: Number(assignedTo),
        title,
        description: description || undefined,
        deadline: deadline ? new Date(deadline).toISOString() : null,
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setAssignedTo("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Vazifa yaratishda xatolik");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
        <h2 className="font-semibold mb-4">Yangi vazifa berish</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">Kimga</label>
            <select
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
              required
              className="w-full border rounded px-3 py-2 text-sm"
            >
              <option value="">— foydalanuvchi tanlang —</option>
              {assignableUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name} ({ROLE_LABELS[u.role] ?? u.role})
                  {!u.bot_started ? " — bot ulanmagan" : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Nima</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="w-full border rounded px-3 py-2 text-sm"
              placeholder="Vazifa nomi"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Tavsif (ixtiyoriy)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              rows={2}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Muddat</label>
            <input
              type="datetime-local"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? "Yuborilmoqda..." : "Vazifa berish"}
          </button>
        </form>
      </div>

      <div className="md:col-span-2 bg-white rounded-lg shadow p-5">
        <h2 className="font-semibold mb-4">Bugungi vazifalar</h2>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        {loading ? (
          <p className="text-sm text-slate-500">Yuklanmoqda...</p>
        ) : tasks.length === 0 ? (
          <p className="text-sm text-slate-500">Bugun hali vazifa berilmagan.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-2">Xodim</th>
                <th className="py-2">Vazifa</th>
                <th className="py-2">Muddat</th>
                <th className="py-2">Holat</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id} className="border-b last:border-0">
                  <td className="py-2">
                    <Link to={`/employees/${task.assigned_to}`} className="text-indigo-600 hover:underline">
                      {task.assigned_to_name}
                    </Link>
                  </td>
                  <td className="py-2">{task.title}</td>
                  <td className="py-2">
                    {task.deadline ? new Date(task.deadline).toLocaleString() : "—"}
                  </td>
                  <td className="py-2">{STATUS_LABELS[task.status] ?? task.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
