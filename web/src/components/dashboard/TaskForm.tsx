import { FormEvent, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { useCreateBulkTasks, useCreateTask, usePositions, useUsers } from "@/lib/queries";

const ROLE_LABELS: Record<string, string> = {
  employee: "Xodim",
  hr: "HR",
  rop: "ROP",
  boss: "Boshliq",
  dasturchi: "Dasturchi",
};

// Boshliq/Dasturchi ROP/HR/xodimga(+boshliqqa), ROP va HR esa faqat xodimga vazifa bera oladi.
const ASSIGNABLE_ROLES: Record<string, string> = {
  boss: "employee,rop,hr",
  dasturchi: "employee,rop,hr,boss",
  rop: "employee",
  hr: "employee",
};

// Ommaviy vazifa rejimlari (faqat Boshliq/Dasturchi)
const BULK_MODES: {
  key: string;
  label: string;
  targetType: "all_employees" | "role";
  roles?: string[];
}[] = [
  { key: "all", label: "👥 Barcha xodimlarga", targetType: "all_employees" },
  { key: "rops", label: "🧭 Barcha ROPlarga", targetType: "role", roles: ["rop"] },
  { key: "hrs", label: "🗂 Barcha HRlarga", targetType: "role", roles: ["hr"] },
  { key: "rophr", label: "🤝 ROP + HR (umumiy)", targetType: "role", roles: ["rop", "hr"] },
];

export default function TaskForm() {
  const { user } = useAuth();
  const canBulk = user?.role === "boss" || user?.role === "dasturchi";
  const roleFilter = user ? (ASSIGNABLE_ROLES[user.role] ?? "employee") : "employee";

  const usersQuery = useUsers(roleFilter);
  const positionsQuery = usePositions();
  const createTask = useCreateTask();
  const createBulk = useCreateBulkTasks();

  // "single" — bitta odamga; "all"/"rops"/"hrs"/"rophr" — ommaviy; "pos:<id>" — lavozimga
  const [targetMode, setTargetMode] = useState("single");
  const [assignedTo, setAssignedTo] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");

  const submitting = createTask.isPending || createBulk.isPending;

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setDeadline("");
    setAssignedTo("");
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title) return;
    if (targetMode === "single" && !assignedTo) {
      toast.error("Foydalanuvchi tanlang");
      return;
    }
    const common = {
      title,
      description: description || undefined,
      deadline: deadline ? new Date(deadline).toISOString() : null,
    };
    if (targetMode === "single") {
      createTask.mutate(
        { assigned_to: Number(assignedTo), ...common },
        {
          onSuccess: () => {
            toast.success("Vazifa berildi ✅");
            resetForm();
          },
        }
      );
    } else if (targetMode.startsWith("pos:")) {
      createBulk.mutate(
        { target_type: "position", position_id: Number(targetMode.slice(4)), ...common },
        {
          onSuccess: (result) => {
            toast.success(`Vazifa ${result.created} kishiga berildi ✅`);
            resetForm();
          },
        }
      );
    } else {
      const mode = BULK_MODES.find((m) => m.key === targetMode);
      if (!mode) return;
      createBulk.mutate(
        { target_type: mode.targetType, target_roles: mode.roles, ...common },
        {
          onSuccess: (result) => {
            toast.success(`Vazifa ${result.created} kishiga berildi ✅`);
            resetForm();
          },
        }
      );
    }
  };

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Yangi vazifa berish</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          {canBulk && (
            <div>
              <Label>Nishon</Label>
              <Select value={targetMode} onValueChange={setTargetMode}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">👤 Bitta odamga</SelectItem>
                  {BULK_MODES.map((m) => (
                    <SelectItem key={m.key} value={m.key}>
                      {m.label}
                    </SelectItem>
                  ))}
                  {positionsQuery.data?.map((p) => (
                    <SelectItem key={`pos:${p.id}`} value={`pos:${p.id}`}>
                      🏷 Lavozim: {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {targetMode === "single" && (
            <div>
              <Label>Kimga</Label>
              <Select value={assignedTo} onValueChange={setAssignedTo}>
                <SelectTrigger>
                  <SelectValue placeholder="— foydalanuvchi tanlang —" />
                </SelectTrigger>
                <SelectContent>
                  {usersQuery.data?.map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.full_name} ({ROLE_LABELS[u.role] ?? u.role})
                      {!u.bot_started ? " — bot ulanmagan" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label htmlFor="task-title">Nima</Label>
            <Input
              id="task-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="Vazifa nomi"
            />
          </div>
          <div>
            <Label htmlFor="task-desc">Tavsif (ixtiyoriy)</Label>
            <textarea
              id="task-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>
          <div>
            <Label htmlFor="task-deadline">Muddat</Label>
            <Input
              id="task-deadline"
              type="datetime-local"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Yuborilmoqda..." : "Vazifa berish"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
