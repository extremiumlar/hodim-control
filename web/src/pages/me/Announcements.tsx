/**
 * «E'lonlar» — xodim kabineti (TZ 3.12 / S-21).
 *
 * ⚠️ Qamrovga kirmagan e'lon bu ro'yxatga UMUMAN kelmaydi — filtr
 * serverda (`announcements.visible_to`). Mijoz hech narsani yashirmaydi,
 * chunki yashiriladigan narsa unga yetib ham kelmaydi.
 *
 * MUHIM e'londa «Tanishdim» talab qilinadi va u `acknowledgements` (S-20)
 * ga yoziladi. Matn tahrirlansa versiya oshadi va tanishuv QAYTA
 * so'raladi — xodim eski matnga rozi bo'lgan, yangisiga emas.
 */
import { AlertTriangle, CheckCircle2, Megaphone } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAcknowledge, useMyAnnouncements } from "@/lib/queries";

function sana(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("ru-RU");
}

export default function MeAnnouncements() {
  const { data, isLoading } = useMyAnnouncements();
  const ack = useAcknowledge();

  const tasdiqlanmagan = (data ?? []).filter(
    (a) => a.important && a.acknowledged === false
  ).length;

  return (
    <div className="space-y-4">
      <PageHeader title="E'lonlar" />

      {tasdiqlanmagan > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <b>{tasdiqlanmagan} ta</b> muhim e'lon bilan tanishmagansiz.
        </div>
      )}

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : !data?.length ? (
        <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
          <Megaphone className="h-4 w-4 shrink-0" />
          Hozircha e'lon yo'q.
        </div>
      ) : (
        <ul className="space-y-3">
          {data.map((a) => (
            <li
              key={a.id}
              className={`rounded-lg border p-3 ${
                a.important && a.acknowledged === false
                  ? "border-amber-300 bg-amber-50"
                  : "bg-white"
              }`}
            >
              <div className="mb-1 flex flex-wrap items-center gap-2">
                {a.important && (
                  <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs font-medium text-rose-800">
                    Muhim
                  </span>
                )}
                <span className="font-medium">{a.title}</span>
                <span className="ml-auto text-xs text-slate-500">
                  {a.author_name ? `${a.author_name} · ` : ""}
                  {sana(a.created_at)}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm text-slate-700">{a.body}</p>

              {a.important &&
                (a.acknowledged ? (
                  <div className="mt-2 flex items-center gap-1 text-xs text-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Tanishdingiz
                  </div>
                ) : (
                  <Button
                    size="sm"
                    className="mt-2"
                    disabled={ack.isPending}
                    onClick={async () => {
                      await ack.mutateAsync({
                        object_type: "announcement",
                        object_id: a.id,
                        version: a.version,
                      });
                      toast.success("Tanishganingiz qayd etildi");
                    }}
                  >
                    Tanishdim
                  </Button>
                ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
