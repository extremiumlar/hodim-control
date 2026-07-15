import { useEffect, useMemo, useState } from "react";
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

export default function Norms() {
  const query = useTeamNorms();
  const updateNorm = useUpdateNorm();
  // Kalit: `${userId}:${metricKey}` — har bir xodimning har bir ko'rsatkichi uchun qoralama
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    if (!query.data) return;
    const next: Record<string, string> = {};
    query.data.forEach((row) => {
      row.metrics.forEach((m) => {
        next[`${row.user_id}:${m.key}`] = m.norm?.toString() ?? "";
      });
    });
    setDrafts(next);
  }, [query.data]);

  const saveMetric = (userId: number, metric: string) => {
    const draftKey = `${userId}:${metric}`;
    const raw = drafts[draftKey] ?? "";
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 0) {
      toast.error("Qiymat manfiy bo'lmagan butun son bo'lishi kerak");
      return;
    }
    setSavingKey(draftKey);
    updateNorm.mutate(
      { user_id: userId, metric_type: metric, value },
      {
        onSuccess: () => toast.success("Norma saqlandi"),
        onSettled: () => setSavingKey(null),
      }
    );
  };

  const columns = useMemo<ColumnDef<TeamNormRow>[]>(
    () => [
      {
        accessorKey: "full_name",
        header: "Xodim",
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
        header: "Normalar",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-4">
            {row.original.metrics.map((m) => {
              const draftKey = `${row.original.user_id}:${m.key}`;
              const metNorm = m.norm !== null && m.value >= m.norm;
              return (
                <div key={m.key} className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">{m.label}:</span>
                  <span
                    className={cn(
                      "text-xs font-medium",
                      !m.tracked || m.norm === null
                        ? "text-slate-400"
                        : metNorm
                          ? "text-emerald-600"
                          : "text-amber-600"
                    )}
                    title={
                      m.tracked
                        ? "Bugungi haqiqiy qiymat (CRM/qo'lda)"
                        : "Kuzatilmayapti — CRM bog'lanmagan"
                    }
                  >
                    {m.tracked ? m.value : "❔"}
                  </span>
                  <span className="text-slate-300">/</span>
                  {row.original.can_edit ? (
                    <>
                      <Input
                        type="number"
                        value={drafts[draftKey] ?? ""}
                        onChange={(e) =>
                          setDrafts((prev) => ({ ...prev, [draftKey]: e.target.value }))
                        }
                        className="h-8 w-20"
                      />
                      <Button
                        variant="link"
                        size="sm"
                        className="h-8 px-1 text-xs"
                        disabled={savingKey === draftKey}
                        onClick={() => saveMetric(row.original.user_id, m.key)}
                      >
                        {savingKey === draftKey ? "Saqlanmoqda..." : "Saqlash"}
                      </Button>
                    </>
                  ) : (
                    <span>{m.norm ?? "—"}</span>
                  )}
                </div>
              );
            })}
          </div>
        ),
      },
    ],
    [drafts, savingKey] // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <div>
      <PageHeader
        title="Xodimlar normalari"
        description={
          'Ko\'rsatkichlar har bir xodimning lavozimiga qarab belgilanadi ("Lavozimlar" bo\'limida sozlanadi). Siz faqat o\'zingiz boshqaradigan xodimlarning normalarini o\'zgartira olasiz. "Bugungi" qiymat CRM (yoki qo\'lda kiritilgan) ma\'lumot asosida jonli ko\'rsatiladi.'
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
