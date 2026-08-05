/**
 * Ma'lumot tayyorligi — oylik/jarima hisobidan oldin ko'riladigan "bo'sh joylar".
 * UX-B: Attendance.tsx dan alohida komponentga ko'chirildi; "Oylik jadval"
 * tabida tanlangan oy davri bilan ko'rsatiladi.
 */
import { format } from "date-fns";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type AttendanceReadiness, type ReadinessIssue } from "@/lib/api";
import { useAttendanceReadiness } from "@/lib/queries";

export default function ReadinessSection({
  dateFrom,
  dateTo,
}: {
  dateFrom: string;
  dateTo: string;
}) {
  const query = useAttendanceReadiness({ date_from: dateFrom, date_to: dateTo });
  const data: AttendanceReadiness | undefined = query.data;

  const groups: { key: keyof AttendanceReadiness; label: string; hint: string }[] = [
    { key: "no_schedule", label: "Ish jadvali yo'q", hint: "kechikish taxminiy hisoblanadi" },
    { key: "open_checkouts", label: "«Ketdim» yopilmagan", hint: "ishlangan vaqt 0 bo'lib qolgan" },
    { key: "auto_closed", label: "Avtomatik yopilgan", hint: "ishlangan vaqt taxminiy" },
    { key: "pending_excused", label: "Sababli kun hal qilinmagan", hint: "jarimani bekor qilishi mumkin" },
    { key: "no_face", label: "Yuz ro'yxatdan o'tmagan", hint: "umuman check-in qila olmaydi" },
  ];

  if (query.isLoading) return <Skeleton className="h-24 w-full rounded-xl" />;
  if (query.error || !data) return null;

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
                    {items.slice(0, 12).map((it, i) => (
                      <span
                        key={`${it.user_id}-${it.date ?? i}`}
                        className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                        title={it.detail ?? undefined}
                      >
                        {it.full_name}
                        {it.date && ` · ${format(new Date(it.date), "dd.MM")}`}
                      </span>
                    ))}
                    {items.length > 12 && (
                      <span className="px-1 text-xs text-slate-500">
                        va yana {items.length - 12} ta
                      </span>
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
