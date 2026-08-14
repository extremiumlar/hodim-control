import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Target } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { type TeamNormRow } from "@/lib/api";
import { useTeamNorms, useUpdateNorm } from "@/lib/queries";

/** Server qiymatini input uchun matnga aylantiradi (norma yo'q -> bo'sh). */
const asDraft = (norm: number | null) => (norm === null ? "" : String(norm));

export default function Norms() {
  const query = useTeamNorms();
  const updateNorm = useUpdateNorm();
  // Kalit: `${userId}:${metricKey}` — har bir xodimning har bir ko'rsatkichi uchun qoralama
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  // Foydalanuvchi TEGGAN, lekin hali saqlanmagan maydonlar.
  //
  // NEGA KERAK (2026-08-14, jonli sinovda isbotlangan xato): ilgari `useEffect`
  // har `query.data` yangilanishida BARCHA qoralamalarni server qiymatiga
  // qaytarardi. Bitta normani saqlash esa ro'yxatni qayta yuklaydi
  // (`useUpdateNorm` -> invalidate) — natijada bir necha xodimga qiymat yozib,
  // bittasini saqlagan odam QOLGANLARINI JIMGINA YO'QOTARDI (hech qanday
  // ogohlantirishsiz). Endi server qiymati faqat TEGILMAGAN maydonlarga
  // yoziladi; tegilgani saqlanmaguncha o'zgarmaydi.
  const dirtyRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!query.data) return;
    setDrafts((prev) => {
      const next = { ...prev };
      query.data.forEach((row) => {
        row.metrics.forEach((m) => {
          const key = `${row.user_id}:${m.key}`;
          if (!dirtyRef.current.has(key)) next[key] = asDraft(m.norm);
        });
      });
      return next;
    });
  }, [query.data]);

  const saveMetric = (userId: number, metric: string) => {
    const draftKey = `${userId}:${metric}`;
    const raw = (drafts[draftKey] ?? "").trim();
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 0) {
      toast.error("Qiymat manfiy bo'lmagan butun son bo'lishi kerak");
      return;
    }
    setSavingKey(draftKey);
    updateNorm.mutate(
      { user_id: userId, metric_type: metric, value },
      {
        onSuccess: () => {
          // Saqlangach maydon yana serverga ergashadi (keyingi yangilanishda
          // haqiqiy qiymat bilan tenglashadi).
          dirtyRef.current.delete(draftKey);
          toast.success("Norma saqlandi");
        },
        onSettled: () => setSavingKey(null),
      }
    );
  };

  const columns = useMemo<ColumnDef<TeamNormRow>[]>(
    () => [
      {
        accessorKey: "full_name",
        header: "Xodim",
        // Normasi yo'qligini ALOHIDA bo'lim ko'rsatadi (pastga qarang) —
        // shuning uchun bu yerda qo'shimcha belgi kerak emas.
        cell: ({ row }) => (
          <Link to={`/employees/${row.original.user_id}`} className="text-primary hover:underline">
            {row.original.full_name}
          </Link>
        ),
      },
      {
        accessorKey: "position_name",
        header: "Lavozim",
        cell: ({ row }) => (
          <span className="text-slate-500">{row.original.position_name ?? "—"}</span>
        ),
      },
      {
        id: "metrics",
        header: "Bugungi natija / norma",
        enableSorting: false,
        cell: ({ row }) => {
          // Lavozimga ko'rsatkich biriktirilmagan bo'lsa — bo'sh katak o'rniga
          // nima qilish kerakligini aytamiz (ilgari shunchaki bo'sh turardi).
          if (row.original.metrics.length === 0) {
            return (
              <span className="text-xs text-slate-400">
                Bu lavozimda ko'rsatkich belgilanmagan — «Lavozimlar» bo'limidan qo'shing
              </span>
            );
          }
          return (
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {row.original.metrics.map((m) => {
                const draftKey = `${row.original.user_id}:${m.key}`;
                const draft = drafts[draftKey] ?? "";
                const metNorm = m.norm !== null && m.value >= m.norm;
                // Qiymat o'zgarmagan bo'lsa saqlash keraksiz — har saqlash
                // normalar tarixiga YANGI qator yozadi, dublikat to'planmasin.
                const changed = draft !== asDraft(m.norm);
                return (
                  <div key={m.key} className="flex items-center gap-1.5">
                    <span className="text-xs text-slate-500">{m.label}:</span>
                    <span
                      className={cn(
                        "text-xs font-medium tabular-nums",
                        !m.tracked || m.norm === null
                          ? "text-slate-400"
                          : metNorm
                            ? "text-emerald-600"
                            : "text-amber-600"
                      )}
                      title={
                        m.tracked
                          ? "Bugungi haqiqiy qiymat (CRM yoki qo'lda kiritilgan)"
                          : "Kuzatilmayapti — bu xodimga CRM ID biriktirilmagan"
                      }
                    >
                      {m.tracked ? m.value : "❔"}
                    </span>
                    <span className="text-slate-300">/</span>
                    {row.original.can_edit ? (
                      <>
                        <Input
                          type="number"
                          min={0}
                          step={1}
                          value={draft}
                          placeholder="yo'q"
                          aria-label={`${row.original.full_name} — ${m.label} normasi`}
                          onChange={(e) => {
                            dirtyRef.current.add(draftKey);
                            setDrafts((prev) => ({ ...prev, [draftKey]: e.target.value }));
                          }}
                          // Enter bilan saqlash — har safar sichqonchaga
                          // o'tishga hojat qolmasin (ro'yxat uzun).
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && changed) {
                              e.preventDefault();
                              saveMetric(row.original.user_id, m.key);
                            }
                          }}
                          className="h-8 w-20"
                        />
                        <Button
                          variant="link"
                          size="sm"
                          className="h-8 px-1 text-xs"
                          disabled={savingKey === draftKey || !changed}
                          onClick={() => saveMetric(row.original.user_id, m.key)}
                        >
                          {savingKey === draftKey ? "Saqlanmoqda..." : "Saqlash"}
                        </Button>
                      </>
                    ) : (
                      <span className="text-sm">{m.norm ?? "—"}</span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        },
      },
    ],
    [drafts, savingKey] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Xodimlarni UCH guruhga ajratamiz — har birida qilinadigan ish BOSHQA,
  // shuning uchun bitta uzun ro'yxatda aralashib yotmasin (egasining talabi
  // 2026-08-14: "hali norma belgilanmaganlar boshqa joyda ko'rinib tursin").
  const groups = useMemo(() => {
    const withNorm: TeamNormRow[] = [];   // normasi bor — kundalik boshqaruv
    const needsNorm: TeamNormRow[] = [];  // ko'rsatkichi bor, normasi yo'q — ISH SHU YERDA
    const noMetrics: TeamNormRow[] = [];  // lavozimiga ko'rsatkich biriktirilmagan
    (query.data ?? []).forEach((row) => {
      if (row.metrics.length === 0) noMetrics.push(row);
      else if (row.metrics.some((m) => m.norm !== null)) withNorm.push(row);
      else needsNorm.push(row);
    });
    return { withNorm, needsNorm, noMetrics };
  }, [query.data]);

  const tableProps = {
    columns,
    isLoading: query.isLoading,
    error: query.error ? query.error.message : null,
    onRetry: () => query.refetch(),
    searchPlaceholder: "Xodim bo'yicha qidirish...",
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Xodimlar normalari"
        description={
          'Har bir xodimga FAQAT o\'z lavozimiga biriktirilgan ko\'rsatkichlar chiqadi ("Lavozimlar" bo\'limida sozlanadi). Chapdagi son — bugungi haqiqiy natija (CRM yoki qo\'lda kiritilgan), o\'ngdagi maydon — norma. Siz faqat o\'zingiz boshqaradigan xodimlarni tahrirlay olasiz.'
        }
      />

      {/* Normasi yo'q — ENG TEPADA, chunki e'tibor talab qiladigan yagona ro'yxat */}
      {groups.needsNorm.length > 0 && (
        <section>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-700">
            <span className="rounded bg-amber-100 px-2 py-0.5">
              Norma belgilanmagan — {groups.needsNorm.length} ta
            </span>
          </h2>
          <p className="mb-3 text-xs text-slate-500">
            Bu xodimlarning lavozimida ko'rsatkich bor, lekin norma hali qo'yilmagan.
          </p>
          <DataTable {...tableProps} data={groups.needsNorm} />
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">
          Normasi belgilangan{groups.withNorm.length > 0 ? ` — ${groups.withNorm.length} ta` : ""}
        </h2>
        <DataTable
          {...tableProps}
          data={groups.withNorm}
          empty={{ icon: Target, text: "Hozircha normasi belgilangan xodim yo'q." }}
        />
      </section>

      {/* Bu yerda ish norma qo'yish EMAS — avval lavozimga ko'rsatkich kerak */}
      {groups.noMetrics.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-500">
            Ko'rsatkich biriktirilmagan — {groups.noMetrics.length} ta
          </h2>
          <p className="mb-3 text-xs text-slate-500">
            Bu xodimlarga norma qo'yib bo'lmaydi: lavozimi yo'q yoki lavozimiga
            ko'rsatkich biriktirilmagan.{" "}
            <Link to="/positions" className="text-primary hover:underline">
              Lavozimlar bo'limi
            </Link>
            dan ko'rsatkich qo'shing.
          </p>
          <DataTable {...tableProps} data={groups.noMetrics} />
        </section>
      )}
    </div>
  );
}
