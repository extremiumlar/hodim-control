/**
 * Xodim kabineti — «Mening oyligim».
 *
 * Botdagi «💵 Mening oyligim» bilan bir xil ma'lumot va bir xil qatorlar:
 * bot `/payroll/my/{tg}` ni, bu sahifa `/payroll/me/payslip` ni chaqiradi,
 * ikkalasi ham `_latest_payslip_for_user(db, user)` ga boradi.
 *
 * Bot `_payslip_text` da qatorlarni FAQAT nol bo'lmaganda ko'rsatadi
 * (`if data.get("overtime_amount")`) — shu qoida bu yerda ham saqlangan,
 * aks holda xodim botda 4 qator, web'da 6 qator ko'rib chalkashardi.
 *
 * Faqat TASDIQLANGAN varaqa ko'rsatiladi — `draft`/`calculated` hali
 * o'zgarishi mumkin (backend shunday filtrlaydi).
 */
import { CheckCircle2 } from "lucide-react";

import LateStatusCard from "@/components/LateStatusCard";
import MyAdvancesCard from "@/components/MyAdvancesCard";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyPayslip } from "@/lib/queries";
import { cn, fmtMoney } from "@/lib/utils";

/** Bir qator: nomi + summa. `sign` — botdagi "+" / "−" belgilari. */
function Row({
  label,
  amount,
  sign,
}: {
  label: string;
  amount: number;
  sign?: "+" | "−";
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-4 py-3">
      <span className="text-sm text-slate-600">{label}</span>
      <span
        className={cn(
          "shrink-0 text-sm font-semibold tabular-nums",
          sign === "+" && "text-emerald-600",
          sign === "−" && "text-rose-600"
        )}
      >
        {sign}
        {fmtMoney(amount)}
      </span>
    </div>
  );
}

export default function MyPayroll() {
  const { data, isLoading, isError } = useMyPayslip();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Oylik ma'lumotini yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  // Botdagi bilan bir xil matn (bot/handlers/payroll.py: show_my_payslip)
  if (!data.calculated) {
    return (
      <div className="space-y-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
          <p className="text-sm text-slate-600">
            Hali tasdiqlangan oyligingiz yo'q. Oy oxirida HR/Boshliq hisoblab
            tasdiqlagach shu yerda ko'rinadi.
          </p>
        </div>
        {/* Varaqa hali yo'q bo'lsa ham avans ko'rinishi SHART: xodim
            joriy oyda avans so'ragan bo'lishi mumkin va uning holati
            aynan shu yerda kerak. */}
        <MyAdvancesCard />
        <LateStatusCard />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-4 py-3">
          <div className="text-xs uppercase tracking-wide text-slate-400">Davr</div>
          <div className="text-base font-semibold">{data.period} oyi</div>
        </div>

        <Row label="Asosiy oylik" amount={data.base_amount ?? 0} />
        {/* Nol bo'lmaganda ko'rsatiladi — botdagi qoida bilan bir xil */}
        {/* Manfiy bo'lishi mumkin (2026-08-15): oy bo'yicha kam ishlangan
            vaqt ortiqchasidan ko'p chiqsa — u holda bu USHLANMA. */}
        {!!data.overtime_amount &&
          (data.overtime_amount > 0 ? (
            <Row label="Qo'shimcha ish" amount={data.overtime_amount} sign="+" />
          ) : (
            <Row
              label="Kam ishlangan vaqt"
              amount={Math.abs(data.overtime_amount)}
              sign="−"
            />
          ))}
        {!!data.bonus_amount && <Row label="Bonus" amount={data.bonus_amount} sign="+" />}
        {!!data.fine_amount && (
          <Row label="Kechikish ushlanmasi" amount={data.fine_amount} sign="−" />
        )}
        {!!data.absent_deduction && (
          <Row label="Kelmagan kun ushlanmasi" amount={data.absent_deduction} sign="−" />
        )}
        {/* Avans va qo'lda kiritilgan qo'shimcha/ushlanmalar (2026-08-13).
            Bular ILGARI KO'RSATILMASDI — «Jami» yuqoridagi qatorlar
            yig'indisiga to'g'ri kelmasdi va xodim farqni tushuntira olmasdi. */}
        {!!data.adjustments_plus && (
          <Row label="Qo'shimcha" amount={data.adjustments_plus} sign="+" />
        )}
        {!!data.advance_amount && (
          <Row label="Avans (olingan)" amount={data.advance_amount} sign="−" />
        )}
        {!!data.adjustments_minus && (
          <Row label="Ushlanma" amount={data.adjustments_minus} sign="−" />
        )}

        <div className="flex items-baseline justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-4">
          <span className="text-sm font-semibold">Jami</span>
          <span className="shrink-0 text-lg font-bold tabular-nums">
            {fmtMoney(data.net ?? 0)}
          </span>
        </div>
      </div>

      {data.approved_at && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Tasdiqlangan: {data.approved_at.slice(0, 10)}
        </p>
      )}

      {/* TZ 5.6: xodim o'z avansini KABINETDA ham ko'rsin —
          payslipdagi bitta qator joriy oydagi hal qilinmagan
          so'rovni ko'rsatmaydi. */}
      <MyAdvancesCard />

      <LateStatusCard />
    </div>
  );
}
