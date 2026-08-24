/**
 * «Birinchi kunlarim» — xodim kabineti (TZ 3.2 / S-47).
 *
 * Chekbox ro'yxati: qadam, muddat, holat.
 *
 * ⚠️ KECHIKKAN QADAM AJRATIB KO'RSATILADI (TZ 3.2 qabul mezoni) —
 * yangi xodim uchun bu ro'yxatning butun ma'nosi: nima qolgani va
 * nimasi kechikkani darhol ko'rinsin.
 *
 * ⚠️ KURS VA HUJJAT QADAMIGA CHEKBOX QO'YILMAYDI. Ularni bu yerdan
 * belgilash mumkin bo'lsa, xodim kursni o'tmasdan «bajardim» deb
 * qo'yardi va holat yolg'on bo'lardi. Bunday qadamlar manba
 * modulda bajarilganda O'ZI belgilanadi (S-45).
 */
import { AlertTriangle, BookOpen, CheckCircle2, FileText, Handshake, HardHat, Pin } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ProgressBar from "@/components/ProgressBar";
import { Skeleton } from "@/components/ui/skeleton";
import type { OnboardingItem } from "@/lib/api/types";
import { useMyOnboarding, useOnboardingItemDone } from "@/lib/queries";

const TUR_BELGI: Record<OnboardingItem["kind"], typeof Pin> = {
  task: Pin,
  document: FileText,
  course: BookOpen,
  briefing: HardHat,
  meeting: Handshake,
};

const TUR_NOMI: Record<OnboardingItem["kind"], string> = {
  task: "Vazifa",
  document: "Hujjat",
  course: "Kurs",
  briefing: "Instruktaj",
  meeting: "Uchrashuv",
};

/** Boshqa modul bajaradigan qadam — bu yerdan belgilanmaydi. */
function tashqiQadam(kind: OnboardingItem["kind"]): boolean {
  return kind === "course" || kind === "document";
}

export default function MyOnboarding() {
  const { data, isLoading } = useMyOnboarding();
  const belgila = useOnboardingItemDone();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Birinchi kunlarim" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Birinchi kunlarim" />
        <Card>
          <CardContent className="py-8 text-center text-sm text-slate-600">
            Sizda faol onboarding rejasi yo'q.
            <div className="mt-1 text-xs">
              Yangi xodim uchun reja ishga qabul qilinganda ochiladi.
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Birinchi kunlarim" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
            <span>{data.template_name ?? "Reja"}</span>
            <span className="text-sm font-normal text-slate-600">
              {data.done}/{data.total} bajarildi
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ProgressBar value={data.percent} />

          {data.overdue > 0 && (
            <div className="flex items-center gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              Kechikkan qadam: <b>{data.overdue}</b>
            </div>
          )}

          <ul className="space-y-2">
            {(data.items ?? []).map((b) => {
              const Belgi = TUR_BELGI[b.kind] ?? Pin;
              return (
                <li
                  key={b.id}
                  className={`rounded border px-3 py-2 ${
                    b.overdue ? "border-amber-300 bg-amber-50/60" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-sm">
                        {b.done ? (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                        ) : (
                          <Belgi className="h-4 w-4 shrink-0 text-slate-500" />
                        )}
                        <span className={b.done ? "text-slate-500 line-through" : ""}>
                          {b.title}
                        </span>
                      </div>
                      <div className="mt-0.5 text-xs text-slate-600">
                        {TUR_NOMI[b.kind]}
                        {b.due_date ? ` · muddat ${b.due_date}` : ""}
                        {b.overdue ? " · ⏰ kechikdi" : ""}
                      </div>
                      {b.description && (
                        <p className="mt-1 text-xs text-slate-600">{b.description}</p>
                      )}
                    </div>

                    {!b.done && !tashqiQadam(b.kind) && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        disabled={belgila.isPending}
                        onClick={() => belgila.mutate({ id: b.id })}
                      >
                        Bajardim
                      </Button>
                    )}
                    {!b.done && tashqiQadam(b.kind) && (
                      <span className="shrink-0 text-xs text-slate-500">
                        {b.kind === "course" ? "kursda" : "HR kutmoqda"}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          {data.status === "done" && (
            <div className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              🎉 Barcha qadam bajarildi — onboarding tugadi.
              {data.next_stage && (
                <div className="mt-0.5 text-xs">
                  Keyingi bosqich: <b>{data.next_stage.label}</b> (
                  {data.next_stage.due_date})
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
