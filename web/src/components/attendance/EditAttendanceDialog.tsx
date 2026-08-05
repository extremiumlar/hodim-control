/**
 * Davomat yozuvini qo'lda tuzatish/yaratish dialogi — HR/Boshliq (backend
 * ATTENDANCE_EDIT_ROLES yoki shaxsiy `can_edit_attendance`).
 *
 * UX-B: ilgari 824-qatorlik Attendance.tsx ichida edi; endi alohida komponent —
 * uni "Yozuvlar" jadvali HAM, matritsa katagi popover'i HAM ochadi (bitta dialog,
 * ikki kirish nuqtasi).
 *
 * IKKI REJIM, BITTA DIALOG:
 *   `row` bor  -> mavjud yozuvni tuzatish;
 *   `row` null -> YANGI yozuv (xodim va sana shu yerda tanlanadi yoki
 *                 `presetUserId`/`presetDate` bilan oldindan to'ldiriladi —
 *                 matritsa katagidan ochilganda).
 */
import { useEffect, useState } from "react";
import { format } from "date-fns";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
import { type Attendance as AttendanceRow } from "@/lib/api";
import { useAdminManualAttendance, useManualAttendance, useUsers } from "@/lib/queries";
import { fmtLocalTime } from "@/lib/utils";

// <input type="time"> uchun — bo'sh qiymat "" bo'lishi kerak ("—" emas).
function toHm(iso: string | null): string {
  return iso ? fmtLocalTime(iso) : "";
}

export default function EditAttendanceDialog({
  open,
  row,
  onClose,
  silent = false,
  presetUserId,
  presetDate,
}: {
  open: boolean;
  /** null — yangi yozuv rejimi. */
  row: AttendanceRow | null;
  onClose: () => void;
  /** Dasturchi rejimi: AUDITSIZ endpoint, sabab so'ralmaydi (hech qayerga
      yozilmaydi). Egasining aniq talabi — "auditlarga tushmasdan". */
  silent?: boolean;
  /** Matritsa katagidan ochilganda — xodim/sana oldindan to'ldirilgan bo'ladi. */
  presetUserId?: number;
  presetDate?: string;
}) {
  const creating = row === null;
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [newUserId, setNewUserId] = useState("");
  const [newDate, setNewDate] = useState("");
  const audited = useManualAttendance();
  const silentMutation = useAdminManualAttendance();
  const mutation = silent ? silentMutation : audited;

  // Xodim ro'yxati faqat yangi yozuv rejimida kerak — tuzatishda xodim
  // qatordan ma'lum.
  const usersQuery = useUsers();

  // Dialog ochilganda maydonlar o'sha yozuv (yoki preset) qiymatlari bilan
  // to'ldiriladi. `open`ga ham bog'liq: yangi yozuv rejimida `row` doim null
  // bo'lgani uchun `[row]` o'zgarmasdi va ikkinchi ochilishda eski qiymatlar
  // qolib ketardi.
  useEffect(() => {
    if (!open) return;
    setCheckIn(toHm(row?.check_in_time ?? null));
    setCheckOut(toHm(row?.check_out_time ?? null));
    setNote(row?.note ?? "");
    setReason("");
    setNewUserId(presetUserId != null ? String(presetUserId) : "");
    setNewDate(presetDate ?? format(new Date(), "yyyy-MM-dd"));
  }, [row, open, presetUserId, presetDate]);

  // Jim rejimda sabab umuman so'ralmaydi — u hech qayerga yozilmaydi,
  // ya'ni majburlash faqat ortiqcha qadam bo'lardi.
  const reasonTooShort = !silent && reason.trim().length < 5;
  const invalidOrder = !!checkIn && !!checkOut && checkOut <= checkIn;
  const outWithoutIn = !!checkOut && !checkIn;
  // Yangi yozuvda xodim va sana majburiy — ularsiz nimaga yozilishi noma'lum.
  const targetMissing = creating && (!newUserId || !newDate);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {creating
              ? "Yangi davomat yozuvi"
              : `${row?.user_full_name} — ${row ? format(new Date(row.date), "dd.MM.yyyy") : ""}`}
          </DialogTitle>
          <DialogDescription>
            Face ID/GPS ishlamagan yoki xodim bosishni unutgan kunni tuzatish — yozuv
            bo'lmasa yangisi ochiladi. Kechikish va ishlangan vaqt ish jadvali bo'yicha
            qayta hisoblanadi.{" "}
            {silent ? (
              <span className="font-medium text-amber-700">
                Dasturchi rejimi: bu o'zgarish audit jurnaliga TUSHMAYDI va hech kimga
                xabar berilmaydi.
              </span>
            ) : (
              "O'zgarish audit jurnaliga tushadi (botga xabar yuborilmaydi)."
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          {creating && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="att-user">
                  Xodim <span className="text-rose-600">*</span>
                </Label>
                <Select value={newUserId} onValueChange={setNewUserId}>
                  <SelectTrigger id="att-user">
                    <SelectValue placeholder="Tanlang..." />
                  </SelectTrigger>
                  <SelectContent>
                    {usersQuery.data?.map((u) => (
                      <SelectItem key={u.id} value={String(u.id)}>
                        {u.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="att-date">
                  Sana <span className="text-rose-600">*</span>
                </Label>
                <Input
                  id="att-date"
                  type="date"
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  max={format(new Date(), "yyyy-MM-dd")}
                />
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="att-in">Keldim</Label>
              <Input
                id="att-in"
                type="time"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="att-out">Ketdim</Label>
              <Input
                id="att-out"
                type="time"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
              />
            </div>
          </div>
          <p className="-mt-2 text-xs text-slate-500">
            Bo'sh qoldirilsa — o'sha belgi tozalanadi (masalan «Keldim» bo'sh bo'lsa,
            kun «kelmagan» bo'lib qoladi).
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="att-note">Izoh (ixtiyoriy)</Label>
            <Input
              id="att-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Masalan: telefon kamerasi ishlamadi"
            />
          </div>

          {!silent && (
            <div className="space-y-1.5">
              <Label htmlFor="att-reason">
                Sabab <span className="text-rose-600">*</span>
              </Label>
              <Input
                id="att-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Nima uchun tuzatilyapti (kamida 5 belgi)"
              />
            </div>
          )}

          {invalidOrder && (
            <p className="text-sm text-rose-600">«Ketdim» «Keldim» dan keyin bo'lishi kerak.</p>
          )}
          {outWithoutIn && (
            <p className="text-sm text-rose-600">«Ketdim» ni «Keldim» siz belgilab bo'lmaydi.</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Bekor qilish
          </Button>
          <Button
            disabled={
              targetMissing || reasonTooShort || invalidOrder || outWithoutIn || mutation.isPending
            }
            onClick={() => {
              const targetId = row ? row.user_id : Number(newUserId);
              const targetDay = row ? row.date : newDate;
              if (!targetId || !targetDay) return;
              mutation.mutate(
                {
                  user_id: targetId,
                  date: targetDay,
                  check_in: checkIn || null,
                  check_out: checkOut || null,
                  note: note.trim() || null,
                  // Jim rejimda sabab yozilmaydi — backend uni talab qilmaydi.
                  reason: silent ? "" : reason.trim(),
                },
                {
                  onSuccess: (updated: { late_minutes?: number }) => {
                    const late = updated.late_minutes;
                    toast.success(
                      late === undefined
                        ? "Saqlandi (jim rejim — audit yozilmadi)."
                        : late > 0
                          ? `Saqlandi — kechikish ${late} daqiqa.`
                          : "Saqlandi — kechikish yo'q."
                    );
                    onClose();
                  },
                }
              );
            }}
          >
            {mutation.isPending ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
