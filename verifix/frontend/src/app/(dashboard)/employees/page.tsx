"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export default function EmployeesPage() {
  const { isHR } = useMe();
  const { data: users, mutate } = useSWR(isHR ? "/accounts/users/?page_size=200" : null, fetcher);
  const { data: depts } = useSWR(isHR ? "/accounts/departments/" : null, fetcher);
  const { data: shifts } = useSWR(isHR ? "/accounts/shifts/" : null, fetcher);
  const { data: offices } = useSWR(isHR ? "/accounts/offices/" : null, fetcher);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<any>({
    username: "", password: "", first_name: "", last_name: "", email: "",
    phone: "", role: "employee", department: "", shift: "", office: "",
    work_days: "1,2,3,4,5",
    base_salary: 0, weekend_rate: 150, late_penalty_per_minute: 0,
  });

  if (!isHR) return <div className="card">Sizda ruxsat yo'q.</div>;

  // Ish kunlarini boshqarish
  const DAYS = [
    { n: 1, label: "Du" }, { n: 2, label: "Se" }, { n: 3, label: "Ch" },
    { n: 4, label: "Pa" }, { n: 5, label: "Ju" }, { n: 6, label: "Sha" }, { n: 7, label: "Ya" },
  ];
  function selectedDays(): number[] {
    return form.work_days.split(",").filter((x: string) => x).map(Number);
  }
  function toggleDay(n: number) {
    const cur = new Set(selectedDays());
    cur.has(n) ? cur.delete(n) : cur.add(n);
    const arr = Array.from(cur).sort((a, b) => a - b);
    setForm({ ...form, work_days: arr.join(",") });
  }
  function setPreset(days: string) {
    setForm({ ...form, work_days: days });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = { ...form };
    ["department", "shift", "office"].forEach((k) => {
      if (!payload[k]) payload[k] = null; else payload[k] = Number(payload[k]);
    });
    await api.post("/accounts/users/", payload);
    setShowForm(false);
    mutate();
  }

  async function toggleLeave(u: any) {
    await api.patch(`/accounts/users/${u.id}/`, { is_on_leave: !u.is_on_leave });
    mutate();
  }

  async function toggleActive(u: any) {
    await api.patch(`/accounts/users/${u.id}/`, { is_active: !u.is_active });
    mutate();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Hodimlar</h1>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>+ Yangi hodim</button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card grid grid-cols-2 gap-3">
          <div className="col-span-2 text-lg font-semibold">Yangi hodim qo'shish</div>
          <div><label className="label">Username</label><input className="input" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
          <div><label className="label">Parol</label><input className="input" type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
          <div><label className="label">Ism</label><input className="input" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></div>
          <div><label className="label">Familiya</label><input className="input" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></div>
          <div><label className="label">Email</label><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
          <div><label className="label">Telefon</label><input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
          <div>
            <label className="label">Rol</label>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="employee">Hodim</option>
              <option value="hr">HR/Manager</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div>
            <label className="label">Bo'lim</label>
            <select className="input" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>
              <option value="">—</option>
              {depts?.results?.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Smena</label>
            <select className="input" value={form.shift} onChange={(e) => setForm({ ...form, shift: e.target.value })}>
              <option value="">—</option>
              {shifts?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Ofis</label>
            <select className="input" value={form.office} onChange={(e) => setForm({ ...form, office: e.target.value })}>
              <option value="">—</option>
              {offices?.results?.map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </div>
          {/* Ish kunlari */}
          <div className="col-span-2">
            <label className="label">Ish kunlari</label>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <button type="button" onClick={() => setPreset("1,2,3,4,5")}
                className={`text-xs px-3 py-1.5 rounded-lg border ${form.work_days === "1,2,3,4,5" ? "bg-primary-600 text-white border-primary-600" : "bg-white border-slate-300 text-slate-600"}`}>
                5 kunlik (Du–Ju)
              </button>
              <button type="button" onClick={() => setPreset("1,2,3,4,5,6")}
                className={`text-xs px-3 py-1.5 rounded-lg border ${form.work_days === "1,2,3,4,5,6" ? "bg-primary-600 text-white border-primary-600" : "bg-white border-slate-300 text-slate-600"}`}>
                6 kunlik (Du–Sha)
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((d) => {
                const on = selectedDays().includes(d.n);
                return (
                  <button key={d.n} type="button" onClick={() => toggleDay(d.n)}
                    className={`w-12 py-2 rounded-lg text-sm font-medium border transition ${on ? "bg-emerald-500 text-white border-emerald-500" : "bg-white border-slate-300 text-slate-500 hover:bg-slate-50"}`}>
                    {d.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Tanlangan: {selectedDays().length} kun/hafta. Belgilanmagan kunlar dam olish hisoblanadi.
            </p>
          </div>

          <div><label className="label">Asosiy oylik</label><input className="input" type="number" value={form.base_salary} onChange={(e) => setForm({ ...form, base_salary: e.target.value })} /></div>
          <div><label className="label">Dam olish kuni stavkasi (%)</label><input className="input" type="number" value={form.weekend_rate} onChange={(e) => setForm({ ...form, weekend_rate: e.target.value })} /></div>
          <div><label className="label">1 daq kechikish jarimasi</label><input className="input" type="number" value={form.late_penalty_per_minute} onChange={(e) => setForm({ ...form, late_penalty_per_minute: e.target.value })} /></div>
          <div className="col-span-2 flex gap-2">
            <button type="submit" className="btn-primary">Saqlash</button>
            <button type="button" className="btn-ghost" onClick={() => setShowForm(false)}>Bekor</button>
          </div>
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-slate-500 border-b">
            <tr>
              <th className="text-left py-2">Ism</th>
              <th className="text-left py-2">Rol</th>
              <th className="text-left py-2">Bo'lim</th>
              <th className="text-left py-2">Ish kunlari</th>
              <th className="text-left py-2">Oylik</th>
              <th className="text-left py-2">Status</th>
              <th className="text-left py-2">Amallar</th>
            </tr>
          </thead>
          <tbody>
            {users?.results?.map((u: any) => (
              <tr key={u.id} className="border-b last:border-0">
                <td className="py-2">
                  <div className="font-medium">{u.full_name}</div>
                  <div className="text-xs text-slate-500">@{u.username}</div>
                </td>
                <td>{u.role === "admin" ? "Admin" : u.role === "hr" ? "HR" : "Hodim"}</td>
                <td>{u.department_name || "—"}</td>
                <td>
                  <span className="badge-blue">{(u.work_days || "").split(",").filter(Boolean).length} kun</span>
                </td>
                <td>{Number(u.base_salary).toLocaleString("uz-UZ")} so'm</td>
                <td>
                  {!u.is_active ? <span className="badge-gray">Faol emas</span>
                   : u.is_on_leave ? <span className="badge-yellow">Ta'tilda</span>
                   : <span className="badge-green">Faol</span>}
                </td>
                <td>
                  <div className="flex gap-2">
                    <button className="text-xs underline" onClick={() => toggleLeave(u)}>{u.is_on_leave ? "Ta'tildan qaytarish" : "Ta'tilga"}</button>
                    <button className="text-xs underline text-rose-600" onClick={() => toggleActive(u)}>{u.is_active ? "O'chirish" : "Yoqish"}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
