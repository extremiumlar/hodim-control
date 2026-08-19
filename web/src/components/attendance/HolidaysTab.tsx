/**
 * Bayramlar jadvali — HR yillik ro'yxatni kiritadigan joy (TZ 2.9 / S-09).
 *
 * NEGA MUHIM: bu ro'yxat butun tizimda ish kuni hisobiga ta'sir qiladi —
 * oylik, normalar, davomat statistikasi, kunlik digest. Kiritilmasa bayram
 * oddiy ish kuni bo'lib qoladi va butun jamoa «kelmagan» sanaladi.
 *
 * Ikki kiritish yo'li bor va ikkalasi ham kerak:
 *   • bitta kun — yil o'rtasida e'lon qilingan qo'shimcha dam olish kuni;
 *   • ro'yxat — yil boshida 15-20 kunni bir marta yopishtirib yuborish
 *     (har birini alohida kiritish HR ni charchatadi va shuning uchun
 *     ro'yxat umuman kiritilmay qoladi).
 */
import { useMemo, useState } from "react";
import { CalendarDays, Trash2 } from "lucide-react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import {
  useAddHoliday,
  useAddHolidaysBulk,
  useDeleteHoliday,
  useHolidays,
} from "@/lib/queries";

const KUN_NOMI = ["Yak", "Du", "Se", "Chor", "Pay", "Ju", "Sha"];

function kunBelgisi(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return Number.isNaN(d.getTime()) ? "" : KUN_NOMI[d.getDay()];
}

/** «2026-01-01 Yangi yil» ko'rinishidagi qatorlarni ajratadi.
 *  Ajratgich sifatida bo'sh joy, tab, vergul va nuqta-vergul qabul
 *  qilinadi — HR ro'yxatni Word yoki Excel dan nusxalaydi. */
function qatorlarniOqi(matn: string): { date: string; name: string }[] {
  const out: { date: string; name: string }[] = [];
  for (const raw of matn.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(\d{4}-\d{2}-\d{2})[\s,;\t-]*(.*)$/);
    if (!m) continue;
    out.push({ date: m[1], name: (m[2] || "Bayram").trim() || "Bayram" });
  }
  return out;
}

export default function HolidaysTab() {
  const hozirgiYil = new Date().getFullYear();
  const [yil, setYil] = useState<number>(hozirgiYil);
  const { data: holidays, isLoading } = useHolidays(yil);
  const addOne = useAddHoliday();
  const addBulk = useAddHolidaysBulk();
  const del = useDeleteHoliday();

  const [sana, setSana] = useState("");
  const [nomi, setNomi] = useState("");
  const [turi, setTuri] = useState("state");
  const [royxat, setRoyxat] = useState("");

  const yillar = useMemo(
    () => [hozirgiYil - 1, hozirgiYil, hozirgiYil + 1],
    [hozirgiYil]
  );
  const tahlil = useMemo(() => qatorlarniOqi(royxat), [royxat]);

  async function bittaQosh() {
    if (!sana || !nomi.trim()) {
      toast.error("Sana va nomini kiriting");
      return;
    }
    await addOne.mutateAsync({ date: sana, name: nomi.trim(), kind: turi });
    toast.success(`${sana} — «${nomi.trim()}» qo'shildi`);
    setSana("");
    setNomi("");
  }

  async function royxatniQosh() {
    if (!tahlil.length) {
      toast.error("Bironta ham to'g'ri qator topilmadi (YYYY-MM-DD Nomi)");
      return;
    }
    const r = await addBulk.mutateAsync({
      items: tahlil.map((i) => ({ ...i, kind: turi })),
      overwrite: false,
    });
    toast.success(
      `${r.added} ta qo'shildi` +
        (r.skipped ? `, ${r.skipped} tasi allaqachon bor edi` : "")
    );
    setRoyxat("");
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
        Bu ro'yxat <b>butun tizimga</b> ta'sir qiladi: bayram kuni oylik,
        normalar va davomat hisobida ish kuni sifatida sanalmaydi. Xodimga
        atayin qo'yilgan kunlik jadval (override) bayramdan kuchliroq — bayram
        navbatchiligi shu tarzda belgilanadi.
        <div className="mt-1">
          ⚠️ Yangi bayram <b>o'tgan davrlarni qayta hisoblamaydi</b> — faqat
          joriy va kelajak oylarga qo'llanadi.
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Bitta kun qo'shish</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <div>
            <div className="mb-1 text-xs text-slate-600">Sana</div>
            <Input
              type="date"
              value={sana}
              onChange={(e) => setSana(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="min-w-[180px] flex-1">
            <div className="mb-1 text-xs text-slate-600">Nomi</div>
            <Input
              value={nomi}
              placeholder="Masalan: Mustaqillik kuni"
              onChange={(e) => setNomi(e.target.value)}
            />
          </div>
          <div>
            <div className="mb-1 text-xs text-slate-600">Turi</div>
            <Select value={turi} onValueChange={setTuri}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="state">Davlat bayrami</SelectItem>
                <SelectItem value="company">Kompaniya qarori</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={bittaQosh} disabled={addOne.isPending}>
            Qo'shish
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yillik ro'yxatni bir marta kiritish</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-slate-600">
            Har qator: <code>YYYY-MM-DD Nomi</code>. Allaqachon kiritilgan
            sanalar o'tkazib yuboriladi — ro'yxatni bo'lak-bo'lak yuborsa ham
            bo'ladi.
          </p>
          <Textarea
            rows={6}
            value={royxat}
            placeholder={"2027-01-01 Yangi yil\n2027-03-08 Xotin-qizlar kuni\n2027-03-21 Navro'z"}
            onChange={(e) => setRoyxat(e.target.value)}
            className="font-mono text-xs"
          />
          <div className="flex items-center gap-3">
            <Button
              onClick={royxatniQosh}
              disabled={addBulk.isPending || !tahlil.length}
            >
              {tahlil.length ? `${tahlil.length} kunni qo'shish` : "Qo'shish"}
            </Button>
            {royxat.trim() && !tahlil.length && (
              <span className="text-xs text-rose-600">
                To'g'ri qator topilmadi — sana YYYY-MM-DD ko'rinishida bo'lsin
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Kiritilgan bayramlar</CardTitle>
          <Select value={String(yil)} onValueChange={(v) => setYil(Number(v))}>
            <SelectTrigger className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {yillar.map((y) => (
                <SelectItem key={y} value={String(y)}>
                  {y}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !holidays?.length ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
              <CalendarDays className="h-4 w-4 shrink-0" />
              {yil}-yilga bironta bayram kiritilmagan — bu kunlar oddiy ish
              kuni sifatida sanaladi.
            </div>
          ) : (
            <ul className="divide-y">
              {holidays.map((h) => (
                <li key={h.id} className="flex items-center gap-3 py-2 text-sm">
                  <span className="w-28 shrink-0 font-mono text-xs text-slate-600">
                    {h.date}
                  </span>
                  <span className="w-10 shrink-0 text-xs text-slate-500">
                    {kunBelgisi(h.date)}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{h.name}</span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${
                      h.kind === "company"
                        ? "bg-sky-100 text-sky-800"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {h.kind === "company" ? "Kompaniya" : "Davlat"}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    disabled={del.isPending}
                    onClick={async () => {
                      await del.mutateAsync(h.id);
                      toast.success(`${h.date} ro'yxatdan olib tashlandi`);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
