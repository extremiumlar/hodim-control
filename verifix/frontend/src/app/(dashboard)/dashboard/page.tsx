"use client";
import useSWR from "swr";
import CheckInCard from "@/components/CheckInCard";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import Link from "next/link";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export default function DashboardPage() {
  const { me } = useMe();
  const { data: tasks } = useSWR("/tasks/?status=new&page_size=5", fetcher);
  const { data: atts } = useSWR("/attendance/?page_size=7", fetcher);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Salom, {me?.full_name?.split(" ")[0] || "Hodim"} 👋</h1>
        <p className="text-slate-500">Bugungi ishingiz qanday ketmoqda?</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CheckInCard />

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Faol vazifalar</h2>
            <Link href="/tasks" className="text-sm text-primary-600 hover:underline">Barchasi →</Link>
          </div>
          {tasks?.results?.length ? (
            <ul className="space-y-2">
              {tasks.results.map((t: any) => (
                <li key={t.id} className="flex items-center justify-between border border-slate-100 rounded-lg p-3 hover:bg-slate-50">
                  <div>
                    <div className="font-medium text-sm">{t.title}</div>
                    {t.due_date && <div className="text-xs text-slate-500">Muddat: {t.due_date}</div>}
                  </div>
                  <span className={`badge-${t.priority === "high" ? "red" : t.priority === "low" ? "gray" : "blue"}`}>
                    {t.priority_display}
                  </span>
                </li>
              ))}
            </ul>
          ) : <div className="text-slate-500 text-sm">Faol vazifalar yo'q.</div>}
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4">So'nggi 7 kun davomati</h2>
        <table className="w-full text-sm">
          <thead className="text-slate-500">
            <tr className="border-b">
              <th className="text-left py-2">Sana</th>
              <th className="text-left py-2">Keldim</th>
              <th className="text-left py-2">Ketdim</th>
              <th className="text-left py-2">Ishlangan</th>
              <th className="text-left py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {atts?.results?.map((a: any) => (
              <tr key={a.id} className="border-b last:border-0">
                <td className="py-2">{a.date}</td>
                <td>{a.check_in_time ? new Date(a.check_in_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                <td>{a.check_out_time ? new Date(a.check_out_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
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
            {!atts?.results?.length && <tr><td colSpan={5} className="py-4 text-center text-slate-400">Hali yozuv yo'q.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
