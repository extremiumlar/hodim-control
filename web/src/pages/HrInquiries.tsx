/**
 * «Murojaatlar» — HR paneli (TZ 3.29 / S-28).
 *
 * Ilgari xodim savoli HR ning shaxsiy yozishmasida qolib ketardi:
 * kim nima so'raganini ham, qanday javob berilganini ham keyin topib
 * bo'lmasdi, va bir savolga ikki xodim ikki xil javob olishi mumkin edi.
 *
 * ⚠️ JAVOBSIZLAR HAR DOIM TEPADA — saralash serverda, sanaga qarab
 * emas, avval holatga qarab. Aks holda eski javobsiz savol yangi
 * javoblar tagida ko'milib ketardi (S-28 qabul mezoni).
 */
import { useState } from "react";
import { CheckCircle2, Clock, MessageSquare, XCircle } from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useAnswerInquiry,
  useCloseInquiry,
  useHrInquiries,
  useHrInquiryStats,
  useInquiryCategories,
  useSetInquiryCategory,
} from "@/lib/queries";

const BARCHASI = "all";

function sana(s: string): string {
  return new Date(s).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function HrInquiries() {
  const [status, setStatus] = useState(BARCHASI);
  const [category, setCategory] = useState(BARCHASI);
  const { data, isLoading } = useHrInquiries(
    status === BARCHASI ? undefined : status,
    category === BARCHASI ? undefined : category
  );
  const { data: stats } = useHrInquiryStats();
  const { data: categories } = useInquiryCategories();
  const answer = useAnswerInquiry();
  const setCat = useSetInquiryCategory();
  const close = useCloseInquiry();

  //  Qaysi murojaatga javob yozilyapti va matni.
  const [openId, setOpenId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  async function yubor(id: number) {
    if (!draft.trim()) {
      toast.error("Javob matnini yozing");
      return;
    }
    const res = await answer.mutateAsync({ id, answer: draft.trim() });
    setOpenId(null);
    setDraft("");
    toast.success(
      res.delivered
        ? "Javob yuborildi"
        : "Javob saqlandi, lekin xodimga xabar yetkazilmadi"
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Murojaatlar" />

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2 pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageSquare className="h-4 w-4" />
            Xodim savollari
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={BARCHASI}>Barcha holat</SelectItem>
                <SelectItem value="open">Javob kutilmoqda</SelectItem>
                <SelectItem value="answered">Javob berilgan</SelectItem>
                <SelectItem value="closed">Yopilgan</SelectItem>
              </SelectContent>
            </Select>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="h-8 w-44 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={BARCHASI}>Barcha toifa</SelectItem>
                {(categories ?? []).map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {stats && stats.open > 0 && (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                {stats.open} ta javobsiz
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !data?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Murojaat yo'q.
            </div>
          ) : (
            <ul className="divide-y">
              {data.map((q) => {
                const ochiq = q.status === "open";
                return (
                  <li
                    key={q.id}
                    className={`py-3 text-sm ${ochiq ? "bg-amber-50/60 -mx-4 px-4" : ""}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      {ochiq ? (
                        <Clock className="h-4 w-4 shrink-0 text-amber-600" />
                      ) : q.status === "answered" ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                      ) : (
                        <XCircle className="h-4 w-4 shrink-0 text-slate-400" />
                      )}
                      <span className="font-medium">{q.user_name ?? "—"}</span>
                      <span className="text-xs text-slate-600">{sana(q.created_at)}</span>
                      <Select
                        value={q.category}
                        onValueChange={(v) =>
                          setCat.mutateAsync({ id: q.id, category: v })
                        }
                      >
                        <SelectTrigger className="h-6 w-40 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(categories ?? []).map((c) => (
                            <SelectItem key={c.value} value={c.value}>
                              {c.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {/* Toifani mashina qo'yganini ko'rsatamiz — HR unga
                          ko'r-ko'rona ishonmasin. */}
                      {q.category_auto && (
                        <span className="text-[11px] text-slate-500">avto</span>
                      )}
                    </div>

                    <p className="mt-1.5 whitespace-pre-wrap">{q.question}</p>

                    {q.answer && (
                      <p className="mt-1.5 rounded bg-emerald-50 p-2 text-xs text-emerald-900">
                        <b>{q.answered_by_name ?? "HR"}:</b> {q.answer}
                      </p>
                    )}

                    {openId === q.id ? (
                      <div className="mt-2 space-y-2">
                        <Textarea
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          placeholder="Javobingiz…"
                          rows={3}
                        />
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => yubor(q.id)}
                            disabled={answer.isPending}
                          >
                            Yuborish
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setOpenId(null);
                              setDraft("");
                            }}
                          >
                            Bekor
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-2 flex gap-2">
                        <Button
                          size="sm"
                          variant={ochiq ? "default" : "outline"}
                          onClick={() => {
                            setOpenId(q.id);
                            setDraft(q.answer ?? "");
                          }}
                        >
                          {q.answer ? "Javobni tahrirlash" : "Javob berish"}
                        </Button>
                        {ochiq && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={async () => {
                              await close.mutateAsync(q.id);
                              toast.success("Yopildi");
                            }}
                          >
                            Javobsiz yopish
                          </Button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
