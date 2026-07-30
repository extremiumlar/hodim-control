/**
 * Xodim kabineti — «Vazifalarim».
 *
 * Botdagi «📋 Vazifalarim» bilan bir xil ma'lumot: bot `/tasks/my/{tg}` ni,
 * bu sahifa `/tasks/me` ni chaqiradi, ikkalasi ham `_my_tasks_for_user` ga
 * boradi (oxirgi 20 vazifa, yangi birinchi).
 *
 * WEB BOTDAN USTUN: botda ro'yxat FAQAT o'qish uchun — vazifani yopish uchun
 * xodim eski eslatma xabarini topib, undagi «✅» tugmasini bosishi kerak
 * (bot/handlers/tasks.py: `task_done:` callback). Bu yerda esa ro'yxatdan
 * to'g'ridan-to'g'ri yopiladi.
 *
 * Ruxsat: backend faqat `assigned_to` xodimga ruxsat beradi va so'rov tanasi
 * yo'q (shaxs tokendan) — mijoz boshqa birovning vazifasini yopa olmaydi.
 */
import { Check, ClipboardList, Clock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompleteMyTask, useMyTasks } from "@/lib/queries";
import type { Task } from "@/lib/api";
import { cn } from "@/lib/utils";

// bot/handlers/menu.py: STATUS_EMOJI bilan bir xil
const STATUS_LABEL: Record<Task["status"], { text: string; cls: string }> = {
  pending: { text: "🕓 Bajarilmoqda", cls: "text-slate-500" },
  done: { text: "✅ Bajarildi", cls: "text-emerald-600" },
  overdue: { text: "⏰ Muddati o'tdi", cls: "text-rose-600" },
  cancelled: { text: "🚫 Bekor qilindi", cls: "text-slate-400" },
};

/** Botdagi format: "muddat: YYYY-MM-DD HH:MM" (deadline[:16], T -> probel). */
function fmtDeadline(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

function TaskCard({ task }: { task: Task }) {
  const complete = useCompleteMyTask();
  const st = STATUS_LABEL[task.status];
  // Yopish faqat ochiq vazifalarda: bajarilgan yoki bekor qilinganda tugma
  // ko'rsatilmaydi (backend idempotent, lekin tugma ham chalkashtirmasin).
  const canComplete = task.status === "pending" || task.status === "overdue";

  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-4",
        task.status === "overdue" ? "border-rose-200" : "border-slate-200",
        task.status === "cancelled" && "opacity-60"
      )}
    >
      <div className="text-sm font-medium">{task.title}</div>
      {task.description && (
        <p className="mt-1 whitespace-pre-line text-xs text-slate-500">{task.description}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className={st.cls}>{st.text}</span>
        {task.deadline && (
          <span className="flex items-center gap-1 text-slate-400">
            <Clock className="h-3.5 w-3.5" />
            {fmtDeadline(task.deadline)}
          </span>
        )}
      </div>

      {canComplete && (
        <Button
          onClick={() => complete.mutate(task.id)}
          disabled={complete.isPending}
          // h-11 — barmoq uchun qulay tegish maydoni
          className="mt-3 h-11 w-full bg-emerald-600 text-sm font-semibold hover:bg-emerald-700"
        >
          <Check className="mr-1.5 h-4 w-4" />
          {complete.isPending ? "Saqlanmoqda..." : "Bajardim"}
        </Button>
      )}
    </div>
  );
}

export default function Tasks() {
  const { data, isLoading, isError } = useMyTasks();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center text-sm text-rose-700">
        Vazifalarni yuklab bo'lmadi. Internetni tekshirib qaytadan urinib ko'ring.
      </p>
    );
  }

  // Botdagi bilan bir xil matn (bot/handlers/menu.py: show_tasks)
  if (!data.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <ClipboardList className="mx-auto mb-3 h-8 w-8 text-slate-300" />
        <p className="text-sm text-slate-600">Hozircha sizga biriktirilgan vazifa yo'q.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((t) => (
        <TaskCard key={t.id} task={t} />
      ))}
      <p className="px-1 text-xs text-slate-400">Oxirgi 20 vazifa ko'rsatiladi.</p>
    </div>
  );
}
