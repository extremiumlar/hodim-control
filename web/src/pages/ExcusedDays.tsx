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
  useDecideExplanation,
  useExcusedDays,
  useExplanations,
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
  // UX2-qoldiq #3: 40 kishilik oddiy Select o'rniga QIDIRUVLI tanlagich —
  // HR ism yozib darhol topadi (skroll qilib o'tirmaydi).
  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selectedName =
    usersQuery.data?.find((u) => String(u.id) === userId)?.full_name ?? "";
  const filteredUsers = (usersQuery.data ?? []).filter((u) =>
    u.full_name.toLowerCase().includes(search.trim().toLowerCase())
  );

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
          <div className="relative">
            <div className="mb-1 text-xs font-medium text-slate-500">Xodim</div>
            <Input
              className="min-w-[220px]"
              placeholder="Xodim ismini yozing..."
              value={pickerOpen ? search : selectedName}
              onFocus={() => {
                setPickerOpen(true);
                setSearch("");
              }}
              onBlur={() => setTimeout(() => setPickerOpen(false), 150)}
              onChange={(e) => setSearch(e.target.value)}
            />
            {pickerOpen && (
              <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg">
                {filteredUsers.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    className="block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50"
                    // onMouseDown — blur'dan OLDIN ishlashi uchun (click kech qolardi)
                    onMouseDown={() => {
                      setUserId(String(u.id));
                      setPickerOpen(false);
                    }}
                  >
                    {u.full_name.trim()}
                  </button>
                ))}
                {filteredUsers.length === 0 && (
                  <div className="px-3 py-1.5 text-sm text-slate-400">Topilmadi</div>
                )}
              </div>
            )}
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

      {canMark && <ExplanationsSection />}
    </div>
  );
}

/**
 * Tushuntirish xatlari — sababsiz kelmagan kun uchun.
 *
 * Oqim: kechqurun tizim sababsiz `absent` kunni topadi -> xodimga botdan
 * «Nega kelmadingiz?» -> xodim javob yozadi -> HR shu yerda qaror qiladi.
 *
 * ⚠️ «Qabul qilish» — MAVJUD sababli kun mexanizmini ishga soladi
 * (`ExcusedDay` yaratiladi, davomat qayta hisoblanadi va jarima o'z-o'zidan
 * tushadi). Yangi jarima yo'li YO'Q.
 */
function ExplanationsSection() {
  // Default «answered» — HR uchun eng muhimi: javob kelgan, qaror kutilyapti.
  const [filter, setFilter] = useState("answered");
  const query = useExplanations(filter === "all" ? undefined : filter);
  const decide = useDecideExplanation();

  const rows = query.data ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">Tushuntirish xatlari</CardTitle>
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="answered">Javob kelgan (qaror kutilyapti)</SelectItem>
              <SelectItem value="pending">Javob kutilmoqda</SelectItem>
              <SelectItem value="accepted">Qabul qilingan</SelectItem>
              <SelectItem value="rejected">Rad etilgan</SelectItem>
              <SelectItem value="all">Barchasi</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-xs text-slate-500">
          Sababsiz kelmagan kun uchun tizim xodimdan tushuntirish so'raydi.{" "}
          <b>«Sababli deb qabul qilish»</b> — o'sha kun sababli kunga o'tadi va jarima
          tushadi. <b>«Rad etish»</b> — jarima o'z kuchida qoladi.
        </p>

        {query.isLoading ? (
          <div className="text-sm text-slate-400">Yuklanmoqda...</div>
        ) : rows.length === 0 ? (
          <div className="text-sm text-slate-400">Bu holatda xat yo'q.</div>
        ) : (
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-medium">
                    {r.user_full_name ?? `#${r.user_id}`}{" "}
                    <span className="text-slate-400">
                      — {format(new Date(r.date), "dd.MM.yyyy")}
                    </span>
                  </div>
                  <StatusBadge kind="request" status={r.status} />
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">
                  {r.answer_text ?? (
                    <span className="text-slate-400">Xodim hali javob yozmagan.</span>
                  )}
                </p>
                {r.decision_note && (
                  <p className="mt-1 text-xs text-slate-400">Izoh: {r.decision_note}</p>
                )}
                {/* Qaror faqat javob kelgan xatga — javobsiz xatni hal qilish
                    xodimga o'zini oqlash imkonini bermay yopib qo'yardi. */}
                {r.status === "answered" && (
                  <div className="mt-2 flex gap-2">
                    <Button
                      size="sm"
                      disabled={decide.isPending}
                      onClick={() =>
                        decide.mutate(
                          { reqId: r.id, accept: true },
                          { onSuccess: () => toast.success("Sababli deb qabul qilindi") }
                        )
                      }
                    >
                      Sababli deb qabul qilish
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={decide.isPending}
                      onClick={() =>
                        decide.mutate(
                          { reqId: r.id, accept: false },
                          { onSuccess: () => toast.success("Rad etildi — jarima qoladi") }
                        )
                      }
                    >
                      Rad etish
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
