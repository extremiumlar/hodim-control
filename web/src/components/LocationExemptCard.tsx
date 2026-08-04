/**
 * «Joylashuvsiz check-in» ruxsatini boshqarish.
 *
 * NEGA ALOHIDA KOMPONENT: ayni bir kartochka IKKI joyda turadi — Davomat
 * sahifasida (HR kundalik ishida shu yerda) va Dasturchi rejimida (qolgan
 * huquqlar bilan yonma-yon). Nusxalansa, ogohlantirish matni yoki tasdiq
 * dialogi bir joyda o'zgarib, ikkinchisida eski holicha qolardi — bu esa
 * GPS'ni chetlab o'tish huquqi bo'lgani uchun xavfli.
 */
import { useState } from "react";
import { toast } from "sonner";

import ReasonDialog from "@/components/ReasonDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocationExempt, useSetLocationExempt, useUsers } from "@/lib/queries";

export default function LocationExemptCard() {
  const usersQuery = useUsers();
  const exemptQuery = useLocationExempt();
  const setExempt = useSetLocationExempt();
  const [userId, setUserId] = useState<number | null>(null);
  const [granting, setGranting] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const selected = (usersQuery.data ?? []).find((u) => u.id === userId);

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Joylashuvsiz check-in («bez lokatsiya»)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-slate-500">
            Ruxsat berilgan xodim «Keldim»/«Ketdim»ni <b>istalgan joydan</b> bosa oladi —
            ofis radiusi va GPS aniqligi tekshirilmaydi. <b>Face ID baribir talab
            qilinadi</b>, aks holda check-in umuman himoyasiz qolardi. Doimiy ob'ektda
            yurmaydigan xodimlar uchun (mobilograf, kuryer, ko'chma sotuv).
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="loc-exempt-user">Xodim</Label>
            <Select
              value={userId ? String(userId) : undefined}
              onValueChange={(v) => setUserId(Number(v))}
            >
              <SelectTrigger id="loc-exempt-user">
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(usersQuery.data ?? []).map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.full_name} ({u.role}){u.skip_location_check ? " — ruxsati bor" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!userId}
              onClick={() => {
                setGranting(true);
                setConfirmOpen(true);
              }}
            >
              Ruxsat berish
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!userId}
              onClick={() => {
                setGranting(false);
                setConfirmOpen(true);
              }}
            >
              Olib qo'yish
            </Button>
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-1 text-xs font-medium text-slate-500">Hozir ruxsati borlar</div>
            {exemptQuery.isLoading ? (
              <div className="text-xs text-slate-400">Yuklanmoqda...</div>
            ) : (exemptQuery.data ?? []).length === 0 ? (
              <div className="text-xs text-slate-400">Hech kimga berilmagan.</div>
            ) : (
              <ul className="space-y-1 text-sm">
                {(exemptQuery.data ?? []).map((e) => (
                  <li key={e.id} className="flex items-center justify-between">
                    <span>
                      {e.full_name} <span className="text-xs text-slate-400">({e.role})</span>
                    </span>
                    {!e.is_active && <span className="text-xs text-rose-500">nofaol</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Sabab MAJBURIY: huquq berish/olishning o'zi audit jurnaliga tushadi
          (check-in tuzatishlaridan farqli). Shuning uchun ConfirmDialog emas. */}
      <ReasonDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={
          granting
            ? `${selected?.full_name ?? "Xodim"} — joylashuvsiz check-in ruxsati beriladi`
            : `${selected?.full_name ?? "Xodim"} — joylashuv ruxsati olinadi`
        }
        description={
          granting
            ? "Bundan keyin u «Keldim»/«Ketdim»ni istalgan joydan bosa oladi. Face ID bekor qilinmaydi — faqat GPS chetlab o'tiladi. Bu amal audit jurnaliga yoziladi."
            : "Bundan keyin u faqat ofis hududidan check-in qila oladi. Bu amal audit jurnaliga yoziladi."
        }
        destructive={!granting}
        loading={setExempt.isPending}
        onConfirm={(reason) => {
          if (!userId) return;
          setExempt.mutate(
            { userId, granted: granting, reason },
            {
              onSuccess: () => {
                toast.success(granting ? "Ruxsat berildi" : "Ruxsat olib qo'yildi");
                setConfirmOpen(false);
              },
            }
          );
        }}
      />
    </>
  );
}
