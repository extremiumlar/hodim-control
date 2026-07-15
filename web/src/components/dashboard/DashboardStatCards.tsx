import { CalendarCheck, Hourglass, LogIn, UserX } from "lucide-react";
import StatCard from "@/components/StatCard";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendanceDashboard } from "@/lib/queries";

/** Bosh sahifa tepasidagi bugungi davomat ko'rsatkichlari. */
export default function DashboardStatCards() {
  const query = useAttendanceDashboard();
  const s = query.data?.summary;

  if (query.isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[86px] rounded-xl" />
        ))}
      </div>
    );
  }
  if (!s) return null;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard label="Bugun keldi" value={s.checked_in_today} icon={LogIn} />
      <StatCard label="Hozir ofisda" value={s.present_now} icon={CalendarCheck} />
      <StatCard label="Kechikdi" value={s.late_today} icon={Hourglass} warn={s.late_today > 0} />
      <StatCard label="Kelmagan" value={s.not_checked_in} icon={UserX} warn={s.not_checked_in > 0} />
    </div>
  );
}
