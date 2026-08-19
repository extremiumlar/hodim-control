/**
 * Xodim kabineti — «E'tiroz va shikoyat».
 *
 * Botda bu ko'p bosqichli FSM oqimi (bot/handlers/appeal.py); web'da bitta
 * forma — xodim nima yuborayotganini yuborishdan OLDIN to'liq ko'radi va
 * tuzata oladi (me/Excused.tsx bilan bir falsafа).
 *
 * Farqi botdan: bu yerda davomat e'tirozining sanasi tugma ro'yxatidan emas,
 * sana maydonidan tanlanadi. Backend baribir tekshiradi — e'tiroz manzilsiz
 * (ref_date/ref_period siz) qabul qilinmaydi.
 */
import { useState } from "react";
import { Scale, Send } from "lucide-react";
import { toast } from "sonner";

import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateMyAppeal, useMyAppeals } from "@/lib/queries";
import type { Appeal } from "@/lib/api";
import { cn } from "@/lib/utils";

const MIN_TEXT = 10;
const MAX_TEXT = 3000;

const KIND_LABELS: Record<Appeal["kind"], string> = {
  objection: "E'tiroz",
  complaint: "Shikoyat",
};
const TOPIC_LABELS: Record<Appeal["topic"], string> = {
  attendance: "Davomat",
  payroll: "Oylik",
  work_env: "Ish sharoiti",
  team: "Jamoa",
  other: "Boshqa",
};

const OBJECTION_TOPICS = [
  { value: "attendance", label: "🕐 Davomat (kechikish/kelmagan kun)" },
  { value: "payroll", label: "💵 Oylik hisobi" },
] as const;

const COMPLAINT_TOPICS = [
  { value: "work_env", label: "🏢 Ish sharoiti" },
  { value: "team", label: "👥 Jamoa" },
  { value: "other", label: "📝 Boshqa" },
] as const;

/** Mahalliy sana ISO — `toISOString()` UTC'ga o'tkazadi va +5 da kunni
 *  bir kun orqaga surardi (me/Excused.tsx dagi bir xil tuzoq). */
function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "—"
    : `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-h-[40px] rounded-lg border px-3 text-sm font-medium",
        active ? "border-primary bg-primary/5 text-primary" : "border-slate-200 text-slate-600"
      )}
    >
      {children}
    </button>
  );
}

export default function MeAppeals() {
  const { data, isLoading } = useMyAppeals();
  const create = useCreateMyAppeal();

  const [kind, setKind] = useState<Appeal["kind"]>("objection");
  const [topic, setTopic] = useState<string>("attendance");
  const [refDate, setRefDate] = useState(isoToday());
  const [refPeriod, setRefPeriod] = useState(currentPeriod());
  const [recipient, setRecipient] = useState<"hr" | "boss">("hr");
  const [anonymous, setAnonymous] = useState(false);
  const [text, setText] = useState("");

  const topics = kind === "objection" ? OBJECTION_TOPICS : COMPLAINT_TOPICS;
  const canSubmit = text.trim().length >= MIN_TEXT && !create.isPending;

  function switchKind(next: Appeal["kind"]) {
    setKind(next);
    // Mavzu turga bog'liq — turni almashtirganda eskisi mos kelmay qoladi
    // (backend ham buni rad etadi, lekin foydalanuvchi 422 ko'rmasligi kerak).
    setTopic(next === "objection" ? "attendance" : "work_env");
    if (next === "objection") setAnonymous(false); // e'tiroz anonim bo'lolmaydi
  }

  function submit() {
    if (!canSubmit) return;
    create.mutate(
      {
        kind,
        topic,
        text: text.trim(),
        is_anonymous: kind === "complaint" && anonymous,
        recipient_role: kind === "objection" ? "hr" : recipient,
        ref_date: kind === "objection" && topic === "attendance" ? refDate : null,
        ref_period: kind === "objection" && topic === "payroll" ? refPeriod : null,
      },
      {
        onSuccess: () => {
          setText("");
          setAnonymous(false);
          toast.success("Murojaatingiz yuborildi — javobini kutib turing.");
        },
      }
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div>
          <div className="mb-1.5 text-xs font-medium text-slate-500">Murojaat turi</div>
          <div className="flex gap-2">
            <Chip active={kind === "objection"} onClick={() => switchKind("objection")}>
              ⚖️ E'tiroz
            </Chip>
            <Chip active={kind === "complaint"} onClick={() => switchKind("complaint")}>
              📨 Shikoyat
            </Chip>
          </div>
          <p className="mt-1.5 text-xs text-slate-400">
            {kind === "objection"
              ? "Aniq qarorga qarshi: kechikish ushlanmasi, kelmagan kun yoki oylik hisobi."
              : "Erkin mavzu: ish sharoiti, jamoa va boshqalar."}
          </p>
        </div>

        <div>
          <div className="mb-1.5 text-xs font-medium text-slate-500">Mavzu</div>
          <div className="flex flex-wrap gap-2">
            {topics.map((t) => (
              <Chip key={t.value} active={topic === t.value} onClick={() => setTopic(t.value)}>
                {t.label}
              </Chip>
            ))}
          </div>
        </div>

        {kind === "objection" && topic === "attendance" && (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Qaysi kun</label>
            <Input
              type="date"
              value={refDate}
              max={isoToday()}
              onChange={(e) => setRefDate(e.target.value)}
              className="h-11"
            />
          </div>
        )}

        {kind === "objection" && topic === "payroll" && (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Qaysi oy</label>
            <Input
              type="month"
              value={refPeriod}
              max={currentPeriod()}
              onChange={(e) => setRefPeriod(e.target.value)}
              className="h-11"
            />
          </div>
        )}

        {kind === "complaint" && (
          <>
            <div>
              <div className="mb-1.5 text-xs font-medium text-slate-500">Kimga borsin</div>
              <div className="flex gap-2">
                <Chip active={recipient === "hr"} onClick={() => setRecipient("hr")}>
                  👤 HR ga
                </Chip>
                <Chip active={recipient === "boss"} onClick={() => setRecipient("boss")}>
                  👔 Boshliqqa
                </Chip>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={anonymous}
                onChange={(e) => setAnonymous(e.target.checked)}
                className="h-4 w-4"
              />
              Anonim yuborish (qabul qiluvchi ismingizni ko'rmaydi)
            </label>
          </>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Murojaat matni (kamida {MIN_TEXT} belgi)
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            maxLength={MAX_TEXT}
            placeholder={
              kind === "objection"
                ? "Nima uchun bu qaror noto'g'ri deb hisoblaysiz?"
                : "Muammoni batafsil yozing"
            }
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>

        <Button onClick={submit} disabled={!canSubmit} className="h-11 w-full text-sm font-semibold">
          <Send className="mr-1.5 h-4 w-4" />
          {create.isPending ? "Yuborilmoqda..." : "Yuborish"}
        </Button>

        <p className="text-xs text-slate-400">
          Javob kelganda shu yerda va Telegram botda ko'rinadi. Rasm yoki hujjat biriktirish
          hozircha faqat botda.
        </p>
      </div>

      <div>
        <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Murojaatlarim
        </div>

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        ) : !data?.length ? (
          <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
            <Scale className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            Hozircha murojaat yubormagansiz.
          </p>
        ) : (
          <div className="space-y-2">
            {data.map((item) => (
              <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium">
                    {KIND_LABELS[item.kind]}
                    <span className="ml-1 text-slate-400">· {TOPIC_LABELS[item.topic]}</span>
                    {item.is_anonymous && (
                      <span className="ml-1.5 text-xs text-slate-400">(anonim)</span>
                    )}
                  </span>
                  <StatusBadge kind="appeal" status={item.status} />
                </div>
                <div className="mt-0.5 text-xs text-slate-400 tabular-nums">
                  {fmtDayMonth(item.created_at)}
                  {item.ref_date && ` · ${item.ref_date}`}
                  {item.ref_period && ` · ${item.ref_period}`}
                </div>
                <p className="mt-1.5 whitespace-pre-line break-words text-sm text-slate-600">
                  {item.text}
                </p>
                {item.decision_note && (
                  <div className="mt-2 rounded-lg bg-slate-50 p-2.5 text-sm">
                    <div className="mb-0.5 text-xs font-semibold text-slate-500">Javob</div>
                    <p className="whitespace-pre-line break-words text-slate-700">
                      {item.decision_note}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
