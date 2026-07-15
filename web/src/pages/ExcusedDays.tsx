import { useState } from "react";
import { format } from "date-fns";
import { CalendarX } from "lucide-react";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type ExcusedDay } from "@/lib/api";
import { useExcusedDays } from "@/lib/queries";

const columns: ColumnDef<ExcusedDay>[] = [
  { accessorKey: "user_full_name", header: "Xodim" },
  {
    accessorKey: "date",
    header: "Sana",
    cell: ({ row }) => format(new Date(row.original.date), "dd.MM.yyyy"),
  },
  { accessorKey: "reason", header: "Sabab", enableSorting: false },
  {
    accessorKey: "status",
    header: "Holat",
    cell: ({ row }) => <StatusBadge kind="request" status={row.original.status} />,
  },
];

export default function ExcusedDays() {
  const [statusFilter, setStatusFilter] = useState("all");
  const query = useExcusedDays(statusFilter === "all" ? undefined : statusFilter);

  return (
    <div>
      <PageHeader
        title="Sababli kunlar"
        description="Qaror qabul qilish HR tomonidan Telegram bot orqali amalga oshiriladi. Bu sahifa faqat tarixni ko'rish uchun."
      >
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Barchasi</SelectItem>
            <SelectItem value="pending">Kutilmoqda</SelectItem>
            <SelectItem value="approved">Tasdiqlangan</SelectItem>
            <SelectItem value="rejected">Rad etilgan</SelectItem>
          </SelectContent>
        </Select>
      </PageHeader>

      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        searchPlaceholder="Xodim yoki sabab bo'yicha qidirish..."
        empty={{ icon: CalendarX, text: "Sababli kun so'rovlari topilmadi." }}
      />
    </div>
  );
}
