/**
 * «Bugun» tabi — jonli nazorat (UX-B, UX2-W1).
 *
 * Rahbarning ertalabki savollari shu yerda hal bo'ladi (boshqa sahifaga
 * o'tmasdan): kim kelmadi → «Eslatish» yoki «Sababli» (2 bosish), kim
 * kechikdi → ismma-ism ro'yxat, hammasiga birdan eslatish — bitta tugma.
 * Ismlar xodim profiliga havola (dashboard endi user_id qaytaradi).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bell,
  BellRing,
  CalendarCheck,
  CalendarOff,
  Hourglass,
  Pencil,
  UserX,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import EditAttendanceDialog, {
  type EditPreset,
} from "@/components/attendance/EditAttendanceDialog";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAttendanceDashboard,
  useRecordExcusedDayForUser,
  useRemindAllAttendance,
  useRemindAttendance,
} from "@/lib/queries";
import { fmtLocalTime as fmtTime } from "@/lib/utils";

/** Ba'zi ismlar bazada ortiqcha bo'shliq bilan ("Kamola ") — ko'rinishda tozalaymiz. */
const nm = (s: string) => s.trim();

/** UX2-W1 (A5): sabab tez-tanlash chiplari — HR har safar jumla yozmasin. */
const EXCUSE_PRESETS = ["Kasallik", "Oilaviy holat", "Ta'til", "Xizmat safari"];

export default function TodayTab({ active, canEdit }: { active: boolean; canEdit: boolean }) {
  const dashQuery = useAttendanceDashboard(active);
  const remind = useRemindAttendance();
  const remindAll = useRemindAllAttendance();
  const recordExcused = useRecordExcusedDayForUser();
  const dash = dashQuery.data;
  const s = dash?.summary;

  // A5: «Sababli» dialogi — xodim va sana ma'lum, faqat sabab so'raladi.
  const [excuseFor, setExcuseFor] = useState<{ userId: number; name: string } | null>(null);
  const [excuseReason, setExcuseReason] = useState("");
  // Bugungi vaqtni SHU YERDA tuzatish — rahbar «Oylik jadval» tabiga o'tib,
  // katak qidirib o'tirmasin (eng ko'p so'raladigan amal: xodim noto'g'ri
  // vaqtda bosgan yoki umuman bosmagan bugungi kunni to'g'rilash).
  const [editPreset, setEditPreset] = useState<EditPreset | null>(null);

  if (dashQuery.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[86px] rounded-xl" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (dashQuery.error) {
    // 4.8-band: xato ko'rsatilmasa rahbar "bugun hech narsa bo'lmagan" deb
    // tushunishi mumkin edi.
    return (
      <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        {dashQuery.error.message}
        <Button variant="outline" size="sm" onClick={() => dashQuery.refetch()}>
          Qayta urinish
        </Button>
      </div>
    );
  }

  // B5: null bo'lsa bo'sh oq ekran emas — skelet (ma'lumot hali kelmagan).
  if (!dash || !s) {
    return <Skeleton className="h-64 rounded-xl" />;
  }

  const attendedPct = s.working_today > 0 ? Math.round((s.checked_in_today / s.working_today) * 100) : 0;
  const lateList = dash.late_list ?? [];
  const remindable = dash.not_come.filter((p) => p.telegram_linked).length;

  /** Bugungi qatorlarda ko'rinadigan kichik «✎ tuzatish» tugmasi. */
  function EditBtn({
    userId,
    userName,
    checkIn,
    checkOut,
  }: {
    userId: number;
    userName: string;
    checkIn: string | null;
    checkOut: string | null;
  }) {
    if (!canEdit || !dash) return null;
    return (
      <button
        type="button"
        title="Vaqtni qo'lda tuzatish"
        className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-primary"
        onClick={() =>
          setEditPreset({
            userId,
            userName,
            date: dash.today,
            checkIn: checkIn ? fmtTime(checkIn) : null,
            checkOut: checkOut ? fmtTime(checkOut) : null,
            note: null,
          })
        }
      >
        <Pencil className="h-3.5 w-3.5" />
      </button>
    );
  }

  function submitExcuse() {
    if (!excuseFor) return;
    const reason = excuseReason.trim();
    if (reason.length < 3) {
      toast.error("Sababni yozing (kamida 3 belgi).");
      return;
    }
    recordExcused.mutate(
      { user_id: excuseFor.userId, reason },
      {
        onSuccess: () => {
          toast.success(`${nm(excuseFor.name)} — bugun sababli deb belgilandi.`);
          setExcuseFor(null);
          setExcuseReason("");
        },
      }
    );
  }

  return (
    <div className="space-y-4">
      {/* B7: ma'lumot qachon yangilangani + qo'lda yangilash — rahbar tabni
          fonda qoldirib qaytsa, eskirgan raqamga bilmay ishonmasin. */}
      <div className="flex items-center justify-end gap-2 text-xs text-slate-400">
        <span>
          Yangilangan:{" "}
          {new Date(dashQuery.dataUpdatedAt).toLocaleTimeString("uz-UZ", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        <button
          type="button"
          className="text-primary underline-offset-2 hover:underline disabled:opacity-50"
          disabled={dashQuery.isFetching}
          onClick={() => dashQuery.refetch()}
        >
          {dashQuery.isFetching ? "yangilanmoqda..." : "yangilash"}
        </button>
      </div>

      {/* Stat kartalar — 5 ta muhimi (UX-B: 8 -> 5) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {/* «Keldi X/Y» — progress bilan (StatCard'da meter yo'q, shu yerda kichik custom) */}
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-xs text-slate-500">Keldi</div>
              <div className="mt-1 text-2xl font-semibold text-slate-800">
                {s.checked_in_today}
                <span className="text-base font-medium text-slate-400">/{s.working_today}</span>
              </div>
            </div>
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <Users className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${Math.min(100, attendedPct)}%` }}
            />
          </div>
        </div>
        <StatCard label="Kechikdi" value={s.late_today} icon={Hourglass} warn={s.late_today > 0} />
        <StatCard label="Hozir ofisda" value={s.present_now} icon={CalendarCheck} />
        <StatCard
          label="Kelmagan"
          value={s.not_checked_in}
          icon={UserX}
          warn={s.not_checked_in > 0}
        />
        <StatCard label="Dam olishda" value={s.on_day_off} icon={CalendarOff} />
      </div>

      {/* Uch ustun: Kelmagan / Kechikdi / Ofisda-Ketdi */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            {/* A3: sarlavha soni endi stat karta bilan MOS (sababli alohida). */}
            <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
              <span>❌ Kelmagan ({dash.not_come.length})</span>
              {dash.not_come.length > 1 && remindable > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 border-indigo-200 bg-indigo-50 px-2 text-xs text-indigo-700 hover:bg-indigo-100"
                  disabled={remindAll.isPending}
                  onClick={() =>
                    remindAll.mutate(undefined, {
                      onSuccess: (r) => {
                        if (r.failed.length === 0) {
                          toast.success(`Hammaga eslatma yuborildi (${r.sent} kishi).`);
                        } else {
                          toast.warning(
                            `${r.sent} ta yuborildi, ${r.failed.length} ta yo'q: ` +
                              r.failed.map((f) => `${nm(f.full_name)} — ${f.reason}`).join("; ")
                          );
                        }
                      },
                    })
                  }
                >
                  <BellRing className="mr-1 h-3 w-3" />
                  {remindAll.isPending ? "Yuborilmoqda..." : `Hammaga eslatish (${remindable})`}
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {dash.not_come.length === 0 ? (
              <div className="text-sm text-slate-400">Hamma keldi 🎉</div>
            ) : (
              <ul className="space-y-1">
                {dash.not_come.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between gap-2 border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <Link
                      to={`/employees/${p.user_id}`}
                      className="min-w-0 truncate hover:text-primary hover:underline"
                    >
                      {nm(p.full_name)}
                      <span className="ml-1.5 text-xs tabular-nums text-slate-400">
                        · jadval {p.schedule_start}
                      </span>
                    </Link>
                    <span className="flex shrink-0 gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 border-indigo-200 bg-indigo-50 px-2 text-xs text-indigo-700 hover:bg-indigo-100"
                        disabled={remind.isPending}
                        title={
                          p.telegram_linked
                            ? "Bot orqali shaxsiy eslatma (kuniga ko'pi bilan 2 marta)"
                            : "Xodim Telegram botga ulanmagan — yetkazib bo'lmasligi mumkin"
                        }
                        onClick={() =>
                          remind.mutate(p.user_id, {
                            onSuccess: (r) =>
                              toast.success(
                                `${nm(p.full_name)}ga eslatma yuborildi (bugun ${r.sent_today}-marta).`
                              ),
                          })
                        }
                      >
                        <Bell className="mr-1 h-3 w-3" />
                        Eslatish
                      </Button>
                      {/* A5: sababli kunni SHU YERDAN belgilash — 2 bosish. */}
                      {canEdit && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 border-sky-200 bg-sky-50 px-2 text-xs text-sky-700 hover:bg-sky-100"
                          title="Bugunni sababli kun deb belgilash (kasallik, ta'til...)"
                          onClick={() => setExcuseFor({ userId: p.user_id, name: p.full_name })}
                        >
                          Sababli
                        </Button>
                      )}
                      {/* Xodim aslida kelgan-u, «Keldim» bosmagan bo'lsa —
                          vaqtni shu yerda qo'lda kiritish. */}
                      <EditBtn
                        userId={p.user_id}
                        userName={p.full_name}
                        checkIn={null}
                        checkOut={null}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {/* A3: sababli kunlilar endi ALOHIDA bo'limcha — «kelmagan» bilan
                aralashmaydi, sonlar zid chiqmaydi. */}
            {dash.excused_today.length > 0 && (
              <div className="mt-3 border-t border-slate-100 pt-2">
                <div className="mb-1 text-xs font-medium text-slate-500">
                  🌿 Sababli ({dash.excused_today.length})
                </div>
                <ul className="space-y-1">
                  {dash.excused_today.map((p) => (
                    <li key={p.user_id} className="flex items-center justify-between gap-2 py-1 text-sm">
                      <Link
                        to={`/employees/${p.user_id}`}
                        className="min-w-0 truncate text-slate-500 hover:text-primary hover:underline"
                      >
                        {nm(p.full_name)}
                      </Link>
                      <StatusBadge kind="attendance" status="excused" />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        {/* A4: KIM kechikdi — endi ismma-ism (eng kattasi tepada). */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">⏱ Kechikdi ({lateList.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {lateList.length === 0 ? (
              <div className="text-sm text-slate-400">Bugun hech kim kechikmadi 🎉</div>
            ) : (
              <ul className="space-y-1">
                {lateList.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between gap-2 border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <Link
                      to={`/employees/${p.user_id}`}
                      className="min-w-0 truncate hover:text-primary hover:underline"
                    >
                      {nm(p.user_name)}
                      {p.left && <span className="ml-1.5 text-xs text-slate-400">· ketgan</span>}
                    </Link>
                    <span className="flex shrink-0 items-center gap-1 tabular-nums text-slate-500">
                      {fmtTime(p.check_in_time)}
                      <span className="font-semibold text-rose-600">+{p.late_minutes} daq</span>
                      <EditBtn
                        userId={p.user_id}
                        userName={p.user_name}
                        checkIn={p.check_in_time}
                        checkOut={null}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">🏢 Ofisda ({dash.in_office.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {dash.in_office.length === 0 ? (
              <div className="text-sm text-slate-400">Hech kim yo'q</div>
            ) : (
              <ul className="space-y-1">
                {dash.in_office.map((p) => (
                  <li
                    key={p.user_id}
                    className="flex items-center justify-between border-t border-slate-100 py-1.5 text-sm first:border-t-0"
                  >
                    <Link
                      to={`/employees/${p.user_id}`}
                      className="min-w-0 truncate hover:text-primary hover:underline"
                    >
                      {nm(p.user_name)}
                    </Link>
                    <span className="flex shrink-0 items-center gap-1 tabular-nums text-slate-500">
                      {fmtTime(p.check_in_time)}
                      {p.late_minutes > 0 && (
                        <span className="font-semibold text-rose-600">+{p.late_minutes}</span>
                      )}
                      <EditBtn
                        userId={p.user_id}
                        userName={p.user_name}
                        checkIn={p.check_in_time}
                        checkOut={null}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {/* Ketdi — alohida karta o'rniga shu kartaning pastki bo'limi
                (uch ustunda joy ochish uchun; ketganlar ro'yxati odatda kun
                oxirida to'ladi, ertalab bo'sh turardi). */}
            {dash.left.length > 0 && (
              <div className="mt-3 border-t border-slate-100 pt-2">
                <div className="mb-1 text-xs font-medium text-slate-500">
                  🚪 Ketdi ({dash.left.length})
                </div>
                <ul className="space-y-1">
                  {dash.left.map((p) => (
                    <li key={p.user_id} className="flex items-center justify-between py-1 text-sm">
                      <Link
                        to={`/employees/${p.user_id}`}
                        className="min-w-0 truncate hover:text-primary hover:underline"
                      >
                        {nm(p.full_name)}
                      </Link>
                      <span className="flex shrink-0 items-center gap-1 tabular-nums text-xs text-slate-500">
                        {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)} ·{" "}
                        {Math.round((p.worked_minutes / 60) * 10) / 10} st
                        <EditBtn
                          userId={p.user_id}
                          userName={p.full_name}
                          checkIn={p.check_in_time}
                          checkOut={p.check_out_time}
                        />
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bugun dam olishdagilar — faqat kimdir bo'lsa (bo'sh karta shovqin) */}
      {dash.on_day_off.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">🌙 Bugun dam olishda ({dash.on_day_off.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {dash.on_day_off.map((p) => (
                <span
                  key={p.user_id}
                  className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600"
                >
                  {nm(p.full_name)}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-400">
              Ish jadvali bo'yicha dam kuni — kechikish va jarima hisoblanmaydi.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Bugungi harakatlar lentasi */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Bugungi harakatlar</CardTitle>
        </CardHeader>
        <CardContent>
          {dash.recent.length === 0 ? (
            <div className="text-sm text-slate-400">Hali yozuv yo'q</div>
          ) : (
            <ul className="space-y-2">
              {dash.recent.map((p) => (
                <li
                  key={`${p.user_id}-${p.check_in_time}`}
                  className="flex items-center justify-between text-sm"
                >
                  <Link
                    to={`/employees/${p.user_id}`}
                    className="hover:text-primary hover:underline"
                  >
                    {nm(p.user_name)}
                  </Link>
                  <span className="flex items-center gap-2 tabular-nums text-slate-500">
                    {fmtTime(p.check_in_time)} → {fmtTime(p.check_out_time)}
                    <StatusBadge kind="attendance" status={p.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Bugungi vaqtni qo'lda tuzatish — «Oylik jadval» tabidagi bilan
          AYNAN bir xil dialog (yagona komponent, bitta mantiq). */}
      {canEdit && (
        <EditAttendanceDialog
          open={editPreset !== null}
          row={null}
          preset={editPreset}
          onClose={() => setEditPreset(null)}
        />
      )}

      {/* A5: «Sababli» dialogi — xodim/sana ma'lum, faqat sabab. */}
      <Dialog
        open={excuseFor !== null}
        onOpenChange={(o) => {
          if (!o) {
            setExcuseFor(null);
            setExcuseReason("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {excuseFor ? `${nm(excuseFor.name)} — bugun sababli` : ""}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-slate-500">
            Darhol tasdiqlangan holda yoziladi (xodimga bot orqali bildiriladi), bugungi
            «kelmadi» hisobidan chiqadi.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {EXCUSE_PRESETS.map((r) => (
              <button
                key={r}
                type="button"
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  excuseReason === r
                    ? "border-sky-400 bg-sky-100 text-sky-800"
                    : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
                }`}
                onClick={() => setExcuseReason(r)}
              >
                {r}
              </button>
            ))}
          </div>
          <Input
            placeholder="Yoki sababni yozing..."
            value={excuseReason}
            onChange={(e) => setExcuseReason(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitExcuse()}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setExcuseFor(null)}>
              Bekor qilish
            </Button>
            <Button onClick={submitExcuse} disabled={recordExcused.isPending}>
              {recordExcused.isPending ? "Saqlanmoqda..." : "Belgilash"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
