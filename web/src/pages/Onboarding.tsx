/**
 * «Onboarding» — HR ekrani (TZ 3.2 / S-47).
 *
 * Hozir onboardingda nechta xodim, kimda qaysi qadam kechikkan.
 *
 * ⚠️ KECHIKKANLAR TEPADA. Ro'yxat backendda aynan shunday
 * saralangan (`-overdue`, keyin `start_date`): HR bu sahifani
 * «kim orqada qolyapti?» degan savol bilan ochadi va javob
 * birinchi qatorda turishi kerak.
 *
 * ⚠️ OG'IR HISOB SAHIFADA EMAS. Progress backendda hisoblanadi va
 * ro'yxat javobida `items` YO'Q — 20 xodimning 15 tadan qadami
 * har sahifa ochilganda uzatilsa, konkurentlik = 1 bo'lgan
 * Passenger'da bu sezilarli kechikish berardi.
 */
import { useState } from "react";
import { AlertTriangle, ClipboardList, Users } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ProgressBar from "@/components/ProgressBar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useOnboardingPlan,
  useOnboardingPlans,
  useOnboardingTemplates,
} from "@/lib/queries";

export default function Onboarding() {
  const { data: rejalar, isLoading } = useOnboardingPlans();
  const { data: shablonlar } = useOnboardingTemplates();
  const [ochiq, setOchiq] = useState<number | null>(null);
  const { data: tafsilot } = useOnboardingPlan(ochiq);

  const kechikkanlar = (rejalar ?? []).filter((r) => r.overdue > 0);

  return (
    <div className="space-y-4">
      <PageHeader title="Onboarding" />

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <Users className="h-5 w-5 text-slate-500" />
            <div>
              <div className="text-xl font-semibold">{rejalar?.length ?? 0}</div>
              <div className="text-xs text-slate-600">Onboardingda</div>
            </div>
          </CardContent>
        </Card>
        <Card className={kechikkanlar.length ? "border-amber-300 bg-amber-50/60" : ""}>
          <CardContent className="flex items-center gap-3 py-4">
            <AlertTriangle
              className={`h-5 w-5 ${
                kechikkanlar.length ? "text-amber-600" : "text-slate-400"
              }`}
            />
            <div>
              <div className="text-xl font-semibold">{kechikkanlar.length}</div>
              <div className="text-xs text-slate-600">Kechikkan xodim</div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <ClipboardList className="h-5 w-5 text-slate-500" />
            <div>
              <div className="text-xl font-semibold">{shablonlar?.length ?? 0}</div>
              <div className="text-xs text-slate-600">Shablon</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Faol rejalar</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !rejalar?.length ? (
            <p className="text-sm text-slate-600">
              Hozir hech kim onboardingda emas.
            </p>
          ) : (
            <div className="space-y-2 text-sm">
              {rejalar.map((r) => (
                <div
                  key={r.plan_id}
                  className={`rounded border ${
                    r.overdue > 0 ? "border-amber-300 bg-amber-50/60" : ""
                  }`}
                >
                  <button
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
                    onClick={() =>
                      setOchiq(ochiq === r.plan_id ? null : r.plan_id)
                    }
                  >
                    <span className="min-w-0">
                      <span className="font-medium">{r.full_name}</span>
                      <span className="text-xs text-slate-600">
                        {" · "}
                        {r.template_name ?? "Reja"} · {r.start_date} dan
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs">
                      {r.overdue > 0 && (
                        <span className="rounded bg-amber-200 px-1.5 py-0.5 text-amber-900">
                          {r.overdue} kechikdi
                        </span>
                      )}
                      <span>
                        {r.done}/{r.total}
                      </span>
                    </span>
                  </button>
                  <div className="px-3 pb-2">
                    <ProgressBar value={r.percent} />
                  </div>

                  {ochiq === r.plan_id && (
                    <div className="border-t px-3 py-2">
                      {!tafsilot?.items ? (
                        <Skeleton className="h-16 w-full" />
                      ) : (
                        <ul className="space-y-1">
                          {tafsilot.items.map((b) => (
                            <li
                              key={b.id}
                              className="flex items-baseline justify-between gap-2"
                            >
                              <span className={b.done ? "text-slate-500" : ""}>
                                {b.done ? "✅" : "▫️"} {b.title}
                              </span>
                              <span className="shrink-0 text-xs text-slate-600">
                                {b.due_date ?? "—"}
                                {b.overdue ? " · ⏰ kechikdi" : ""}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
