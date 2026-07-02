import { FormEvent, useEffect, useState } from "react";
import { api, User } from "../lib/api";

const ROLE_LABELS: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
};

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("employee");
  const [submitting, setSubmitting] = useState(false);
  const [lastInviteLink, setLastInviteLink] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setUsers(await api.listUsers());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!fullName) return;
    setSubmitting(true);
    setError(null);
    setLastInviteLink(null);
    try {
      const { invite_link } = await api.createUser({ full_name: fullName, role });
      setLastInviteLink(invite_link);
      setFullName("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Foydalanuvchi yaratishda xatolik");
    } finally {
      setSubmitting(false);
    }
  };

  const showInviteLink = async (userId: number) => {
    setError(null);
    setLastInviteLink(null);
    try {
      const { invite_link, already_started } = await api.inviteLink(userId);
      if (already_started) {
        setError("Bu foydalanuvchi botni allaqachon ishga tushirgan.");
      } else {
        setLastInviteLink(invite_link);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Havolani olishda xatolik");
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
        <h2 className="font-semibold mb-4">Foydalanuvchi qo'shish</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">To'liq ism</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="w-full border rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">Rol</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
            >
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? "Yaratilmoqda..." : "Qo'shish"}
          </button>
        </form>

        {lastInviteLink && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded text-xs break-all">
            <p className="font-medium text-emerald-700 mb-1">Bot havolasi:</p>
            <a href={lastInviteLink} target="_blank" rel="noreferrer" className="text-emerald-800 underline">
              {lastInviteLink}
            </a>
          </div>
        )}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      </div>

      <div className="md:col-span-2 bg-white rounded-lg shadow p-5">
        <h2 className="font-semibold mb-4">Barcha foydalanuvchilar</h2>
        {loading ? (
          <p className="text-sm text-slate-500">Yuklanmoqda...</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-2">Ism</th>
                <th className="py-2">Rol</th>
                <th className="py-2">Bot holati</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="py-2">{u.full_name}</td>
                  <td className="py-2">{ROLE_LABELS[u.role] ?? u.role}</td>
                  <td className="py-2">{u.bot_started ? "✅ ulangan" : "— kutilmoqda"}</td>
                  <td className="py-2 text-right">
                    {!u.bot_started && (
                      <button
                        onClick={() => showInviteLink(u.id)}
                        className="text-indigo-600 hover:underline text-xs"
                      >
                        Havola olish
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
