/**
 * «Ish takliflari» — HR paneli (TZ 3.3 / S-15).
 *
 * ⚠️ TIZIM NOMZODGA HECH NARSA YUBORMAYDI. Hujjat tayyorlanib HR ning
 * Telegram'iga boradi; nomzodga uni HR o'zi jo'natadi. Nomzod hali xodim
 * emas va uning aloqasi tizimda bo'lmasligi kerak.
 *
 * Hujjat SO'ROV ICHIDA tayyorlanmaydi (Passenger konkurentligi = 1) —
 * navbatga qo'yiladi va tayyor bo'lgach Telegram orqali keladi.
 */
import { useState } from "react";
import { FileDown, Search, UserPlus } from "lucide-react";
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
import {
  useAddOffer,
  useDocumentTemplates,
  useGenerateOfferDoc,
  useOffers,
  usePositions,
  useSetOfferStatus,
  useUsers,
} from "@/lib/queries";

const HOLATLAR = [
  { value: "draft", label: "Qoralama" },
  { value: "sent", label: "Yuborilgan" },
  { value: "accepted", label: "Qabul qilingan" },
  { value: "declined", label: "Rad etilgan" },
  { value: "cancelled", label: "Bekor qilingan" },
];

const HOLAT_RANGI: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  sent: "bg-sky-100 text-sky-800",
  accepted: "bg-emerald-100 text-emerald-800",
  declined: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-100 text-slate-500",
};

function pul(n: number): string {
  return n.toLocaleString("ru-RU").replace(/ /g, " ");
}

export default function Offers() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useOffers(q);
  const { data: positions } = usePositions();
  const { data: users } = useUsers();
  const { data: templates } = useDocumentTemplates();
  const add = useAddOffer();
  const setStatus = useSetOfferStatus();
  const generate = useGenerateOfferDoc();

  const [fish, setFish] = useState("");
  const [tel, setTel] = useState("");
  const [posId, setPosId] = useState("");
  const [salary, setSalary] = useState("");
  const [probation, setProbation] = useState("");
  const [start, setStart] = useState("");
  const [managerId, setManagerId] = useState("");
  const [tmplId, setTmplId] = useState("");

  const offerTemplates = (templates ?? []).filter((t) => t.kind === "offer");

  async function qosh() {
    const oylik = Number(salary.replace(/\s/g, ""));
    if (!fish.trim() || !posId || !oylik) {
      toast.error("F.I.Sh., lavozim va oylikni kiriting");
      return;
    }
    await add.mutateAsync({
      candidate_name: fish.trim(),
      phone: tel.trim() || null,
      position_id: Number(posId),
      salary: oylik,
      probation_months: probation ? Number(probation) : null,
      start_date: start || null,
      manager_id: managerId ? Number(managerId) : null,
    });
    toast.success("Taklif saqlandi");
    setFish("");
    setTel("");
    setSalary("");
    setProbation("");
    setStart("");
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Ish takliflari" />

      <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
        Tizim nomzodga <b>hech narsa yubormaydi</b>. Hujjat tayyorlanib{" "}
        <b>sizning Telegram'ingizga</b> keladi — nomzodga uni o'zingiz
        jo'natasiz.
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <UserPlus className="h-4 w-4" />
            Yangi taklif
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div className="min-w-[200px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Nomzod F.I.Sh.</div>
            <Input value={fish} onChange={(e) => setFish(e.target.value)} />
          </div>
          <div className="w-40">
            <div className="mb-1 text-xs text-slate-600">Telefon</div>
            <Input value={tel} onChange={(e) => setTel(e.target.value)} placeholder="+998..." />
          </div>
          <div className="min-w-[180px]">
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
          <div className="w-40">
            <div className="mb-1 text-xs text-slate-600">Oylik (so'm)</div>
            <Input
              value={salary}
              inputMode="numeric"
              onChange={(e) => setSalary(e.target.value)}
              placeholder="12000000"
            />
          </div>
          <div className="w-28">
            <div className="mb-1 text-xs text-slate-600">Sinov (oy)</div>
            <Input
              value={probation}
              inputMode="numeric"
              onChange={(e) => setProbation(e.target.value)}
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-slate-600">Ishga chiqish</div>
            <Input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="min-w-[170px]">
            <div className="mb-1 text-xs text-slate-600">Rahbari</div>
            <Select value={managerId} onValueChange={setManagerId}>
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
          <Button onClick={qosh} disabled={add.isPending}>
            Saqlash
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Takliflar</CardTitle>
          <div className="flex items-center gap-2">
            {offerTemplates.length > 0 && (
              <Select value={tmplId} onValueChange={setTmplId}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Hujjat shabloni" />
                </SelectTrigger>
                <SelectContent>
                  {offerTemplates.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ism yoki telefon"
                className="w-48 pl-7"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              {q ? "Hech narsa topilmadi." : "Hali taklif yo'q."}
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((o) => (
                <li key={o.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                  <span className="min-w-[160px] flex-1">
                    <span className="block truncate font-medium">{o.candidate_name}</span>
                    <span className="block text-xs text-slate-600">
                      {o.position_label}
                      {o.phone ? ` · ${o.phone}` : ""}
                      {o.manager_name ? ` · rahbar: ${o.manager_name}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 font-medium">{pul(o.salary)} so'm</span>
                  {o.start_date && (
                    <span className="shrink-0 font-mono text-xs text-slate-500">
                      {o.start_date}
                    </span>
                  )}
                  <Select
                    value={o.status}
                    onValueChange={async (v) => {
                      await setStatus.mutateAsync({ id: o.id, status: v });
                      toast.success("Holat yangilandi");
                    }}
                  >
                    <SelectTrigger
                      className={`h-7 w-40 shrink-0 text-xs ${HOLAT_RANGI[o.status] ?? ""}`}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOLATLAR.map((h) => (
                        <SelectItem key={h.value} value={h.value}>
                          {h.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    variant="outline"
                    className="shrink-0"
                    disabled={!tmplId || generate.isPending}
                    title={
                      tmplId
                        ? "Hujjat tayyorlanib Telegram'ga keladi"
                        : "Avval hujjat shablonini tanlang"
                    }
                    onClick={async () => {
                      const r = await generate.mutateAsync({
                        id: o.id,
                        template_id: Number(tmplId),
                      });
                      toast.success(
                        r.missing?.length
                          ? `Navbatga qo'yildi. To'ldirilmaydi: ${r.missing.join(", ")}`
                          : "Navbatga qo'yildi — tayyor bo'lgach Telegram'ga keladi"
                      );
                    }}
                  >
                    <FileDown className="mr-1 h-3.5 w-3.5" />
                    Hujjat
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {offerTemplates.length === 0 && (
            <p className="mt-3 text-xs text-amber-800">
              ⚠️ «Ish taklifi» turidagi hujjat shabloni yuklanmagan — hujjat
              tayyorlab bo'lmaydi.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
