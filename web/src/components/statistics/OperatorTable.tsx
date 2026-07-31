import { type ReactNode } from "react";
import { type OperatorSummary } from "@/lib/api";
import { MobileCard, MobileCardRow } from "@/components/MobileCard";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

function fmtTalk(sec: number): string {
  const minutes = Math.floor(sec / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}s ${m}d` : `${m}d`;
}

function fmtDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

function PctBadge({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  const positive = pct > 0;
  const cls = positive
    ? "text-emerald-700 bg-emerald-50"
    : pct < 0
      ? "text-rose-700 bg-rose-50"
      : "text-slate-600 bg-slate-100";
  return (
    <span className={cn("ml-1 rounded px-1.5 py-0.5 text-xs font-medium", cls)}>
      {positive ? "+" : ""}
      {pct}%
    </span>
  );
}

/**
 * Ustunlar BIR MARTA e'lon qilinadi — jadval (desktop) va karta (telefon)
 * ikkalasi ham shu ro'yxatdan quriladi. Aks holda ustun qo'shilganda biri
 * yangilanib, ikkinchisi jimgina eskirib qolardi.
 */
const FIELDS: { key: keyof OperatorRow; label: string }[] = [
  { key: "name", label: "Xodim" },
  { key: "calls", label: "📞 Qo'ng'iroq" },
  { key: "talk", label: "🗣 Gaplashgan" },
  { key: "leads", label: "🧲 Lid" },
  { key: "visits", label: "🏠 Tashrif" },
  { key: "tasks", label: "✅ Vazifa" },
];

type OperatorRow = {
  id: string;
  name: ReactNode;
  calls: ReactNode;
  talk: ReactNode;
  leads: ReactNode;
  visits: ReactNode;
  tasks: ReactNode;
};

/** Operator kesimi jadvali — davr jami va oldingi davrga % farq bilan. */
export default function OperatorTable({
  summary,
  isLoading,
}: {
  summary: OperatorSummary | null | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="space-y-2 py-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (!summary || summary.operators.length === 0) {
    return <p className="py-4 text-center text-sm text-slate-400">Bu davr uchun ma'lumot yo'q.</p>;
  }

  const rows: OperatorRow[] = summary.operators.map((op) => ({
    id: String(op.responsible_id),
    name: (
      <>
        {op.name}
        {!op.is_system_user && (
          <span
            className="ml-1 text-xs text-slate-400"
            title="Tizim foydalanuvchisiga bog'lanmagan (CRM ID)"
          >
            ⚠
          </span>
        )}
      </>
    ),
    calls: (
      <>
        <b>{op.calls}</b>
        <PctBadge pct={op.calls_pct} />
      </>
    ),
    talk: op.talk_sec ? fmtTalk(op.talk_sec) : "—",
    leads: op.leads,
    visits: op.visits,
    tasks: op.tasks_total != null ? `${op.tasks_done}/${op.tasks_total}` : "—",
  }));

  const totalsRow: OperatorRow = {
    id: "jami",
    name: "Jami",
    calls: (
      <>
        {summary.totals.calls}
        <PctBadge pct={summary.totals.calls_pct} />
      </>
    ),
    talk: fmtTalk(summary.totals.talk_sec),
    leads: summary.totals.leads,
    visits: summary.totals.visits,
    tasks: null,
  };

  return (
    <>
      <p className="mb-2 text-xs text-slate-400">
        {fmtDay(summary.date_from)} – {fmtDay(summary.date_to)} · % — oldingi teng davrga (
        {fmtDay(summary.prev_from)} – {fmtDay(summary.prev_to)}) nisbatan
      </p>

      {/* ── Telefon (md dan kichik): karta ko'rinishi ──
          Ilgari bu yerda faqat `overflow-x-auto` bor edi va 6 ustunli jadval
          360 px ekranda 255 px yashirin gorizontal scroll berardi. Sahifa
          darajasidagi overflow 0 bo'lgani uchun (shadcn `Table` o'zi
          `overflow-auto` wrapper bilan keladi) bu nuqson Bosqich 6 da
          o'lchovdan chetda qolgan edi. */}
      <div className="space-y-2 md:hidden">
        {[...rows, totalsRow].map((row) => (
          <MobileCard key={row.id} className={row.id === "jami" ? "font-medium" : undefined}>
            {FIELDS.map((f) => (
              <MobileCardRow key={f.key} label={f.label}>
                {row[f.key]}
              </MobileCardRow>
            ))}
          </MobileCard>
        ))}
      </div>

      {/* ── Desktop (md va yuqori): jadval ── */}
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow>
              {FIELDS.map((f) => (
                <TableHead key={f.key}>{f.label}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                {FIELDS.map((f) => (
                  <TableCell key={f.key}>{row[f.key]}</TableCell>
                ))}
              </TableRow>
            ))}
            <TableRow className="font-medium">
              {FIELDS.map((f) => (
                <TableCell key={f.key}>{totalsRow[f.key]}</TableCell>
              ))}
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </>
  );
}
