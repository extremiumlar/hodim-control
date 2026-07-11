"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export default function TasksPage() {
  const { isHR } = useMe();
  const { data, mutate } = useSWR("/tasks/?page_size=50", fetcher);
  const { data: users } = useSWR(isHR ? "/accounts/users/?page_size=200" : null, fetcher);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", assigned_to: "", due_date: "", priority: "normal", kpi_points: 10 });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await api.post("/tasks/", form);
    setShowForm(false);
    setForm({ title: "", description: "", assigned_to: "", due_date: "", priority: "normal", kpi_points: 10 });
    mutate();
  }

  async function complete(id: number) {
    await api.post(`/tasks/${id}/complete/`);
    mutate();
  }

  async function approve(id: number) {
    await api.post(`/tasks/${id}/approve/`);
    mutate();
  }

  async function uploadProof(taskId: number, file: File) {
    const fd = new FormData();
    fd.append("task", String(taskId));
    fd.append("file", file);
    await api.post("/tasks/proofs/", fd, { headers: { "Content-Type": "multipart/form-data" } });
    mutate();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Vazifalar</h1>
        {isHR && (
          <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
            + Yangi vazifa
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={submit} className="card space-y-3">
          <div>
            <label className="label">Sarlavha</label>
            <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </div>
          <div>
            <label className="label">Tavsif</label>
            <textarea className="input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Hodim</label>
              <select className="input" value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })} required>
                <option value="">— Tanlang —</option>
                {users?.results?.map((u: any) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Muddat</label>
              <input className="input" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </div>
            <div>
              <label className="label">Muhimligi</label>
              <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="low">Past</option>
                <option value="normal">O'rta</option>
                <option value="high">Yuqori</option>
              </select>
            </div>
            <div>
              <label className="label">KPI ball</label>
              <input className="input" type="number" value={form.kpi_points} onChange={(e) => setForm({ ...form, kpi_points: Number(e.target.value) })} />
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" type="submit">Saqlash</button>
            <button className="btn-ghost" type="button" onClick={() => setShowForm(false)}>Bekor qilish</button>
          </div>
        </form>
      )}

      <div className="space-y-3">
        {data?.results?.map((t: any) => (
          <div key={t.id} className="card">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold">{t.title}</h3>
                  <span className={
                    t.status === "approved" ? "badge-green"
                    : t.status === "done" ? "badge-blue"
                    : t.status === "rejected" ? "badge-red"
                    : t.status === "in_progress" ? "badge-yellow"
                    : "badge-gray"
                  }>{t.status_display}</span>
                  <span className={`badge-${t.priority === "high" ? "red" : t.priority === "low" ? "gray" : "blue"}`}>{t.priority_display}</span>
                </div>
                <p className="text-sm text-slate-600">{t.description}</p>
                <div className="text-xs text-slate-500 mt-2">
                  {t.assigned_to_name} {t.due_date && `· Muddat: ${t.due_date}`} · KPI: {t.kpi_points}
                </div>
                {t.proofs?.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {t.proofs.map((p: any) => (
                      <a key={p.id} href={p.file} target="_blank" rel="noreferrer"
                         className="text-xs bg-slate-100 px-2 py-1 rounded hover:bg-slate-200">
                        📎 {p.file.split("/").pop()}
                      </a>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-2 shrink-0">
                {t.status !== "approved" && t.status !== "done" && (
                  <>
                    <label className="btn-ghost text-xs cursor-pointer">
                      📎 Isbot yuklash
                      <input type="file" className="hidden" onChange={(e) => e.target.files && uploadProof(t.id, e.target.files[0])} />
                    </label>
                    <button className="btn-success text-xs" onClick={() => complete(t.id)}>Tugatdim</button>
                  </>
                )}
                {isHR && t.status === "done" && (
                  <button className="btn-primary text-xs" onClick={() => approve(t.id)}>Tasdiqlash</button>
                )}
              </div>
            </div>
          </div>
        ))}
        {!data?.results?.length && <div className="card text-center text-slate-500">Vazifalar yo'q.</div>}
      </div>
    </div>
  );
}
