/**
 * Kadr hujjatlari ro'yxati — BITTA komponent, ikki joyda (TZ 3.4 / S-11).
 *
 * Xodim kabineti («Hujjatlarim») va HR paneli («Kadr hujjatlari») bir xil
 * ro'yxatni ko'rsatadi; farqi faqat `canManage` — o'chirish tugmasi.
 * Loyihaning naqshi: bitta mantiq + ikki adapter.
 *
 * Muddat holatini SERVER hisoblaydi (`is_expired`, `days_left`) — bot,
 * sayt va kabinet bir xil javob bersin. Bu yerda faqat rang tanlanadi.
 */
import { AlertTriangle, FileArchive, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteDocument } from "@/lib/queries";
import type { EmployeeDocument } from "@/lib/api";

/** Muddat holatiga qarab rang va matn. Muddatsiz hujjat — belgi yo'q. */
function muddat(d: EmployeeDocument): { matn: string; klass: string } | null {
  if (d.days_left === null || d.days_left === undefined) return null;
  if (d.is_expired) {
    return {
      matn: `Muddati ${Math.abs(d.days_left)} kun oldin tugagan`,
      klass: "bg-rose-100 text-rose-800",
    };
  }
  if (d.days_left <= 30) {
    return { matn: `${d.days_left} kun qoldi`, klass: "bg-amber-100 text-amber-900" };
  }
  return { matn: `${d.expires_at} gacha`, klass: "bg-slate-100 text-slate-700" };
}

export default function DocumentList({
  documents,
  isLoading,
  canManage = false,
  emptyText = "Hali hujjat yo'q.",
}: {
  documents: EmployeeDocument[] | undefined;
  isLoading: boolean;
  canManage?: boolean;
  emptyText?: string;
}) {
  const del = useDeleteDocument();

  if (isLoading) return <Skeleton className="h-32 w-full" />;

  if (!documents?.length) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-slate-600">
        <FileArchive className="h-4 w-4 shrink-0" />
        {emptyText}
      </div>
    );
  }

  const expired = documents.filter((d) => d.is_expired).length;

  return (
    <div className="space-y-2">
      {expired > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {expired} ta hujjatning muddati o'tgan — yangilanishi kerak.
        </div>
      )}
      <ul className="divide-y rounded-lg border">
        {documents.map((d) => {
          const m = muddat(d);
          return (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2.5 text-sm">
              <FileArchive className="h-4 w-4 shrink-0 text-slate-400" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{d.name}</span>
                <span className="block text-xs text-slate-600">{d.doc_type_label}</span>
              </span>
              {m && (
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${m.klass}`}>
                  {m.matn}
                </span>
              )}
              {canManage && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  disabled={del.isPending}
                  onClick={async () => {
                    await del.mutateAsync(d.id);
                    toast.success(`«${d.name}» o'chirildi`);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-slate-500">
        Fayllar Telegram'da saqlanadi — botdagi «📁 Hujjatlarim» tugmasi orqali
        yuklab olasiz.
      </p>
    </div>
  );
}
