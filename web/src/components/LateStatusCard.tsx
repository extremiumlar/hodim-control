/**
 * Joriy oydagi kechikish limiti holati — 1.5-band (Shaffoflik): xodim jarima
 * boshlanishidan OLDIN ogohlantiriladi. Qoida umuman sozlanmagan bo'lsa
 * (free_limit_minutes=null) hech narsa ko'rsatilmaydi.
 *
 * Ilgari CheckIn.tsx ichida edi. Xodim kabinetidagi «Mening oyligim» sahifasi
 * ham shu kartani ko'rsatadi (kechikish jarimasi oylikka bevosita ta'sir
 * qiladi — botda ham oylik xabari ostida «🕐 Kechikishlarim» tugmasi bor),
 * shuning uchun umumiy komponentga chiqarildi — ikki nusxa bo'lib
 * ketmasligi uchun.
 */
import { useMyLateStatus } from "@/lib/queries";

export default function LateStatusCard() {
  const { data } = useMyLateStatus();
  if (!data || data.free_limit_minutes == null) return null;

  const overLimit = (data.remaining_minutes ?? 0) <= 0;
  return (
    <div
      className={`rounded-xl border p-4 text-sm ${
        overLimit ? "border-rose-200 bg-rose-50 text-rose-800" : "border-slate-200 bg-white text-slate-700"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">Bu oy kechikish limiti</span>
        <span className="font-semibold">
          {data.used_minutes} / {data.free_limit_minutes} daq
        </span>
      </div>
      {overLimit ? (
        <p className="mt-1 text-xs">
          Limit tugagan — shu kundan keyingi har bir kechikkan kunga jarima yoziladi
          {data.fined_days_so_far > 0 && ` (bu oy allaqachon ${data.fined_days_so_far} kun jarimalandi)`}.
        </p>
      ) : (
        <p className="mt-1 text-xs text-slate-500">
          Yana {data.remaining_minutes} daqiqa bepul kechikish qoldi.
        </p>
      )}
    </div>
  );
}
