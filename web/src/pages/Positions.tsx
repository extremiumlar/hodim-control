import { FormEvent, useEffect, useState } from "react";
import { api, Position } from "../lib/api";
import { useAuth } from "../lib/auth";

const METRIC_OPTIONS: { key: string; label: string }[] = [
  { key: "suhbat", label: "Suhbatlar" },
  { key: "tashrif", label: "Tashriflar" },
  { key: "video", label: "Videolar (mobilograf)" },
];

const MENU_OPTIONS: { key: string; label: string }[] = [
  { key: "tasks", label: "📋 Vazifalarim" },
  { key: "norm", label: "📊 Bugungi normam" },
  { key: "kpi", label: "💰 Oylik KPI'm" },
  { key: "excused", label: "🙋 Sababli kun so'rash" },
];

const MANAGER_OPTIONS: { key: string; label: string }[] = [
  { key: "rop", label: "ROP (sotuv boshlig'i)" },
  { key: "hr", label: "HR" },
];

interface Draft {
  name: string;
  metrics: string[];
  menuFlags: Record<string, boolean>;
  managedBy: string[];
}

const emptyDraft = (): Draft => ({
  name: "",
  metrics: ["suhbat", "tashrif"],
  menuFlags: { tasks: true, norm: true, kpi: true, excused: true },
  managedBy: [],
});

export default function Positions() {
  const { user: currentUser } = useAuth();
  const canManage = currentUser?.role === "boss" || currentUser?.role === "dasturchi";

  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setPositions(await api.listPositions(true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggleListValue = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  const startEdit = (p: Position) => {
    setEditingId(p.id);
    setDraft({
      name: p.name,
      metrics: p.metrics ?? [],
      menuFlags: { tasks: true, norm: true, kpi: true, excused: true, ...(p.menu_flags ?? {}) },
      managedBy: p.managed_by_roles ?? [],
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraft(emptyDraft());
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const name = draft.name.trim();
    if (!name) {
      setError("Lavozim nomini kiriting");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        name,
        metrics: draft.metrics,
        menu_flags: draft.menuFlags,
        managed_by_roles: draft.managedBy,
      };
      if (editingId !== null) {
        await api.updatePosition(editingId, payload);
      } else {
        await api.createPosition(payload);
      }
      cancelEdit();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saqlashda xatolik");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (p: Position) => {
    setError(null);
    try {
      await api.updatePosition(p.id, { is_active: !p.is_active });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "O'zgartirishda xatolik");
    }
  };

  if (!canManage) {
    return (
      <div className="bg-white rounded-lg shadow p-5">
        <p className="text-sm text-slate-500">
          Lavozimlarni faqat Boshliq yoki Dasturchi boshqara oladi.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <div className="md:col-span-1 bg-white rounded-lg shadow p-5 h-fit">
        <h2 className="font-semibold mb-4">
          {editingId !== null ? "Lavozimni tahrirlash" : "Yangi lavozim"}
        </h2>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-600 mb-1">Nomi</label>
            <input
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              required
              placeholder="masalan: Sotuvchi, Mobilograf"
              className="w-full border rounded px-3 py-2 text-sm"
            />
          </div>

          <div>
            <p className="text-sm text-slate-600 mb-1">Kuzatiladigan ko'rsatkichlar</p>
            <div className="space-y-1">
              {METRIC_OPTIONS.map((opt) => (
                <label key={opt.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={draft.metrics.includes(opt.key)}
                    onChange={() =>
                      setDraft((d) => ({ ...d, metrics: toggleListValue(d.metrics, opt.key) }))
                    }
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm text-slate-600 mb-1">Botda ko'rinadigan tugmalar</p>
            <div className="space-y-1">
              {MENU_OPTIONS.map((opt) => (
                <label key={opt.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={draft.menuFlags[opt.key] ?? true}
                    onChange={() =>
                      setDraft((d) => ({
                        ...d,
                        menuFlags: { ...d.menuFlags, [opt.key]: !(d.menuFlags[opt.key] ?? true) },
                      }))
                    }
                  />
                  {opt.label}
                </label>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              "📈 Statistikam" tugmasi har doim ko'rinadi.
            </p>
          </div>

          <div>
            <p className="text-sm text-slate-600 mb-1">Kim boshqaradi (vazifa/norma)</p>
            <div className="space-y-1">
              {MANAGER_OPTIONS.map((opt) => (
                <label key={opt.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={draft.managedBy.includes(opt.key)}
                    onChange={() =>
                      setDraft((d) => ({ ...d, managedBy: toggleListValue(d.managedBy, opt.key) }))
                    }
                  />
                  {opt.label}
                </label>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Boshliq va Dasturchi har doim barcha lavozimlarni boshqaradi.
            </p>
          </div>

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting ? "Saqlanmoqda..." : editingId !== null ? "Saqlash" : "Qo'shish"}
            </button>
            {editingId !== null && (
              <button
                type="button"
                onClick={cancelEdit}
                className="px-3 border rounded text-sm text-slate-600 hover:bg-slate-50"
              >
                Bekor
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="md:col-span-2 bg-white rounded-lg shadow p-5">
        <h2 className="font-semibold mb-4">Lavozimlar</h2>
        {loading ? (
          <p className="text-sm text-slate-500">Yuklanmoqda...</p>
        ) : positions.length === 0 ? (
          <p className="text-sm text-slate-500">
            Hozircha lavozim yo'q — chapdagi formadan birinchi lavozimni qo'shing (masalan
            "Sotuvchi", "Mobilograf").
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-2">Nomi</th>
                <th className="py-2">Ko'rsatkichlar</th>
                <th className="py-2">Boshqaradi</th>
                <th className="py-2">Holat</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.id} className={`border-b last:border-0 ${!p.is_active ? "opacity-50" : ""}`}>
                  <td className="py-2 font-medium">{p.name}</td>
                  <td className="py-2">
                    {(p.metrics ?? [])
                      .map((m) => METRIC_OPTIONS.find((o) => o.key === m)?.label ?? m)
                      .join(", ") || "—"}
                  </td>
                  <td className="py-2">
                    {(p.managed_by_roles ?? [])
                      .map((r) => MANAGER_OPTIONS.find((o) => o.key === r)?.label ?? r)
                      .join(", ") || "Boshliq/Dasturchi"}
                  </td>
                  <td className="py-2">{p.is_active ? "Faol" : "O'chirilgan"}</td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-3">
                      <button
                        onClick={() => startEdit(p)}
                        className="text-indigo-600 hover:underline text-xs"
                      >
                        Tahrirlash
                      </button>
                      <button
                        onClick={() => toggleActive(p)}
                        className={`hover:underline text-xs ${p.is_active ? "text-red-600" : "text-emerald-600"}`}
                      >
                        {p.is_active ? "O'chirish" : "Tiklash"}
                      </button>
                    </div>
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
