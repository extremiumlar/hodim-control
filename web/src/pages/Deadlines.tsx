/**
 * «Muddatlar» — HR paneli (TZ 3.5 / S-13).
 *
 * Ro'yxat IKKI manbadan birlashadi: qo'lda kiritilgani va hisoblangani
 * (sinov muddati, hujjat muddati). Hisoblangan bandning sanasini bu
 * yerdan tahrirlab bo'lmaydi — manbasini (hujjat yoki ishga qabul
 * sanasi) tuzatish kerak, aks holda ikkita manba paydo bo'lardi.
 *
 * O'TIB KETGANLAR ro'yxatdan chiqmaydi: cron bir kun ishlamay qolsa ham
 * muddat yo'qolmasligi kerak (`api/services/deadlines.py` izohi).
 */
import { useState } from "react";
import { AlertTriangle, CalendarClock, Check, Lock } from "lucide-react";
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
  useAddDeadline,
  useCloseDeadline,
  useDeadlineKinds,
  useDeadlines,
  useUsers,
} from "@/lib/queries";

/** TZ: panel 7 va 30 kunlik ko'rinishni talab qiladi. */
const OYNALAR = [
  { days: 7, label: "7 kun" },
  { days: 30, label: "30 kun" },
  { days: 90, label: "90 kun" },
];

export default function Deadlines() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useDeadlines(days);
  const { data: kinds } = useDeadlineKinds();
  const { data: users } = useUsers();
  const add = useAddDeadline();
  const close = useCloseDeadline();

  const [userId, setUserId] = useState("");
  const [kind, setKind] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");

  // Hisoblanadigan turlarni qo'lda kiritib bo'lmaydi — backend 400
  // beradi, shuning uchun ro'yxatdan ham chiqarib tashlaymiz.
  const qollanadigan = (kinds ?? []).filter((k) => !k.computed);
  const otgan = (data ?? []).filter((d) => d.is_overdue);

  async function qosh() {
    if (!userId || !kind || !due) {
      toast.error("Xodim, tur va sanani tanlang");
      return;
    }
    await add.mutateAsync({
      user_id: Number(userId),
      kind,
      due_date: due,
      note: note.trim() || null,
    });
    toast.success("Muddat qo'shildi");
    setKind("");
    setDue("");
    setNote("");
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Muddatlar" />

      {otgan.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <b>{otgan.length} ta</b> muddat o'tib ketgan — ular yopilmaguncha
          ro'yxatda qoladi.
        </div>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Qo'lda muddat qo'shish</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-end gap-2">
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
              <div className="mb-1 text-xs text-slate-600">Tur</div>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger>
                  <SelectValue placeholder="Tanlang" />
                </SelectTrigger>
                <SelectContent>
                  {qollanadigan.map((k) => (
                    <SelectItem key={k.value} value={k.value}>
                      {k.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <div className="mb-1 text-xs text-slate-600">Sana</div>
              <Input
                type="date"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                className="w-40"
              />
            </div>
            <div className="min-w-[160px] flex-1">
              <div className="mb-1 text-xs text-slate-600">Izoh</div>
              <Input value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <Button onClick={qosh} disabled={add.isPending}>
              Qo'shish
            </Button>
          </div>
          <p className="text-xs text-slate-500">
            Sinov, shartnoma va hujjat muddatlari <b>avtomatik hisoblanadi</b> —
            ular ro'yxatda o'zi paydo bo'ladi.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="text-base">Yaqinlashayotgan muddatlar</CardTitle>
          <div className="flex gap-1">
            {OYNALAR.map((o) => (
              <Button
                key={o.days}
                size="sm"
                variant={days === o.days ? "default" : "outline"}
                onClick={() => setDays(o.days)}
              >
                {o.label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : !data?.length ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
              <CalendarClock className="h-4 w-4 shrink-0" />
              {days} kun ichida muddat yo'q.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((d) => (
                <li key={d.key} className="flex items-center gap-3 py-2 text-sm">
                  <span
                    className={`w-24 shrink-0 rounded px-1.5 py-0.5 text-center text-xs ${
                      d.is_overdue
                        ? "bg-rose-100 text-rose-800"
                        : d.days_left <= 7
                          ? "bg-amber-100 text-amber-900"
                          : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {d.is_overdue
                      ? `${Math.abs(d.days_left)} kun o'tdi`
                      : d.days_left === 0
                        ? "bugun"
                        : `${d.days_left} kun`}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{d.user_name}</span>
                    <span className="block text-xs text-slate-600">
                      {d.kind_label}
                      {d.note ? ` — ${d.note}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-xs text-slate-500">
                    {d.due_date}
                  </span>
                  {d.computed && (
                    <span
                      className="shrink-0 text-slate-400"
                      title="Sana manbasidan hisoblanadi — hujjat yoki ishga qabul sanasini tuzating"
                    >
                      <Lock className="h-3.5 w-3.5" />
                    </span>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    title="Yopish"
                    disabled={close.isPending}
                    onClick={async () => {
                      await close.mutateAsync({ key: d.key });
                      toast.success("Yopildi");
                    }}
                  >
                    <Check className="h-4 w-4 text-emerald-600" />
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
