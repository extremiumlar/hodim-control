/**
 * «Kompaniya» — xodim kabineti (TZ 3.16 / S-43).
 *
 * Missiya, qadriyatlar, maqsadlar va tuzilma. Ma'lumot HR kiritgan
 * kompaniya profilidan keladi.
 *
 * ⚠️ AI CHAQIRILMAYDI va HECH NARSA O'YLAB TOPILMAYDI (TZ 3.16
 * qabul mezoni). Kiritilmagan maydon uchun ochiq «kiritilmagan»
 * yoziladi — bu «bilmayman» dan aniqroq va yolg'on emas. Xodim
 * shundan keyin HR ga savol berishi mumkin, savol esa bilim
 * bazasiga `unknown` bo'lib tushadi va bo'shliq ko'rinadi.
 *
 * ⚠️ TUZILMADA XODIM ISMLARI YO'Q — faqat lavozim, ota lavozim va
 * son. «Kim qayerda ishlaydi» ro'yxati shaxsiy ma'lumot.
 */
import { Building2, Compass, ListChecks, Network } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompanyCard } from "@/lib/queries";

function Kiritilmagan() {
  return <p className="text-sm italic text-slate-500">Kiritilmagan.</p>;
}

function Royxat({ bandlar }: { bandlar: string[] }) {
  if (!bandlar.length) return <Kiritilmagan />;
  return (
    <ul className="list-disc space-y-0.5 pl-5 text-sm">
      {bandlar.map((b, i) => (
        <li key={i}>{b}</li>
      ))}
    </ul>
  );
}

export default function Company() {
  const { data, isLoading } = useCompanyCard();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Kompaniya" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Kompaniya" />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Compass className="h-4 w-4" />
            Missiyamiz
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data?.mission ? (
            <p className="text-sm">{data.mission}</p>
          ) : (
            <Kiritilmagan />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Building2 className="h-4 w-4" />
            Qadriyatlarimiz
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Royxat bandlar={data?.values ?? []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ListChecks className="h-4 w-4" />
            Maqsadlarimiz
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Royxat bandlar={data?.goals ?? []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Network className="h-4 w-4" />
            Tuzilma
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!data?.positions.length ? (
            <Kiritilmagan />
          ) : (
            <ul className="space-y-1 text-sm">
              {data.positions.map((p) => (
                <li key={p.id} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="font-medium">{p.name}</span>
                  {p.parent && (
                    <span className="text-xs text-slate-600">→ {p.parent}</span>
                  )}
                  {!!p.employees && (
                    <span className="text-xs text-slate-600">
                      · {p.employees} xodim
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-slate-600">
            O'z o'rningizni «Mening o'rnim» bo'limida ko'rasiz.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
