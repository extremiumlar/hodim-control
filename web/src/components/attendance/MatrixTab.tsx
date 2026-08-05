/**
 * «Oylik jadval» tabi (UX-B bosqichida — tayyorlik + yozuvlar; UX-C bosqichida
 * tepaga oylik matritsa qo'shiladi).
 */
import { format, startOfMonth } from "date-fns";
import ReadinessSection from "@/components/attendance/ReadinessSection";
import RecordsSection from "@/components/attendance/RecordsSection";

export default function MatrixTab({
  canEdit,
  isDasturchi,
}: {
  active: boolean;
  canEdit: boolean;
  isDasturchi: boolean;
}) {
  const monthFrom = format(startOfMonth(new Date()), "yyyy-MM-dd");
  const monthTo = format(new Date(), "yyyy-MM-dd");

  return (
    <div className="space-y-4">
      <ReadinessSection dateFrom={monthFrom} dateTo={monthTo} />
      <RecordsSection canEdit={canEdit} isDasturchi={isDasturchi} />
    </div>
  );
}
