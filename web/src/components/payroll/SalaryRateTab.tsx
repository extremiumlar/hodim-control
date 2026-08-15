/**
 * Oylik stavkalar — kiritish, tarix va TAHRIRLASH.
 *
 * NEGA BU YERDA (2026-08-13, egasining talabi): bu bo'lim ilgari
 * `Sozlamalar` sahifasida turardi. Lekin oylik stavka — sozlama emas, u
 * xodimning puli; HR uni `Ish haqi` sahifasida hisob-kitob bilan yonma-yon
 * ko'rishi kerak. `Sozlamalar`da faqat qoidalar qoldi (jarima, KPI stavkasi,
 * qo'shimcha ish profili).
 *
 * TAHRIRLASH NEGA QO'SHILDI: `POST /rates` bir sanaga ikkinchi stavka
 * kiritilsa «avval eskisini o'zgartiring» deb rad etardi, lekin
 * o'zgartiradigan tugma HECH QAYERDA yo'q edi — faqat Dasturchining
 * `/admin/records` sahifasida. Ya'ni xato summa kiritilsa, HR uni tuzata
 * olmasdi.
 *
 * MUHIM: tahrir allaqachon hisoblangan payslip'ni O'ZGARTIRMAYDI — u
 * saqlangan summalar bilan turadi. Yangi summa faqat davr qayta
 * hisoblanganda kuchga kiradi.
 */
import { useState, type FormEvent } from "react";
import { format, startOfMonth } from "date-fns";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";

import DataTable from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type ReadinessIssue, type SalaryRate } from "@/lib/api";
import {
  useCreateSalaryRate,
  usePayrollPreflight,
  useSalaryRates,
  useUpdateSalaryRate,
  useUsers,
} from "@/lib/queries";
import { fmtMoney } from "@/lib/utils";

const BASIS_LABELS: Record<string, string> = {
  monthly: "Oylik",
  daily: "Kunlik",
  hourly: "Soatlik",
};

/** Stavkani tahrirlash oynasi. Faqat O'ZGARGAN maydonlar yuboriladi (PATCH). */
function EditRateDialog({ rate, onClose }: { rate: SalaryRate | null; onClose: () => void }) {
  const update = useUpdateSalaryRate();
  const [amount, setAmount] = useState("");
  const [payBasis, setPayBasis] = useState("monthly");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [note, setNote] = useState("");

  // Oyna ochilganda joriy qiymatlarni yuklaymiz. `key` bilan qayta
  // yaratilgani uchun bu bir marta ishlaydi.
  const [loadedId, setLoadedId] = useState<number | null>(null);
  if (rate && loadedId !== rate.id) {
    setLoadedId(rate.id);
    setAmount(String(rate.amount));
    setPayBasis(rate.pay_basis);
    setEffectiveFrom(rate.effective_from.slice(0, 10));
    setNote(rate.note ?? "");
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!rate) return;
    const n = Number(amount);
    if (!n || n <= 0) {
      toast.error("Summa musbat son bo'lishi kerak");
      return;
    }
    // Faqat haqiqatan o'zgargan maydonlarni yuboramiz — auditda «nima
    // o'zgardi» aniq ko'rinsin va tegilmagan maydon bekorga yozilmasin.
    const data: { amount?: number; pay_basis?: string; effective_from?: string; note?: string | null } = {};
    if (n !== rate.amount) data.amount = n;
    if (payBasis !== rate.pay_basis) data.pay_basis = payBasis;
    if (effectiveFrom !== rate.effective_from.slice(0, 10)) data.effective_from = effectiveFrom;
    if ((note || null) !== rate.note) data.note = note || null;

    if (Object.keys(data).length === 0) {
      toast.info("Hech narsa o'zgarmadi");
      onClose();
      return;
    }
    update.mutate(
      { rateId: rate.id, data },
      {
        onSuccess: () => {
          toast.success("Stavka o'zgartirildi");
          setLoadedId(null);
          onClose();
        },
      }
    );
  };

  return (
    <Dialog
      open={rate !== null}
      onOpenChange={(open) => {
        if (!open) {
          setLoadedId(null);
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Stavkani o'zgartirish</DialogTitle>
          <DialogDescription>
            Bu o'zgarish allaqachon hisoblangan oyliklarni o'zgartirmaydi — yangi summa davr qayta
            hisoblanganda kuchga kiradi.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label htmlFor="er-amount">Summa (so'm)</Label>
            <Input
              id="er-amount"
              type="number"
              min={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>
          <div>
            <Label>Hisob asosi</Label>
            <Select value={payBasis} onValueChange={setPayBasis}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="monthly">Oylik (qat'iy)</SelectItem>
                <SelectItem value="daily">Kunbay</SelectItem>
                <SelectItem value="hourly">Soatbay</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="er-date">Kuchga kirish sanasi</Label>
            <Input
              id="er-date"
              type="date"
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="er-note">Izoh (ixtiyoriy)</Label>
            <Input id="er-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Bekor qilish
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saqlanmoqda..." : "Saqlash"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function SalaryRateTab({ period }: { period: string }) {
  const usersQuery = useUsers();
  const [userId, setUserId] = useState<number | null>(null);
  const ratesQuery = useSalaryRates(userId ?? 0, userId !== null);
  const createRate = useCreateSalaryRate();
  const [editing, setEditing] = useState<SalaryRate | null>(null);

  // Kimda stavka YO'Q — `preflight` allaqachon shuni hisoblaydi (u yerda
  // qamrov backend bilan bir xil: davomat kuzatiladigan faol xodimlar).
  //
  // ⚠️ `period` PROP ORQALI keladi, `currentMonthKey()` EMAS (§4.2): ilgari bu
  // tab doim joriy oyni so'rardi, «Hisob-kitob» tabi esa HR tanlagan oyni.
  // Ikki xil kalit — react-query keshi bo'linib, og'ir `collect_readiness`
  // bitta sahifada IKKI marta ishlardi. Endi ikkalasi bir xil kalitni ishlatadi.
  const preflightQuery = usePayrollPreflight(period);
  const missingRate = preflightQuery.data?.no_salary_rate ?? [];

  const [amount, setAmount] = useState("");
  const [payBasis, setPayBasis] = useState("monthly");
  // Default — JORIY OY BOSHI, bugungi kun EMAS.
  //
  // NEGA (§5.2): `monthly` stavkada oylik PRORATA qilinadi — birinchi
  // stavkaning `effective_from` sanasidan boshlab. Default bugun bo'lsa,
  // HR 14-avgustda stavka kiritganda avgust oyligi ~13/26 ulushga bo'linib,
  // xodim yarim oylik oladi. Oy boshi esa to'liq oylik beradi.
  const [effectiveFrom, setEffectiveFrom] = useState(format(startOfMonth(new Date()), "yyyy-MM-dd"));
  const [note, setNote] = useState("");
  // Oy boshidan keyingi sana — prorata ogohlantirishi (jim qolmasin)
  const rateLateStart = effectiveFrom > format(startOfMonth(new Date()), "yyyy-MM-dd");

  const rateColumns: ColumnDef<SalaryRate>[] = [
    {
      accessorKey: "effective_from",
      header: "Kuchga kirgan",
      cell: ({ row }) => format(new Date(row.original.effective_from), "dd.MM.yyyy"),
    },
    { accessorKey: "amount", header: "Summa", cell: ({ row }) => fmtMoney(row.original.amount) },
    {
      accessorKey: "pay_basis",
      header: "Asos",
      cell: ({ row }) => BASIS_LABELS[row.original.pay_basis] ?? row.original.pay_basis,
    },
    { accessorKey: "note", header: "Izoh", cell: ({ row }) => row.original.note ?? "—" },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          aria-label="Stavkani o'zgartirish"
          onClick={() => setEditing(row.original)}
        >
          <Pencil className="h-4 w-4" />
        </Button>
      ),
    },
  ];

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
    createRate.mutate(
      { user_id: userId, amount: n, pay_basis: payBasis, effective_from: effectiveFrom, note: note || null },
      {
        onSuccess: () => {
          const nomi = (usersQuery.data ?? []).find((u) => u.id === userId)?.full_name ?? "";
          toast.success(nomi ? `${nomi} — stavka qo'shildi` : "Stavka qo'shildi");
          setAmount("");
          setNote("");
          // Xodim tanlovi ham TOZALANADI. Ilgari tanlangan xodim qolib
          // ketardi va HR ketma-ket bir necha kishiga stavka kiritayotganda
          // xodimni almashtirishni unutib, AYNI sana uchun ikkinchi marta
          // yuborardi -> 400 «Bu sanaga allaqachon stavka kiritilgan».
          setUserId(null);
        },
      }
    );
  };

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <Card className="h-fit md:col-span-1">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yangi stavka</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Stavkasi hali yo'q xodimlar. Ularga oylik ham, jarima ham
              hisoblanmaydi — ya'ni jarima qoidasi qanday sozlansa ham natija
              0 bo'ladi. Shuning uchun ro'yxat ko'rinib tursin va bir bosishda
              tanlansin (HR ketma-ket bir necha kishiga kiritadi). */}
          {missingRate.length > 0 && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <div className="text-xs font-medium text-amber-900">
                Stavkasi yo'q — {missingRate.length} xodim
              </div>
              <p className="mt-0.5 text-xs text-amber-800">
                Ularga oylik ham, jarima ham hisoblanmaydi. Ismni bosing.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {missingRate.map((u: ReadinessIssue) => (
                  <button
                    key={u.user_id}
                    type="button"
                    onClick={() => setUserId(u.user_id)}
                    className={
                      "rounded-md border px-2 py-1 text-xs " +
                      (userId === u.user_id
                        ? "border-amber-500 bg-amber-100 font-medium text-amber-900"
                        : "border-amber-300 bg-white text-amber-900 hover:bg-amber-100")
                    }
                  >
                    {u.full_name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mb-4">
            <Label>Xodim</Label>
            <Select value={userId ? String(userId) : undefined} onValueChange={(v) => setUserId(Number(v))}>
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
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <Label htmlFor="sr-amount">Summa (so'm)</Label>
              <Input
                id="sr-amount"
                type="number"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
            <div>
              <Label>Hisob asosi</Label>
              <Select value={payBasis} onValueChange={setPayBasis}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Oylik (qat'iy)</SelectItem>
                  <SelectItem value="daily">Kunbay</SelectItem>
                  <SelectItem value="hourly">Soatbay</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="sr-date">Kuchga kirish sanasi</Label>
              <Input
                id="sr-date"
                type="date"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
                required
              />
              {rateLateStart ? (
                <p className="mt-1 text-xs text-amber-700">
                  ⚠️ Bu xodimning <b>shu oylik oyligi TO'LIQ bo'lmaydi</b> — oylik shu
                  sanadan boshlab proratalanadi. To'liq oylik uchun oy boshini tanlang.
                </p>
              ) : (
                <p className="mt-1 text-xs text-slate-500">
                  Odatda oy boshi qo'yiladi — shunda oylik to'liq hisoblanadi.
                </p>
              )}
            </div>
            <div>
              <Label htmlFor="sr-note">Izoh (ixtiyoriy)</Label>
              <Input id="sr-note" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <Button type="submit" disabled={createRate.isPending || !userId} className="w-full">
              {createRate.isPending ? "Saqlanmoqda..." : "Qo'shish"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="md:col-span-2">
        <h3 className="mb-2 font-semibold">Stavka tarixi</h3>
        {!userId ? (
          <p className="text-sm text-slate-500">Tarixni ko'rish uchun xodimni tanlang.</p>
        ) : (
          <DataTable
            columns={rateColumns}
            data={ratesQuery.data}
            isLoading={ratesQuery.isLoading}
            error={ratesQuery.error ? ratesQuery.error.message : null}
            onRetry={() => ratesQuery.refetch()}
            empty={{ text: "Bu xodim uchun hali stavka kiritilmagan." }}
          />
        )}
      </div>

      <EditRateDialog rate={editing} onClose={() => setEditing(null)} />
    </div>
  );
}
