/**
 * «Mening avanslarim» — xodim kabineti uchun (Avans TZ 5-bo'lim, 6-band).
 *
 * MUAMMO (TZ): «Xodim o'z avansini ko'radimi — noma'lum. Kabinetda va
 * botda ko'rinsin. Aks holda oylik kam chiqqanda savol tug'iladi.»
 *
 * Payslipdagi «Avans (olingan)» qatori YETARLI EMAS: u faqat oxirgi
 * TASDIQLANGAN varaqada ko'rinadi, ya'ni joriy oyda so'ralgan va hali
 * hal qilinmagan avans hech qayerda ko'rinmasdi. Bu kartochka joriy
 * oyni ko'rsatadi: har bir so'rov, holati, jami va QOLGAN CHEGARA.
 *
 * Botdagi «💵 Avanslarim» bilan bir xil ma'lumot — ikkalasi ham
 * `_my_advances()` ni chaqiradi, shuning uchun ikki joyda ikki xil
 * raqam chiqmaydi.
 */
import { Skeleton } from "@/components/ui/skeleton";
import StatusBadge from "@/components/StatusBadge";
import { useMyAdvances } from "@/lib/queries";
import { fmtMoney } from "@/lib/utils";

export default function MyAdvancesCard() {
  const { data, isLoading, error } = useMyAdvances();

  if (isLoading) return <Skeleton className="h-28 w-full rounded-xl" />;
  // Xatoda JIM qolamiz: bu yordamchi kartochka, oylik varaqasi emas —
  // uning xatosi butun sahifani buzmasligi kerak.
  if (error || !data) return null;

  const { rows, total, remaining_limit: remaining, limit_reason: reason } = data;
  // So'rov ham, chegara ham yo'q bo'lsa kartochka umuman ko'rsatilmaydi:
  // bo'sh blok sahifani faqat uzaytiradi.
  if (rows.length === 0 && remaining <= 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-baseline justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <span className="text-sm font-semibold">Mening avanslarim</span>
        <span className="text-xs text-slate-500">{data.period}</span>
      </div>

      {rows.length === 0 ? (
        <div className="px-4 py-3 text-sm text-slate-500">
          Bu oyda avans so'ramagansiz.
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {rows.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold tabular-nums">
                  {fmtMoney(r.amount)}
                </div>
                <div className="truncate text-xs text-slate-500">
                  {r.issued_on
                    ? `${r.issued_on.slice(0, 10)} da to'langan`
                    : r.reason}
                </div>
              </div>
              <StatusBadge kind="advance" status={r.status} />
            </div>
          ))}
          <div className="flex items-baseline justify-between gap-3 bg-slate-50 px-4 py-3">
            <span className="text-sm text-slate-600">
              Jami <span className="text-xs text-slate-400">(rad etilganlarsiz)</span>
            </span>
            <span className="text-sm font-semibold tabular-nums">{fmtMoney(total)}</span>
          </div>
        </div>
      )}

      {/* Qolgan chegara — «nega ko'proq so'ray olmayapman?» degan
          savolga oldindan javob. 0 bo'lsa SABABI ko'rsatiladi. */}
      <div className="border-t border-slate-200 px-4 py-3 text-sm">
        {remaining > 0 ? (
          <span className="text-slate-600">
            Yana <b className="text-emerald-700">{fmtMoney(remaining)}</b> gacha avans
            so'rashingiz mumkin.
          </span>
        ) : (
          <span className="text-slate-500">
            Hozircha yangi avans so'rab bo'lmaydi{reason ? ` (${reason})` : ""}.
          </span>
        )}
      </div>
    </div>
  );
}
