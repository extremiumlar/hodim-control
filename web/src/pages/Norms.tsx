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
        cell: ({ row }) => {
          const hasAnyNorm = row.original.metrics.some((m) => m.norm !== null);
          return (
            <div className="flex flex-col gap-0.5">
              <Link
                to={`/employees/${row.original.user_id}`}
                className="text-primary hover:underline"
              >
                {row.original.full_name}
              </Link>
              {/* Normasi yo'q xodimni ro'yxatdan darrov topish uchun — ilgari
                  har bir maydonni ko'zdan kechirish kerak edi. */}
              {row.original.metrics.length > 0 && !hasAnyNorm && (
                <span className="w-fit rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">
                  norma yo'q
                </span>
              )}
            </div>
          );
        },
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

  return (
    <div>
      <PageHeader
        title="Xodimlar normalari"
        description={
          'Har bir xodimga o\'z lavozimidagi ko\'rsatkichlar chiqadi ("Lavozimlar" bo\'limida sozlanadi). Chapdagi son — bugungi haqiqiy natija (CRM yoki qo\'lda kiritilgan), o\'ngdagi maydon — norma. Siz faqat o\'zingiz boshqaradigan xodimlarni tahrirlay olasiz.'
        }
      />
      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        searchPlaceholder="Xodim bo'yicha qidirish..."
        empty={{ icon: Target, text: "Hozircha xodimlar yo'q." }}
      />
    </div>
  );
}
