import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import PageHeader from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { type WorkDayEntry } from "@/lib/api";
import {
  useDeleteScheduleOverride,
  useScheduleOverrides,
  useSetScheduleOverride,
  useSetWeeklySchedule,
  useUsers,
  useWeeklySchedule,
} from "@/lib/queries";

const WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];

function emptyWeek(): WorkDayEntry[] {
  return Array.from({ length: 7 }, (_, wd) => ({
    weekday: wd,
    is_working: wd < 6,
    start_time: wd < 6 ? "09:00" : null,
    end_time: wd < 6 ? "18:00" : null,
  }));
}

export default function WorkSchedule() {
  const usersQuery = useUsers();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [week, setWeek] = useState<WorkDayEntry[]>(emptyWeek());

  // Yangi override formasi
  const [ovDate, setOvDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [ovWorking, setOvWorking] = useState(false);
  const [ovStart, setOvStart] = useState("09:00");
  const [ovEnd, setOvEnd] = useState("18:00");
  const [ovNote, setOvNote] = useState("");

  useEffect(() => {
    if (usersQuery.data?.length && selectedId == null) {
      setSelectedId(usersQuery.data[0].id);
    }
  }, [usersQuery.data, selectedId]);

  const weeklyQuery = useWeeklySchedule(selectedId ?? 0, selectedId != null);
  const overridesQuery = useScheduleOverrides(selectedId ?? 0, undefined, undefined, selectedId != null);
  const saveWeekly = useSetWeeklySchedule();
  const saveOverride = useSetScheduleOverride();
  const deleteOverride = useDeleteScheduleOverride();

  useEffect(() => {
    if (weeklyQuery.data) {
      setWeek([...weeklyQuery.data.days].sort((a, b) => a.weekday - b.weekday));
    }
  }, [weeklyQuery.data]);

  function updateDay(wd: number, patch: Partial<WorkDayEntry>) {
    setWeek((prev) => prev.map((d) => (d.weekday === wd ? { ...d, ...patch } : d)));
  }

  function onSaveWeekly() {
    if (selectedId == null) return;
    for (const d of week) {
      if (d.is_working && (!d.start_time || !d.end_time)) {
        toast.error(`${WEEKDAYS[d.weekday]}: ish kuni uchun vaqt kerak`);
        return;
      }
      if (d.is_working && d.start_time! >= d.end_time!) {
        toast.error(`${WEEKDAYS[d.weekday]}: tugash vaqti kechroq bo'lishi kerak`);
        return;
      }
    }
    saveWeekly.mutate(
      { userId: selectedId, days: week },
      { onSuccess: () => toast.success("Haftalik jadval saqlandi") }
    );
  }

  function onAddOverride() {
    if (selectedId == null) return;
    saveOverride.mutate(
      {
        userId: selectedId,
        data: {
          date: ovDate,
          is_working: ovWorking,
          start_time: ovWorking ? ovStart : null,
          end_time: ovWorking ? ovEnd : null,
          note: ovNote || null,
        },
      },
      {
        onSuccess: () => {
          setOvNote("");
          toast.success("O'zgartirish saqlandi");
        },
      }
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Ish jadvali">
        <Select
          value={selectedId != null ? String(selectedId) : ""}
          onValueChange={(v) => setSelectedId(Number(v))}
        >
          <SelectTrigger className="min-w-[220px]">
            <SelectValue placeholder="Xodim tanlang" />
          </SelectTrigger>
          <SelectContent>
            {usersQuery.data?.map((u) => (
              <SelectItem key={u.id} value={String(u.id)}>
                {u.full_name} ({u.role})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Haftalik andoza */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Haftalik andoza (har hafta takrorlanadi)</CardTitle>
          </CardHeader>
          <CardContent>
            {weeklyQuery.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 7 }).map((_, i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {week.map((d) => (
                  <div key={d.weekday} className="flex items-center gap-2 text-sm">
                    <label className="flex w-28 items-center gap-2">
                      <input
                        type="checkbox"
                        checked={d.is_working}
                        onChange={(e) => updateDay(d.weekday, { is_working: e.target.checked })}
                      />
                      {WEEKDAYS[d.weekday]}
                    </label>
                    {d.is_working ? (
                      <>
                        <Input
                          type="time"
                          value={d.start_time ?? ""}
                          onChange={(e) => updateDay(d.weekday, { start_time: e.target.value })}
                          className="h-8 w-auto"
                        />
                        <span>—</span>
                        <Input
                          type="time"
                          value={d.end_time ?? ""}
                          onChange={(e) => updateDay(d.weekday, { end_time: e.target.value })}
                          className="h-8 w-auto"
                        />
                      </>
                    ) : (
                      <span className="text-slate-400">dam olish</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <Button className="mt-4" onClick={onSaveWeekly} disabled={saveWeekly.isPending}>
              {saveWeekly.isPending ? "Saqlanmoqda..." : "Haftalik jadvalni saqlash"}
            </Button>
          </CardContent>
        </Card>

        {/* Aniq sana o'zgartirishlari */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Aniq sana o'zgartirishi (bayram, almashtirilgan smena)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  type="date"
                  value={ovDate}
                  onChange={(e) => setOvDate(e.target.value)}
                  className="h-8 w-auto"
                />
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={ovWorking}
                    onChange={(e) => setOvWorking(e.target.checked)}
                  />
                  Ish kuni
                </label>
                {ovWorking && (
                  <>
                    <Input
                      type="time"
                      value={ovStart}
                      onChange={(e) => setOvStart(e.target.value)}
                      className="h-8 w-auto"
                    />
                    <span>—</span>
                    <Input
                      type="time"
                      value={ovEnd}
                      onChange={(e) => setOvEnd(e.target.value)}
                      className="h-8 w-auto"
                    />
                  </>
                )}
              </div>
              <Input
                type="text"
                placeholder="Izoh (masalan: Bayram)"
                value={ovNote}
                onChange={(e) => setOvNote(e.target.value)}
              />
              <Button variant="secondary" onClick={onAddOverride} disabled={saveOverride.isPending}>
                {saveOverride.isPending ? "Saqlanmoqda..." : "O'zgartirishni qo'shish"}
              </Button>
            </div>

            <div className="mt-4 space-y-1">
              {overridesQuery.isLoading ? (
                <Skeleton className="h-16 w-full" />
              ) : overridesQuery.data?.length === 0 ? (
                <p className="text-sm text-slate-400">O'zgartirishlar yo'q.</p>
              ) : (
                overridesQuery.data?.map((o) => (
                  <div
                    key={o.id}
                    className="flex items-center justify-between border-b border-slate-100 py-1 text-sm"
                  >
                    <span>
                      {format(new Date(o.date), "dd.MM.yyyy")} —{" "}
                      {o.is_working ? (
                        <b>
                          {o.start_time}–{o.end_time}
                        </b>
                      ) : (
                        <span className="text-amber-600">dam olish</span>
                      )}
                      {o.note ? ` (${o.note})` : ""}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-600 hover:text-rose-700"
                      onClick={() =>
                        selectedId != null &&
                        deleteOverride.mutate(
                          { userId: selectedId, day: o.date },
                          { onSuccess: () => toast.success("O'zgartirish o'chirildi") }
                        )
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
