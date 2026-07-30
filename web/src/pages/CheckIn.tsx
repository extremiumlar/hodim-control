import { useEffect, useState } from "react";
import { CheckCircle2, LogIn, LogOut, MapPin, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import FaceCapture from "@/components/FaceCapture";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type Attendance } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useMyAttendanceToday,
  useMyCheckIn,
  useMyCheckOut,
  useMyLateStatus,
  useRegisterMyFace,
} from "@/lib/queries";
import { type LiveResult } from "@/lib/face";
import { fmtLocalTime as fmtTime, translateGeoError } from "@/lib/utils";

type Action = "check-in" | "check-out";

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Brauzer geolokatsiyani qo'llab-quvvatlamaydi."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    });
  });
}

// Ba'zi brauzerlarda uz-UZ locale oy/kun nomlari yo'q ("M07 14, Tue" chiqadi) —
// shuning uchun o'zbekcha nomlar qo'lda.
const UZ_MONTHS = [
  "yanvar", "fevral", "mart", "aprel", "may", "iyun",
  "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
];
const UZ_WEEKDAYS = ["Yakshanba", "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"];

function fmtDateUz(d: Date): string {
  return `${UZ_WEEKDAYS[d.getDay()]}, ${d.getDate()}-${UZ_MONTHS[d.getMonth()]}`;
}

/** Joriy oydagi kechikish limiti holati — 1.5-band (Shaffoflik): xodim
 * jarima boshlanishidan OLDIN ogohlantiriladi. Qoida umuman sozlanmagan
 * bo'lsa (free_limit_minutes=null) hech narsa ko'rsatilmaydi. */
function LateStatusCard() {
  const { data } = useMyLateStatus();
  if (!data || data.free_limit_minutes == null) return null;

  const overLimit = (data.remaining_minutes ?? 0) <= 0;
  return (
    <div
      className={`rounded-xl border p-4 text-sm ${
        overLimit ? "border-rose-200 bg-rose-50 text-rose-800" : "border-slate-200 bg-white text-slate-700"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">Bu oy kechikish limiti</span>
        <span className="font-semibold">
          {data.used_minutes} / {data.free_limit_minutes} daq
        </span>
      </div>
      {overLimit ? (
        <p className="mt-1 text-xs">
          Limit tugagan — shu kundan keyingi har bir kechikkan kunga jarima yoziladi
          {data.fined_days_so_far > 0 && ` (bu oy allaqachon ${data.fined_days_so_far} kun jarimalandi)`}.
        </p>
      ) : (
        <p className="mt-1 text-xs text-slate-500">
          Yana {data.remaining_minutes} daqiqa bepul kechikish qoldi.
        </p>
      )}
    </div>
  );
}

/** Muvaffaqiyatli check-in/outdan keyingi yashil tasdiq ekrani. */
function SuccessScreen({
  action,
  att,
  onClose,
}: {
  action: Action;
  att: Attendance;
  onClose: () => void;
}) {
  const isIn = action === "check-in";
  // overflow-y-auto — landscape'da (masalan 640x360) ikonka+sarlavha+3 qator+
  // tugma 312px ga sig'masligi mumkin; «Yopish» tugmasiga yetish shart.
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-emerald-600 p-6">
      <div className="w-full max-w-sm text-center text-white">
        <CheckCircle2 className="mx-auto mb-4 h-20 w-20" />
        <h2 className="text-2xl font-bold">{isIn ? "Keldingiz!" : "Ketdingiz!"}</h2>
        <p className="mt-1 text-emerald-100">
          {isIn ? "Kelish muvaffaqiyatli qayd etildi." : "Ketish muvaffaqiyatli qayd etildi."}
        </p>

        <div className="mt-6 space-y-3 rounded-2xl bg-white/10 p-4 text-left text-sm">
          <div className="flex items-center justify-between">
            <span className="text-emerald-100">Vaqt</span>
            <span className="text-lg font-bold">
              {fmtTime(isIn ? att.check_in_time : att.check_out_time)}
            </span>
          </div>
          {isIn && (
            <div className="flex items-center justify-between">
              <span className="text-emerald-100">Kechikish</span>
              <span className="font-semibold">
                {att.late_minutes > 0 ? `${att.late_minutes} daqiqa` : "Yo'q ✅"}
              </span>
            </div>
          )}
          {!isIn && (
            <div className="flex items-center justify-between">
              <span className="text-emerald-100">Ishlangan vaqt</span>
              <span className="font-semibold">
                {att.worked_minutes > 0
                  ? `${Math.floor(att.worked_minutes / 60)} soat ${att.worked_minutes % 60} daq`
                  : "—"}
              </span>
            </div>
          )}
          {att.check_in_distance_m != null && (
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 text-emerald-100">
                <MapPin className="h-4 w-4" />
                Ofisgacha masofa
              </span>
              <span className="font-semibold">~{att.check_in_distance_m} m</span>
            </div>
          )}
        </div>

        <Button
          onClick={onClose}
          className="mt-6 h-12 w-full bg-white text-base font-semibold text-emerald-700 hover:bg-emerald-50"
        >
          Yopish
        </Button>
      </div>
    </div>
  );
}

export default function CheckIn() {
  const { user, refreshUser } = useAuth();
  const todayQuery = useMyAttendanceToday();
  const checkIn = useMyCheckIn();
  const checkOut = useMyCheckOut();
  const registerFace = useRegisterMyFace();

  const [statusMsg, setStatusMsg] = useState("");
  const [time, setTime] = useState(new Date());
  const [showFace, setShowFace] = useState<null | Action>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [success, setSuccess] = useState<{ action: Action; att: Attendance } | null>(null);
  // 4.1-band: server rad etsa (masalan ofisdan tashqarida), xabar endi faqat
  // tez o'tib ketuvchi toast emas — modal ICHIDA doimiy ko'rinadi va modal
  // YOPILMAYDI, shuning uchun xodim butun GPS/kamera oqimini qaytadan
  // boshlamay (FaceCapture hali ochiq), DARHOL qayta urinishi mumkin.
  const [checkError, setCheckError] = useState<string | null>(null);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const att = todayQuery.data ?? null;
  const busy = checkIn.isPending || checkOut.isPending;

  async function startCheck(action: Action) {
    if (!user?.has_face) {
      toast.error("Avval yuzingizni ro'yxatdan o'tkazing.");
      setShowRegister(true);
      return;
    }
    setCheckError(null);
    setStatusMsg("Joylashuv tekshirilmoqda...");
    try {
      // Faqat ruxsat/xatoni ERTA ushlash uchun — qiymatning o'zi ishlatilmaydi
      // (3.6-band: yuz tasdiqlangandan keyin QAYTA olinadi, aks holda eskiradi).
      await getPosition();
      setShowFace(action);
      setStatusMsg("");
    } catch (e: any) {
      setStatusMsg("");
      toast.error(translateGeoError(e));
    }
  }

  function onFaceCaptured(result: LiveResult | any) {
    if (!showFace) return;
    const action = showFace;
    setCheckError(null);
    setStatusMsg("Joylashuv aniqlanmoqda...");
    // 3.6-band: GPS yuz tasdiqlashdan OLDIN emas, ENDI (yuborishdan darhol
    // oldin) olinadi. Model yuklanishi (~10s) + qayta urinishlar 2-3 daqiqagacha
    // cho'zilishi mumkin edi — oldin olingan joylashuv shuncha vaqt eskirib,
    // xodim allaqachon ofisga kirgan bo'lsa ham eski (masalan tashqaridagi)
    // koordinata yuborilardi.
    getPosition()
      .then((pos) => {
        setStatusMsg("Serverga yuborilmoqda...");
        const body = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          face_descriptor: result.descriptor,
          // 4.5-band: default ENG YUQORI ishonch (1.0) emas — server "liveness
          // yuborilmadi" holatini "mukammal tiriklik" deb noto'g'ri talqin
          // qilmasligi uchun eng PAST (0) qo'yiladi.
          liveness: result.liveness ?? 0,
          accuracy: pos.coords.accuracy ?? null,
        };
        const mutation = action === "check-in" ? checkIn : checkOut;
        mutation.mutate(body, {
          onSuccess: (updated) => {
            setStatusMsg("");
            setShowFace(null);
            setSuccess({ action, att: updated });
          },
          onError: (err: any) => {
            setStatusMsg("");
            // 4.1-band: modal ATAYLAB yopilmaydi — FaceCapture hali ochiq,
            // xodim xabarni o'qib, kamerani darhol qayta sinab ko'rishi mumkin.
            setCheckError(err?.message || "Xatolik yuz berdi. Qaytadan urinib ko'ring.");
          },
        });
      })
      .catch((e: any) => {
        setStatusMsg("");
        setCheckError(translateGeoError(e));
      });
  }

  function onFaceRegistered(result: any) {
    setStatusMsg("Yuz saqlanmoqda...");
    registerFace.mutate(result.descriptor, {
      onSuccess: async (res) => {
        await refreshUser();
        setShowRegister(false);
        setStatusMsg("");
        if (res.status === "pending_approval") {
          toast.success("So'rov HR/rahbarga yuborildi — tasdiqlangach yuzingiz yangilanadi.");
        } else {
          toast.success("Yuz muvaffaqiyatli ro'yxatdan o'tkazildi!");
        }
      },
      onError: () => setStatusMsg(""),
    });
  }

  const hasCheckIn = !!att?.check_in_time;
  const hasCheckOut = !!att?.check_out_time;

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <Card>
        <CardContent className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Bugungi davomat</h2>
              <p className="text-sm text-slate-500">{fmtDateUz(time)}</p>
            </div>
            <div className="text-3xl font-bold tabular-nums text-primary">
              {time.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </div>
          </div>

          {todayQuery.isLoading ? (
            <div className="mb-5 grid grid-cols-2 gap-4">
              <Skeleton className="h-20 rounded-lg" />
              <Skeleton className="h-20 rounded-lg" />
            </div>
          ) : (
            <div className="mb-5 grid grid-cols-2 gap-4">
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="mb-1 text-xs text-slate-500">Keldim</div>
                <div className="text-2xl font-semibold">{fmtTime(att?.check_in_time ?? null)}</div>
                {att && att.late_minutes > 0 && (
                  <div className="mt-1 text-xs text-rose-600">Kechikish: {att.late_minutes} daq</div>
                )}
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="mb-1 text-xs text-slate-500">Ketdim</div>
                <div className="text-2xl font-semibold">{fmtTime(att?.check_out_time ?? null)}</div>
                {att && att.early_leave_minutes > 0 && (
                  <div className="mt-1 text-xs text-amber-600">
                    Erta ketish: {att.early_leave_minutes} daq
                  </div>
                )}
              </div>
            </div>
          )}

          {user && !user.has_face && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              ⚠️ Check-in qilish uchun avval{" "}
              <button onClick={() => setShowRegister(true)} className="font-semibold underline">
                yuzingizni ro'yxatdan o'tkazing
              </button>
            </div>
          )}

          <div className="flex gap-3">
            <Button
              className="h-14 flex-1 bg-emerald-600 text-base font-semibold hover:bg-emerald-700"
              disabled={hasCheckIn || busy || !user?.has_face}
              onClick={() => startCheck("check-in")}
            >
              <LogIn className="mr-2 h-5 w-5" />
              Keldim
            </Button>
            <Button
              className="h-14 flex-1 bg-rose-600 text-base font-semibold hover:bg-rose-700"
              disabled={!hasCheckIn || hasCheckOut || busy || !user?.has_face}
              onClick={() => startCheck("check-out")}
            >
              <LogOut className="mr-2 h-5 w-5" />
              Ketdim
            </Button>
          </div>

          {statusMsg && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-base text-blue-700">
              {statusMsg}
            </div>
          )}

          <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4" />
            <span>GPS + yuz tasdiqlash (Face ID) bilan tekshiriladi.</span>
          </div>
        </CardContent>
      </Card>

      <LateStatusCard />

      {user?.has_face && !showRegister && (
        <div className="text-center">
          <button onClick={() => setShowRegister(true)} className="text-sm text-primary hover:underline">
            Yuzni qayta ro'yxatdan o'tkazish
          </button>
        </div>
      )}

      {showRegister && (
        <Card>
          <CardContent className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">Yuzni ro'yxatdan o'tkazish</h3>
              <button
                onClick={() => setShowRegister(false)}
                className="text-sm text-slate-400 hover:text-slate-700"
              >
                Yopish
              </button>
            </div>
            <FaceCapture
              mode="register"
              onResult={onFaceRegistered}
              onCancel={() => setShowRegister(false)}
              buttonLabel={registerFace.isPending ? "Saqlanmoqda..." : "Yuzimni saqlash"}
              disabled={registerFace.isPending}
            />
          </CardContent>
        </Card>
      )}

      {showFace && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          {/* max-h + overflow: past ekranda (yoki landscape'da) video + matn +
              tugma modaldan chiqib ketardi va scroll qilib bo'lmasdi — xodim
              «Keldim» tugmasiga yeta olmasdi. 100dvh (100vh emas): mobil
              brauzerda manzil satri paydo bo'lganda vh o'zgarmay qoladi. */}
          <div className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">
                Yuz tasdiqlash ({showFace === "check-in" ? "Keldim" : "Ketdim"})
              </h3>
              <button
                onClick={() => {
                  setShowFace(null);
                  setStatusMsg("");
                  setCheckError(null);
                }}
                className="text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            {checkError && (
              <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
                {checkError}
              </div>
            )}
            <FaceCapture
              mode="verify"
              onResult={onFaceCaptured}
              onCancel={() => {
                setShowFace(null);
                setStatusMsg("");
                setCheckError(null);
              }}
              buttonLabel={showFace === "check-in" ? "Keldim" : "Ketdim"}
              disabled={busy}
            />
          </div>
        </div>
      )}

      {success && (
        <SuccessScreen action={success.action} att={success.att} onClose={() => setSuccess(null)} />
      )}
    </div>
  );
}
