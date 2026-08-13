/**
 * Avans — oy o'rtasida qo'lga berilgan pul, oy oxirida oylikdan ayiriladi.
 *
 * NEGA KERAK (2026-08-13, egasining talabi): backendda model bor edi
 * (`PayrollAdjustment`, `kind='minus'`), lekin web panelda HECH QANDAY oyna
 * yo'q edi va ro'yxat qaytaradigan endpoint ham yo'q edi — ya'ni avansni
 * amalda kiritib bo'lmasdi.
 *
 * OQIM (egasining qarori): HR kiritadi -> `pending` (oylikka KIRMAYDI) ->
 * Boshliq tasdiqlaydi -> oylikdan ayiriladi va xodimga xabar boradi.
 * Tasdiqlanmagan avans oylikni O'ZGARTIRMAYDI — bu ataylab: HR bir o'zi
 * pul harakatini yakunlab qo'ymasin (oylik tasdig'i bilan bir xil ruh).
 */
import { useState, type FormEvent } from "react";
import { format } from "date-fns";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";

import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { MonthPicker, currentMonthKey } from "@/components/PeriodPicker";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type PayrollAdjustment } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCreateAdvance, useDecideAdvance, usePayrollAdjustments, useUsers } from "@/lib/queries";
import { fmtMoney } from "@/lib/utils";

export default function AdvanceTab() {
  const { user } = useAuth();
  // Tasdiqlash — FAQAT Boshliq/Dasturchi (backend ham 403 beradi). HR bu
  // tugmalarni umuman ko'rmaydi: ko'rinib turib bosilmaydigan tugma yomon UX.
  const canDecide = !!user && ["boss", "dasturchi"].includes(user.role);

  const [period, setPeriod] = useState(currentMonthKey());
  const usersQuery = useUsers();
  const listQuery = usePayrollAdjustments({ period, category: "advance" });
  const createAdvance = useCreateAdvance();
  const decide = useDecideAdvance();

  const [userId, setUserId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [issuedOn, setIssuedOn] = useState(format(new Date(), "yyyy-MM-dd"));
  const [reason, setReason] = useState("");

  const rows = listQuery.data ?? [];
  const pendingTotal = rows
    .filter((a) => a.status === "pending")
    .reduce((s, a) => s + a.amount, 0);
  const approvedTotal = rows
    .filter((a) => a.status === "approved")
    .reduce((s, a) => s + a.amount, 0);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!userId) {
      toast.error("Xodimni tanlang");
      return;
    }
    const n = Number(amount);
    if (!n || n <= 0) {
      toast.error("Summa musbat son bo'lishi kerak");
      return;
    }
    if (reason.trim().length < 3) {
      toast.error("Sababni yozing (kamida 3 harf)");
      return;
    }
    createAdvance.mutate(
      { user_id: userId, period, amount: n, issued_on: issuedOn, reason: reason.trim() },
      {
        onSuccess: () => {
          const nomi = (usersQuery.data ?? []).find((u) => u.id === userId)?.full_name ?? "";
          toast.success(
            nomi
              ? `${nomi} — avans kiritildi, Boshliq tasdig'i kutilmoqda`
              : "Avans kiritildi, Boshliq tasdig'i kutilmoqda"
          );
          setAmount("");
          setReason("");
          setUserId(null);
        },
      }
    );
  };

  const columns: ColumnDef<PayrollAdjustment>[] = [
    {
      accessorKey: "full_name",
      header: "Xodim",
      cell: ({ row }) => <b>{row.original.full_name ?? `#${row.original.user_id}`}</b>,
    },
    {
      accessorKey: "amount",
      header: "Summa",
      cell: ({ row }) => <span className="text-rose-600">−{fmtMoney(row.original.amount)}</span>,
    },
    {
      accessorKey: "issued_on",
      header: "Berilgan sana",
      cell: ({ row }) =>
        row.original.issued_on ? format(new Date(row.original.issued_on), "dd.MM.yyyy") : "—",
    },
    { accessorKey: "reason", header: "Sabab" },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="advance" status={row.original.status} />,
    },
    {
      id: "who",
      header: "Kim",
      cell: ({ row }) => (
        <div className="text-xs text-slate-500">
          <div>Kiritdi: {row.original.created_by_name ?? "—"}</div>
          {row.original.decided_by_name && <div>Qaror: {row.original.decided_by_name}</div>}
        </div>
      ),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => {
        if (!canDecide || row.original.status !== "pending") return null;
        return (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { adjustmentId: row.original.id, approve: true },
                  { onSuccess: () => toast.success("Avans tasdiqlandi — xodimga xabar berildi") }
                )
              }
            >
              <Check className="mr-1 h-4 w-4" />
              Tasdiqlash
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { adjustmentId: row.original.id, approve: false },
                  { onSuccess: () => toast.success("Avans rad etildi") }
                )
              }
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Avans"
        description="Oy o'rtasida berilgan pul. Boshliq tasdiqlagach oy oxirida oylikdan avtomatik ayiriladi."
      >
        <MonthPicker value={period} onChange={setPeriod} />
      </PageHeader>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="h-fit md:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Yangi avans</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <Label>Xodim</Label>
                <Select
                  value={userId ? String(userId) : undefined}
                  onValueChange={(v) => setUserId(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Tanlang" />
                  </SelectTrigger>
                  <SelectContent>
                    {(usersQuery.data ?? []).map((u) => (
                      <SelectItem key={u.id} value={String(u.id)}>
                        {u.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="adv-amount">Summa (so'm)</Label>
                <Input
                  id="adv-amount"
                  type="number"
                  min={1}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </div>
              <div>
                {/* Pul QO'LGA BERILGAN sana — bugungi sana emas: HR pulni
                    5-kuni berib, tizimga 12-kuni kiritishi mumkin. */}
                <Label htmlFor="adv-date">Berilgan sana</Label>
                <Input
                  id="adv-date"
                  type="date"
                  value={issuedOn}
                  onChange={(e) => setIssuedOn(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="adv-reason">Sabab</Label>
                <Input
                  id="adv-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Masalan: oilaviy ehtiyoj"
                  required
                />
              </div>
              <p className="text-xs text-slate-500">
                Avans <b>{period}</b> oyligidan ayiriladi. Kiritilgach Boshliqqa tasdiq uchun xabar
                boradi — tasdiqlangunicha oylikka kirmaydi.
              </p>
              <Button type="submit" disabled={createAdvance.isPending || !userId} className="w-full">
                {createAdvance.isPending ? "Saqlanmoqda..." : "Kiritish"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-3 md:col-span-2">
          {rows.length > 0 && (
            <div className="flex flex-wrap gap-3 text-sm">
              {pendingTotal > 0 && (
                <span className="rounded-lg bg-amber-50 px-3 py-1.5 text-amber-800">
                  Tasdiq kutilmoqda: <b>{fmtMoney(pendingTotal)}</b>
                </span>
              )}
              <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-slate-700">
                Tasdiqlangan (oylikdan ayiriladi): <b>{fmtMoney(approvedTotal)}</b>
              </span>
            </div>
          )}
          <DataTable
            columns={columns}
            data={listQuery.data}
            isLoading={listQuery.isLoading}
            error={listQuery.error ? listQuery.error.message : null}
            onRetry={() => listQuery.refetch()}
            searchPlaceholder="Xodim bo'yicha qidirish..."
            empty={{ text: "Bu oy uchun avans kiritilmagan." }}
          />
        </div>
      </div>
    </div>
  );
}
