"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export default function LeavesPage() {
  const { isHR } = useMe();
  const { data, mutate } = useSWR("/leave/?page_size=50", fetcher);
  const [form, setForm] = useState({ type: "vacation", start_date: "", end_date: "", reason: "" });
  const [show, setShow] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await api.post("/leave/", form);
    setShow(false);
    mutate();
  }

  async function approve(id: number) { await api.post(`/leave/${id}/approve/`); mutate(); }
  async function reject(id: number) { await api.post(`/leave/${id}/reject/`); mutate(); }
  async function finish(id: number) { await api.post(`/leave/${id}/finish/`); mutate(); }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Ta'til so'rovlari</h1>
        <button className="btn-primary" onClick={() => setShow(!show)}>+ So'rov yuborish</button>
      </div>

      {show && (
        <form onSubmit={submit} className="card space-y-3">
          <div>
            <label className="label">Turi</label>
            <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              <option value="vacation">Ta'til</option>
              <option value="sick">Kasallik</option>
              <option value="unpaid">To'lovsiz</option>
              <option value="other">Boshqa</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="label">Boshlanish</label><input className="input" type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></div>
            <div><label className="label">Tugash</label><input className="input" type="date" required value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></div>
          </div>
          <div>
            <label className="label">Sabab</label>
            <textarea className="input" rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary">Yuborish</button>
            <button type="button" className="btn-ghost" onClick={() => setShow(false)}>Bekor</button>
          </div>
        </form>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-slate-500 border-b">
            <tr>
              {isHR && <th className="text-left py-2">Hodim</th>}
              <th className="text-left py-2">Turi</th>
              <th className="text-left py-2">Boshlanish</th>
              <th className="text-left py-2">Tugash</th>
              <th className="text-left py-2">Sabab</th>
              <th className="text-left py-2">Status</th>
              {isHR && <th className="text-left py-2">Amallar</th>}
            </tr>
          </thead>
          <tbody>
            {data?.results?.map((l: any) => (
              <tr key={l.id} className="border-b last:border-0">
                {isHR && <td className="py-2">{l.user_name}</td>}
                <td>{l.type_display}</td>
                <td>{l.start_date}</td>
                <td>{l.end_date}</td>
                <td className="text-slate-500">{l.reason}</td>
                <td><span className={
                  l.status === "approved" ? "badge-green"
                  : l.status === "rejected" ? "badge-red"
                  : "badge-yellow"
                }>{l.status_display}</span></td>
                {isHR && (
                  <td>
                    {l.status === "pending" && (
                      <div className="flex gap-2">
                        <button className="text-xs text-emerald-600 underline" onClick={() => approve(l.id)}>Tasdiqlash</button>
                        <button className="text-xs text-rose-600 underline" onClick={() => reject(l.id)}>Rad etish</button>
                      </div>
                    )}
                    {l.status === "approved" && (
                      <button className="text-xs underline" onClick={() => finish(l.id)}>Yakunlash</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
