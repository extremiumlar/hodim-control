import { useState, type ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

/**
 * Dasturchi rejimi (super-admin) uchun "sabab so'raydigan" tasdiqlash dialogi
 * (ConfirmDialog'ning kengaytmasi — OYLIK_JARIMA_REJASI.md 11.2/11.5-band:
 * har bir override majburiy sabab bilan). `ConfirmDialog`dan farqli, matn
 * kiritish maydoni bor va shu matn `onConfirm`ga uzatiladi.
 */
export default function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  destructive = false,
  loading = false,
  onConfirm,
  requireTypedConfirmation,
  extra,
  reasonLabel = "Sabab (majburiy, kamida 5 belgi)",
  reasonPlaceholder = "Nega bu amal bajarilmoqda?",
  confirmLabel = "Tasdiqlash",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: (reason: string) => void;
  /** 11.6-band: juda xavfli amallar (masalan butun davrni o'chirish) uchun —
   * berilgan matnni ANIQ terib tasdiqlash talab qilinadi (tasodifan bosishdan
   * himoya, sabab yozishdan qo'shimcha). */
  requireTypedConfirmation?: string;
  /** Sabab maydonidan YUQORIDA chiziladigan qo'shimcha boshqaruv (masalan
   * e'tiroz qarorining turi). Dasturchi rejimida ishlatilmaydi. */
  extra?: ReactNode;
  /** Matn maydonining sarlavhasi/joy egasi — «sabab» har doim ham to'g'ri
   * so'z emas (murojaat qarorida bu «izoh»). */
  reasonLabel?: string;
  reasonPlaceholder?: string;
  confirmLabel?: string;
}) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const validReason = reason.trim().length >= 5;
  const validTyped = !requireTypedConfirmation || typed === requireTypedConfirmation;
  const valid = validReason && validTyped;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) {
          setReason("");
          setTyped("");
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {extra}
        <div>
          <Label htmlFor="override-reason">{reasonLabel}</Label>
          <textarea
            id="override-reason"
            className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={reasonPlaceholder}
            autoFocus
          />
        </div>
        {requireTypedConfirmation && (
          <div>
            <Label htmlFor="override-typed-confirm">
              Tasdiqlash uchun <span className="font-mono font-semibold">{requireTypedConfirmation}</span> deb
              yozing
            </Label>
            <input
              id="override-typed-confirm"
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Bekor qilish
          </Button>
          <Button
            type="button"
            disabled={!valid || loading}
            variant={destructive ? "destructive" : "default"}
            onClick={() => onConfirm(reason.trim())}
          >
            {loading ? "Bajarilmoqda..." : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
