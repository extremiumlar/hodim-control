/**
 * «Shtat jadvali» — rahbar paneli (TZ 3.20 / S-23).
 *
 * ⚠️ «BAND» soni HISOBLANADI, kiritilmaydi. Faol xodimlar bo'yicha.
 * Qo'lda kiritilsa u darhol eskirardi: xodim ishdan bo'shaydi, jadvalni
 * yangilash unutiladi va tizim «hammasi band» deb yolg'on ko'rsatardi.
 *
 * ⚠️ ROP faqat O'Z qamrovidagi lavozimlarni ko'radi — filtr SERVERDA.
 */
import { useState } from "react";
import { Briefcase, UserSearch } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAddStaff, useCloseStaff, usePositions, useStaff, useStaffSummary } from "@/lib/queries";
import { useAuth } from "@/lib/auth";

function pul(n: number | null): string {
  return n === null ? "—" : n.toLocaleString("ru-RU").replace(/ /g, " ");
}

const HOLATLAR = [
  { value: "open", label: "Amalda" },
  { value: "frozen", label: "Muzlatilgan" },
  { value: "closed", label: "Yopilgan" },
];

export default function Staff() {
  const { user } = useAuth();
  const { data, isLoading } = useStaff();
  const { data: sum } = useStaffSummary();
  const { data: positions } = usePositions();
  const add = useAddStaff();
  const close = useCloseStaff();

  const [dept, setDept] = useState("");
  const [posId, setPosId] = useState("");
  const [units, setUnits] = useState("1");
  const [smin, setSmin] = useState("");
  const [smax, setSmax] = useState("");

  //  ROP tahrirlay olmaydi — shtat jadvali byudjet hujjati.
  const canEdit = user ? ["hr", "boss", "dasturchi"].includes(user.role) : false;

  async function qosh() {
    if (!dept.trim() || !posId) {
      toast.error("Bo'lim va lavozimni tanlang");
      return;
    }
    await add.mutateAsync({
      department: dept.trim(),
      position_id: Number(posId),
      units: Math.max(1, Number(units) || 1),
      salary_min: smin ? Number(smin.replace(/\s/g, "")) : null,
      salary_max: smax ? Number(smax.replace(/\s/g, "")) : null,
    });
    toast.success("Shtat birligi qo'shildi");
    setSmin("");
    setSmax("");
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Shtat jadvali" />

      {sum && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border bg-white p-3">
            <div className="text-xs text-slate-600">Jami shtat</div>
            <div className="text-2xl font-semibold">{sum.total}</div>
          </div>
          <div className="rounded-lg border bg-white p-3">
            <div className="text-xs text-slate-600">Band</div>
            <div className="text-2xl font-semibold text-slate-700">{sum.occupied}</div>
          </div>
          <div
            className={`rounded-lg border p-3 ${
              sum.vacant > 0 ? "border-amber-200 bg-amber-50" : "bg-white"
            }`}
          >
            <div className="text-xs text-slate-600">Bo'sh</div>
            <div className="text-2xl font-semibold text-amber-800">{sum.vacant}</div>
          </div>
        </div>
      )}

      {sum && sum.vacancies.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <UserSearch className="h-4 w-4" />
              Bo'sh o'rinlar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {sum.vacancies.map((v) => (
                <li key={v.staff_id} className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                    {v.vacant} ta
                  </span>
                  <span className="font-medium">{v.position_name}</span>
                  <span className="text-xs text-slate-600">{v.department}</span>
                  {v.salary_min !== null && (
                    <span className="text-xs text-slate-500">
                      {pul(v.salary_min)}
                      {v.salary_max !== null ? ` – ${pul(v.salary_max)}` : ""} so'm
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {canEdit && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Briefcase className="h-4 w-4" />
              Yangi shtat birligi
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-2">
            <div className="min-w-[160px] flex-1">
              <div className="mb-1 text-xs text-slate-600">Bo'lim</div>
              <Input value={dept} onChange={(e) => setDept(e.target.value)} placeholder="Sotuv" />
            </div>
            <div className="min-w-[170px]">
              <div className="mb-1 text-xs text-slate-600">Lavozim</div>
              <Select value={posId} onValueChange={setPosId}>
                <SelectTrigger>
                  <SelectValue placeholder="Tanlang" />
                </SelectTrigger>
                <SelectContent>
                  {(positions ?? []).map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-24">
              <div className="mb-1 text-xs text-slate-600">Birlik</div>
              <Input
                value={units}
                inputMode="numeric"
                onChange={(e) => setUnits(e.target.value)}
              />
            </div>
            <div className="w-32">
              <div className="mb-1 text-xs text-slate-600">Oylik (dan)</div>
              <Input value={smin} inputMode="numeric" onChange={(e) => setSmin(e.target.value)} />
            </div>
            <div className="w-32">
              <div className="mb-1 text-xs text-slate-600">Oylik (gacha)</div>
              <Input value={smax} inputMode="numeric" onChange={(e) => setSmax(e.target.value)} />
            </div>
            <Button onClick={qosh} disabled={add.isPending}>
              Qo'shish
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Barcha birliklar</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Shtat jadvali hali to'ldirilmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((sp) => (
                <li key={sp.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                  <span className="w-28 shrink-0 truncate text-xs text-slate-600">
                    {sp.department}
                  </span>
                  <span className="min-w-[120px] flex-1 truncate font-medium">
                    {sp.position_name}
                  </span>
                  <span className="shrink-0 text-xs">
                    <b>{sp.occupied}</b>/{sp.units}
                    {sp.vacant > 0 && (
                      <span className="ml-1 rounded bg-amber-100 px-1 text-amber-900">
                        {sp.vacant} bo'sh
                      </span>
                    )}
                  </span>
                  {sp.salary_min !== null && (
                    <span className="shrink-0 text-xs text-slate-500">
                      {pul(sp.salary_min)}
                      {sp.salary_max !== null ? ` – ${pul(sp.salary_max)}` : ""}
                    </span>
                  )}
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${
                      sp.status === "open"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {sp.status_label}
                  </span>
                  {canEdit && sp.status !== "closed" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      disabled={close.isPending}
                      onClick={async () => {
                        await close.mutateAsync(sp.id);
                        toast.success("Yopildi (tarixda qoladi)");
                      }}
                    >
                      Yopish
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-slate-500">
            «Band» soni faol xodimlardan <b>avtomatik hisoblanadi</b> — qo'lda
            kiritilmaydi.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
