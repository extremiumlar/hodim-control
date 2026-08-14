import { lazy, Suspense, useEffect, useState } from "react";
import { Check, CheckCircle2, LogIn, LogOut, MapPin, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import LateStatusCard from "@/components/LateStatusCard";
import PushEnableCard from "@/components/PushEnableCard";
import MyHistoryCard from "@/components/attendance/MyHistoryCard";
import TodayScheduleChip from "@/components/attendance/TodayScheduleChip";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type Attendance } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useMyAttendanceToday,
  useMyCheckIn,
  useMyCheckOut,
  useRegisterMyFace,
} from "@/lib/queries";
import { type LiveResult } from "@/lib/face";
import { cn, fmtLocalTime as fmtTime, translateGeoError } from "@/lib/utils";

// FaceCapture ATAYLAB lazy: u @vladmandic/face-api ni tortadi (~340 KB
// siqilgan holda). Tab-bar qo'shilgach /check-in xodimning KIRISH sahifasi
// bo'lib qoldi (HomeIndex shu yerga yo'naltiradi, PWA start_url ham shu) —
// ya'ni faqat jadvalini ko'rmoqchi bo'lgan xodim ham yuz kutubxonasini
// yuklardi. Endi u faqat kamera oqimi boshlanganda keladi.
// `LiveResult` — TIP importi, u kompilyatsiyada yo'qoladi va chunk tortmaydi.
const FaceCapture = lazy(() => import("@/components/FaceCapture"));

// UX2-MC3: modellar (~6.8 MB) ilgari FAQAT «Keldim» bosilgach yuklanardi —
// zaif tarmoqda xodim telefonni yuziga tutib 30-60 soniya kutardi. Endi sahifa
// ochilgach BO'SH VAQTDA chunk + modellar oldindan yuklab qo'yiladi (30 kunlik
// keshga tushadi); tugma bosilganda hammasi tayyor bo'ladi. Xatolar jim
// yutiladi — prefetch muvaffaqiyatsiz bo'lsa, eski (bosilganda yuklash) yo'l
// o'z-o'zidan ishlayveradi.
let modelsPrefetched = false;
function prefetchFaceModels() {
  if (modelsPrefetched) return;
  modelsPrefetched = true;
  const run = () =>
    import("@/components/FaceCapture")
      .then(() => import("@/lib/face"))
      .then((m) => m.loadModels())
      .catch(() => {
        modelsPrefetched = false; // keyingi urinishga ruxsat
      });
  if ("requestIdleCallback" in window) {
    (window as any).requestIdleCallback(run, { timeout: 5000 });
  } else {
    setTimeout(run, 1500);
  }
}

/** Lazy FaceCapture yuklanguncha — video idishi bilan bir xil o'lchamda. */
function FaceCaptureFallback() {
  return (
    <div className="flex aspect-[4/3] w-full max-w-md mx-auto items-center justify-center rounded-xl bg-black/90 text-sm text-white">
      <div className="text-center">
        <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-2 border-white border-t-transparent" />
        Kamera tayyorlanmoqda...
      </div>
    </div>
  );
}

type Action = "check-in" | "check-out";

/**
 * UX-D3: yuz tasdiqlash modalidagi qadam ko'rsatkichi — model yuklanayotgan
 * ~10 soniyada xodim "qotib qoldimi?" deb o'ylamasligi uchun qayerdaligini
 * ko'rsatib turadi. `done` — o'tilgan qadamlar soni (ular ✓ bilan).
 */
function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="mb-3 flex items-center gap-1.5 text-[11px] font-medium">
      {steps.map((label, i) => {
        const done = i < current;
        const activeStep = i === current;
        return (
          <div key={label} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && <span className="h-px w-3 shrink-0 bg-slate-200" />}
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                done && "bg-emerald-100 text-emerald-700",
                activeStep && "bg-primary text-primary-foreground",
                !done && !activeStep && "bg-slate-100 text-slate-400"
              )}
            >
              {done ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <span
              className={cn(
                "truncate",
                activeStep ? "text-slate-800" : done ? "text-emerald-700" : "text-slate-400"
              )}
            >
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

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

/** Muvaffaqiyatli check-in/outdan keyingi yashil tasdiq ekrani.
 *
 * UX2-qoldiq #1: endi 6 soniyada O'ZI yopiladi (pastda kamayuvchi chiziq) va
 * Android «orqaga»/ESC ham yopadi (ilgari oddiy fixed div edi — «orqaga»
 * butun sahifadan chiqarib yuborardi). */
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

  useEffect(() => {
    const t = setTimeout(onClose, 6000);
    // ESC / Android «orqaga» (history) — ekranni yopadi, sahifadan chiqarmaydi.
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onPop = () => onClose();
    window.addEventListener("keydown", onKey);
    window.history.pushState({ success: true }, "");
    window.addEventListener("popstate", onPop);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("popstate", onPop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // overflow-y-auto — landscape'da (masalan 640x360) ikonka+sarlavha+3 qator+
  // tugma 312px ga sig'masligi mumkin; «Yopish» tugmasiga yetish shart.
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-emerald-600 p-6">
      {/* 6s avto-yopilish ko'rsatkichi */}
      <div className="absolute left-0 top-0 h-1 w-full bg-white/20">
        <div className="h-full animate-[shrink_6s_linear_forwards] bg-white/70" />
      </div>
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

/** UX2-W1 (A10): jonli soat ALOHIDA komponentda — ilgari `setInterval` sahifa
 * ildizida edi va har soniyada butun sahifa (kalendar bilan birga) qayta
 * chizilardi; arzon telefonlarda "sayt sekin" his qilinardi. */
function LiveClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="mb-4 flex items-center justify-between">
      <div>
        <h2 className="text-lg font-semibold">Bugungi davomat</h2>
        <p className="text-sm text-slate-500">{fmtDateUz(time)}</p>
      </div>
      <div className="text-3xl font-bold tabular-nums text-primary">
        {time.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
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
  // UX2-W2: tarix kalendari endi akkordeonda — sahifa qisqaradi va uning
  // so'rovi faqat ochilganda ketadi (check-in lahzasida tarmoq band emas).
  const [historyOpen, setHistoryOpen] = useState(false);

  // UX2-MC3: Face ID modellari bo'sh vaqtda oldindan yuklab qo'yiladi.
  useEffect(() => {
    prefetchFaceModels();
  }, []);

  const [statusMsg, setStatusMsg] = useState("");
  const [showFace, setShowFace] = useState<null | Action>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [success, setSuccess] = useState<{ action: Action; att: Attendance } | null>(null);
  // 4.1-band: server rad etsa (masalan ofisdan tashqarida), xabar endi faqat
  // tez o'tib ketuvchi toast emas — modal ICHIDA doimiy ko'rinadi va modal
  // YOPILMAYDI, shuning uchun xodim butun GPS/kamera oqimini qaytadan
  // boshlamay (FaceCapture hali ochiq), DARHOL qayta urinishi mumkin.
  const [checkError, setCheckError] = useState<string | null>(null);

  // UX2-qoldiq #11 (mobil ilova WebView'i uchun): modal holati nativ tomonga
  // bildiriladi — Android «orqaga» avval MODALNI yopsin, butun ekranni emas.
  const anyModalOpen = showFace !== null || showRegister || success !== null;
  useEffect(() => {
    const rn = (window as any).ReactNativeWebView;
    rn?.postMessage(JSON.stringify({ type: "modal", open: anyModalOpen }));
  }, [anyModalOpen]);

  useEffect(() => {
    const onNativeBack = () => {
      setShowFace(null);
      setShowRegister(false);
      setSuccess(null);
      setStatusMsg("");
    };
    window.addEventListener("native-back", onNativeBack);
    return () => window.removeEventListener("native-back", onNativeBack);
  }, []);

  const att = todayQuery.data ?? null;
  const busy = checkIn.isPending || checkOut.isPending;
  // «Bez lokatsiya» ruxsati — GPS umuman so'ralmaydi (server ham tekshirmaydi).
  const skipLocation = !!user?.skip_location_check;

  async function startCheck(action: Action) {
    if (!user?.has_face) {
      toast.error("Avval yuzingizni ro'yxatdan o'tkazing.");
      setShowRegister(true);
      return;
    }
    setCheckError(null);
    // «Bez lokatsiya» ruxsati bo'lsa GPS UMUMAN so'ralmaydi — server ham uni
    // tekshirmaydi, ya'ni ruxsat so'rash faqat ortiqcha to'siq bo'lardi
    // (ko'chada yurgan xodimda GPS aniqligi ko'pincha yomon).
    if (skipLocation) {
      setShowFace(action);
      setStatusMsg("");
      return;
    }
    // Brauzer shu paytda joylashuv ruxsatini so'raydi — xodim "nega kutyapman"
    // deb qolmasligi uchun matn aynan shuni aytadi (keyin kamera ruxsati).
    setStatusMsg("Joylashuv ruxsati so'ralmoqda — «Ruxsat berish»ni tanlang...");
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

    const submit = (body: Record<string, unknown>) => {
      setStatusMsg("Serverga yuborilmoqda...");
      const mutation = action === "check-in" ? checkIn : checkOut;
      mutation.mutate(body as never, {
        onSuccess: (updated) => {
          setStatusMsg("");
          setShowFace(null);
          setSuccess({ action, att: updated });
          // Server ogohlantirishi (masalan «bugun sizga sababli kun
          // belgilangan») — check-in bloklanmaydi, lekin xodim buni bilishi
          // kerak. Uzoq turadi: muhim va o'qib ulgurilishi shart.
          if (updated?.warning) {
            toast.warning(updated.warning, { duration: 10_000 });
          }
        },
        onError: (err: any) => {
          setStatusMsg("");
          // 4.1-band: modal ATAYLAB yopilmaydi — FaceCapture hali ochiq,
          // xodim xabarni o'qib, kamerani darhol qayta sinab ko'rishi mumkin.
          setCheckError(err?.message || "Xatolik yuz berdi. Qaytadan urinib ko'ring.");
        },
      });
    };

    // «Bez lokatsiya» xodimi: koordinata umuman olinmaydi. 0,0 yubormaymiz —
    // server bayroqni ko'rib masofani tekshirmaydi, lekin 0,0 ma'lumotda
    // "Atlantika okeanida check-in qildi" degan soxta iz qoldirardi.
    if (skipLocation) {
      submit({
        latitude: null,
        longitude: null,
        face_descriptor: result.descriptor,
        liveness: result.liveness ?? 0,
        accuracy: null,
      });
      return;
    }

    setStatusMsg("Joylashuv aniqlanmoqda...");
    // 3.6-band: GPS yuz tasdiqlashdan OLDIN emas, ENDI (yuborishdan darhol
    // oldin) olinadi. Model yuklanishi (~10s) + qayta urinishlar 2-3 daqiqagacha
    // cho'zilishi mumkin edi — oldin olingan joylashuv shuncha vaqt eskirib,
    // xodim allaqachon ofisga kirgan bo'lsa ham eski (masalan tashqaridagi)
    // koordinata yuborilardi.
    getPosition()
      .then((pos) => {
        submit({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          face_descriptor: result.descriptor,
          // 4.5-band: default ENG YUQORI ishonch (1.0) emas — server "liveness
          // yuborilmadi" holatini "mukammal tiriklik" deb noto'g'ri talqin
          // qilmasligi uchun eng PAST (0) qo'yiladi.
          liveness: result.liveness ?? 0,
          accuracy: pos.coords.accuracy ?? null,
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
    <div className="mx-auto max-w-lg space-y-4">
      {/* UX-D1: bugungi jadval — kechikish "kutilmagan" bo'lmasin */}
      <TodayScheduleChip />

      <Card>
        <CardContent className="p-5">
          <LiveClock />

          {/* UX2-W2 (A9): ASOSIY amal — bitta katta, to'liq kenglikdagi tugma
              ENG TEPADA (birinchi ekranga sig'adi). Bir paytda baribir faqat
              bitta amal mumkin edi — ikkita yonma-yon tugmaning bittasi doim
              o'lik turardi. B16: yuz ro'yxatdan o'tmagan bo'lsa asosiy amal —
              yuzni ro'yxatdan o'tkazish. */}
          {user && !user.has_face ? (
            <Button
              className="mb-4 h-16 w-full bg-amber-500 text-base font-semibold hover:bg-amber-600"
              onClick={() => setShowRegister(true)}
            >
              📸 Yuzni ro'yxatdan o'tkazish (bir marta)
            </Button>
          ) : !hasCheckIn ? (
            <Button
              className="mb-4 h-16 w-full bg-emerald-600 text-lg font-semibold hover:bg-emerald-700"
              disabled={busy}
              onClick={() => startCheck("check-in")}
            >
              <LogIn className="mr-2 h-6 w-6" />
              Keldim
            </Button>
          ) : !hasCheckOut ? (
            <Button
              className="mb-4 h-16 w-full bg-rose-600 text-lg font-semibold hover:bg-rose-700"
              disabled={busy}
              onClick={() => startCheck("check-out")}
            >
              <LogOut className="mr-2 h-6 w-6" />
              Ketdim
            </Button>
          ) : (
            <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-center text-sm font-medium text-emerald-700">
              ✅ Bugungi davomat yakunlandi — yaxshi dam oling!
            </div>
          )}

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

          {statusMsg && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-base text-blue-700">
              {statusMsg}
            </div>
          )}

          <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4" />
            <span>
              {skipLocation
                ? "Yuz tasdiqlash (Face ID) bilan tekshiriladi — sizga joylashuv talab qilinmaydi."
                : "GPS + yuz tasdiqlash (Face ID) bilan tekshiriladi."}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* iPhone uchun asosiy push yo'li — taklif aynan shu yerda, chunki
          eslatma «Keldim/Ketdim» uchun kerak. Android APK ichida (embed)
          ko'rsatilmaydi: u yerda nativ push bor. */}
      <PushEnableCard />

      <LateStatusCard />

      {/* UX-D2: xodimning o'z oylik tarixi. UX2-W2: akkordeon — sahifa
          qisqaradi, so'rov faqat ochilganda ketadi. */}
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
        onClick={() => setHistoryOpen((o) => !o)}
      >
        <span>📅 Oylik davomatim</span>
        <span className="text-slate-400">{historyOpen ? "▴ yopish" : "▾ ochish"}</span>
      </button>
      {historyOpen && <MyHistoryCard />}

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
            <Suspense fallback={<FaceCaptureFallback />}>
              <FaceCapture
                mode="register"
                onResult={onFaceRegistered}
                onCancel={() => setShowRegister(false)}
                buttonLabel={registerFace.isPending ? "Saqlanmoqda..." : "Yuzimni saqlash"}
                disabled={registerFace.isPending}
              />
            </Suspense>
          </CardContent>
        </Card>
      )}

      {showFace && (
        // Telefonda TO'LIQ EKRAN (sm dan kichik): ilgari qorong'i fon ustidagi
        // kichkina karta edi va kamera juda tor ko'rinardi — modal p-4 + karta
        // p-5 = 72px chekka yo'qolardi. Kattaroq ekranda (sm+) eski markazlashgan
        // karta ko'rinishi saqlanadi.
        // max-h + overflow: past ekranda (yoki landscape'da) kontent chiqib
        // ketardi va scroll qilib bo'lmasdi. 100dvh (100vh emas): mobil
        // brauzerda manzil satri paydo bo'lganda vh o'zgarmay qoladi.
        <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 sm:items-center sm:p-4">
          <div
            className="flex h-full w-full flex-col overflow-y-auto bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] sm:h-auto sm:max-h-[calc(100dvh-2rem)] sm:max-w-lg sm:rounded-2xl sm:p-5 sm:shadow-2xl"
          >
            <div className="mb-3 flex items-center justify-between">
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
            {/* UX-D3: qadam ko'rsatkichi. Joylashuv ruxsati modal ochilishidan
                OLDIN olinadi (startCheck), ya'ni modal ichida u doim ✓;
                skipLocation xodimida bu qadam umuman ko'rinmaydi. */}
            <StepIndicator
              steps={
                skipLocation
                  ? ["Yuz tasdiqlash", "Yuborish"]
                  : ["Joylashuv", "Yuz tasdiqlash", "Yuborish"]
              }
              current={(skipLocation ? 0 : 1) + (statusMsg ? 1 : 0)}
            />
            {checkError && (
              <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
                {checkError}
              </div>
            )}
            <Suspense fallback={<FaceCaptureFallback />}>
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
            </Suspense>
          </div>
        </div>
      )}

      {success && (
        <SuccessScreen action={success.action} att={success.att} onClose={() => setSuccess(null)} />
      )}
    </div>
  );
}
