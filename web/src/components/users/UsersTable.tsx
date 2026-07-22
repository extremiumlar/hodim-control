import { useEffect, useMemo, useState } from "react";
import { Users as UsersIcon } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import DataTable from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type User } from "@/lib/api";
import {
  useActivateUser,
  useDeactivateUser,
  useDeleteUser,
  usePositions,
  useResetAccount,
  useUpdateCrmExternalId,
  useUpdateRole,
  useUpdateUserPosition,
  useUsers,
} from "@/lib/queries";
import { api } from "@/lib/api";
import { ROLE_LABELS } from "./constants";

type PendingAction =
  | { type: "role"; user: User; role: string }
  | { type: "deactivate"; user: User }
  | { type: "reset"; user: User }
  | { type: "delete"; user: User };

/** Barcha foydalanuvchilar jadvali: rol/lavozim/CRM ID tahriri va amallar. */
export default function UsersTable({
  hasFullControl,
  isDasturchi,
  canSetPosition,
  onInviteLink,
}: {
  hasFullControl: boolean;
  isDasturchi: boolean;
  canSetPosition: boolean;
  onInviteLink: (link: string) => void;
}) {
  const usersQuery = useUsers(undefined, true);
  const positionsQuery = usePositions();
  const updateRole = useUpdateRole();
  const updatePosition = useUpdateUserPosition();
  const updateCrmId = useUpdateCrmExternalId();
  const deactivate = useDeactivateUser();
  const activate = useActivateUser();
  const resetAccount = useResetAccount();
  const deleteUser = useDeleteUser();

  const [crmDrafts, setCrmDrafts] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<PendingAction | null>(null);

  useEffect(() => {
    if (!usersQuery.data) return;
    const drafts: Record<number, string> = {};
    usersQuery.data.forEach((u) => {
      drafts[u.id] = u.crm_external_id ?? "";
    });
    setCrmDrafts(drafts);
  }, [usersQuery.data]);

  const showInviteLink = async (userId: number) => {
    try {
      const { invite_link, already_started } = await api.inviteLink(userId);
      if (already_started || !invite_link) {
        toast.info("Bu foydalanuvchi botni allaqachon ishga tushirgan.");
      } else {
        onInviteLink(invite_link);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Havolani olishda xatolik");
    }
  };

  const actionLoading =
    updateRole.isPending || deactivate.isPending || resetAccount.isPending || deleteUser.isPending;

  const confirmPending = () => {
    if (!pending) return;
    const done = () => setPending(null);
    if (pending.type === "role") {
      updateRole.mutate(
        { userId: pending.user.id, role: pending.role },
        { onSuccess: () => { toast.success("Rol o'zgartirildi"); done(); } }
      );
    } else if (pending.type === "deactivate") {
      deactivate.mutate(pending.user.id, {
        onSuccess: () => { toast.success("Foydalanuvchi o'chirildi (tiklash mumkin)"); done(); },
      });
    } else if (pending.type === "reset") {
      resetAccount.mutate(pending.user.id, {
        onSuccess: ({ invite_link }) => {
          toast.success("Yangi havola yaratildi");
          onInviteLink(invite_link);
          done();
        },
      });
    } else {
      deleteUser.mutate(pending.user.id, {
        onSuccess: () => { toast.success("Foydalanuvchi butunlay o'chirildi"); done(); },
      });
    }
  };

  const pendingDialog: { title: string; description?: string; confirmLabel: string; destructive: boolean } | null =
    pending &&
    (pending.type === "role"
      ? {
          title: `Rolni "${ROLE_LABELS[pending.role] ?? pending.role}"ga o'zgartirishni tasdiqlaysizmi?`,
          description: pending.user.full_name,
          confirmLabel: "O'zgartirish",
          destructive: false,
        }
      : pending.type === "deactivate"
        ? {
            title: "Bu foydalanuvchini o'chirishni tasdiqlaysizmi?",
            description: `${pending.user.full_name} — keyinroq tiklash mumkin.`,
            confirmLabel: "O'chirish",
            destructive: true,
          }
        : pending.type === "reset"
          ? {
              title: "Akkauntni qayta bog'laysizmi?",
              description:
                "Eski Telegram ulanishi bekor bo'ladi va yangi havola yaratiladi.",
              confirmLabel: "Qayta bog'lash",
              destructive: false,
            }
          : {
              title: `"${pending.user.full_name}"ni bazadan BUTUNLAY o'chirmoqchimisiz?`,
              description: isDasturchi
                ? "Bu amalni ORTGA QAYTARIB BO'LMAYDI. Dasturchi sifatida bu xodimga norma belgilangan yoki vazifa berilgan bo'lsa ham, unga bog'liq BARCHA ma'lumotlar (vazifa, norma, kunlik natija, mobilograf, sababli kun, bonus) birga o'chiriladi."
                : "Bu amalni ORTGA QAYTARIB BO'LMAYDI. Agar bu foydalanuvchida tarixiy ma'lumot (vazifa, norma va h.k.) bo'lsa, o'chirish rad etiladi.",
              confirmLabel: isDasturchi ? "Majburiy o'chirish" : "Butunlay o'chirish",
              destructive: true,
            });

  const columns = useMemo<ColumnDef<User>[]>(() => {
    const cols: ColumnDef<User>[] = [
      {
        accessorKey: "full_name",
        header: "Ism",
        cell: ({ row }) => (
          <span className={!row.original.is_active ? "opacity-50" : ""}>{row.original.full_name}</span>
        ),
      },
      {
        accessorKey: "role",
        header: "Rol",
        cell: ({ row }) => (
          <select
            value={row.original.role}
            onChange={(e) => setPending({ type: "role", user: row.original, role: e.target.value })}
            className="rounded border px-2 py-1 text-xs"
          >
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        ),
      },
      {
        accessorKey: "position_id",
        header: "Lavozim",
        cell: ({ row }) =>
          canSetPosition ? (
            <select
              value={row.original.position_id ?? ""}
              disabled={updatePosition.isPending}
              onChange={(e) =>
                updatePosition.mutate(
                  {
                    userId: row.original.id,
                    positionId: e.target.value ? Number(e.target.value) : null,
                  },
                  { onSuccess: () => toast.success("Lavozim o'zgartirildi") }
                )
              }
              className="rounded border px-2 py-1 text-xs disabled:opacity-50"
            >
              <option value="">— yo'q —</option>
              {positionsQuery.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : (
            (row.original.position?.name ?? "—")
          ),
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
        accessorKey: "bot_started",
        header: "Bot",
        cell: ({ row }) => (
          <span className={row.original.bot_started ? "text-emerald-700" : "text-slate-400"}>
            {row.original.bot_started ? "✅ ulangan" : "— kutilmoqda"}
            {row.original.is_seat && " · o'rin"}
          </span>
        ),
      },
    ];

    if (hasFullControl) {
      cols.push({
        id: "crm_id",
        header: "CRM ID",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Input
              value={crmDrafts[row.original.id] ?? ""}
              onChange={(e) =>
                setCrmDrafts((prev) => ({ ...prev, [row.original.id]: e.target.value }))
              }
              placeholder="masalan email@uysot"
              className="h-7 w-40 text-xs"
            />
            <Button
              variant="link"
              size="sm"
              className="h-7 px-1 text-xs"
              disabled={updateCrmId.isPending}
              onClick={() =>
                updateCrmId.mutate(
                  {
                    userId: row.original.id,
                    crmExternalId: crmDrafts[row.original.id]?.trim() || null,
                  },
                  { onSuccess: () => toast.success("CRM ID saqlandi") }
                )
              }
            >
              Saqlash
            </Button>
          </div>
        ),
      });
    }

    cols.push({
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => {
        const u = row.original;
        return (
          <div className="flex items-center justify-end gap-1 whitespace-nowrap">
            {u.is_seat ? (
              <Button
                variant="link"
                size="sm"
                className="h-7 px-1 text-xs"
                onClick={() => showInviteLink(u.id)}
                title="O'rin uchun havola doimiy qayta olinadi — eski egasi almashadi"
              >
                Havolani yangilash
              </Button>
            ) : !u.bot_started ? (
              <Button variant="link" size="sm" className="h-7 px-1 text-xs" onClick={() => showInviteLink(u.id)}>
                Havola olish
              </Button>
            ) : (
              <Button
                variant="link"
                size="sm"
                className="h-7 px-1 text-xs"
                onClick={() => setPending({ type: "reset", user: u })}
              >
                Qayta bog'lash
              </Button>
            )}
            {u.is_active ? (
              <Button
                variant="link"
                size="sm"
                className="h-7 px-1 text-xs text-rose-600"
                onClick={() => setPending({ type: "deactivate", user: u })}
              >
                O'chirish
              </Button>
            ) : (
              <Button
                variant="link"
                size="sm"
                className="h-7 px-1 text-xs text-emerald-600"
                onClick={() => activate.mutate(u.id, { onSuccess: () => toast.success("Tiklandi") })}
              >
                Tiklash
              </Button>
            )}
            {hasFullControl && (
              <Button
                variant="link"
                size="sm"
                className="h-7 px-1 text-xs font-medium text-rose-800"
                title={
                  isDasturchi ? "Dasturchi: norma/vazifa borligiga qaramay to'liq o'chiradi" : undefined
                }
                onClick={() => setPending({ type: "delete", user: u })}
              >
                {isDasturchi ? "Majburiy o'chirish" : "Butunlay o'chirish"}
              </Button>
            )}
          </div>
        );
      },
    });
    return cols;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasFullControl, isDasturchi, canSetPosition, crmDrafts, positionsQuery.data]);

  return (
    <div>
      <h3 className="mb-2 font-semibold">Barcha foydalanuvchilar</h3>
      <DataTable
        columns={columns}
        data={usersQuery.data}
        isLoading={usersQuery.isLoading}
        error={usersQuery.error ? usersQuery.error.message : null}
        onRetry={() => usersQuery.refetch()}
        searchPlaceholder="Ism bo'yicha qidirish..."
        empty={{ icon: UsersIcon, text: "Foydalanuvchilar yo'q." }}
      />
      {pendingDialog && (
        <ConfirmDialog
          open={pending !== null}
          onOpenChange={(open) => !open && setPending(null)}
          title={pendingDialog.title}
          description={pendingDialog.description}
          confirmLabel={pendingDialog.confirmLabel}
          destructive={pendingDialog.destructive}
          loading={actionLoading}
          onConfirm={confirmPending}
        />
      )}
    </div>
  );
}
