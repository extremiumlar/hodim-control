/**
 * «Sozlamalar» tabi — davomat bilan bog'liq admin amallari (UX-B):
 *   - Joylashuv ruxsati (LocationExemptCard — mavjud komponent);
 *   - Yuzni qayta ro'yxatdan o'tkazish so'rovlari (UX-A6 — endi WEBDAN hal
 *     qilinadi; ilgari faqat botda edi, HR xabarni o'tkazib yuborsa so'rov
 *     osilib qolardi).
 */
import { format } from "date-fns";
import { ScanFace } from "lucide-react";
import { toast } from "sonner";
import LocationExemptCard from "@/components/LocationExemptCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDecideFaceReregWeb, useFaceReregList } from "@/lib/queries";

function FaceReregCard({ active }: { active: boolean }) {
  const query = useFaceReregList("pending", active);
  const decide = useDecideFaceReregWeb();
  const rows = query.data ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ScanFace className="h-4 w-4 text-indigo-500" />
          Yuzni qayta ro'yxatdan o'tkazish so'rovlari
          {rows.length > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
              {rows.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-xs text-slate-500">
          Xodim yuzini qayta yozdirmoqchi bo'lsa, avval siz tasdiqlashingiz kerak
          (birovning yuzi birovning hisobiga qo'yilmasligi uchun). Tasdiqlashda tizim
          yangi yuz boshqa xodimnikiga o'xshab ketmasligini ham o'zi tekshiradi.
        </p>
        {query.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : rows.length === 0 ? (
          <div className="text-sm text-slate-400">Kutilayotgan so'rov yo'q.</div>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3"
              >
                <div className="text-sm">
                  <span className="font-medium">{r.user_full_name}</span>
                  <span className="ml-2 text-xs text-slate-400">
                    {format(new Date(r.created_at), "dd.MM.yyyy HH:mm")}
                  </span>
                  <StatusBadge kind="request" status={r.status} className="ml-2" />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={decide.isPending}
                    onClick={() =>
                      decide.mutate(
                        { itemId: r.id, decision: "approved" },
                        { onSuccess: () => toast.success(`${r.user_full_name} — yuz tasdiqlandi`) }
                      )
                    }
                  >
                    Tasdiqlash
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-rose-600 hover:text-rose-700"
                    disabled={decide.isPending}
                    onClick={() =>
                      decide.mutate(
                        { itemId: r.id, decision: "rejected" },
                        { onSuccess: () => toast.success(`${r.user_full_name} — so'rov rad etildi`) }
                      )
                    }
                  >
                    Rad etish
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsTab({
  active,
  canManageLocationExempt,
}: {
  active: boolean;
  canManageLocationExempt: boolean;
}) {
  return (
    <div className="space-y-4">
      <FaceReregCard active={active} />
      {canManageLocationExempt && <LocationExemptCard />}
    </div>
  );
}
