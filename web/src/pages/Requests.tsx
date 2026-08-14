/**
 * Rahbar — «Arizalar».
 *
 * `Appeals.tsx` dan farqi: ariza tasdiqlanganda tizim REAL yozuv yaratadi
 * (ta'til → sababli kunlar, avans → oylik tuzatishi). Shuning uchun bu
 * sahifada ikkita qo'shimcha narsa bor:
 *   - qaror natijasi («5 ta sababli kun yozildi») — HR nima bo'lganini
 *     taxmin qilmasin;
 *   - «Bekor qilish» — tasdiqlangan arizani qaytarish (yozuvlar ham
 *     qaytariladi, `source_request_id` bo'yicha).
 */
import { useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { CheckCheck, FileText, Info, Undo2 } from "lucide-react";
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
import { useDecideRequest, useRequests, useRevokeRequest } from "@/lib/queries";
import type { EmployeeRequest, RequestKind } from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<RequestKind, string> = {
  vacation: "Mehnat ta'tili",
  unpaid: "O'z hisobidan",
  sick: "Kasallik",
  advance: "Avans",
  certificate: "Ma'lumotnoma",
  schedule_change: "Jadval o'zgartirish",
  resignation: "Ishdan bo'shash",
  other: "Boshqa",
};

function isOpen(r: EmployeeRequest): boolean {
  return r.status === "pending" || r.status === "manager_ok";
}

function ageDays(iso: string): number {
  const t = new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
  return Math.floor((Date.now() - t) / 86_400_000);
}

function fmtDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "—"
    : `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function fmtMoney(v: number): string {
  return `${Math.round(v).toLocaleString("ru-RU").replace(/ /g, " ")} so'm`;
}

/** Ariza mazmuni: muddat yoki summa + sabab + javob. */
function DetailCell({ item }: { item: EmployeeRequest }) {
  return (
    <div className="max-w-[420px]">
      {item.start_date && (
        <div className="text-sm font-medium tabular-nums">
          {item.start_date} — {item.end_date}
          {item.working_days != null && (
            <span className="ml-1.5 text-xs font-normal text-slate-400">
              {item.working_days} ish kuni
            </span>
          )}
        </div>
      )}
      {item.amount != null && (
        <div className="text-sm font-medium tabular-nums">{fmtMoney(item.amount)}</div>
      )}
      <p className="whitespace-pre-line break-words text-sm text-slate-600">{item.reason}</p>
      {/* To'qnashuv — server yaratishda aniqlagan (payload.conflict_dates) */}
      {Array.isArray((item.payload as { conflict_dates?: string[] })?.conflict_dates) && (
        <p className="mt-1 text-[11px] text-amber-700">
          ⚠ Bu kunlarda allaqachon sababli kun bor:{" "}
          {((item.payload as { conflict_dates: string[] }).conflict_dates || []).join(", ")}
        </p>
      )}
      {item.decision_note && (
        <p className="mt-1 whitespace-pre-line break-words text-xs text-slate-500">
          <b>Javob:</b> {item.decision_note}
        </p>
      )}
    </div>
  );
}

function buildColumns(
  onDecide: (item: EmployeeRequest) => void,
  onRevoke: (item: EmployeeRequest) => void,
  pending: boolean
): ColumnDef<EmployeeRequest>[] {
  return [
    {
      accessorKey: "created_at",
      header: "Kelgan",
      cell: ({ row }) => {
        const r = row.original;
        const days = ageDays(r.created_at);
        return (
          <div className="whitespace-nowrap">
            <div className="tabular-nums">{fmtDate(r.created_at)}</div>
            {isOpen(r) && days >= 3 && (
              <div className={cn("text-[11px]", days >= 5 ? "text-rose-600" : "text-amber-600")}>
                {days} kun kutmoqda
              </div>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "user_full_name",
      header: "Xodim",
      cell: ({ row }) => (
        <span className="font-medium">{row.original.user_full_name?.trim() ?? "?"}</span>
      ),
    },
    {
      accessorKey: "kind",
      header: "Turi",
      cell: ({ row }) => (
        <span className="whitespace-nowrap">{KIND_LABELS[row.original.kind]}</span>
      ),
    },
    {
      id: "detail",
      header: "Mazmuni",
      enableSorting: false,
      cell: ({ row }) => <DetailCell item={row.original} />,
    },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="employee_request" status={row.original.status} />,
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => {
        const r = row.original;
        if (isOpen(r)) {
          return (
            <div className="flex justify-end">
              <Button size="sm" disabled={pending} onClick={() => onDecide(r)}>
                <CheckCheck className="mr-1 h-3.5 w-3.5" />
                Hal qilish
              </Button>
            </div>
          );
        }
        if (r.status === "approved") {
          return (
            <div className="flex justify-end">
              <Button size="sm" variant="outline" disabled={pending} onClick={() => onRevoke(r)}>
                <Undo2 className="mr-1 h-3.5 w-3.5" />
                Bekor qilish
              </Button>
            </div>
          );
        }
        return null;
      },
    },
  ];
}

export default function Requests() {
  const [statusFilter, setStatusFilter] = useState("open");
  const [kindFilter, setKindFilter] = useState("all");
  const [decideTarget, setDecideTarget] = useState<{ item: EmployeeRequest; decision: string } | null>(
    null
  );
  const [revokeTarget, setRevokeTarget] = useState<EmployeeRequest | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const query = useRequests({
    status_filter: ["open", "all"].includes(statusFilter) ? undefined : statusFilter,
    kind: kindFilter === "all" ? undefined : kindFilter,
  });
  const decide = useDecideRequest();
  const revoke = useRevokeRequest();

  const rows = (query.data ?? []).filter((r) => statusFilter !== "open" || isOpen(r));

  const columns = buildColumns(
    (item) => setDecideTarget({ item, decision: "approved" }),
    (item) => setRevokeTarget(item),
    decide.isPending || revoke.isPending
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Arizalar"
        description="Ta'til, avans, ma'lumotnoma. Tasdiqlanganda tizim yozuvlarni O'ZI yaratadi — natija shu yerda ko'rinadi."
      >
        <Select value={kindFilter} onValueChange={setKindFilter}>
          <SelectTrigger className="w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Barcha turlar</SelectItem>
            {(Object.keys(KIND_LABELS) as RequestKind[]).map((k) => (
              <SelectItem key={k} value={k}>
                {KIND_LABELS[k]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Ochiq</SelectItem>
            <SelectItem value="approved">Tasdiqlangan</SelectItem>
            <SelectItem value="rejected">Rad etilgan</SelectItem>
            <SelectItem value="revoked">Bekor qilingan</SelectItem>
            <SelectItem value="cancelled">Qaytarib olingan</SelectItem>
            <SelectItem value="all">Hammasi</SelectItem>
          </SelectContent>
        </Select>
      </PageHeader>

      {banner && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="flex-1 whitespace-pre-line">{banner}</div>
          <button
            type="button"
            onClick={() => setBanner(null)}
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
        empty={{ icon: FileText, text: "Ariza topilmadi." }}
      />

      {decideTarget && (
        <ReasonDialog
          open
          onOpenChange={(o) => !o && setDecideTarget(null)}
          title={`${KIND_LABELS[decideTarget.item.kind]} — qaror`}
          description={
            decideTarget.decision === "approved"
              ? "Tasdiqlangach tizim yozuvlarni O'ZI yaratadi (sababli kunlar yoki oylik tuzatishi)."
              : "Izoh xodimga to'liq ko'rinadi."
          }
          confirmLabel="Qarorni saqlash"
          reasonLabel="Izoh (majburiy, kamida 5 belgi) — xodimga ko'rinadi"
          reasonPlaceholder="Nega shunday qaror qilindi?"
          loading={decide.isPending}
          extra={
            <div className="flex flex-wrap gap-2">
              {[
                { v: "approved", label: "✅ Tasdiqlash" },
                { v: "rejected", label: "❌ Rad etish" },
              ].map((o) => (
                <button
                  key={o.v}
                  type="button"
                  onClick={() => setDecideTarget({ ...decideTarget, decision: o.v })}
                  className={cn(
                    "min-h-[36px] rounded-lg border px-3 text-sm font-medium",
                    decideTarget.decision === o.v
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-slate-200 text-slate-600"
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
          }
          onConfirm={(note) =>
            decide.mutate(
              { itemId: decideTarget.item.id, decision: decideTarget.decision, note },
              {
                onSuccess: (res) => {
                  setDecideTarget(null);
                  // Materializatsiya natijasini KO'RSATAMIZ — HR nima
                  // yozilganini taxmin qilmasin.
                  const parts: string[] = [];
                  if (res.applied?.excused_created) {
                    parts.push(`📅 ${res.applied.excused_created} ta sababli kun yozildi.`);
                  }
                  if (res.applied?.period) {
                    parts.push(
                      `💵 Avans ${res.applied.period} davriga qo'shildi — Boshliq tasdig'i kutilmoqda.`
                    );
                  }
                  if (res.next_step) parts.push(`📌 Keyingi qadam: ${res.next_step}`);
                  setBanner(parts.join("\n") || null);
                  toast.success("Qaror saqlandi, xodimga xabar yuborildi");
                },
              }
            )
          }
        />
      )}

      {revokeTarget && (
        <ReasonDialog
          open
          onOpenChange={(o) => !o && setRevokeTarget(null)}
          title="Tasdiqlangan arizani bekor qilish"
          description="Yozilgan sababli kunlar qaytariladi va davomat qayta hisoblanadi. Tasdiqlangan avansga tegilmaydi."
          // ⚠️ «Bekor qilish» DEB YOZMANG: `ReasonDialog` ning o'z yopish
          // tugmasi ham aynan shunday nomlanadi va foydalanuvchi qaysi biri
          // dialogni yopishini, qaysi biri ARIZANI bekor qilishini
          // ajratolmaydi (brauzer sinovida aniqlangan).
          confirmLabel="Ha, arizani qaytarish"
          reasonLabel="Sabab (majburiy, kamida 5 belgi) — xodimga ko'rinadi"
          reasonPlaceholder="Nega bekor qilinmoqda?"
          destructive
          loading={revoke.isPending}
          onConfirm={(reason) =>
            revoke.mutate(
              { itemId: revokeTarget.id, reason },
              {
                onSuccess: (res) => {
                  setRevokeTarget(null);
                  const parts: string[] = [];
                  if (res.reverted?.excused_reverted) {
                    parts.push(`↩️ ${res.reverted.excused_reverted} ta sababli kun qaytarildi.`);
                  }
                  if (res.reverted?.advance_removed) {
                    parts.push(`↩️ ${res.reverted.advance_removed} ta avans olib tashlandi.`);
                  }
                  if (res.reverted?.warning) parts.push(`⚠️ ${res.reverted.warning}`);
                  setBanner(parts.join("\n") || null);
                  toast.success("Ariza bekor qilindi");
                },
              }
            )
          }
        />
      )}
    </div>
  );
}
