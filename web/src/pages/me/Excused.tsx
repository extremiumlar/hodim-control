/**
 * Xodim kabineti — «Sababli kun so'rash».
 *
 * Botda bu ko'p bosqichli FSM oqimi: tugma → sana so'raladi → sabab
 * so'raladi → yuboriladi (bot/handlers/excused.py). Web'da bitta forma —
 * sana va sabab birga ko'rinadi, xodim nima yuborayotganini yuborishdan
 * OLDIN ko'radi va tuzata oladi.
 *
 * Backend bir xil: `POST /excused-days/me` (JWT) va bot yo'li ikkalasi ham
 * `_request_excused_day_for_user` ga boradi — dublikat nazorati va HR'ga
 * xabar bir joyda.
 *
 * Sxema ataylab boshqa (`ExcusedDayMeCreate`): tanada `telegram_id` YO'Q,
 * shaxs tokendan olinadi.
 */
import { useState } from "react";
import { CalendarPlus, Clock } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyExcusedDays, useRequestMyExcusedDay } from "@/lib/queries";
import type { ExcusedDay } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS: Record<ExcusedDay["status"], { text: string; cls: string }> = {
  pending: { text: "🕓 Ko'rib chiqilmoqda", cls: "text-slate-500" },
  approved: { text: "✅ Tasdiqlangan", cls: "text-emerald-600" },
  rejected: { text: "❌ Rad etilgan", cls: "text-rose-600" },
};

/** Mahalliy sana ISO ko'rinishida. `toISOString()` UTC'ga o'tkazadi va
 *  Toshkentda (+5) ertalab 05:00 gacha bir kun orqaga surardi. */
function isoToday(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

export default function Excused() {
  const { data, isLoading } = useMyExcusedDays();
  const request = useRequestMyExcusedDay();

  const [day, setDay] = useState(isoToday());
  const [reason, setReason] = useState("");

  const canSubmit = reason.trim().length > 0 && !request.isPending;

  function submit() {
    if (!canSubmit) return;
    request.mutate(
      { reason: reason.trim(), date: day },
      {
        onSuccess: () => {
          setReason("");
          // Botdagi bilan bir xil xabar (bot/handlers/excused.py)
          toast.success("So'rovingiz HR'ga yuborildi, javobini kutib turing.");
        },
        // Xato (masalan shu kunga allaqachon so'rov bor) useApiMutation'da
        // toast.error bilan ko'rsatiladi — backend matni o'zgarmaydi.
      }
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">Qaysi sana uchun</label>
          <Input
            type="date"
            value={day}
            min={isoToday(-7)}
            onChange={(e) => setDay(e.target.value)}
            className="h-11"
          />
          {/* Botda "bugun / ertaga" tugmalari bor — shu yerda ham tez tanlash */}
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => setDay(isoToday())}
              className={cn(
                "min-h-[36px] rounded-lg border px-3 text-xs font-medium",
                day === isoToday() ? "border-primary text-primary" : "border-slate-200 text-slate-500"
              )}
            >
              Bugun
            </button>
            <button
              type="button"
              onClick={() => setDay(isoToday(1))}
              className={cn(
                "min-h-[36px] rounded-lg border px-3 text-xs font-medium",
                day === isoToday(1) ? "border-primary text-primary" : "border-slate-200 text-slate-500"
              )}
            >
              Ertaga
            </button>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">Sabab</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Masalan: kasallik, oilaviy holat"
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>

        <Button onClick={submit} disabled={!canSubmit} className="h-11 w-full text-sm font-semibold">
          <CalendarPlus className="mr-1.5 h-4 w-4" />
          {request.isPending ? "Yuborilmoqda..." : "So'rov yuborish"}
        </Button>

        <p className="text-xs text-slate-400">
          So'rov HR'ga boradi. Javob kelganda shu yerda va Telegram botda ko'rinadi.
        </p>
      </div>

      <div>
        <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          So'rovlarim
        </div>

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full rounded-xl" />
            <Skeleton className="h-16 w-full rounded-xl" />
          </div>
        ) : !data?.length ? (
          <p className="rounded-xl border border-slate-200 bg-white p-4 text-center text-sm text-slate-500">
            Hozircha so'rov yubormagansiz.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            {data.map((item, i) => (
              <div key={item.id} className={cn("px-4 py-3", i > 0 && "border-t border-slate-100")}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="flex items-center gap-1.5 text-sm font-medium tabular-nums">
                    <Clock className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                    {fmtDayMonth(item.date)}
                  </span>
                  <span className={cn("shrink-0 text-xs font-medium", STATUS[item.status].cls)}>
                    {STATUS[item.status].text}
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-line text-xs text-slate-500">{item.reason}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
