/**
 * Xodim kabineti — «Ish kundaligi».
 *
 * Botda bu faqat QO'SHISH oqimi (bot/handlers/work_log.py): tugma → matn →
 * saqlandi. Web'da qo'shimcha ikki narsa bor: oylik ko'rinish (qaysi kunda
 * yozgan/yozmagan) va BUGUNGI yozuvni tahrirlash/o'chirish.
 *
 * QULF: `editable` bayrog'ini SERVER beradi (`date === bugun`, Toshkent
 * vaqti bo'yicha) — mijoz kun chegarasini o'zi hisoblamaydi. Ertangi kundan
 * yozuv hujjat bo'lib qoladi va faqat 🔒 ko'rinadi.
 *
 * Backend bir xil: bot yo'li ham, `POST /work-log/me` ham
 * `_add_entry_for_user` ga boradi — sana va manba bir joyda hal qilinadi.
 */
import { useState } from "react";
import { CalendarDays, Lock, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import MonthNav, { currentMonthKey } from "@/components/attendance/MonthNav";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  useAddMyWorkLogEntry,
  useDeleteMyWorkLogEntry,
  useEditMyWorkLogEntry,
  useMyWorkLog,
} from "@/lib/queries";
import type { WorkLogDay, WorkLogEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_LEN = 2000;

/** Mahalliy sana ISO ko'rinishida — `toISOString()` UTC'ga o'tkazadi va
 *  Toshkentda (+5) ertalab 05:00 gacha bir kun orqaga surardi (me/Excused.tsx). */
function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Bazadagi naive-UTC vaqt → mahalliy "HH:MM" (bot bilan bir xil ko'rinish). */
function localHm(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return Number.isNaN(d.getTime())
    ? "--:--"
    : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

const WEEKDAYS = ["Dush", "Sesh", "Chor", "Pay", "Juma", "Shan", "Yak"];
function weekdayName(iso: string): string {
  return WEEKDAYS[(new Date(iso + "T00:00:00").getDay() + 6) % 7];
}

/** Bitta yozuv qatori — bugungisi tahrirlanadi, o'tgani 🔒. */
function EntryRow({ entry }: { entry: WorkLogEntry }) {
  const edit = useEditMyWorkLogEntry();
  const remove = useDeleteMyWorkLogEntry();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.text);

  function save() {
    const text = draft.trim();
    if (text.length < 3) {
      toast.error("Juda qisqa — bajargan ishingizni to'liqroq yozing.");
      return;
    }
    edit.mutate(
      { entryId: entry.id, text },
      {
        onSuccess: () => {
          setEditing(false);
          toast.success("Yozuv yangilandi");
        },
      }
    );
  }

  if (editing) {
    return (
      <div className="space-y-2 px-4 py-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          maxLength={MAX_LEN}
          className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <div className="flex gap-2">
          <Button onClick={save} disabled={edit.isPending} className="h-9 text-xs">
            {edit.isPending ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setDraft(entry.text);
              setEditing(false);
            }}
            className="h-9 text-xs"
          >
            <X className="mr-1 h-3.5 w-3.5" />
            Bekor
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 whitespace-pre-line break-words text-sm text-slate-700">{entry.text}</p>
        <span className="shrink-0 text-xs tabular-nums text-slate-400">{localHm(entry.created_at)}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-3">
        {entry.updated_at && <span className="text-[11px] text-slate-400">tahrirlangan</span>}
        {entry.editable ? (
          <>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-primary"
            >
              <Pencil className="h-3 w-3" />
              Tahrirlash
            </button>
            <ConfirmDialog
              title="Yozuvni o'chirish"
              description="Bu yozuv kundalikdan olib tashlanadi. Davom etamizmi?"
              confirmLabel="O'chirish"
              destructive
              loading={remove.isPending}
              onConfirm={() =>
                remove.mutate(entry.id, { onSuccess: () => toast.success("Yozuv o'chirildi") })
              }
              trigger={
                <button
                  type="button"
                  className="flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-rose-600"
                >
                  <Trash2 className="h-3 w-3" />
                  O'chirish
                </button>
              }
            />
          </>
        ) : (
          <span className="flex items-center gap-1 text-[11px] text-slate-400">
            <Lock className="h-3 w-3" />
            Qulflangan
          </span>
        )}
      </div>
    </div>
  );
}

/** Bugungi kunga yangi yozuv qo'shish formasi. */
function AddForm() {
  const add = useAddMyWorkLogEntry();
  const [text, setText] = useState("");
  const canSubmit = text.trim().length >= 3 && !add.isPending;

  function submit() {
    if (!canSubmit) return;
    add.mutate(
      { text: text.trim() },
      {
        onSuccess: () => {
          setText("");
          toast.success("Saqlandi");
        },
      }
    );
  }

  return (
    <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4">
      <label className="block text-xs font-medium text-slate-500">Bugun nima qildingiz?</label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={MAX_LEN}
        placeholder="Masalan: 14 ta lid bilan gaplashdim, 3 ta ko'rsatuvga chiqdim"
        className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <Button onClick={submit} disabled={!canSubmit} className="h-11 w-full text-sm font-semibold">
        <Plus className="mr-1.5 h-4 w-4" />
        {add.isPending ? "Saqlanmoqda..." : "Qo'shish"}
      </Button>
      <p className="text-xs text-slate-400">
        Kun davomida bir necha marta yozsangiz bo'ladi. Yozuvni faqat o'sha kuni tahrirlash mumkin.
      </p>
    </div>
  );
}

/** Bir kunning kartasi. Ish kuni bo'lib yozuv yo'q bo'lsa — sariq ogohlantirish. */
function DayCard({ day, isToday }: { day: WorkLogDay; isToday: boolean }) {
  const empty = day.entries.length === 0;
  if (empty && !day.is_working) return null; // dam kuni va bo'sh — ko'rsatmaymiz

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border bg-white",
        empty ? "border-amber-200" : "border-slate-200",
        isToday && "ring-1 ring-primary"
      )}
    >
      <div className="flex items-baseline justify-between gap-2 border-b border-slate-100 px-4 py-2">
        <span className="text-sm font-semibold tabular-nums">
          {fmtDayMonth(day.date)}
          <span className="ml-1.5 text-xs font-normal text-slate-400">{weekdayName(day.date)}</span>
          {isToday && <span className="ml-1.5 text-xs font-medium text-primary">bugun</span>}
        </span>
        {empty ? (
          <span className="text-xs text-amber-600">yozuv yo'q</span>
        ) : (
          <span className="text-xs text-slate-400">{day.entries.length} ta</span>
        )}
      </div>
      {!empty && (
        <div className="divide-y divide-slate-100">
          {day.entries.map((e) => (
            <EntryRow key={e.id} entry={e} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MeWorkLog() {
  const [month, setMonth] = useState(currentMonthKey());
  const { data, isLoading, isPlaceholderData } = useMyWorkLog(month);
  const today = isoToday();

  // Yangi kun tepada — xodim oxirgi yozganini birinchi ko'radi.
  const days = [...(data?.days ?? [])]
    .filter((d) => d.date <= today)
    .reverse();

  return (
    <div className="space-y-4">
      {month === currentMonthKey() && <AddForm />}

      <div className="flex items-center justify-between gap-2">
        <MonthNav month={month} maxMonth={currentMonthKey()} onChange={setMonth} />
        {data && (
          <span className="text-xs text-slate-500">
            {data.logged_days}/{data.work_days} kun
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : !days.length ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          <CalendarDays className="mx-auto mb-2 h-6 w-6 text-slate-300" />
          Bu oyda hali yozuv yo'q.
        </p>
      ) : (
        <div className={cn("space-y-2", isPlaceholderData && "opacity-60")}>
          {days.map((d) => (
            <DayCard key={d.date} day={d} isToday={d.date === today} />
          ))}
        </div>
      )}
    </div>
  );
}
