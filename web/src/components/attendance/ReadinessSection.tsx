/**
 * Ma'lumot tayyorligi — oylik/jarima hisobidan oldin ko'riladigan "bo'sh joylar".
 *
 * UX2-A7: chiplar endi O'LIK EMAS — har biri muammoni HAL QILISH yo'liga
 * olib boradi: jadval yo'q → o'sha xodimning jadval muharriri; yopilmagan/
 * avto-yopilgan kun → tuzatish dialogi (onFixDay orqali); sababli kutmoqda →
 * sababli kunlar sahifasi. «va yana N ta» ham endi ochiladi.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type AttendanceReadiness, type ReadinessIssue } from "@/lib/api";
import { useAttendanceReadiness } from "@/lib/queries";

type GroupKey = "no_schedule" | "open_checkouts" | "auto_closed" | "pending_excused" | "no_face";

export default function ReadinessSection({
  dateFrom,
  dateTo,
  onFixDay,
}: {
  dateFrom: string;
  dateTo: string;
  /** Yopilmagan/avto-yopilgan kun chipi bosilganda tuzatish dialogini ochish. */
  onFixDay?: (issue: ReadinessIssue) => void;
}) {
  const query = useAttendanceReadiness({ date_from: dateFrom, date_to: dateTo });
  const data: AttendanceReadiness | undefined = query.data;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const groups: { key: GroupKey; label: string; hint: string }[] = [
    { key: "no_schedule", label: "Ish jadvali yo'q", hint: "kechikish taxminiy hisoblanadi" },
    { key: "open_checkouts", label: "«Ketdim» yopilmagan", hint: "ishlangan vaqt 0 bo'lib qolgan" },
    { key: "auto_closed", label: "Avtomatik yopilgan", hint: "ishlangan vaqt taxminiy" },
    { key: "pending_excused", label: "Sababli kun hal qilinmagan", hint: "jarimani bekor qilishi mumkin" },
    { key: "no_face", label: "Yuz ro'yxatdan o'tmagan", hint: "umuman check-in qila olmaydi" },
  ];

  if (query.isLoading) return <Skeleton className="h-24 w-full rounded-xl" />;
  // B5: xato endi JIMGINA yashirilmaydi — "muammo yo'q"dek ko'rinib qolardi.
  if (query.error) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        Tayyorlikni yuklab bo'lmadi: {query.error.message}
        <Button variant="outline" size="sm" onClick={() => query.refetch()}>
          Qayta urinish
        </Button>
      </div>
    );
  }
  if (!data) return null;

  /** Chip qaysi yo'l bilan hal qilinadi — guruhga qarab. */
  function chip(key: GroupKey, it: ReadinessIssue, i: number) {
    const label = (
      <>
        {it.full_name.trim()}
        {it.date && ` · ${format(new Date(it.date), "dd.MM")}`}
      </>
    );
    const cls =
      "rounded-md px-2 py-0.5 text-xs transition-colors";
    if (key === "no_schedule") {
      return (
        <Link
          key={`${it.user_id}-${i}`}
          to={`/work-schedule?tab=bitta&user=${it.user_id}`}
          className={`${cls} bg-slate-100 text-slate-700 underline-offset-2 hover:bg-primary/10 hover:text-primary hover:underline`}
          title="Jadvalini sozlash uchun bosing"
        >
          {label} ✎
        </Link>
      );
    }
    if ((key === "open_checkouts" || key === "auto_closed") && onFixDay) {
      return (
        <button
          key={`${it.user_id}-${it.date ?? i}`}
          type="button"
          className={`${cls} bg-slate-100 text-slate-700 hover:bg-primary/10 hover:text-primary`}
          title={it.detail ?? "Kunni tuzatish uchun bosing"}
          onClick={() => onFixDay(it)}
        >
          {label} ✎
        </button>
      );
    }
    if (key === "pending_excused") {
      return (
        <Link
          key={`${it.user_id}-${it.date ?? i}`}
          to="/excused-days"
          className={`${cls} bg-slate-100 text-slate-700 underline-offset-2 hover:bg-primary/10 hover:text-primary hover:underline`}
          title="Sababli kunlar sahifasida qaror qiling"
        >
          {label} →
        </Link>
      );
    }
    return (
      <span
        key={`${it.user_id}-${it.date ?? i}`}
        className={`${cls} bg-slate-100 text-slate-700`}
        title={it.detail ?? undefined}
      >
        {label}
      </span>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          {data.ok ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          )}
          Ma'lumot tayyorligi ({format(new Date(data.date_from), "dd.MM")}—
          {format(new Date(data.date_to), "dd.MM")})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.ok ? (
          <p className="text-sm text-slate-500">
            Bo'sh joy yo'q — davomat ma'lumoti oylik hisob uchun tayyor.
          </p>
        ) : (
          <ul className="space-y-3">
            {groups.map(({ key, label, hint }) => {
              const items = data[key] as ReadinessIssue[];
              if (!items.length) return null;
              const showAll = expanded[key];
              const visible = showAll ? items : items.slice(0, 12);
              return (
                <li key={key}>
                  <div className="mb-1 text-sm font-medium">
                    {label}{" "}
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                      {items.length}
                    </span>
                    <span className="ml-2 text-xs font-normal text-slate-500">— {hint}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {visible.map((it, i) => chip(key, it, i))}
                    {items.length > 12 && !showAll && (
                      <button
                        type="button"
                        className="px-1 text-xs text-primary underline"
                        onClick={() => setExpanded((e) => ({ ...e, [key]: true }))}
                      >
                        va yana {items.length - 12} ta — ko'rsatish
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
