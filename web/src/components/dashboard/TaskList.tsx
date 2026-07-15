import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";
import { ClipboardList } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { type Task } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCancelTask, useDeleteTask, useTasks } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

/** Bugungi vazifalar jadvali — 20 soniyada bir avtomatik yangilanadi. */
export default function TaskList() {
  const { user } = useAuth();
  const canCancel = user?.role === "boss" || user?.role === "rop" || user?.role === "dasturchi";
  const isDasturchi = user?.role === "dasturchi";

  const qc = useQueryClient();
  const query = useTasks("today");
  const cancelTask = useCancelTask();
  const deleteTask = useDeleteTask();

  const [cancelling, setCancelling] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);

  // MVP uchun real-vaqt sinxronizatsiya shart emas — 20 soniyada bir polling yetarli
  useMemo(() => {
    qc.setQueryDefaults(["tasks"], { refetchInterval: 20_000 });
  }, [qc]);

  const columns = useMemo<ColumnDef<Task>[]>(() => {
    const cols: ColumnDef<Task>[] = [
      {
        accessorKey: "assigned_to_name",
        header: "Xodim",
        cell: ({ row }) => (
          <Link to={`/employees/${row.original.assigned_to}`} className="text-primary hover:underline">
            {row.original.assigned_to_name}
          </Link>
        ),
      },
      { accessorKey: "title", header: "Vazifa" },
      {
        accessorKey: "deadline",
        header: "Muddat",
        cell: ({ row }) =>
          row.original.deadline
            ? format(new Date(row.original.deadline), "dd.MM.yyyy, HH:mm")
            : "—",
      },
      {
        accessorKey: "status",
        header: "Holat",
        cell: ({ row }) => <StatusBadge kind="task" status={row.original.status} />,
      },
    ];
    if (canCancel || isDasturchi) {
      cols.push({
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          const task = row.original;
          const canCancelThis = canCancel && task.status !== "done" && task.status !== "cancelled";
          return (
            <div className="flex items-center justify-end gap-1 whitespace-nowrap">
              {canCancelThis && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-amber-600 hover:text-amber-700"
                  onClick={() => setCancelling(task)}
                >
                  Bekor qilish
                </Button>
              )}
              {isDasturchi && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="font-medium text-rose-700 hover:text-rose-800"
                  onClick={() => setDeleting(task)}
                >
                  Butunlay o'chirish
                </Button>
              )}
            </div>
          );
        },
      });
    }
    return cols;
  }, [canCancel, isDasturchi]);

  return (
    <div>
      <h3 className="mb-2 font-semibold">Bugungi vazifalar</h3>
      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        empty={{ icon: ClipboardList, text: "Bugun hali vazifa berilmagan." }}
      />

      <ConfirmDialog
        open={cancelling !== null}
        onOpenChange={(open) => !open && setCancelling(null)}
        title="Bu vazifani bekor qilishni tasdiqlaysizmi?"
        description={cancelling ? `«${cancelling.title}» — ${cancelling.assigned_to_name}` : undefined}
        confirmLabel="Bekor qilish"
        loading={cancelTask.isPending}
        onConfirm={() => {
          if (!cancelling) return;
          cancelTask.mutate(cancelling.id, {
            onSuccess: () => {
              toast.success("Vazifa bekor qilindi");
              setCancelling(null);
            },
          });
        }}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Vazifani bazadan BUTUNLAY o'chirmoqchimisiz?"
        description="Bu amalni ortga qaytarib bo'lmaydi."
        confirmLabel="Butunlay o'chirish"
        destructive
        loading={deleteTask.isPending}
        onConfirm={() => {
          if (!deleting) return;
          deleteTask.mutate(deleting.id, {
            onSuccess: () => {
              toast.success("Vazifa o'chirildi");
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}
