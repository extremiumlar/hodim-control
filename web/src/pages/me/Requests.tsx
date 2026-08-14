/**
 * Xodim kabineti — «Arizalarim».
 *
 * Botdagi ko'p bosqichli FSM o'rniga bitta forma: tur tanlanadi, unga qarab
 * maydonlar o'zgaradi. Ta'til turlarida sanalar to'liq bo'lishi bilan
 * KALKULYATOR javobi ko'rinadi («7 kundan 5 tasi ish kuni») — xodim
 * yuborishdan oldin nima so'rayotganini aniq biladi.
 */
import { useMemo, useState } from "react";
import { CalendarRange, FileText, Send, Undo2 } from "lucide-react";
import { toast } from "sonner";

import ConfirmDialog from "@/components/ConfirmDialog";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCancelMyRequest,
  useCreateMyRequest,
  useMyLeaveBalance,
  useMyRequests,
  useRequestCalc,
} from "@/lib/queries";
import type { EmployeeRequest, RequestKind } from "@/lib/api";
import { cn } from "@/lib/utils";

const MIN_REASON = 10;
const MAX_REASON = 2000;

const KINDS: { value: RequestKind; label: string; hint: string }[] = [
  { value: "vacation", label: "🏖 Mehnat ta'tili", hint: "To'lovli yillik ta'til" },
  { value: "unpaid", label: "🚫 O'z hisobidan", hint: "Haq to'lanmaydi" },
  { value: "sick", label: "🤒 Kasallik", hint: "Kasallik kunlari" },
  { value: "advance", label: "💵 Avans", hint: "Oylikdan oldin" },
  { value: "certificate", label: "📄 Ma'lumotnoma", hint: "Ish joyidan hujjat" },
  { value: "schedule_change", label: "🗓 Jadval", hint: "Ish vaqtini o'zgartirish" },
  { value: "resignation", label: "🚪 Ishdan bo'shash", hint: "" },
  { value: "other", label: "📝 Boshqa", hint: "" },
];

const KIND_LABELS: Record<RequestKind, string> = Object.fromEntries(
  KINDS.map((k) => [k.value, k.label])
) as Record<RequestKind, string>;

const LEAVE_KINDS: RequestKind[] = ["vacation", "unpaid", "sick"];

/** Mahalliy sana — `toISOString()` UTC'ga o'tkazadi va +5 da kunni surardi. */
function isoToday(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "—"
    : `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function fmtMoney(v: number): string {
  return `${Math.round(v).toLocaleString("ru-RU").replace(/ /g, " ")} so'm`;
}

export default function MeRequests() {
  const { data, isLoading } = useMyRequests();
  const create = useCreateMyRequest();
  const cancel = useCancelMyRequest();

  const [kind, setKind] = useState<RequestKind>("vacation");
  const [startDate, setStartDate] = useState(isoToday(1));
  const [endDate, setEndDate] = useState(isoToday(7));
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  const isLeave = LEAVE_KINDS.includes(kind);
  const isMoney = kind === "advance";

  // Kalkulyator faqat ta'til turlarida va sanalar to'g'ri bo'lganda.
  const calcEnabled = isLeave && !!startDate && !!endDate && endDate >= startDate;
  const calc = useRequestCalc(startDate, endDate, calcEnabled);
  const balance = useMyLeaveBalance();

  const canSubmit = useMemo(() => {
    if (reason.trim().length < MIN_REASON || create.isPending) return false;
    if (isLeave) return !!startDate && !!endDate && endDate >= startDate;
    if (isMoney) return Number(amount) > 0;
    return true;
  }, [reason, create.isPending, isLeave, isMoney, startDate, endDate, amount]);

  function submit() {
    if (!canSubmit) return;
    create.mutate(
      {
        kind,
        start_date: isLeave ? startDate : null,
        end_date: isLeave ? endDate : null,
        amount: isMoney ? Number(amount) : null,
        reason: reason.trim(),
      },
      {
        onSuccess: () => {
          setReason("");
          setAmount("");
          toast.success("Arizangiz yuborildi — javobini kutib turing.");
        },
      }
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <div className="mb-1.5 text-xs font-medium text-slate-500">Ariza turi</div>
          <div className="grid grid-cols-2 gap-2">
            {KINDS.map((k) => (
              <button
                key={k.value}
                type="button"
                onClick={() => setKind(k.value)}
                className={cn(
                  "min-h-[44px] rounded-lg border px-2 py-1.5 text-left text-sm font-medium",
                  kind === k.value
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-slate-200 text-slate-600"
                )}
              >
                <div>{k.label}</div>
                {k.hint && <div className="text-[11px] font-normal text-slate-400">{k.hint}</div>}
              </button>
            ))}
          </div>
        </div>

        {isLeave && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Boshlanishi</label>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="h-11"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Tugashi</label>
                <Input
                  type="date"
                  value={endDate}
                  min={startDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="h-11"
                />
              </div>
            </div>

            {/* Kalkulyator — nizoning oldini oladi: xodim 10 kun so'radim deb
                o'ylab, aslida 8 ish kuni olayotganini yuborishdan OLDIN
                ko'radi. */}
            {calcEnabled && calc.data && (
              <div
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm",
                  calc.data.working_days === 0
                    ? "border-rose-200 bg-rose-50 text-rose-800"
                    : "border-sky-200 bg-sky-50 text-sky-900",
                  calc.isPlaceholderData && "opacity-60"
                )}
              >
                <div className="flex items-start gap-2">
                  <CalendarRange className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <div>{calc.data.summary}</div>
                    {calc.data.conflict_dates.length > 0 && (
                      <div className="mt-1 text-xs text-amber-700">
                        ⚠ Bu kunlarda allaqachon sababli kun bor:{" "}
                        {calc.data.conflict_dates.slice(0, 5).join(", ")}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Ta'til balansi — faqat mehnat ta'tilida va faqat MASLAHAT
                sifatida: `hire_date` taxminiy bo'lishi mumkin, shuning
                uchun ariza yuborish BLOKLANMAYDI. */}
            {kind === "vacation" && balance.data && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                <span className="font-medium">{balance.data.year}-yil ta'til balansi:</span>{" "}
                {balance.data.used_days} / {balance.data.entitled_days} kun ishlatilgan —{" "}
                <b className={cn(balance.data.remaining_days === 0 && "text-rose-700")}>
                  {balance.data.remaining_days} kun qoldi
                </b>
                {balance.data.estimated && (
                  <div className="mt-0.5 text-xs text-slate-500">
                    Ishga kirgan sana kiritilmagan — raqam taxminiy. HR aniqlashtiradi.
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {isMoney && (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Summa (so'm)</label>
            <Input
              type="number"
              min={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="500000"
              className="h-11"
            />
          </div>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Sabab (kamida {MIN_REASON} belgi)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            maxLength={MAX_REASON}
            placeholder="Nima uchun kerakligini qisqacha yozing"
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>

        <Button onClick={submit} disabled={!canSubmit} className="h-11 w-full text-sm font-semibold">
          <Send className="mr-1.5 h-4 w-4" />
          {create.isPending ? "Yuborilmoqda..." : "Yuborish"}
        </Button>

        <p className="text-xs text-slate-400">
          Javob kelganda shu yerda va Telegram botda ko'rinadi.
        </p>
      </div>

      <div>
        <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Arizalarim
        </div>

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        ) : !data?.length ? (
          <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
            <FileText className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            Hozircha ariza yubormagansiz.
          </p>
        ) : (
          <div className="space-y-2">
            {data.map((item) => (
              <RequestCard key={item.id} item={item} onCancel={cancel} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RequestCard({
  item,
  onCancel,
}: {
  item: EmployeeRequest;
  onCancel: ReturnType<typeof useCancelMyRequest>;
}) {
  const canCancel = item.status === "pending" || item.status === "manager_ok";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{KIND_LABELS[item.kind]}</span>
        <StatusBadge kind="employee_request" status={item.status} />
      </div>
      <div className="mt-0.5 text-xs tabular-nums text-slate-400">
        {fmtDayMonth(item.created_at)}
        {item.start_date && ` · ${item.start_date} — ${item.end_date}`}
        {item.amount != null && ` · ${fmtMoney(item.amount)}`}
      </div>
      <p className="mt-1.5 whitespace-pre-line break-words text-sm text-slate-600">{item.reason}</p>
      {item.decision_note && (
        <div className="mt-2 rounded-lg bg-slate-50 p-2.5 text-sm">
          <div className="mb-0.5 text-xs font-semibold text-slate-500">Javob</div>
          <p className="whitespace-pre-line break-words text-slate-700">{item.decision_note}</p>
        </div>
      )}
      {canCancel && (
        <div className="mt-2">
          <ConfirmDialog
            title="Arizani qaytarib olish"
            description="Ariza bekor qilinadi va rahbarga bormaydi."
            confirmLabel="Qaytarib olish"
            loading={onCancel.isPending}
            onConfirm={() =>
              onCancel.mutate(item.id, {
                onSuccess: () => toast.success("Ariza qaytarib olindi"),
              })
            }
            trigger={
              <button
                type="button"
                className="flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-rose-600"
              >
                <Undo2 className="h-3 w-3" />
                Qaytarib olish
              </button>
            }
          />
        </div>
      )}
    </div>
  );
}
