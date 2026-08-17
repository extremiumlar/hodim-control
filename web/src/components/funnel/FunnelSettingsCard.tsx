/**
 * Voronka qoidalari — panelda boshqariladi (TZ 0-bosqichdagi ochiq ta'riflar).
 *
 * NEGA PANELDA: «bekor qilingan shartnoma sotuvdan ayrilsinmi?» — bu texnik
 * sozlama emas, BIZNES qarori. U vaqt o'tib o'zgarishi mumkin va har safar
 * deploy kutib o'tirmasligi kerak.
 *
 * Ikkalasi ham DEFAULT O'CHIQ: sozlama paydo bo'lishi bilan mavjud raqamlar
 * o'zgarib ketmasin — rahbar ongli ravishda yoqadi.
 */
import { useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useFunnelSettings, useSaveFunnelSettings } from "@/lib/queries";

/** Bosqich tanlash — ko'p tanlovli, chunki bir nechta voronkada bir xil
 *  ma'noli bosqich bor (masalan ikkita «Muvaffaqiyatsiz»). */
function StagePicker({
  stages,
  selected,
  onToggle,
  disabled,
}: {
  stages: { pipe_status_id: number; name: string }[];
  selected: number[];
  onToggle: (id: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="mt-2 flex max-h-44 flex-wrap gap-1.5 overflow-y-auto rounded-md border p-2">
      {stages.length === 0 && (
        <span className="text-xs text-muted-foreground">
          Bosqichlar ro'yxati hali bo'sh — CRM ma'lumoti yig'ilgach paydo bo'ladi.
        </span>
      )}
      {stages.map((s) => {
        const on = selected.includes(s.pipe_status_id);
        return (
          <button
            key={s.pipe_status_id}
            type="button"
            disabled={disabled}
            onClick={() => onToggle(s.pipe_status_id)}
            className={`rounded-md border px-2 py-1 text-xs transition-colors ${
              on
                ? "border-emerald-400 bg-emerald-100 text-emerald-900"
                : "bg-card hover:bg-muted"
            } ${disabled ? "opacity-50" : ""}`}
            title={`ID: ${s.pipe_status_id}`}
          >
            {s.name}
          </button>
        );
      })}
    </div>
  );
}

export default function FunnelSettingsCard({ canEdit }: { canEdit: boolean }) {
  const q = useFunnelSettings();
  const save = useSaveFunnelSettings();

  const [subtractCancelled, setSubtractCancelled] = useState(false);
  const [excludeLowQuality, setExcludeLowQuality] = useState(false);
  const [cancelledIds, setCancelledIds] = useState<number[]>([]);
  const [lowQualityIds, setLowQualityIds] = useState<number[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (q.data && !loaded) {
      setSubtractCancelled(q.data.subtract_cancelled);
      setExcludeLowQuality(q.data.exclude_low_quality);
      setCancelledIds(q.data.cancelled_pipe_status_ids);
      setLowQualityIds(q.data.low_quality_pipe_status_ids);
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const toggle = (list: number[], setList: (v: number[]) => void, id: number) =>
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const stages = q.data?.stages ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Settings2 className="size-4" /> Voronka qoidalari
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {q.isLoading && !q.data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <>
            {/* ── Bekor qilingan shartnoma ── */}
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="fs-cancel" className="text-sm font-medium">
                  Bekor qilingan shartnoma sotuvdan ayrilsin
                </Label>
                <input
                  id="fs-cancel"
                  type="checkbox"
                  className="size-4"
                  checked={subtractCancelled}
                  disabled={!canEdit}
                  onChange={(e) => setSubtractCancelled(e.target.checked)}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Yoqilsa: shartnomaga yetgan, lekin keyin quyidagi bosqichlarga o'tgan lid
                sotuv sanalmaydi. O'chiq bo'lsa — hozirgidek, shartnoma bir marta
                sanalgach kamaymaydi.
              </p>
              {subtractCancelled && cancelledIds.length === 0 && (
                <p className="rounded bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950/30">
                  Bosqich tanlanmagan — qoida yoqilgan bo'lsa ham ISHLAMAYDI.
                </p>
              )}
              <StagePicker
                stages={stages}
                selected={cancelledIds}
                disabled={!canEdit}
                onToggle={(id) => toggle(cancelledIds, setCancelledIds, id)}
              />
            </div>

            {/* ── Sifatsiz lead ── */}
            <div className="space-y-1 border-t pt-4">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="fs-low" className="text-sm font-medium">
                  «Sifatsiz lead» lid soniga kirmasin
                </Label>
                <input
                  id="fs-low"
                  type="checkbox"
                  className="size-4"
                  checked={excludeLowQuality}
                  disabled={!canEdit}
                  onChange={(e) => setExcludeLowQuality(e.target.checked)}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Yoqilsa: hozirgi holati «sifatsiz» bo'lgan lid maxrajdan chiqadi va
                konversiya foizi ko'tariladi (spam/noto'g'ri raqam operatorni ayblamasin).
              </p>
              {excludeLowQuality && lowQualityIds.length === 0 && (
                <p className="rounded bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950/30">
                  Bosqich tanlanmagan — qoida yoqilgan bo'lsa ham ISHLAMAYDI.
                </p>
              )}
              <StagePicker
                stages={stages}
                selected={lowQualityIds}
                disabled={!canEdit}
                onToggle={(id) => toggle(lowQualityIds, setLowQualityIds, id)}
              />
            </div>

            {canEdit && (
              <div className="flex items-center gap-3 border-t pt-4">
                <Button
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate(
                      {
                        subtract_cancelled: subtractCancelled,
                        cancelled_pipe_status_ids: cancelledIds,
                        exclude_low_quality: excludeLowQuality,
                        low_quality_pipe_status_ids: lowQualityIds,
                      },
                      {
                        onSuccess: () =>
                          toast.success("Qoidalar saqlandi — raqamlar shu qoida bilan qayta chiqadi"),
                      }
                    )
                  }
                >
                  {save.isPending ? "Saqlanmoqda…" : "Qoidalarni saqlash"}
                </Button>
                <span className="text-xs text-muted-foreground">
                  O'zgarish BARCHA davrlarga darhol ta'sir qiladi (tarix jonli hisoblanadi).
                </span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
