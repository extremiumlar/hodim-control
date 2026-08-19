/**
 * «Sozlanmagan modullar» bloki — bosh sahifada (TZ 2.7 / S-08).
 *
 * NEGA KERAK: bir necha modulning MEXANIZMI tayyor, lekin qiymat
 * kiritilmagani uchun jim turadi va natija doim 0 chiqadi. Bu holat hech
 * qayerda ko'rinmasdi — «nega KPI bonusi nol?» degan savol qayta-qayta
 * qaytardi. Jonli isbot (2026-08-17): `kpi_rates` jadvali butunlay bo'sh
 * edi va buni topguncha butun oylik tekshiruvi kerak bo'ldi.
 *
 * Hammasi sozlangan bo'lsa blok UMUMAN ko'rinmaydi — «hammasi joyida»
 * degan doimiy yashil quti e'tiborni o'g'irlaydi, keyin esa haqiqiy
 * ogohlantirish ham ko'zga tashlanmay qoladi.
 */
import { AlertTriangle, ArrowRight, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";

import { useSetupStatus } from "@/lib/queries";

export default function SetupStatusCard({ enabled }: { enabled: boolean }) {
  const { data = [] } = useSetupStatus(enabled);
  const pending = data.filter((i) => !i.ready);

  if (!pending.length) return null;

  const critical = pending.filter((i) => i.critical);

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium text-amber-900">
        <Settings2 className="h-4 w-4 shrink-0" />
        Sozlanmagan modullar
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs">{pending.length}</span>
      </div>
      <p className="mb-3 text-xs text-amber-800">
        Bu modullarning mexanizmi tayyor, lekin qiymat kiritilmagani uchun ular{" "}
        <b>jim turibdi</b> — natija doim 0 chiqadi.
        {critical.length > 0 && (
          <>
            {" "}
            Qizil belgilanganlarsiz <b>pul noto'g'ri hisoblanadi</b>.
          </>
        )}
      </p>
      <ul className="space-y-1.5">
        {pending.map((item) => (
          <li key={item.key}>
            <Link
              to={item.link}
              className={`flex items-start gap-2 rounded-lg border bg-white px-3 py-2 text-xs transition hover:border-slate-400 ${
                item.critical ? "border-rose-200" : "border-slate-200"
              }`}
            >
              {item.critical && (
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-600" />
              )}
              <span className="min-w-0 flex-1">
                <span className={item.critical ? "font-medium text-rose-700" : "font-medium"}>
                  {item.label}
                </span>
                <span className="block text-slate-600">{item.missing}</span>
              </span>
              <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
