"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export default function AttendancePage() {
  const { isHR } = useMe();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  params.set("page_size", "100");

  const { data } = useSWR(`/attendance/?${params.toString()}`, fetcher);

  async function downloadXlsx() {
    const r = await api.get(`/reports/attendance.xlsx?${params.toString()}`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = "davomat.xlsx"; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Davomat</h1>

      <div className="card flex flex-wrap items-end gap-3">
        <div>
          <label className="label">Boshlanish</label>
          <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="label">Tugash</label>
          <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        {isHR && <button className="btn-primary" onClick={downloadXlsx}>📥 Excel yuklab olish</button>}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-slate-500 border-b">
            <tr>
              <th className="text-left py-2">Sana</th>
              {isHR && <th className="text-left py-2">Hodim</th>}
              <th className="text-left py-2">Keldim</th>
              <th className="text-left py-2">Ketdim</th>
              <th className="text-left py-2">Kechikish</th>
              <th className="text-left py-2">Erta ketish</th>
              <th className="text-left py-2">Ishlangan</th>
              <th className="text-left py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {data?.results?.map((a: any) => (
              <tr key={a.id} className="border-b last:border-0">
                <td className="py-2">{a.date}</td>
                {isHR && <td>{a.user_name}</td>}
                <td>{a.check_in_time ? new Date(a.check_in_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                <td>{a.check_out_time ? new Date(a.check_out_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                <td>{a.late_minutes > 0 ? <span className="text-rose-600">{a.late_minutes} daq</span> : "—"}</td>
                <td>{a.early_leave_minutes > 0 ? <span className="text-amber-600">{a.early_leave_minutes} daq</span> : "—"}</td>
                <td>{a.worked_minutes ? `${Math.floor(a.worked_minutes / 60)}s ${a.worked_minutes % 60}d` : "—"}</td>
                <td>
                  <span className={
                    a.status === "late" ? "badge-yellow"
                    : a.status === "absent" ? "badge-red"
                    : a.status === "weekend" ? "badge-gray"
                    : "badge-green"
                  }>{a.status_display}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
