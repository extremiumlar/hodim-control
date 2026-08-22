/**
 * «Darsliklarim» — xodim kabineti (TZ 3.1 / S-36).
 *
 * ⚠️ BOT BILAN BITTA HOLAT. Sahifa hech qanday progress SAQLAMAYDI —
 * har amal serverga boradi va joriy holat qaytadi. Xodim botda
 * boshlab, saytda davom ettirishi mumkin (va teskarisi): backend
 * ikkalasi uchun bir xil `_me_*` funksiyalarini ishlatadi (S-35).
 *
 * ⚠️ VIDEO/HUJJAT brauzerda KO'RSATILMAYDI. Material fayli Telegram
 * `file_id` sifatida saqlanadi (serverda fayl yo'q) va uni brauzer
 * o'qiy olmaydi; serverdan oqizib berish esa Passenger'ni bloklardi
 * (konkurentlik = 1). Shuning uchun fayl xodimning o'z Telegramiga
 * yuboriladi — kadr hujjatlaridagi naqsh.
 */
import { useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  Clock,
  GraduationCap,
  Send,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { CourseResultOut } from "@/lib/api/types";
import {
  useMyCourseAnswer,
  useMyCourseFinish,
  useMyCourseNextMaterial,
  useMyCourseProgress,
  useMyCourseRetry,
  useMyCourseSendMaterial,
  useMyCourses,
} from "@/lib/queries";

function holatBelgisi(k: { passed: boolean | null; pending_review: boolean | null; status: string }) {
  if (k.passed) return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />;
  if (k.pending_review) return <Clock className="h-4 w-4 shrink-0 text-amber-600" />;
  if (k.status === "finished") return <XCircle className="h-4 w-4 shrink-0 text-rose-600" />;
  return <BookOpen className="h-4 w-4 shrink-0 text-slate-500" />;
}

export default function MyCourses() {
  const { data: courses, isLoading } = useMyCourses();
  const [openId, setOpenId] = useState<number | null>(null);
  const { data: progress } = useMyCourseProgress(openId);

  const nextMaterial = useMyCourseNextMaterial();
  const answer = useMyCourseAnswer();
  const finish = useMyCourseFinish();
  const retry = useMyCourseRetry();
  const sendMaterial = useMyCourseSendMaterial();

  const [openText, setOpenText] = useState("");
  const [result, setResult] = useState<CourseResultOut | null>(null);

  async function yakunla(id: number) {
    const r = await finish.mutateAsync(id);
    setResult(r);
  }

  const band = progress?.item;

  return (
    <div className="space-y-4">
      <PageHeader title="Darsliklarim" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <GraduationCap className="h-4 w-4" />
            Menga tayinlangan kurslar
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : !courses?.length ? (
            <div className="rounded-lg border border-dashed p-4 text-sm text-slate-600">
              Sizga hali kurs tayinlanmagan.
            </div>
          ) : (
            <ul className="divide-y">
              {courses.map((k) => (
                <li key={k.assignment_id} className="py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    {holatBelgisi(k)}
                    <button
                      className="min-w-[150px] flex-1 text-left font-medium hover:underline"
                      onClick={() => {
                        setOpenId(openId === k.assignment_id ? null : k.assignment_id);
                        setResult(null);
                        setOpenText("");
                      }}
                    >
                      {k.title}
                    </button>
                    {k.is_mandatory && (
                      <span className="rounded bg-rose-100 px-2 py-0.5 text-xs text-rose-900">
                        majburiy
                      </span>
                    )}
                    {k.due_date && (
                      <span className="text-xs text-slate-600">muddat {k.due_date}</span>
                    )}
                    <span className="text-xs text-slate-600">
                      urinish {k.attempt_no} · o'tish {k.pass_percent}%
                    </span>
                    {k.percent !== null && (
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          k.pending_review
                            ? "bg-amber-100 text-amber-900"
                            : k.passed
                              ? "bg-emerald-100 text-emerald-900"
                              : "bg-rose-100 text-rose-900"
                        }`}
                      >
                        {k.percent}%
                        {k.pending_review
                          ? " · baholanmagan"
                          : k.passed
                            ? " · o'tdi"
                            : " · o'tmadi"}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Natija ── */}
      {result && (
        <Card
          className={
            result.pending_review
              ? "border-amber-300 bg-amber-50/60"
              : result.passed
                ? "border-emerald-300 bg-emerald-50/60"
                : "border-rose-300 bg-rose-50/60"
          }
        >
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {result.pending_review
                ? "🕓 Javoblaringiz qabul qilindi"
                : result.passed
                  ? "🎉 Kurs o'tildi"
                  : "❌ Chegaradan o'tmadi"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {result.pending_review ? (
              <p>
                Ball: {result.score}/{result.max_score}. Ochiq savollar bor — ularni HR
                ko'rib chiqadi va yakuniy natija shundan keyin ma'lum bo'ladi.
              </p>
            ) : (
              <p>
                Natija: <b>{result.percent}%</b> · ball {result.score}/{result.max_score} ·
                o'tish chegarasi {result.pass_percent}% · urinish {result.attempt_no}
              </p>
            )}
            {result.can_retry && openId !== null && (
              <Button
                size="sm"
                onClick={async () => {
                  await retry.mutateAsync(openId);
                  setResult(null);
                  toast.success("Yangi urinish boshlandi");
                }}
                disabled={retry.isPending}
              >
                🔄 Qayta urinish
              </Button>
            )}
            {!result.can_retry && !result.passed && !result.pending_review && (
              <p className="text-xs text-rose-800">
                ⚠️ Urinishlar tugadi — HR bilan bog'laning.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Joriy bosqich ── */}
      {openId !== null && progress && !result && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {progress.stage === "material"
                ? `Material ${progress.material_index + 1}/${progress.material_total}`
                : progress.stage === "savol"
                  ? `Savol ${progress.question_index + 1}/${progress.question_total}`
                  : "Yakunlash"}
              {progress.attempt_no > 1 && (
                <span className="ml-2 text-xs font-normal text-slate-600">
                  {progress.attempt_no}-urinish
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {progress.status === "finished" ? (
              <p className="text-slate-600">
                Bu kurs yakunlangan. Natija yuqoridagi ro'yxatda ko'rinadi.
              </p>
            ) : progress.stage === "material" ? (
              <>
                <p className="font-medium">{band?.title}</p>
                {band?.body && <p className="whitespace-pre-wrap">{band.body}</p>}
                {band?.url && (
                  <a
                    className="text-blue-700 underline"
                    href={band.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {band.url}
                  </a>
                )}
                {band?.file_id && (
                  <div className="rounded border border-dashed p-3">
                    <p className="mb-2 text-xs text-slate-600">
                      Bu material — {band.kind_label?.toLowerCase()}. Fayl Telegramda
                      saqlanadi, shuning uchun uni botga yuboramiz.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        const r = await sendMaterial.mutateAsync(openId);
                        toast[r.delivered ? "success" : "error"](
                          r.delivered
                            ? "Telegramga yuborildi"
                            : "Yuborib bo'lmadi — botni oching"
                        );
                      }}
                      disabled={sendMaterial.isPending}
                    >
                      <Send className="mr-1 h-4 w-4" />
                      Telegramga yuborish
                    </Button>
                  </div>
                )}
                <Button
                  onClick={async () => {
                    await nextMaterial.mutateAsync(openId);
                  }}
                  disabled={nextMaterial.isPending}
                >
                  Ko'rdim, keyingisi
                </Button>
              </>
            ) : progress.stage === "savol" ? (
              <>
                <p className="font-medium">{band?.text}</p>
                <p className="text-xs text-slate-600">{band?.points} ball</p>
                {band?.is_open ? (
                  <div className="space-y-2">
                    <Textarea
                      rows={3}
                      value={openText}
                      onChange={(e) => setOpenText(e.target.value)}
                      placeholder="Javobingizni yozing…"
                    />
                    <Button
                      onClick={async () => {
                        if (!openText.trim()) {
                          toast.error("Javob bo'sh");
                          return;
                        }
                        await answer.mutateAsync({
                          id: openId,
                          body: { text: openText.trim() },
                        });
                        setOpenText("");
                      }}
                      disabled={answer.isPending}
                    >
                      Javobni yuborish
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {(band?.options ?? []).map((o, i) => (
                      <Button
                        key={i}
                        variant="outline"
                        className="justify-start"
                        onClick={async () => {
                          await answer.mutateAsync({ id: openId, body: { choice: i } });
                        }}
                        disabled={answer.isPending}
                      >
                        {o}
                      </Button>
                    ))}
                  </div>
                )}
                {/*  ⚠️ To'g'ri/noto'g'ri DARHOL ko'rsatilmaydi — xodim
                    savollarni ketma-ket o'tsin, natija yakunda chiqadi
                    (botdagi bilan bir xil qaror). */}
              </>
            ) : (
              <>
                <p>Barcha material va savollar tugadi.</p>
                <Button onClick={() => yakunla(openId)} disabled={finish.isPending}>
                  🏁 Yakunlash va natijani olish
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
