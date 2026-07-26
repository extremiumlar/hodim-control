import { FormEvent, useState } from "react";
import { format } from "date-fns";
import { Check, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "@/components/DataTable";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type OvertimeEntry } from "@/lib/api";
import {
  useCreateOvertimeEntry,
  useDecideOvertimeEntry,
  useOvertimeEntries,
  useUsers,
} from "@/lib/queries";

function NewEntryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const usersQuery = useUsers();
  const create = useCreateOvertimeEntry();
  const [userId, setUserId] = useState<number | null>(null);
  const [date, setDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [minutes, setMinutes] = useState("");
  const [note, setNote] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const m = Number(minutes);
    if (!userId || !m || m <= 0) {
      toast.error("Xodim va musbat daqiqa kiriting");
      return;
    }
    create.mutate(
      { user_id: userId, date, minutes: m, note: note || null },
      {
        onSuccess: () => {
          toast.success("Qo'shimcha ish kiritildi — tasdiqlash kutilmoqda");
          setMinutes("");
          setNote("");
          onClose();
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Qo'shimcha ish kiritish</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label>Xodim</Label>
            <Select value={userId ? String(userId) : undefined} onValueChange={(v) => setUserId(Number(v))}>
              <SelectTrigger>
                <SelectValue placeholder="Tanlang" />
              </SelectTrigger>
              <SelectContent>
                {(usersQuery.data ?? []).map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="ne-date">Sana</Label>
            <Input id="ne-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </div>
          <div>
            <Label htmlFor="ne-min">Daqiqa</Label>
            <Input
              id="ne-min"
              type="number"
              min={1}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="ne-note">Izoh (ixtiyoriy)</Label>
            <Input id="ne-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Bekor qilish
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Saqlanmoqda..." : "Kiritish"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function Overtime() {
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [creating, setCreating] = useState(false);
  const query = useOvertimeEntries(statusFilter ? { status_filter: statusFilter } : {});
  const decide = useDecideOvertimeEntry();

  const columns: ColumnDef<OvertimeEntry>[] = [
    {
      accessorKey: "date",
      header: "Sana",
      cell: ({ row }) => format(new Date(row.original.date), "dd.MM.yyyy"),
    },
    { accessorKey: "user_full_name", header: "Xodim" },
    { accessorKey: "minutes", header: "Daqiqa" },
    {
      accessorKey: "source",
      header: "Manba",
      cell: ({ row }) => (row.original.source === "manual" ? "Qo'lda" : "Avtomatik (davomat)"),
    },
    { accessorKey: "note", header: "Izoh", cell: ({ row }) => row.original.note ?? "—" },
    {
      accessorKey: "status",
      header: "Holat",
      cell: ({ row }) => <StatusBadge kind="overtime" status={row.original.status} />,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) =>
        row.original.status === "pending" ? (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="text-emerald-600 hover:text-emerald-700"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { entryId: row.original.id, decision: "approved" },
                  { onSuccess: () => toast.success("Tasdiqlandi") }
                )
              }
            >
              <Check className="mr-1 h-3.5 w-3.5" />
              Tasdiqlash
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-rose-600 hover:text-rose-700"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { entryId: row.original.id, decision: "rejected" },
                  { onSuccess: () => toast.success("Rad etildi") }
                )
              }
            >
              <X className="mr-1 h-3.5 w-3.5" />
              Rad etish
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Qo'shimcha ish" description="Xodimlarning qo'shimcha ish so'rovlarini tasdiqlash.">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">Kutilmoqda</SelectItem>
            <SelectItem value="approved">Tasdiqlangan</SelectItem>
            <SelectItem value="rejected">Rad etilgan</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Kiritish
        </Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        error={query.error ? query.error.message : null}
        onRetry={() => query.refetch()}
        empty={{ text: "Bu holatda yozuv yo'q." }}
      />

      <NewEntryDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
