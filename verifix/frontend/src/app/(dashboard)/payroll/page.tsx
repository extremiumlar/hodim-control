"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

function currentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function PayrollPage() {
  const { isHR } = useMe();
  const [period, setPeriod] = useState(currentPeriod());
  const { data, mutate } = useSWR(`/payroll/payrolls/?period=${period}&page_size=100`, fetcher);

  async function compute() {
    await api.post("/payroll/payrolls/compute/", { period });
    mutate();
  }

  async function approve(id: number) {
    await api.post(`/payroll/payrolls/${id}/approve/`);
    mutate();
  }

  async function downloadPdf(id: number, name: string) {
    const r = await api.get(`/reports/payslip/${id}.pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = `oylik_${name}_${period}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  async function downloadXlsx() {
    const r = await api.get(`/reports/payroll.xlsx?period=${period}`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = `oylik_${period}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Oylik hisob-kitob</h1>

      <div className="card flex flex-wrap items-end gap-3">
        <div>
          <label className="label">Davr</label>
          <input className="input" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
        </div>
        {isHR && (
          <>
            <button className="btn-primary" onClick={compute}>🔄 Avtomatik hisoblash</button>
            <button className="btn-ghost" onClick={downloadXlsx}>📥 Excel</button>
          </>
        )}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-slate-500 border-b">
            <tr>
              {isHR && <th className="text-left py-2">Hodim</th>}
              <th className="text-right py-2">Asosiy</th>
              <th className="text-right py-2">Kelmagan</th>
              <th className="text-right py-2">Dam olish</th>
              <th className="text-right py-2">Bonus</th>
              <th className="text-right py-2">Jarima</th>
              <th className="text-right py-2">Kechikish</th>
              <th className="text-right py-2 font-bold">Yakuniy</th>
              <th className="text-left py-2">Holat</th>
              <th className="text-left py-2">Amallar</th>
            </tr>
          </thead>
          <tbody>
            {data?.results?.map((p: any) => (
              <tr key={p.id} className="border-b last:border-0">
                {isHR && <td className="py-2">{p.user_name}</td>}
                <td className="text-right">{Number(p.base_salary).toLocaleString("uz-UZ")}</td>
                <td className="text-right text-rose-600" title={`${p.absent_days || 0} kun × ${Number(p.per_day_rate || 0).toLocaleString("uz-UZ")}`}>
                  {Number(p.absence_deduction) > 0 ? `-${Number(p.absence_deduction).toLocaleString("uz-UZ")}` : "—"}
                </td>
                <td className="text-right text-emerald-600">+{Number(p.weekend_extra).toLocaleString("uz-UZ")}</td>
                <td className="text-right text-emerald-600">+{Number(p.bonus_total).toLocaleString("uz-UZ")}</td>
                <td className="text-right text-rose-600">-{Number(p.penalty_total).toLocaleString("uz-UZ")}</td>
                <td className="text-right text-rose-600">-{Number(p.late_penalty_total).toLocaleString("uz-UZ")}</td>
                <td className="text-right font-bold">{Number(p.total).toLocaleString("uz-UZ")}</td>
                <td>{p.is_approved ? <span className="badge-green">Tasdiqlangan</span> : <span className="badge-yellow">Kutilmoqda</span>}</td>
                <td>
                  <div className="flex gap-2">
                    <button className="text-xs underline" onClick={() => downloadPdf(p.id, p.user_name)}>PDF</button>
                    {isHR && !p.is_approved && (
                      <button className="text-xs text-emerald-600 underline" onClick={() => approve(p.id)}>Tasdiqlash</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!data?.results?.length && <tr><td colSpan={isHR ? 10 : 9} className="py-4 text-center text-slate-400">Bu davr uchun ma'lumot yo'q. "Avtomatik hisoblash" tugmasini bosing.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
