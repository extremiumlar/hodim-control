import { useState } from "react";
import { format } from "date-fns";
import { ScrollText } from "lucide-react";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { DateRangePicker } from "@/components/PeriodPicker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type AuditLog } from "@/lib/api";
import { useAuditLogs } from "@/lib/queries";

const ACTION_LABELS: Record<string, string> = {
  user_created: "Foydalanuvchi qo'shildi",
  norm_changed: "Norma o'zgartirildi",
  excused_day_decided: "Sababli kun bo'yicha qaror",
  task_created: "Vazifa berildi",
  task_completed: "Vazifa bajarildi",
  mobilograf_confirmed: "Mobilograf tasdiqlandi",
  mobilograf_unconfirmed: "Mobilograf tasdig'i bekor qilindi",
  bonus_calculated: "Bonus hisoblandi",
};

function formatValue(value: Record<string, unknown> | null): string {
  if (!value) return "—";
  return Object.entries(value)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

const columns: ColumnDef<AuditLog>[] = [
  {
    accessorKey: "created_at",
    header: "Vaqt",
    cell: ({ row }) => (
      <span className="whitespace-nowrap">
        {format(new Date(row.original.created_at), "dd.MM.yyyy, HH:mm")}
      </span>
    ),
  },
  {
    accessorKey: "action",
    header: "Harakat",
    cell: ({ row }) => ACTION_LABELS[row.original.action] ?? row.original.action,
  },
  {
    accessorKey: "actor_name",
    header: "Kim",
    cell: ({ row }) => row.original.actor_name ?? "tizim",
  },
  {
    accessorKey: "target_name",
    header: "Kimga",
    cell: ({ row }) => row.original.target_name ?? "—",
  },
  {
    id: "change",
    header: "O'zgarish",
    enableSorting: false,
    cell: ({ row }) => (
      <div className="text-xs text-slate-500">
        <div>oldin: {formatValue(row.original.before)}</div>
        <div>keyin: {formatValue(row.original.after)}</div>
      </div>
    ),
  },
];

export default function AuditLogs() {
  const [action, setAction] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const query = useAuditLogs({
    action: action === "all" ? undefined : action,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });

  return (
    <div>
      <PageHeader title="Audit jurnali" description="Tizimdagi muhim o'zgarishlar tarixi.">
        <Select value={action} onValueChange={setAction}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Barcha harakatlar</SelectItem>
            {Object.entries(ACTION_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DateRangePicker
          from={dateFrom}
          to={dateTo}
          withPresets={false}
          onChange={(f, t) => {
            setDateFrom(f);
            setDateTo(t);
          }}
        />
      </PageHeader>

      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        searchPlaceholder="Kim yoki kimga bo'yicha qidirish..."
        empty={{ icon: ScrollText, text: "Audit yozuvlari topilmadi." }}
      />
    </div>
  );
}
