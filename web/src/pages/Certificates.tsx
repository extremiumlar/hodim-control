/**
 * «Ma'lumotnomalar» arxivi — HR paneli (TZ 3.9 / S-17).
 *
 * Ma'lumotnomaning O'ZI bu yerdan berilmaydi: xodim ariza yuboradi, HR
 * tasdiqlaydi va hujjat AVTOMATIK tayyorlanadi. Bu yerda arxiv («kimga,
 * qachon, qaysi maqsadda») va HR ning arizasiz berish yo'li — xodim
 * og'zaki so'ragan holat uchun.
 *
 * ⚠️ O'rtacha oylik SUMMASI arxivda ko'rsatilmaydi — faqat «yozilganmi?»
 * bayrog'i. Summa maxfiy va u hujjatning o'zida.
 */
import { useState } from "react";
import { FileCheck2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCertificatePurposes,
  useCertificates,
  useIssueCertificate,
  useUsers,
} from "@/lib/queries";

export default function Certificates() {
  const [filterUser, setFilterUser] = useState<string>("");
  const { data, isLoading } = useCertificates(
    filterUser ? Number(filterUser) : undefined
  );
  const { data: users } = useUsers();
  const { data: purposes } = useCertificatePurposes();
  const issue = useIssueCertificate();

  const [userId, setUserId] = useState("");
  const [purpose, setPurpose] = useState("");
  const [withSalary, setWithSalary] = useState(false);

  async function ber() {
    if (!userId || !purpose) {
      toast.error("Xodim va maqsadni tanlang");
      return;
    }
    const r = await issue.mutateAsync({
      user_id: Number(userId),
      purpose,
      include_salary: withSalary,
    });
    toast.success(
      r.note ? `${r.number} — ${r.note}` : `${r.number} tayyorlanmoqda`
    );
    setPurpose("");
    setWithSalary(false);
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Ma'lumotnomalar" />

      <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        Xodim ariza yuborsa, siz tasdiqlaganingizda ma'lumotnoma{" "}
        <b>avtomatik tayyorlanadi</b> va uning Telegram'iga boradi. Pastdagi
        forma faqat <b>og'zaki so'rov</b> uchun.
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCheck2 className="h-4 w-4" />
            Arizasiz berish
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="min-w-[200px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Xodim</div>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger>
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(users ?? []).map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[180px]">
            <div className="mb-1 text-xs text-slate-600">Maqsad</div>
            <Select value={purpose} onValueChange={setPurpose}>
              <SelectTrigger>
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(purposes ?? []).map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex cursor-pointer items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={withSalary}
              onChange={(e) => setWithSalary(e.target.checked)}
              className="h-4 w-4"
            />
            O'rtacha oylik yozilsin
          </label>
          <Button onClick={ber} disabled={issue.isPending}>
            Berish
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Arxiv</CardTitle>
          <Select
            value={filterUser}
            onValueChange={(v) => setFilterUser(v === "all" ? "" : v)}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Barcha xodimlar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Barcha xodimlar</SelectItem>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hali ma'lumotnoma berilmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((c) => (
                <li key={c.id} className="flex items-center gap-3 py-2 text-sm">
                  <span className="w-24 shrink-0 font-mono text-xs">{c.number}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {c.user_name}
                  </span>
                  <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
                    {c.purpose_label}
                  </span>
                  {c.include_salary && (
                    <span
                      className="flex shrink-0 items-center gap-1 text-xs text-amber-800"
                      title="Hujjatda o'rtacha oylik ko'rsatilgan"
                    >
                      <ShieldAlert className="h-3.5 w-3.5" />
                      oylik bilan
                    </span>
                  )}
                  <span className="shrink-0 font-mono text-xs text-slate-500">
                    {c.issued_at}
                  </span>
                  {c.request_id ? (
                    <span className="shrink-0 text-xs text-slate-500">ariza</span>
                  ) : (
                    <span className="shrink-0 text-xs text-slate-400">qo'lda</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
