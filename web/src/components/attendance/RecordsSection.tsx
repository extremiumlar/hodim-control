/**
 * «Yozuvlar» — xom davomat qatorlari jadvali (sana oralig'i + xodim filtri).
 *
 * UX-B: Attendance.tsx dan ko'chirildi. UX-G2: xodim filtri qo'shildi —
 * qidiruvga ism yozish o'rniga tanlash. Tahrirlash/o'chirish dialoglari
 * shu yerda (matritsa katagi o'z popover'idan xuddi shu EditAttendanceDialog'ni
 * ochadi — lekin o'z holati bilan).
 */
import { useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import EditAttendanceDialog from "@/components/attendance/EditAttendanceDialog";
import { DateRangePicker } from "@/components/PeriodPicker";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type Attendance as AttendanceRow } from "@/lib/api";
import { useAttendanceList, useDeleteAttendance, useUsers } from "@/lib/queries";
import { fmtLocalTime as fmtTime } from "@/lib/utils";

function baseRowColumns(): ColumnDef<AttendanceRow>[] {
  return [
    {
      accessorKey: "date",
      header: "Sana",
      cell: ({ row }) => format(new Date(row.original.date), "dd.MM.yyyy"),
    },
    {
      accessorKey: "user_full_name",
      header: "Xodim",
      cell: ({ row }) => <b>{row.original.user_full_name}</b>,
    },
    { accessorKey: "check_in_time", header: "Keldim", cell: ({ row }) => fmtTime(row.original.check_in_time) },
    { accessorKey: "check_out_time", header: "Ketdim", cell: ({ row }) => fmtTime(row.original.check_out_time) },
    {
      accessorKey: "late_minutes",
      header: "Kechikish",
      cell: ({ row }) =>
        row.original.late_minutes > 0 ? (
          <span className="text-rose-600">{row.original.late_minutes} daq</span>
        ) : (
          "—"
        ),
    },
    {
      accessorKey: "worked_minutes",
      header: "Ishlangan",
      cell: ({ row }) =>
        row.original.worked_minutes > 0
          ? `${Math.round((row.original.worked_minutes / 60) * 10) / 10} soat`
          : "—",
    },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="attendance" status={row.original.status} />,
    },
  ];
}

export default function RecordsSection({
  canEdit,
  isDasturchi,
}: {
  canEdit: boolean;
  isDasturchi: boolean;
}) {
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), "yyyy-MM-dd"));
  const [dateTo, setDateTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [userFilter, setUserFilter] = useState("all");
  const [deleting, setDeleting] = useState<AttendanceRow | null>(null);
  const [editing, setEditing] = useState<AttendanceRow | null>(null);
  // Yangi yozuv dialogi — `editing` null qolgani uchun alohida bayroq kerak.
  const [adding, setAdding] = useState(false);

  const usersQuery = useUsers();
  const listQuery = useAttendanceList({
    date_from: dateFrom,
    date_to: dateTo,
    ...(userFilter !== "all" ? { user_id: Number(userFilter) } : {}),
  });
  const deleteAttendance = useDeleteAttendance();

  // Amallar ustuni: qalam — HR/Boshliq qo'lda tuzatishi; savat — faqat Dasturchi
  // (check-in oqimini qaytadan sinash uchun yozuvni butunlay tozalash).
  const rowColumns = useMemo<ColumnDef<AttendanceRow>[]>(() => {
    const cols = baseRowColumns();
    if (!canEdit && !isDasturchi) return cols;
    return [
      ...cols,
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex gap-1">
            {canEdit && (
              <Button
                variant="ghost"
                size="sm"
                title={isDasturchi ? "Qo'lda tuzatish (Dasturchi — auditsiz)" : "Qo'lda tuzatish"}
                onClick={() => setEditing(row.original)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
            {isDasturchi && (
              <Button
                variant="ghost"
                size="sm"
                title="O'chirish"
                className="text-rose-600 hover:text-rose-700"
                onClick={() => setDeleting(row.original)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        ),
      },
    ];
  }, [canEdit, isDasturchi]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h3 className="font-semibold">Yozuvlar</h3>
        <DateRangePicker
          from={dateFrom}
          to={dateTo}
          onChange={(f, t) => {
            setDateFrom(f);
            setDateTo(t);
          }}
        />
        {/* UX-G2: xodim filtri — qidiruv yozish o'rniga tanlash */}
        <Select value={userFilter} onValueChange={setUserFilter}>
          <SelectTrigger className="h-9 w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Barcha xodimlar</SelectItem>
            {usersQuery.data?.map((u) => (
              <SelectItem key={u.id} value={String(u.id)}>
                {u.full_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {/* Xodim umuman bosmagan kun uchun — o'sha kun jadvalda qator
            sifatida umuman yo'q, ya'ni tuzatish uchun bosadigan joy yo'q. */}
        {canEdit && (
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => setAdding(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Yozuv qo'shish
          </Button>
        )}
      </div>
      <DataTable
        columns={rowColumns}
        data={listQuery.data}
        isLoading={listQuery.isLoading}
        error={listQuery.error ? listQuery.error.message : null}
        onRetry={() => listQuery.refetch()}
        searchPlaceholder="Xodim bo'yicha qidirish..."
        empty={{ text: "Tanlangan oraliqda yozuv yo'q" }}
      />

      {canEdit && (
        <EditAttendanceDialog
          open={editing !== null || adding}
          row={editing}
          onClose={() => {
            setEditing(null);
            setAdding(false);
          }}
          silent={isDasturchi}
        />
      )}

      {isDasturchi && (
        <ConfirmDialog
          open={deleting !== null}
          onOpenChange={(open) => !open && setDeleting(null)}
          title={
            deleting
              ? `${deleting.user_full_name} — ${format(new Date(deleting.date), "dd.MM.yyyy")} yozuvini o'chirasizmi?`
              : ""
          }
          description="Bu amalni qaytarib bo'lmaydi. Faqat sinov/tozalash uchun (dasturchi huquqi) — xodim shu kun uchun qaytadan Keldim/Ketdim qila oladi."
          confirmLabel="O'chirish"
          destructive
          loading={deleteAttendance.isPending}
          onConfirm={() => {
            if (!deleting) return;
            deleteAttendance.mutate(deleting.id, {
              onSuccess: () => {
                toast.success("Davomat yozuvi o'chirildi.");
                setDeleting(null);
              },
            });
          }}
        />
      )}
    </div>
  );
}
