import { type StatsReason } from "@/lib/api";

const REASON_CATEGORY_LABELS: Record<string, string> = {
  no_answer: "Mijoz ko'tarmadi",
  no_base: "Lid/baza tugadi",
  tech: "Texnik muammo",
  meeting: "Yig'ilish/band",
  other: "Boshqa",
};

function fmtDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** Orqada qolish sabablari lentasi — operator javoblari + AI tekshiruv belgilari. */
export default function ReasonsFeed({ reasons }: { reasons: StatsReason[] }) {
  if (reasons.length === 0) {
    return <p className="text-sm text-slate-400">Bu davrda sabab so'ralmagan.</p>;
  }
  return (
    <div className="space-y-2">
      {reasons.map((r, i) => (
        <div key={i} className="flex items-start gap-3 border-b border-slate-100 pb-2 text-sm">
          <span className="whitespace-nowrap text-slate-400">
            {fmtDay(r.date)} {String(r.hour).padStart(2, "0")}:00
          </span>
          <span className="whitespace-nowrap font-medium">{r.user_name}</span>
          <span className="flex-1">
            {r.reason ?? <i className="text-slate-400">Javob yozilmagan</i>}
            {r.ai_category &&
              r.reason &&
              (REASON_CATEGORY_LABELS[r.ai_category] ?? r.ai_category) !== r.reason && (
                <span className="text-slate-400">
                  {" "}
                  · {REASON_CATEGORY_LABELS[r.ai_category] ?? r.ai_category}
                </span>
              )}
            {r.raw_text && <span className="mt-0.5 block text-xs text-slate-400">«{r.raw_text}»</span>}
          </span>
          {r.verified === false && (
            <span
              className="whitespace-nowrap rounded bg-rose-50 px-1.5 py-0.5 text-xs text-rose-700"
              title={r.verify_note ?? ""}
            >
              ⚠ mos kelmadi
            </span>
          )}
          {r.verified === true && (
            <span
              className="whitespace-nowrap rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700"
              title={r.verify_note ?? ""}
            >
              ✓ tasdiqlandi
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
