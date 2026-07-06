import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Position, Task, User } from "../lib/api";
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
  dasturchi: "Dasturchi",
};

// Boshliq/Dasturchi ROP/HR/xodimga(+boshliqqa), ROP va HR esa faqat xodimga vazifa bera oladi.
const ASSIGNABLE_ROLES: Record<string, string> = {
  boss: "employee,rop,hr",
  dasturchi: "employee,rop,hr,boss",
  rop: "employee",
  hr: "employee",
};

// Ommaviy vazifa rejimlari (faqat Boshliq/Dasturchi)
const BULK_MODES: { key: string; label: string; targetType: "all_employees" | "role"; roles?: string[] }[] = [
  { key: "all", label: "👥 Barcha xodimlarga", targetType: "all_employees" },
  { key: "rops", label: "🧭 Barcha ROPlarga", targetType: "role", roles: ["rop"] },
  { key: "hrs", label: "🗂 Barcha HRlarga", targetType: "role", roles: ["hr"] },
  { key: "rophr", label: "🤝 ROP + HR (umumiy)", targetType: "role", roles: ["rop", "hr"] },
];

export default function Dashboard() {
  const { user } = useAuth();
  const canBulk = user?.role === "boss" || user?.role === "dasturchi";
  const canCancel = user?.role === "boss" || user?.role === "rop" || user?.role === "dasturchi";
  const isDasturchi = user?.role === "dasturchi";
  const [tasks, setTasks] = useState<Task[]>([]);
  const [assignableUsers, setAssignableUsers] = useState<User[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actingTaskId, setActingTaskId] = useState<number | null>(null);

  // "single" — bitta odamga; "all"/"rops"/"hrs"/"rophr" — ommaviy; "pos:<id>" — lavozimga
  const [targetMode, setTargetMode] = useState("single");
  const [assignedTo, setAssignedTo] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const latestRequestId = useRef(0);

  const load = async (showSpinner = true) => {
    const requestId = ++latestRequestId.current;
    if (showSpinner) setLoading(true);
    try {
      const roleFilter = user ? ASSIGNABLE_ROLES[user.role] ?? "employee" : "employee";
      const [taskList, userList] = await Promise.all([
        api.listTasks("today"),
        api.listUsers(roleFilter),
      ]);
      if (requestId !== latestRequestId.current) return; // yangiroq so'rov allaqachon boshlangan
      setTasks(taskList);
      setAssignableUsers(userList);
    } catch (e) {
      if (requestId !== latestRequestId.current) return;
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      if (requestId === latestRequestId.current && showSpinner) setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (canBulk) {
      api.listPositions().then(setPositions).catch(() => {
        // Lavozimlar hali sozlanmagan bo'lishi mumkin — jim o'tkazamiz
      });
    }
    // MVP uchun real-vaqt sinxronizatsiya shart emas — 20 soniyada bir polling yetarli
    // (spetsifikatsiya 11-bo'lim, 6-band: WebSocket 4-bosqichdan tashqarida qoldirilgan).
    const interval = setInterval(() => load(false), 20000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title) return;
    if (targetMode === "single" && !assignedTo) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const common = {
        title,
        description: description || undefined,
        deadline: deadline ? new Date(deadline).toISOString() : null,
      };
      if (targetMode === "single") {
        await api.createTask({ assigned_to: Number(assignedTo), ...common });
      } else if (targetMode.startsWith("pos:")) {
        const result = await api.createBulkTasks({
          target_type: "position",
          position_id: Number(targetMode.slice(4)),
          ...common,
        });
        setNotice(`Vazifa ${result.created} kishiga berildi ✅`);
      } else {
        const mode = BULK_MODES.find((m) => m.key === targetMode);
        if (!mode) throw new Error("Noma'lum nishon");
        const result = await api.createBulkTasks({
          target_type: mode.targetType,
          target_roles: mode.roles,
          ...common,
        });
        setNotice(`Vazifa ${result.created} kishiga berildi ✅`);
      }
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

  const handleCancelTask = async (taskId: number) => {
    if (!window.confirm("Bu vazifani bekor qilishni tasdiqlaysizmi?")) return;
    setActingTaskId(taskId);
    setError(null);
    try {
      await api.cancelTask(taskId);
      await load(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bekor qilishda xatolik");
    } finally {
      setActingTaskId(null);
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    if (!window.confirm("Bu vazifani bazadan BUTUNLAY o'chirmoqchimisiz? Bu amalni ortga qaytarib bo'lmaydi.")) return;
    setActingTaskId(taskId);
    setError(null);
    try {
      await api.deleteTask(taskId);
      await load(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Butunlay o'chirishda xatolik");
    } finally {
      setActingTaskId(null);
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
        <h2 className="font-semibold mb-4">Yangi vazifa berish</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          {canBulk && (
            <div>
              <label className="block text-sm text-slate-600 mb-1">Nishon</label>
              <select
                value={targetMode}
                onChange={(e) => setTargetMode(e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm"
              >
                <option value="single">👤 Bitta odamga</option>
                {BULK_MODES.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label}
                  </option>
                ))}
                {positions.map((p) => (
                  <option key={`pos:${p.id}`} value={`pos:${p.id}`}>
                    🏷 Lavozim: {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {targetMode === "single" && (
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
          )}
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
          {notice && <p className="text-sm text-emerald-700">{notice}</p>}
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
                {(canCancel || isDasturchi) && <th className="py-2"></th>}
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const canCancelThis = canCancel && task.status !== "done" && task.status !== "cancelled";
                return (
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
                    {(canCancel || isDasturchi) && (
                      <td className="py-2 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-3">
                          {canCancelThis && (
                            <button
                              onClick={() => handleCancelTask(task.id)}
                              disabled={actingTaskId === task.id}
                              className="text-amber-600 hover:underline text-xs disabled:opacity-50"
                            >
                              Bekor qilish
                            </button>
                          )}
                          {isDasturchi && (
                            <button
                              onClick={() => handleDeleteTask(task.id)}
                              disabled={actingTaskId === task.id}
                              className="text-red-800 hover:underline text-xs font-medium disabled:opacity-50"
                            >
                              Butunlay o'chirish
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
