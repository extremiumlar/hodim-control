/**
 * Ish jadvali — ikki tab (UX-E):
 *   «Umumiy»      — barcha xodimlar bir jadvalda (J1); jadvalsizlar oshkor (J4);
 *   «Bitta xodim» — mavjud tahrirlash UI (tezkor sozlash, haftalik, override)
 *                   + boshqa xodimdan NUSXALASH (J2) + override ro'yxati
 *                   filtri (J3).
 */
import { useEffect, useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import { Copy, Trash2 } from "lucide-react";
import { toast } from "sonner";
import PageHeader from "@/components/PageHeader";
import ScheduleOverviewTab from "@/components/attendance/ScheduleOverviewTab";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type WorkDayEntry } from "@/lib/api";
import {
  useDeleteScheduleOverride,
  useScheduleOverrides,
  useSetScheduleOverride,
  useSetWeeklySchedule,
  useUsers,
  useWeeklySchedule,
} from "@/lib/queries";

const WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];
const WEEKDAYS_SHORT = ["Du", "Se", "Ch", "Pa", "Ju", "Sha", "Yak"];

function emptyWeek(): WorkDayEntry[] {
  return Array.from({ length: 7 }, (_, wd) => ({
    weekday: wd,
    is_working: wd < 6,
    start_time: wd < 6 ? "09:00" : null,
    end_time: wd < 6 ? "18:00" : null,
  }));
}

/** J2: boshqa xodimning haftalik andozasini FORMAGA yuklash (saqlamasdan). */
function CopyScheduleDialog({
  open,
  onClose,
  excludeId,
  onLoaded,
}: {
  open: boolean;
  onClose: () => void;
  excludeId: number | null;
  onLoaded: (days: WorkDayEntry[], fromName: string) => void;
}) {
  const usersQuery = useUsers();
  const [sourceId, setSourceId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) setSourceId("");
  }, [open]);

  const candidates = (usersQuery.data ?? []).filter((u) => u.id !== excludeId);

  async function load() {
    if (!sourceId) return;
    setLoading(true);
    try {
      const data = await api.getWeeklySchedule(Number(sourceId));
      const days = [...data.days].sort((a, b) => a.weekday - b.weekday);
      onLoaded(days, data.user_full_name);
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Jadvalni yuklab bo'lmadi");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Jadvalni nusxalash</DialogTitle>
          <DialogDescription>
            Tanlangan xodimning haftalik andozasi FORMAGA yuklanadi — ko'rib chiqib
            «Saqlash»ni o'zingiz bosasiz (avtomatik saqlanmaydi).
          </DialogDescription>
        </DialogHeader>
        <Select value={sourceId} onValueChange={setSourceId}>
          <SelectTrigger>
            <SelectValue placeholder="Kimdan nusxa olamiz?" />
          </SelectTrigger>
          <SelectContent>
            {candidates.map((u) => (
              <SelectItem key={u.id} value={String(u.id)}>
                {u.full_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Bekor qilish
          </Button>
          <Button onClick={load} disabled={!sourceId || loading}>
            {loading ? "Yuklanmoqda..." : "Yuklash"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SingleEmployeeEditor({
  selectedId,
  onSelectUser,
}: {
  selectedId: number | null;
  onSelectUser: (id: number) => void;
}) {
  const usersQuery = useUsers();
  const [week, setWeek] = useState<WorkDayEntry[]>(emptyWeek());

  // Yangi override formasi
  const [ovDate, setOvDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [ovWorking, setOvWorking] = useState(false);
  const [ovStart, setOvStart] = useState("09:00");
  const [ovEnd, setOvEnd] = useState("18:00");
  const [ovNote, setOvNote] = useState("");

  // Tezkor sozlash: bitta ish vaqti + dam kunlari → barcha ish kunlariga qo'llanadi
  const [quickStart, setQuickStart] = useState("09:00");
  const [quickEnd, setQuickEnd] = useState("18:00");
  const [restDays, setRestDays] = useState<number[]>([6]);

  const [copyOpen, setCopyOpen] = useState(false);
  // J3: override ro'yxati default oxirgi 30 kun + kelajak; hammasi — tugma bilan.
  const [showAllOverrides, setShowAllOverrides] = useState(false);

  const weeklyQuery = useWeeklySchedule(selectedId ?? 0, selectedId != null);
  const overridesQuery = useScheduleOverrides(
    selectedId ?? 0,
    showAllOverrides ? undefined : format(subDays(new Date(), 30), "yyyy-MM-dd"),
    undefined,
    selectedId != null
  );
  const saveWeekly = useSetWeeklySchedule();
  const saveOverride = useSetScheduleOverride();
  const deleteOverride = useDeleteScheduleOverride();

  useEffect(() => {
    if (weeklyQuery.data) {
      const days = [...weeklyQuery.data.days].sort((a, b) => a.weekday - b.weekday);
      setWeek(days);
      setRestDays(days.filter((d) => !d.is_working).map((d) => d.weekday));
      const firstWorking = days.find((d) => d.is_working && d.start_time && d.end_time);
      if (firstWorking) {
        setQuickStart(firstWorking.start_time!);
        setQuickEnd(firstWorking.end_time!);
      }
    }
  }, [weeklyQuery.data]);

  // 3.7-band: saqlanmagan o'zgarish bilan xodim almashtirishdan himoya.
  const isDirty = useMemo(() => {
    if (!weeklyQuery.data) return false;
    const original = [...weeklyQuery.data.days].sort((a, b) => a.weekday - b.weekday);
    return JSON.stringify(week) !== JSON.stringify(original);
  }, [week, weeklyQuery.data]);

  function trySelectUser(id: number) {
    if (
      isDirty &&
      !window.confirm(
        "Saqlanmagan o'zgarishlar bor. Xodimni almashtirsangiz ular yo'qoladi. Davom etasizmi?"
      )
    ) {
      return;
    }
    onSelectUser(id);
  }

  function toggleRestDay(wd: number) {
    setRestDays((prev) => (prev.includes(wd) ? prev.filter((d) => d !== wd) : [...prev, wd]));
  }

  function onApplyQuick() {
    if (selectedId == null) return;
    if (quickStart >= quickEnd) {
      toast.error("Tugash vaqti boshlanishdan kechroq bo'lishi kerak");
      return;
    }
    if (restDays.length === 7) {
      toast.error("Kamida bitta ish kuni qolishi kerak");
      return;
    }
    const days: WorkDayEntry[] = Array.from({ length: 7 }, (_, wd) => {
      const isRest = restDays.includes(wd);
      return {
        weekday: wd,
        is_working: !isRest,
        start_time: isRest ? null : quickStart,
        end_time: isRest ? null : quickEnd,
      };
    });
    setWeek(days);
    saveWeekly.mutate(
      { userId: selectedId, days },
      {
        onSuccess: () =>
          toast.success(
            `Saqlandi: ${quickStart}–${quickEnd}` +
              (restDays.length
                ? `, dam kunlari — ${restDays.map((d) => WEEKDAYS_SHORT[d]).join(", ")}`
                : ", dam kunisiz")
          ),
      }
    );
  }

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
    // 4.7-band: start<end tekshiruvi override formasida ham.
    if (ovWorking && ovStart >= ovEnd) {
      toast.error("Tugash vaqti boshlanishdan kechroq bo'lishi kerak");
      return;
    }
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
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={selectedId != null ? String(selectedId) : ""}
          onValueChange={(v) => trySelectUser(Number(v))}
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
      </div>

      {/* Tezkor sozlash */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Tezkor sozlash</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">Ish vaqti (har kuni)</div>
              <div className="flex items-center gap-2">
                <Input
                  type="time"
                  value={quickStart}
                  onChange={(e) => setQuickStart(e.target.value)}
                  className="h-9 w-auto"
                />
                <span className="text-slate-400">—</span>
                <Input
                  type="time"
                  value={quickEnd}
                  onChange={(e) => setQuickEnd(e.target.value)}
                  className="h-9 w-auto"
                />
              </div>
            </div>

            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">
                Dam kunlari (bosib tanlang)
              </div>
              <div className="flex flex-wrap gap-1">
                {WEEKDAYS_SHORT.map((label, wd) => {
                  const isRest = restDays.includes(wd);
                  return (
                    <button
                      key={wd}
                      type="button"
                      onClick={() => toggleRestDay(wd)}
                      title={WEEKDAYS[wd] + (isRest ? " — dam olish" : " — ish kuni")}
                      className={
                        "h-9 min-w-[44px] rounded-md border px-2 text-sm font-medium transition-colors " +
                        (isRest
                          ? "border-amber-300 bg-amber-100 text-amber-800"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")
                      }
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <Button
              onClick={onApplyQuick}
              disabled={saveWeekly.isPending || selectedId == null || weeklyQuery.isFetching}
            >
              {saveWeekly.isPending ? "Saqlanmoqda..." : "Qo'llash va saqlash"}
            </Button>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Belgilangan vaqt barcha ish kunlariga qo'llanadi; sariq tanlangan kunlar dam olish
            bo'ladi. Alohida kunni boshqacha qilish kerak bo'lsa — pastdagi haftalik jadvaldan
            o'zgartiring.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Haftalik andoza */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">Haftalik andoza (har hafta takrorlanadi)</CardTitle>
              {/* J2: yangi xodimga jadvalni qo'lda qayta terish o'rniga nusxalash */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCopyOpen(true)}
                disabled={selectedId == null}
              >
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                Nusxalash…
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {weeklyQuery.isLoading || weeklyQuery.isFetching ? (
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
            <Button
              className="mt-4"
              onClick={onSaveWeekly}
              disabled={saveWeekly.isPending || weeklyQuery.isFetching}
            >
              {saveWeekly.isPending ? "Saqlanmoqda..." : "Haftalik jadvalni saqlash"}
            </Button>
            {isDirty && (
              <p className="mt-2 text-xs text-amber-600">Saqlanmagan o'zgarishlar bor.</p>
            )}
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
                <p className="text-sm text-slate-400">
                  {showAllOverrides
                    ? "O'zgartirishlar yo'q."
                    : "Oxirgi 30 kun va kelajakda o'zgartirish yo'q."}
                </p>
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
              {/* J3: eski o'zgartirishlar default yashirin — ro'yxat cheksiz o'smasin */}
              <button
                type="button"
                className="pt-1 text-xs text-primary hover:underline"
                onClick={() => setShowAllOverrides((v) => !v)}
              >
                {showAllOverrides ? "Faqat so'nggilarini ko'rsatish" : "Hammasini ko'rsatish"}
              </button>
            </div>
          </CardContent>
        </Card>
      </div>

      <CopyScheduleDialog
        open={copyOpen}
        onClose={() => setCopyOpen(false)}
        excludeId={selectedId}
        onLoaded={(days, fromName) => {
          setWeek(days);
          setRestDays(days.filter((d) => !d.is_working).map((d) => d.weekday));
          toast.success(`${fromName} jadvali yuklandi — ko'rib chiqib «Saqlash»ni bosing.`);
        }}
      />
    </div>
  );
}

export default function WorkSchedule() {
  const usersQuery = useUsers();
  const [tab, setTab] = useState<"umumiy" | "bitta">("umumiy");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (usersQuery.data?.length && selectedId == null) {
      setSelectedId(usersQuery.data[0].id);
    }
  }, [usersQuery.data, selectedId]);

  return (
    <div className="space-y-4">
      <PageHeader title="Ish jadvali" />
      <Tabs value={tab} onValueChange={(v) => setTab(v as "umumiy" | "bitta")}>
        <TabsList>
          <TabsTrigger value="umumiy">Umumiy</TabsTrigger>
          <TabsTrigger value="bitta">Bitta xodim</TabsTrigger>
        </TabsList>
        <TabsContent value="umumiy" className="mt-4">
          <ScheduleOverviewTab
            onPick={(id) => {
              setSelectedId(id);
              setTab("bitta");
            }}
          />
        </TabsContent>
        <TabsContent value="bitta" className="mt-4">
          <SingleEmployeeEditor selectedId={selectedId} onSelectUser={setSelectedId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
