/**
 * Rahbar — «E'tiroz va shikoyatlar».
 *
 * Ro'yxat + qaror. Backenddagi ikki qoida bu yerda ham ko'rinadi:
 *  - HR faqat O'ZIGA yuborilgan murojaatlarni oladi (server filtrlaydi;
 *    frontend hech narsa yashirmaydi — u shunchaki kelganini ko'rsatadi);
 *  - anonim shikoyatda ism serverda NULL qilingan, ya'ni bu yerda ko'rsatadigan
 *    narsa ham yo'q.
 *
 * Qaror izohi MAJBURIY (≥5 belgi) — `ReasonDialog` shu shartni allaqachon
 * biladi, shuning uchun o'z formasi yozilmadi.
 *
 * ⚠️ Qondirilgan e'tirozdan keyin tuzatish AVTOMATIK bo'lmaydi: backend
 * `next_step` matnini qaytaradi va u toast + ko'rsatma paneli sifatida
 * chiqadi (modul hech narsani hisoblamaydi — KUNDALIK_ETIROZ_REJASI.md).
 */
import { useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { CheckCheck, Info, Scale, Search } from "lucide-react";
import { toast } from "sonner";

import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import ReasonDialog from "@/components/ReasonDialog";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppeals, useDecideAppeal, useReviewAppeal } from "@/lib/queries";
import type { Appeal } from "@/lib/api";
import { cn } from "@/lib/utils";

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

/** Ochiq murojaat necha kundan beri kutmoqda (SLA: 3 kun eslatma, 5 eskalatsiya). */
function ageDays(iso: string): number {
  const created = new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
  return Math.floor((Date.now() - created) / 86_400_000);
}

function isOpen(a: Appeal): boolean {
  return a.status === "pending" || a.status === "in_review";
}

function fmtDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "—"
    : `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function RefCell({ item }: { item: Appeal }) {
  if (item.ref_date) return <span className="tabular-nums">{item.ref_date}</span>;
  if (item.ref_period) return <span className="tabular-nums">{item.ref_period}</span>;
  return <span className="text-slate-300">—</span>;
}

function buildColumns(
  onReview: (item: Appeal) => void,
  onDecide: (item: Appeal) => void,
  pending: boolean
): ColumnDef<Appeal>[] {
  return [
    {
      accessorKey: "created_at",
      header: "Kelgan",
      cell: ({ row }) => {
        const a = row.original;
        const days = ageDays(a.created_at);
        return (
          <div className="whitespace-nowrap">
            <div className="tabular-nums">{fmtDate(a.created_at)}</div>
            {isOpen(a) && days >= 3 && (
              <div className={cn("text-[11px]", days >= 5 ? "text-rose-600" : "text-amber-600")}>
                {days} kun kutmoqda
              </div>
            )}
          </div>
        );
      },
    },
    {
      id: "author",
      header: "Kimdan",
      cell: ({ row }) =>
        row.original.is_anonymous ? (
          <span className="italic text-slate-400">Anonim</span>
        ) : (
          <span className="font-medium">{row.original.user_full_name?.trim() ?? "?"}</span>
        ),
    },
    {
      id: "kind",
      header: "Turi",
      cell: ({ row }) => (
        <span className="whitespace-nowrap">
          {KIND_LABELS[row.original.kind]}
          <span className="ml-1 text-slate-400">· {TOPIC_LABELS[row.original.topic]}</span>
        </span>
      ),
    },
    { id: "ref", header: "Manzil", cell: ({ row }) => <RefCell item={row.original} /> },
    {
      accessorKey: "text",
      header: "Mazmuni",
      cell: ({ row }) => (
        <div className="max-w-[420px]">
          <p className="whitespace-pre-line break-words text-sm text-slate-700">
            {row.original.text}
          </p>
          {row.original.file_id && (
            <p className="mt-1 text-[11px] text-slate-400">
              📎 Ilova biriktirilgan — botdagi xabarda ochiladi
            </p>
          )}
          {row.original.decision_note && (
            <p className="mt-1 whitespace-pre-line break-words text-xs text-slate-500">
              <b>Javob:</b> {row.original.decision_note}
            </p>
          )}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="appeal" status={row.original.status} />,
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => {
        const a = row.original;
        if (!isOpen(a)) return null;
        return (
          <div className="flex flex-wrap justify-end gap-1.5">
            {a.status === "pending" && (
              <Button size="sm" variant="outline" disabled={pending} onClick={() => onReview(a)}>
                <Search className="mr-1 h-3.5 w-3.5" />
                O'rganyapman
              </Button>
            )}
            <Button size="sm" disabled={pending} onClick={() => onDecide(a)}>
              <CheckCheck className="mr-1 h-3.5 w-3.5" />
              Hal qilish
            </Button>
          </div>
        );
      },
    },
  ];
}

export default function Appeals() {
  const [statusFilter, setStatusFilter] = useState("open");
  const [kindFilter, setKindFilter] = useState("all");
  const [decideTarget, setDecideTarget] = useState<{ item: Appeal; decision: string } | null>(null);
  const [nextStep, setNextStep] = useState<string | null>(null);

  // "open" — server tomonda yagona status emas (pending + in_review), shuning
  // uchun filtr mijozda: ro'yxat kichik (murojaatlar kuniga bir nechta).
  const query = useAppeals({
    status_filter: ["open", "all"].includes(statusFilter) ? undefined : statusFilter,
    kind: kindFilter === "all" ? undefined : kindFilter,
  });
  const review = useReviewAppeal();
  const decide = useDecideAppeal();

  const rows = (query.data ?? []).filter((a) => statusFilter !== "open" || isOpen(a));

  const columns = buildColumns(
    (item) =>
      review.mutate(item.id, {
        onSuccess: () => toast.success("Xodimga «ko'rib chiqilmoqda» deb xabar berildi"),
      }),
    (item) => setDecideTarget({ item, decision: item.kind === "objection" ? "accepted" : "resolved" }),
    review.isPending || decide.isPending
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="E'tiroz va shikoyatlar"
        description="Xodimlarning rasmiy murojaatlari. Har bir qaror izoh bilan yoziladi va xodimga to'liq ko'rinadi."
      >
        <Select value={kindFilter} onValueChange={setKindFilter}>
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Barcha turlar</SelectItem>
            <SelectItem value="objection">E'tirozlar</SelectItem>
            <SelectItem value="complaint">Shikoyatlar</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Ochiq (yangi + o'rganilmoqda)</SelectItem>
            <SelectItem value="pending">Yangi</SelectItem>
            <SelectItem value="in_review">O'rganilmoqda</SelectItem>
            <SelectItem value="accepted">Qondirilgan</SelectItem>
            <SelectItem value="resolved">Hal qilingan</SelectItem>
            <SelectItem value="rejected">Rad etilgan</SelectItem>
            <SelectItem value="all">Hammasi</SelectItem>
          </SelectContent>
        </Select>
      </PageHeader>

      {nextStep && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="flex-1">
            <b>Keyingi qadam:</b> {nextStep}
          </div>
          <button
            type="button"
            onClick={() => setNextStep(null)}
            className="shrink-0 text-xs font-medium text-emerald-700 hover:underline"
          >
            Yopish
          </button>
        </div>
      )}

      <DataTable
        columns={columns}
        data={rows}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        searchPlaceholder="Xodim yoki mazmun bo'yicha qidirish..."
        empty={{ icon: Scale, text: "Murojaat topilmadi." }}
      />

      {decideTarget && (
        <DecideDialog
          target={decideTarget}
          onChangeDecision={(decision) => setDecideTarget({ ...decideTarget, decision })}
          loading={decide.isPending}
          onClose={() => setDecideTarget(null)}
          onConfirm={(note) =>
            decide.mutate(
              { itemId: decideTarget.item.id, decision: decideTarget.decision, note },
              {
                onSuccess: (res) => {
                  setDecideTarget(null);
                  setNextStep(res.next_step);
                  toast.success("Qaror saqlandi, xodimga xabar yuborildi");
                },
              }
            )
          }
        />
      )}
    </div>
  );
}

/** Qaror turi + majburiy izoh. `ReasonDialog` izohni (≥5 belgi) o'zi
 *  tekshiradi; qaror turi tanlovi uning ustiga qo'yiladi. */
function DecideDialog({
  target,
  onChangeDecision,
  onConfirm,
  onClose,
  loading,
}: {
  target: { item: Appeal; decision: string };
  onChangeDecision: (decision: string) => void;
  onConfirm: (note: string) => void;
  onClose: () => void;
  loading: boolean;
}) {
  const isObjection = target.item.kind === "objection";
  // Qaror turi murojaat turiga mos bo'lishi shart — backend ham tekshiradi
  // (e'tiroz: accepted/rejected, shikoyat: resolved/rejected).
  const options = isObjection
    ? [
        { value: "accepted", label: "✅ Qondirish" },
        { value: "rejected", label: "❌ Rad etish" },
      ]
    : [
        { value: "resolved", label: "✅ Hal qilindi" },
        { value: "rejected", label: "❌ Rad etish" },
      ];

  return (
    <ReasonDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`${KIND_LABELS[target.item.kind]} bo'yicha qaror`}
      description={
        target.decision === "accepted"
          ? "Qondirilgandan keyin tuzatishni O'ZINGIZ kiritasiz — tizim avtomatik o'zgartirmaydi."
          : "Izoh xodimga to'liq ko'rinadi."
      }
      confirmLabel="Qarorni saqlash"
      reasonLabel="Izoh (majburiy, kamida 5 belgi) — xodimga to'liq ko'rinadi"
      reasonPlaceholder="Nega shunday qaror qilindi?"
      loading={loading}
      onConfirm={onConfirm}
      extra={
        <div className="flex flex-wrap gap-2">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => onChangeDecision(o.value)}
              className={cn(
                "min-h-[36px] rounded-lg border px-3 text-sm font-medium",
                target.decision === o.value
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-slate-200 text-slate-600"
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      }
    />
  );
}
