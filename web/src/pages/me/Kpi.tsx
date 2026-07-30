/**
 * Xodim kabineti — «Oylik KPI'm».
 *
 * Botda bu bo'lim ATAYLAB qisqa: faqat "so'nggi hisoblangan davr" aytiladi
 * va "Bonus tafsiloti uchun saytga kiring (Panelim tugmasi)" deyiladi
 * (bot/handlers/menu.py: show_kpi). Lekin «Panelim» tugmasi FAQAT rahbarlarda
 * bor — xodim menyusida u yo'q, ya'ni bot xodimni mavjud bo'lmagan tugmaga
 * yo'naltirardi. Shu sahifa o'sha va'daning bajarilishi.
 *
 * Ma'lumot manbai `/bonuses/me` (JWT) — rahbar varianti
 * `GET /bonuses?user_id=N` bilan bir xil `BonusOut` shakli, faqat o'ziga
 * cheklangan. `breakdown` ichida faqat xodimning O'Z jamlari va stavkalari.
 */
import { TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyBonuses } from "@/lib/queries";
import type { Bonus } from "@/lib/api";
import { fmtMoney } from "@/lib/utils";

/** breakdown kalitlarini o'zbekcha nomga moslash (api/services/bonus.py). */
const TOTAL_LABELS: Record<string, string> = {
  total_conversations: "Suhbatlar",
  total_visits: "Tashriflar",
  total_oddiy_video: "Oddiy videolar",
  total_dumaloq_video: "Dumaloq videolar",
};
const RATE_KEY: Record<string, string> = {
  total_conversations: "rate_per_conversation",
  total_visits: "rate_per_visit",
  total_oddiy_video: "rate_per_oddiy_video",
  total_dumaloq_video: "rate_per_dumaloq_video",
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function BreakdownRows({ breakdown }: { breakdown: Record<string, unknown> }) {
  const rows = Object.keys(TOTAL_LABELS)
    .map((key) => {
      const total = num(breakdown[key]);
      if (total === null) return null;
      const rate = num(breakdown[RATE_KEY[key]]) ?? 0;
      return { key, label: TOTAL_LABELS[key], total, rate, sum: total * rate };
    })
    .filter((r): r is NonNullable<typeof r> => r !== null);

  if (!rows.length) return null;

  return (
    <div className="border-t border-slate-100">
      {rows.map((r) => (
        <div key={r.key} className="flex items-baseline justify-between gap-3 px-4 py-2.5">
          <span className="min-w-0 text-sm text-slate-600">
            {r.label}
            <span className="text-slate-400">
              {" "}
              — {r.total} × {fmtMoney(r.rate)}
            </span>
          </span>
          <span className="shrink-0 text-sm font-semibold tabular-nums">{fmtMoney(r.sum)}</span>
        </div>
      ))}
    </div>
  );
}

function LatestCard({ bonus }: { bonus: Bonus }) {
  const days = num(bonus.breakdown?.days_with_data ?? null);
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="px-4 py-4">
        <div className="text-xs uppercase tracking-wide text-slate-400">{bonus.period} oyi</div>
        <div className="mt-0.5 text-2xl font-bold tabular-nums">{fmtMoney(bonus.amount)}</div>
        {days !== null && (
          <div className="mt-1 text-xs text-slate-400">Ma'lumot bo'lgan kunlar: {days}</div>
        )}
      </div>
      {bonus.breakdown && <BreakdownRows breakdown={bonus.breakdown} />}
    </div>
  );
}

export default function Kpi() {
  const { data, isLoading, isError } = useMyBonuses();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-36 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        KPI ma'lumotini yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  // Botdagi bilan bir xil matn (bot/handlers/menu.py: show_kpi)
  if (!data.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <TrendingUp className="mx-auto mb-3 h-8 w-8 text-slate-300" />
        <p className="text-sm text-slate-600">
          Joriy oy uchun KPI/bonus hali hisoblanmagan — oy oxirida avtomatik
          hisoblanadi.
        </p>
      </div>
    );
  }

  const [latest, ...older] = data;

  return (
    <div className="space-y-3">
      <LatestCard bonus={latest} />

      {!!older.length && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Oldingi davrlar
          </div>
          {older.map((b, i) => (
            <div
              key={b.id}
              className={
                "flex items-baseline justify-between gap-3 px-4 py-3" +
                (i > 0 ? " border-t border-slate-100" : "")
              }
            >
              <span className="text-sm text-slate-600">{b.period}</span>
              <span className="shrink-0 text-sm font-semibold tabular-nums">
                {fmtMoney(b.amount)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
