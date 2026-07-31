import { useState } from "react";
import { format } from "date-fns";
import { CalendarX } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type ExcusedDay } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useDecideExcusedDay,
  useExcusedDays,
  useRecordExcusedDayForUser,
  useUsers,
} from "@/lib/queries";

// decide_excused_day bilan bir xil qamrov — ROP xodim nomidan sababli kun
// belgilay olmaydi (faqat hr/boss/dasturchi).
const MARK_EXCUSED_ROLES = ["hr", "boss", "dasturchi"];

/** Ustunlar funksiyadan quriladi: qaror tugmalari mutatsiyaga muhtoj. */
function buildColumns(
  canDecide: boolean,
  onDecide: (itemId: number, decision: "approved" | "rejected") => void,
  isPending: boolean
): ColumnDef<ExcusedDay>[] {
  const base: ColumnDef<ExcusedDay>[] = [
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
  if (!canDecide) return base;

  base.push({
    id: "actions",
    header: "",
    enableSorting: false,
    cell: ({ row }) => {
      // Faqat KUTILAYOTGAN so'rovga qaror chiqariladi. Allaqachon hal
      // qilinganini backend ham rad etadi (idempotentlik) — tugmani
      // ko'rsatmaslik shunchaki foydalanuvchini urinishdan qutqaradi.
      if (row.original.status !== "pending") return null;
      return (
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={isPending}
            onClick={() => onDecide(row.original.id, "approved")}
          >
            Tasdiqlash
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-rose-600 hover:text-rose-700"
            disabled={isPending}
            onClick={() => onDecide(row.original.id, "rejected")}
          >
            Rad etish
          </Button>
        </div>
      );
    },
  });
  return base;
}

function MarkExcusedForm() {
  const usersQuery = useUsers("employee");
  const record = useRecordExcusedDayForUser();

  const [userId, setUserId] = useState<string>("");
  const [day, setDay] = useState(format(new Date(), "yyyy-MM-dd"));
  const [reason, setReason] = useState("");

  function onSubmit() {
    if (!userId) {
      toast.error("Xodimni tanlang");
      return;
    }
    if (!reason.trim()) {
      toast.error("Sababni kiriting");
      return;
    }
    record.mutate(
      { user_id: Number(userId), date: day, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success("Sababli kun belgilandi");
          setReason("");
        },
      }
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Xodim uchun sababli kun belgilash</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Bu yerda kiritilgan yozuv SO'ROV emas — darhol tasdiqlangan holda
            yoziladi (kirituvchi allaqachon qaror chiqarishga vakolatli). */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="mb-1 text-xs font-medium text-slate-500">Xodim</div>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger className="min-w-[220px]">
                <SelectValue placeholder="Xodim tanlang" />
              </SelectTrigger>
              <SelectContent>
                {usersQuery.data?.map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-slate-500">Sana</div>
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-40" />
          </div>
          <div className="min-w-[240px] flex-1">
            <div className="mb-1 text-xs font-medium text-slate-500">Sabab</div>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Masalan: kasallik, oilaviy holat"
            />
          </div>
          <Button onClick={onSubmit} disabled={record.isPending}>
            Belgilash
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ExcusedDays() {
  const { user } = useAuth();
  const [statusFilter, setStatusFilter] = useState("all");
  const query = useExcusedDays(statusFilter === "all" ? undefined : statusFilter);
  const canMark = MARK_EXCUSED_ROLES.includes(user?.role ?? "");
  const decide = useDecideExcusedDay();

  // Qaror chiqarish qamrovi belgilash bilan bir xil (hr/boss/dasturchi) —
  // backend ham aynan shu ro'yxatni tekshiradi (excused_days.py: DECIDE_ROLES).
  const columns = buildColumns(
    canMark,
    (itemId, decision) =>
      decide.mutate(
        { itemId, decision },
        {
          onSuccess: () =>
            toast.success(decision === "approved" ? "Tasdiqlandi" : "Rad etildi"),
        }
      ),
    decide.isPending
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Sababli kunlar"
        description="Kutilayotgan so'rovni shu yerdan yoki Telegram bot orqali tasdiqlash mumkin."
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

      {canMark && <MarkExcusedForm />}

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
