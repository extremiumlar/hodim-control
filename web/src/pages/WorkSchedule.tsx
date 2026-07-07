import { useEffect, useState } from "react";
import { api, User, WorkDayEntry, WorkOverride } from "../lib/api";
import { toLocalDateString } from "../lib/date";

const WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];

function emptyWeek(): WorkDayEntry[] {
  return Array.from({ length: 7 }, (_, wd) => ({
    weekday: wd,
    is_working: wd < 6,
    start_time: wd < 6 ? "09:00" : null,
    end_time: wd < 6 ? "18:00" : null,
  }));
}

export default function WorkSchedule() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [week, setWeek] = useState<WorkDayEntry[]>(emptyWeek());
  const [overrides, setOverrides] = useState<WorkOverride[]>([]);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  // Yangi override formasi
  const [ovDate, setOvDate] = useState(toLocalDateString(new Date()));
  const [ovWorking, setOvWorking] = useState(false);
  const [ovStart, setOvStart] = useState("09:00");
  const [ovEnd, setOvEnd] = useState("18:00");
  const [ovNote, setOvNote] = useState("");

  useEffect(() => {
    api.listUsers().then((list) => {
      setUsers(list);
      if (list.length && selectedId == null) setSelectedId(list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId == null) return;
    setMsg(null);
    api.getWeeklySchedule(selectedId).then((w) => setWeek(w.days.sort((a, b) => a.weekday - b.weekday)));
    api.listScheduleOverrides(selectedId).then(setOverrides);
  }, [selectedId]);

  function updateDay(wd: number, patch: Partial<WorkDayEntry>) {
    setWeek((prev) => prev.map((d) => (d.weekday === wd ? { ...d, ...patch } : d)));
  }

  async function saveWeekly() {
    if (selectedId == null) return;
    for (const d of week) {
      if (d.is_working && (!d.start_time || !d.end_time)) {
        setMsg({ kind: "err", text: `${WEEKDAYS[d.weekday]}: ish kuni uchun vaqt kerak` });
        return;
      }
      if (d.is_working && d.start_time! >= d.end_time!) {
        setMsg({ kind: "err", text: `${WEEKDAYS[d.weekday]}: tugash vaqti kechroq bo'lishi kerak` });
        return;
      }
    }
    setSaving(true);
    try {
      await api.setWeeklySchedule(selectedId, week);
      setMsg({ kind: "ok", text: "Haftalik jadval saqlandi" });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Xatolik" });
    } finally {
      setSaving(false);
    }
  }

  async function addOverride() {
    if (selectedId == null) return;
    try {
      await api.setScheduleOverride(selectedId, {
        date: ovDate,
        is_working: ovWorking,
        start_time: ovWorking ? ovStart : null,
        end_time: ovWorking ? ovEnd : null,
        note: ovNote || null,
      });
      setOverrides(await api.listScheduleOverrides(selectedId));
      setOvNote("");
      setMsg({ kind: "ok", text: "O'zgartirish saqlandi" });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : "Xatolik" });
    }
  }

  async function removeOverride(day: string) {
    if (selectedId == null) return;
    await api.deleteScheduleOverride(selectedId, day);
    setOverrides(await api.listScheduleOverrides(selectedId));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold">🗓 Ish jadvali</h2>
        <select
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
          className="border rounded px-3 py-1.5 text-sm min-w-[220px]"
        >
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name} ({u.role})
            </option>
          ))}
        </select>
      </div>

      {msg && (
        <div className={`text-sm rounded px-3 py-2 ${msg.kind === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
          {msg.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Haftalik andoza */}
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="font-medium mb-3">Haftalik andoza (har hafta takrorlanadi)</h3>
          <div className="space-y-2">
            {week.map((d) => (
              <div key={d.weekday} className="flex items-center gap-2 text-sm">
                <label className="w-28 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={d.is_working}
                    onChange={(e) => updateDay(d.weekday, { is_working: e.target.checked })}
                  />
                  {WEEKDAYS[d.weekday]}
                </label>
                {d.is_working ? (
                  <>
                    <input
                      type="time"
                      value={d.start_time ?? ""}
                      onChange={(e) => updateDay(d.weekday, { start_time: e.target.value })}
                      className="border rounded px-2 py-1"
                    />
                    <span>—</span>
                    <input
                      type="time"
                      value={d.end_time ?? ""}
                      onChange={(e) => updateDay(d.weekday, { end_time: e.target.value })}
                      className="border rounded px-2 py-1"
                    />
                  </>
                ) : (
                  <span className="text-slate-400">dam olish</span>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={saveWeekly}
            disabled={saving}
            className="mt-4 bg-indigo-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "Saqlanmoqda..." : "Haftalik jadvalni saqlash"}
          </button>
        </div>

        {/* Aniq sana o'zgartirishlari */}
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="font-medium mb-3">Aniq sana o'zgartirishi (bayram, almashtirilgan smena)</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 flex-wrap">
              <input type="date" value={ovDate} onChange={(e) => setOvDate(e.target.value)} className="border rounded px-2 py-1" />
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={ovWorking} onChange={(e) => setOvWorking(e.target.checked)} />
                Ish kuni
              </label>
              {ovWorking && (
                <>
                  <input type="time" value={ovStart} onChange={(e) => setOvStart(e.target.value)} className="border rounded px-2 py-1" />
                  <span>—</span>
                  <input type="time" value={ovEnd} onChange={(e) => setOvEnd(e.target.value)} className="border rounded px-2 py-1" />
                </>
              )}
            </div>
            <input
              type="text"
              placeholder="Izoh (masalan: Bayram)"
              value={ovNote}
              onChange={(e) => setOvNote(e.target.value)}
              className="border rounded px-2 py-1 w-full"
            />
            <button onClick={addOverride} className="bg-slate-700 text-white rounded px-4 py-1.5 text-sm hover:bg-slate-800">
              O'zgartirishni qo'shish
            </button>
          </div>

          <div className="mt-4 space-y-1">
            {overrides.length === 0 ? (
              <p className="text-sm text-slate-400">O'zgartirishlar yo'q.</p>
            ) : (
              overrides.map((o) => (
                <div key={o.id} className="flex items-center justify-between text-sm border-b border-slate-100 py-1">
                  <span>
                    {o.date} —{" "}
                    {o.is_working ? (
                      <b>{o.start_time}–{o.end_time}</b>
                    ) : (
                      <span className="text-amber-600">dam olish</span>
                    )}
                    {o.note ? ` (${o.note})` : ""}
                  </span>
                  <button onClick={() => removeOverride(o.date)} className="text-red-600 hover:underline">
                    o'chirish
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
