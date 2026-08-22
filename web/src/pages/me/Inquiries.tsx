/**
 * «HR ga savol» — xodim kabineti (TZ 3.29 / S-28).
 *
 * ⚠️ Bu yerda FAQAT o'z murojaatlarim ko'rinadi — boshqa xodimniki
 * hech qachon. Savollar ko'pincha shaxsiy (oylik, oilaviy sharoit),
 * shuning uchun chegara serverda ham qat'iy (`/hr-inquiries/me`).
 */
import { useState } from "react";
import { CheckCircle2, Clock, Lightbulb, XCircle } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAskHr, useAskHrSuggestion, useMyInquiries } from "@/lib/queries";

function sana(s: string): string {
  return new Date(s).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MyInquiries() {
  const { data, isLoading } = useMyInquiries();
  const ask = useAskHr();
  const resolve = useAskHrSuggestion();
  const [text, setText] = useState("");
  //  ── S-29: bilim bazasidan chiqqan taklif ──
  //  ⚠️ Taklif YAKUNIY javob emas. Solishtirish o'zbekcha erkin matnda
  //  xato qilishi mumkin, shuning uchun oxirgi so'z xodimda: tasdiqlamasa
  //  savol HR ga boradi.
  const [suggestion, setSuggestion] = useState<{
    inquiryId: number;
    entryId: number;
    question: string;
    answer: string;
  } | null>(null);

  async function taklifgaJavob(accepted: boolean) {
    if (!suggestion) return;
    const res = await resolve.mutateAsync({
      inquiryId: suggestion.inquiryId,
      entryId: suggestion.entryId,
      accepted,
    });
    setSuggestion(null);
    toast.success(
      res.resolved
        ? "Savolingiz yopildi — HR bezovta qilinmadi"
        : "Savolingiz HR ga yuborildi"
    );
  }

  async function yubor() {
    const matn = text.trim();
    if (matn.length < 5) {
      toast.error("Savolni to'liqroq yozing");
      return;
    }
    const res = await ask.mutateAsync(matn);
    setText("");
    if (res.suggestion) {
      setSuggestion({
        inquiryId: res.id,
        entryId: res.suggestion.entry_id,
        question: res.suggestion.question,
        answer: res.suggestion.answer,
      });
      return;
    }
    toast.success(
      res.notified
        ? `Yuborildi — toifa: ${res.category_label}`
        : "Saqlandi, lekin hozir HR xodimi tizimda ko'rinmadi"
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="HR ga savol" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Yangi savol</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Savolingizni yozing…"
            rows={3}
          />
          <Button onClick={yubor} disabled={ask.isPending}>
            Yuborish
          </Button>
        </CardContent>
      </Card>

      {suggestion && (
        <Card className="border-amber-300 bg-amber-50/60">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Lightbulb className="h-4 w-4 text-amber-600" />
              Shu savolga tayyor javob bor
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="italic text-slate-600">{suggestion.question}</p>
            <p className="whitespace-pre-wrap rounded bg-white p-3">
              {suggestion.answer}
            </p>
            <p className="text-sm font-medium">Shu javob sizga to'g'ri keldimi?</p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => taklifgaJavob(true)} disabled={resolve.isPending}>
                Ha, rahmat
              </Button>
              <Button
                variant="outline"
                onClick={() => taklifgaJavob(false)}
                disabled={resolve.isPending}
              >
                Yo'q, HR ga yuboring
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Murojaatlarim</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Hali savol bermagansiz.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((q) => (
                <li key={q.id} className="py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    {q.status === "open" ? (
                      <Clock className="h-4 w-4 shrink-0 text-amber-600" />
                    ) : q.status === "answered" ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                    ) : (
                      <XCircle className="h-4 w-4 shrink-0 text-slate-400" />
                    )}
                    <span className="text-xs text-slate-600">
                      {sana(q.created_at)} · {q.category_label} · {q.status_label}
                    </span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap">{q.question}</p>
                  {q.answer && (
                    <p className="mt-1.5 rounded bg-emerald-50 p-2 text-xs text-emerald-900">
                      <b>
                        {q.auto_answered
                          ? "🤖 Bilim bazasi"
                          : (q.answered_by_name ?? "HR")}
                        :
                      </b>{" "}
                      {q.answer}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
