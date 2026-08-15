/**
 * Sotuv voronkasi — o'lchov (1-bosqich).
 *
 * Reja: `VORONKA_TARGET_REJASI.html` · Ta'riflar: `VORONKA_TARIFLAR.md`
 *
 * IKKI REJIM ATAYLAB AJRATILGAN:
 *  - «Davr kesimi» — shu oy ichida nima bo'ldi (operativ nazorat)
 *  - «Kogorta» — shu oyda KELGAN lidlar keyin qayergacha yetdi (haqiqiy
 *    konversiya). Rejalashtirishga faqat shu raqam asos bo'ladi.
 */
import { useState } from "react";
import { AlertTriangle, Filter, Info } from "lucide-react";
import EconomicsCard from "@/components/funnel/EconomicsCard";
import PageHeader from "@/components/PageHeader";
import { MonthPicker, currentMonthKey } from "@/components/PeriodPicker";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type FunnelData, type FunnelRow, type FunnelSpread } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFunnel, useFunnelChannels, useFunnelMonths } from "@/lib/queries";

const fmt = (n: number) => n.toLocaleString("ru-RU").replace(/,/g, " ");
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v}%`);

/** Voronka qatori — kenglik eng katta qiymatga nisbatan. */
function Bar({ row, max, weakest }: { row: FunnelRow; max: number; weakest: boolean }) {
  const width = max > 0 ? Math.max(8, Math.round((row.value / max) * 100)) : 100;
  const outside = row.outside_chain;

  return (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        <div
          className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-2.5 transition-all ${
            outside
              ? "border-dashed border-slate-300 bg-slate-50 dark:bg-slate-900/40"
              : weakest
                ? "border-amber-300 bg-amber-50 dark:bg-amber-950/30"
                : "border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30"
          }`}
          style={{ width: `${width}%` }}
        >
          <span className="truncate text-sm font-medium">{row.label}</span>
          <span className="shrink-0 font-mono text-sm font-bold tabular-nums">
            {fmt(row.value)}
          </span>
        </div>
      </div>
      <div className="w-28 shrink-0 text-right">
        {row.conv_from_prev !== null && row.conv_from_prev !== undefined ? (
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-xs ${
              weakest ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-600"
            }`}
            title={row.conv_label ?? "oldingi bosqichdan"}
          >
            {pct(row.conv_from_prev)}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </div>
    </div>
  );
}

function FunnelCard({ data, isLoading }: { data?: FunnelData; isLoading: boolean }) {
  if (isLoading && !data) return <Skeleton className="h-80 w-full rounded-xl" />;
  if (!data) return null;

  const max = Math.max(...data.rows.map((r) => r.value), 1);
  const notConfigured = Object.entries(data.stages_configured)
    .filter(([, ok]) => !ok)
    .map(([k]) => k);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">
          {data.mode === "cohort" ? "Kogorta — haqiqiy konversiya" : "Davr kesimi — operativ"}
        </CardTitle>
        {data.mode === "cohort" && data.mature === false && (
          <Badge variant="secondary" title={`Kogorta ${data.maturity_days} kunda «pishadi»`}>
            hali to'liq emas
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {notConfigured.length > 0 && (
          <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            CRM bosqichi sozlanmagan: {notConfigured.join(", ")} — dasturchiga ayting
            (<code>CRM_UYSOT_*_PIPE_STATUS_IDS</code>).
          </p>
        )}

        <div className="space-y-2">
          {data.rows.map((r) => (
            <Bar key={r.key} row={r} max={max} weakest={data.weakest_link?.key === r.key} />
          ))}
        </div>

        {data.weakest_link && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/30">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>
              Eng zaif bo'g'in — <b>{data.weakest_link.label}</b> ({data.weakest_link.conv}%).
              Shu o'tishni yaxshilash butun zanjirga eng ko'p ta'sir qiladi.
            </span>
          </div>
        )}

        {data.mode === "period" && data.calls_quality && (
          <p className="text-xs text-muted-foreground">
            Suhbat sifati: {fmt(data.calls_quality.talk_minutes)} daqiqa jami ·{" "}
            {fmt(data.calls_quality.short_calls)} ta qisqa qo'ng'iroq (15 soniyadan kam)
          </p>
        )}

        {data.approx_leads > 0 && (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            {fmt(data.approx_leads)} ta lidning CRM'da yaratilgan vaqti noma'lum — skaner
            ularni birinchi ko'rgan sana ishlatildi (taxminiy).
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SpreadRow({ label, s }: { label: string; s: FunnelSpread }) {
  return (
    <tr>
      <td className="py-1.5">{label}</td>
      <td className="py-1.5 text-right font-mono font-semibold">{pct(s.avg)}</td>
      <td className="py-1.5 text-right font-mono text-muted-foreground">
        {s.min === null ? "—" : `${s.min}–${s.max}%`}
      </td>
      <td className="py-1.5 text-right text-muted-foreground">{s.months} oy</td>
    </tr>
  );
}

/**
 * Kanal kesimi — «qaysi reklama sotuv keltirdi».
 *
 * Har doim KOGORTA: shu oyda kelgan lidlar keyin qayergacha yetdi. Davr
 * kesimi bu yerda ma'nosiz bo'lardi — kanal lidga biriktirilgan, hodisaga
 * emas.
 */
function ChannelCard({
  month,
  groupBy,
  setGroupBy,
}: {
  month: string;
  groupBy: "tag" | "source";
  setGroupBy: (v: "tag" | "source") => void;
}) {
  const q = useFunnelChannels(groupBy, month);
  const rows = q.data?.rows ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">Kanal kesimi — qaysi manba sotuv keltiradi</CardTitle>
        <Tabs value={groupBy} onValueChange={(v) => setGroupBy(v as "tag" | "source")}>
          <TabsList>
            <TabsTrigger value="tag">Teglar</TabsTrigger>
            <TabsTrigger value="source">Manba</TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent>
        {q.isLoading && !q.data ? (
          <Skeleton className="h-40 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Bu davrda lid yo'q.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2 text-left font-medium">
                      {groupBy === "tag" ? "Teg" : "Manba"}
                    </th>
                    <th className="py-2 text-right font-medium">Lid</th>
                    <th className="py-2 text-right font-medium">Tashrif</th>
                    <th className="py-2 text-right font-medium">Shartnoma</th>
                    <th className="py-2 text-right font-medium">Lid→tashrif</th>
                    <th className="py-2 text-right font-medium">Lid→shartnoma</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.channel} className="border-b last:border-0">
                      <td className="max-w-[220px] truncate py-1.5" title={r.channel}>
                        {r.channel}
                      </td>
                      <td className="py-1.5 text-right font-mono">{fmt(r.leads)}</td>
                      <td className="py-1.5 text-right font-mono">{fmt(r.visits)}</td>
                      <td className="py-1.5 text-right font-mono font-semibold">
                        {fmt(r.contracts)}
                      </td>
                      <td className="py-1.5 text-right font-mono">{pct(r.lead_to_visit)}</td>
                      <td className="py-1.5 text-right font-mono">{pct(r.lead_to_contract)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {groupBy === "tag" ? (
                <>
                  Bitta lid bir nechta tegda bo'lishi mumkin — shuning uchun yig'indi umumiy
                  liddan ko'p chiqadi, bu xato emas.
                </>
              ) : (
                <>
                  Manba CRM'dan lid-ma'lumoti orqali sekin to'ldiriladi (so'rov limiti
                  sababli). «(manba yo'q)» — hali so'ralmagan yoki CRM'da ko'rsatilmagan.
                </>
              )}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function FunnelPage() {
  const { user } = useAuth();
  const [mode, setMode] = useState<"period" | "cohort">("cohort");
  const [month, setMonth] = useState(currentMonthKey());
  const [groupBy, setGroupBy] = useState<"tag" | "source">("tag");
  // Xarajatni kim kiritadi — backend `funnel.py: _EDIT_ROLES` bilan bir xil
  const canEdit = ["boss", "dasturchi", "rop"].includes(user?.role ?? "");
  const funnel = useFunnel(mode, month);
  const months = useFunnelMonths(6);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Sotuv voronkasi"
        description="Lid → taklif → tashrif → shartnoma: har bosqich va konversiya"
      >
        <MonthPicker value={month} onChange={setMonth} />
      </PageHeader>

      <Tabs value={mode} onValueChange={(v) => setMode(v as "period" | "cohort")}>
        <TabsList>
          <TabsTrigger value="cohort">Kogorta (haqiqiy)</TabsTrigger>
          <TabsTrigger value="period">Davr kesimi</TabsTrigger>
        </TabsList>
      </Tabs>

      <p className="text-sm text-muted-foreground">
        {mode === "cohort" ? (
          <>
            <b>Kogorta:</b> shu oyda <b>kelgan</b> lidlarning nechtasi keyinchalik sotuvga
            aylandi. Avgustda kelgan lid oktyabrda shartnoma qilsa ham avgustga yoziladi —
            rejalashtirish uchun yagona to'g'ri hisob.
          </>
        ) : (
          <>
            <b>Davr kesimi:</b> shu oy <b>ichida</b> sodir bo'lgan hodisalar. Kunlik nazorat
            uchun qulay, lekin konversiya vaqt siljishi tufayli chalg'itishi mumkin —
            reja tuzishda kogortaga qarang.
          </>
        )}
      </p>

      <FunnelCard data={funnel.data} isLoading={funnel.isLoading} />

      <ChannelCard month={month} groupBy={groupBy} setGroupBy={setGroupBy} />

      <EconomicsCard period={month} groupBy={groupBy} canEdit={canEdit} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="size-4" /> Oxirgi oylar — o'rtacha va tebranish
          </CardTitle>
        </CardHeader>
        <CardContent>
          {months.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2 text-left font-medium">Konversiya</th>
                    <th className="py-2 text-right font-medium">O'rtacha</th>
                    <th className="py-2 text-right font-medium">Oralig'i</th>
                    <th className="py-2 text-right font-medium">Asos</th>
                  </tr>
                </thead>
                <tbody>
                  <SpreadRow label="Lid → tashrif" s={months.data!.summary.lead_to_visit} />
                  <SpreadRow label="Lid → shartnoma" s={months.data!.summary.lead_to_contract} />
                  <SpreadRow label="Tashrif → shartnoma" s={months.data!.summary.visit_to_contract} />
                </tbody>
              </table>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase text-muted-foreground">
                      <th className="py-2 text-left font-medium">Oy</th>
                      <th className="py-2 text-right font-medium">Lid</th>
                      <th className="py-2 text-right font-medium">Tashrif</th>
                      <th className="py-2 text-right font-medium">Shartnoma</th>
                      <th className="py-2 text-right font-medium">Lid→shartnoma</th>
                    </tr>
                  </thead>
                  <tbody>
                    {months.data!.series.map((m) => (
                      <tr key={m.period} className="border-b last:border-0">
                        <td className="py-1.5">
                          {m.period}
                          {!m.mature && (
                            <span className="ml-2 text-xs text-muted-foreground">(pishmagan)</span>
                          )}
                        </td>
                        <td className="py-1.5 text-right font-mono">{fmt(m.leads)}</td>
                        <td className="py-1.5 text-right font-mono">{fmt(m.visits)}</td>
                        <td className="py-1.5 text-right font-mono">{fmt(m.contracts)}</td>
                        <td className="py-1.5 text-right font-mono">{pct(m.lead_to_contract)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="mt-3 text-xs text-muted-foreground">
                O'rtachaga faqat <b>pishgan</b> oylar kiradi — yosh kogortada lidlarning bir
                qismi hali sotuvga yetib ulgurmagan va foiz sun'iy past chiqadi.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
