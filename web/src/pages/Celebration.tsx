/**
 * Tabrik videolari — CRM'da lid «Tashrif» yoki «Shartnoma qilindi» bosqichiga
 * o'tganda umumiy guruhga chiqadigan video (yoki GIF).
 *
 * Bot panelidagi bilan BIR XIL imkoniyat (Boshliq/HR botdan ham, saytdan ham
 * qila oladi) — ikkalasi ham `api/services/celebration.py` ni chaqiradi.
 *
 * Fayl serverda SAQLANMAYDI: backend uni Telegram'ga uzatib, doimiy `file_id`
 * oladi va faqat shuni bazaga yozadi.
 */
import { useRef, useState } from "react";
import { FlaskConical, Power, Upload } from "lucide-react";
import { toast } from "sonner";
import PageHeader from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { type CelebrationMediaRow } from "@/lib/api";
import {
  useCelebrationSettings,
  useDisableCelebrationMedia,
  useTestCelebrationMedia,
  useUploadCelebrationMedia,
} from "@/lib/queries";

const MAX_MB = 45;

const KIND_HINTS: Record<string, string> = {
  visit: "Mijoz ofisga kelib, lid «Tashrif» bosqichiga o'tganda chiqadi.",
  contract: "Lid «Shartnoma qilindi» bosqichiga o'tganda chiqadi — kuchliroq video qo'ying.",
};

function MediaCard({ row }: { row: CelebrationMediaRow }) {
  const [caption, setCaption] = useState(row.caption ?? "");
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useUploadCelebrationMedia();
  const disable = useDisableCelebrationMedia();
  const test = useTestCelebrationMedia();

  const tooBig = !!file && file.size > MAX_MB * 1024 * 1024;

  const onUpload = () => {
    if (!file) {
      toast.error("Avval video yoki GIF tanlang");
      return;
    }
    if (tooBig) {
      toast.error(`Fayl juda katta. Chegara — ${MAX_MB} MB`);
      return;
    }
    upload.mutate(
      { kind: row.kind, file, caption },
      {
        onSuccess: () => {
          toast.success("Video o'rnatildi — nusxasi Telegramingizga yuborildi");
          setFile(null);
          if (inputRef.current) inputRef.current.value = "";
        },
      }
    );
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="flex items-center gap-2">
          {row.kind === "visit" ? "🎉" : "🤝"} {row.label}
        </CardTitle>
        {row.configured ? (
          <Badge variant="default">
            {row.file_type === "animation" ? "GIF" : "Video"} o'rnatilgan
          </Badge>
        ) : (
          <Badge variant="secondary">Video yo'q</Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{KIND_HINTS[row.kind]}</p>

        {!row.stages_configured && (
          <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            CRM bosqichi sozlanmagan — dasturchiga ayting, aks holda bu tur hech qachon
            ishlamaydi.
          </p>
        )}

        {!row.configured && (
          <p className="rounded-md bg-muted p-3 text-sm">
            Video yuklanmaguncha guruhga <b>hech narsa yuborilmaydi</b>.
          </p>
        )}

        <div className="grid gap-2">
          <Label htmlFor={`file-${row.kind}`}>Video yoki GIF (mp4 / mov / webm / gif)</Label>
          <Input
            id={`file-${row.kind}`}
            ref={inputRef}
            type="file"
            accept="video/*,image/gif"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file && (
            <p className={`text-xs ${tooBig ? "text-destructive" : "text-muted-foreground"}`}>
              {file.name} — {(file.size / 1024 / 1024).toFixed(1)} MB
              {tooBig ? ` (chegara ${MAX_MB} MB)` : ""}
            </p>
          )}
        </div>

        <div className="grid gap-2">
          <Label htmlFor={`caption-${row.kind}`}>Qo'shimcha matn (ixtiyoriy)</Label>
          <Input
            id={`caption-${row.kind}`}
            value={caption}
            maxLength={500}
            placeholder="Masalan: Zo'r ish! Shu tempda davom!"
            onChange={(e) => setCaption(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Har tabrikning oxiriga qo'shiladi (xodim ismi va soni avtomatik yoziladi).
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={onUpload} disabled={upload.isPending || !file || tooBig}>
            <Upload className="mr-2 size-4" />
            {upload.isPending ? "Yuklanmoqda…" : row.configured ? "Almashtirish" : "Yuklash"}
          </Button>
          <Button
            variant="outline"
            disabled={!row.configured || test.isPending}
            onClick={() =>
              test.mutate(row.kind, {
                onSuccess: () => toast.success("Sinov Telegramingizga yuborildi (guruhga emas)"),
              })
            }
          >
            <FlaskConical className="mr-2 size-4" />
            Sinov
          </Button>
          <Button
            variant="ghost"
            className="text-destructive"
            disabled={!row.configured || disable.isPending}
            onClick={() =>
              disable.mutate(row.kind, {
                onSuccess: () => toast.success("O'chirildi — bu tur uchun guruhga video ketmaydi"),
              })
            }
          >
            <Power className="mr-2 size-4" />
            O'chirish
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          Guruhga yuborilgan: <b>{row.posts_total}</b> ta
          {row.updated_at
            ? ` · oxirgi o'zgarish: ${new Date(row.updated_at).toLocaleString("uz-UZ")}`
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}

export default function Celebration() {
  const { data, isLoading } = useCelebrationSettings();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tabrik videolari"
        description="Tashrif va shartnoma bo'lganda umumiy guruhga chiqadigan video"
      />

      <Card>
        <CardContent className="space-y-1 pt-6 text-sm text-muted-foreground">
          <p>
            Video Telegram orqali yuboriladi, shuning uchun yuklash uchun Telegram hisobingiz
            botga ulangan bo'lishi shart — yuklangan video darhol sizning Telegramingizga
            nusxa qilib yuboriladi.
          </p>
          <p>
            Guruhdagi xabarda «👏 Tabriklash» tugmasi bo'ladi; har xodim bir marta bosa
            oladi. Xuddi shu sozlamani botdagi «🎬 Tabrik videolari» tugmasidan ham
            qilish mumkin.
          </p>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {(data?.items ?? []).map((row) => (
            <MediaCard key={row.kind} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}
