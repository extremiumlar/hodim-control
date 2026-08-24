/**
 * Oddiy progress chizig'i (TZ 3.2 / S-47).
 *
 * ⚠️ Radix `Progress` komponenti QO'SHILMADI: loyihaning UI to'plami
 * ataylab kichik va bitta chiziq uchun yangi bog'liqlik olib kelish
 * bundle hajmini oshirardi. Bu yerda kerak bo'lgani — ikkita `div`.
 */
export default function ProgressBar({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  //  Qiymat 0..100 oralig'iga qisiladi: server xato bersa ham
  //  chiziq konteynerdan chiqib ketmasin.
  const foiz = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div
      className={`h-2 w-full overflow-hidden rounded-full bg-slate-200 ${className}`}
      role="progressbar"
      aria-valuenow={foiz}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-slate-800 transition-all"
        style={{ width: `${foiz}%` }}
      />
    </div>
  );
}
