import { type OperatorSummary } from "@/lib/api";
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

  return (
    <>
      <p className="mb-2 text-xs text-slate-400">
        {fmtDay(summary.date_from)} – {fmtDay(summary.date_to)} · % — oldingi teng davrga (
        {fmtDay(summary.prev_from)} – {fmtDay(summary.prev_to)}) nisbatan
      </p>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Xodim</TableHead>
              <TableHead>📞 Qo'ng'iroq</TableHead>
              <TableHead>🗣 Gaplashgan</TableHead>
              <TableHead>🧲 Lid</TableHead>
              <TableHead>🏠 Tashrif</TableHead>
              <TableHead>✅ Vazifa</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {summary.operators.map((op) => (
              <TableRow key={op.responsible_id}>
                <TableCell>
                  {op.name}
                  {!op.is_system_user && (
                    <span
                      className="ml-1 text-xs text-slate-400"
                      title="Tizim foydalanuvchisiga bog'lanmagan (CRM ID)"
                    >
                      ⚠
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <b>{op.calls}</b>
                  <PctBadge pct={op.calls_pct} />
                </TableCell>
                <TableCell>{op.talk_sec ? fmtTalk(op.talk_sec) : "—"}</TableCell>
                <TableCell>{op.leads}</TableCell>
                <TableCell>{op.visits}</TableCell>
                <TableCell>
                  {op.tasks_total != null ? `${op.tasks_done}/${op.tasks_total}` : "—"}
                </TableCell>
              </TableRow>
            ))}
            <TableRow className="font-medium">
              <TableCell>Jami</TableCell>
              <TableCell>
                {summary.totals.calls}
                <PctBadge pct={summary.totals.calls_pct} />
              </TableCell>
              <TableCell>{fmtTalk(summary.totals.talk_sec)}</TableCell>
              <TableCell>{summary.totals.leads}</TableCell>
              <TableCell>{summary.totals.visits}</TableCell>
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </>
  );
}
