import { FormEvent, useState } from "react";
import { Briefcase, Pencil, Power } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Position } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCreatePosition, usePositions, useUpdatePosition } from "@/lib/queries";

const METRIC_OPTIONS: { key: string; label: string }[] = [
  { key: "suhbat", label: "Suhbatlar" },
  { key: "tashrif", label: "Tashriflar" },
  { key: "video", label: "Videolar (mobilograf)" },
];

const MENU_OPTIONS: { key: string; label: string }[] = [
  { key: "tasks", label: "📋 Vazifalarim" },
  { key: "norm", label: "📊 Bugungi normam" },
  { key: "kpi", label: "💰 Oylik KPI'm" },
  { key: "excused", label: "🙋 Sababli kun so'rash" },
];

const MANAGER_OPTIONS: { key: string; label: string }[] = [
  { key: "rop", label: "ROP (sotuv boshlig'i)" },
  { key: "hr", label: "HR" },
];

interface Draft {
  name: string;
  metrics: string[];
  menuFlags: Record<string, boolean>;
  managedBy: string[];
}

const emptyDraft = (): Draft => ({
  name: "",
  metrics: ["suhbat", "tashrif"],
  menuFlags: { tasks: true, norm: true, kpi: true, excused: true },
  managedBy: [],
});

export default function Positions() {
  const { user: currentUser } = useAuth();
  const canManage = currentUser?.role === "boss" || currentUser?.role === "dasturchi";

  const query = usePositions(true);
  const createPosition = useCreatePosition();
  const updatePosition = useUpdatePosition();

  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [editingId, setEditingId] = useState<number | null>(null);

  const toggleListValue = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  const startEdit = (p: Position) => {
    setEditingId(p.id);
    setDraft({
      name: p.name,
      metrics: p.metrics ?? [],
      menuFlags: { tasks: true, norm: true, kpi: true, excused: true, ...(p.menu_flags ?? {}) },
      managedBy: p.managed_by_roles ?? [],
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraft(emptyDraft());
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const name = draft.name.trim();
    if (!name) {
      toast.error("Lavozim nomini kiriting");
      return;
    }
    const payload = {
      name,
      metrics: draft.metrics,
      menu_flags: draft.menuFlags,
      managed_by_roles: draft.managedBy,
    };
    if (editingId !== null) {
      updatePosition.mutate(
        { positionId: editingId, data: payload },
        {
          onSuccess: () => {
            toast.success("Lavozim saqlandi");
            cancelEdit();
          },
        }
      );
    } else {
      createPosition.mutate(payload, {
        onSuccess: () => {
          toast.success("Lavozim qo'shildi");
          cancelEdit();
        },
      });
    }
  };

  const submitting = createPosition.isPending || updatePosition.isPending;

  const columns: ColumnDef<Position>[] = [
    {
      accessorKey: "name",
      header: "Nomi",
      cell: ({ row }) => (
        <span className={!row.original.is_active ? "font-medium opacity-50" : "font-medium"}>
          {row.original.name}
        </span>
      ),
    },
    {
      id: "metrics",
      header: "Ko'rsatkichlar",
      enableSorting: false,
      cell: ({ row }) =>
        (row.original.metrics ?? [])
          .map((m) => METRIC_OPTIONS.find((o) => o.key === m)?.label ?? m)
          .join(", ") || "—",
    },
    {
      id: "managed_by",
      header: "Boshqaradi",
      enableSorting: false,
      cell: ({ row }) =>
        (row.original.managed_by_roles ?? [])
          .map((r) => MANAGER_OPTIONS.find((o) => o.key === r)?.label ?? r)
          .join(", ") || "Boshliq/Dasturchi",
    },
    {
      accessorKey: "is_active",
      header: "Holat",
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">Faol</Badge>
        ) : (
          <Badge variant="secondary">O'chirilgan</Badge>
        ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1 whitespace-nowrap">
          <Button variant="ghost" size="sm" onClick={() => startEdit(row.original)}>
            <Pencil className="mr-1 h-3.5 w-3.5" />
            Tahrirlash
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className={
              row.original.is_active
                ? "text-rose-600 hover:text-rose-700"
                : "text-emerald-600 hover:text-emerald-700"
            }
            onClick={() =>
              updatePosition.mutate(
                { positionId: row.original.id, data: { is_active: !row.original.is_active } },
                {
                  onSuccess: () =>
                    toast.success(
                      row.original.is_active ? "Lavozim o'chirildi" : "Lavozim tiklandi"
                    ),
                }
              )
            }
          >
            <Power className="mr-1 h-3.5 w-3.5" />
            {row.original.is_active ? "O'chirish" : "Tiklash"}
          </Button>
        </div>
      ),
    },
  ];

  if (!canManage) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-sm text-slate-500">
            Lavozimlarni faqat Boshliq yoki Dasturchi boshqara oladi.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div>
      <PageHeader
        title="Lavozimlar"
        description="Lavozim xodimning bot menyusi, kuzatiladigan ko'rsatkichlari va kim boshqarishini belgilaydi."
      />
      <div className="grid gap-6 md:grid-cols-3">
        <Card className="h-fit md:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {editingId !== null ? "Lavozimni tahrirlash" : "Yangi lavozim"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="pos-name">Nomi</Label>
                <Input
                  id="pos-name"
                  value={draft.name}
                  onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                  required
                  placeholder="masalan: Sotuvchi, Mobilograf"
                />
              </div>

              <div>
                <p className="mb-1 text-sm text-slate-600">Kuzatiladigan ko'rsatkichlar</p>
                <div className="space-y-1">
                  {METRIC_OPTIONS.map((opt) => (
                    <label key={opt.key} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.metrics.includes(opt.key)}
                        onChange={() =>
                          setDraft((d) => ({ ...d, metrics: toggleListValue(d.metrics, opt.key) }))
                        }
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <p className="mb-1 text-sm text-slate-600">Botda ko'rinadigan tugmalar</p>
                <div className="space-y-1">
                  {MENU_OPTIONS.map((opt) => (
                    <label key={opt.key} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.menuFlags[opt.key] ?? true}
                        onChange={() =>
                          setDraft((d) => ({
                            ...d,
                            menuFlags: {
                              ...d.menuFlags,
                              [opt.key]: !(d.menuFlags[opt.key] ?? true),
                            },
                          }))
                        }
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  "📈 Statistikam" tugmasi har doim ko'rinadi.
                </p>
              </div>

              <div>
                <p className="mb-1 text-sm text-slate-600">Kim boshqaradi (vazifa/norma)</p>
                <div className="space-y-1">
                  {MANAGER_OPTIONS.map((opt) => (
                    <label key={opt.key} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.managedBy.includes(opt.key)}
                        onChange={() =>
                          setDraft((d) => ({
                            ...d,
                            managedBy: toggleListValue(d.managedBy, opt.key),
                          }))
                        }
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Boshliq va Dasturchi har doim barcha lavozimlarni boshqaradi.
                </p>
              </div>

              <div className="flex gap-2">
                <Button type="submit" disabled={submitting} className="flex-1">
                  {submitting ? "Saqlanmoqda..." : editingId !== null ? "Saqlash" : "Qo'shish"}
                </Button>
                {editingId !== null && (
                  <Button type="button" variant="outline" onClick={cancelEdit}>
                    Bekor qilish
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="md:col-span-2">
          <DataTable
            columns={columns}
            data={query.data}
            isLoading={query.isLoading}
            error={query.error ? query.error.message : null}
            onRetry={() => query.refetch()}
            empty={{
              icon: Briefcase,
              text: 'Hozircha lavozim yo\'q — chapdagi formadan birinchi lavozimni qo\'shing (masalan "Sotuvchi", "Mobilograf").',
            }}
          />
        </div>
      </div>
    </div>
  );
}
