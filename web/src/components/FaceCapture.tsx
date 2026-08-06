import { useEffect, useRef, useState } from "react";
import {
  loadModels,
  captureFace,
  captureLiveFace,
  captureForRegister,
  LiveResult,
  LivenessProgress,
  RegisterResult,
  MIN_FACE_SIZE,
  MIN_VERIFY_FACE_SIZE,
  CHALLENGE_MAX_MS,
  NUDGE_AFTER_MS,
} from "../lib/face";

type Mode = "register" | "verify";

interface Props {
  mode?: Mode;
  onResult: (result: LiveResult | RegisterResult) => void;
  onCancel?: () => void;
  livenessThreshold?: number;
  buttonLabel?: string;
  hint?: string;
  // Yuz aniqlanib, o'lchami yetarli bo'lgan zahoti tiriklik sinovi TUGMASIZ
  // boshlanadi. Default: `verify` uchun yoqiq, `register` uchun o'chiq —
  // ro'yxatdan o'tkazish ongli (bir martalik) amal, tasodifan boshlanmasin.
  autoStart?: boolean;
  // 4.11-band: `capturing` faqat FaceCapture ICHKI (freym olish) holatini
  // bildiradi — natija chaqiruvchiga (`onResult`) uzatilgach, chaqiruvchining
  // O'ZINING tarmoq so'rovi (masalan register-face) hali ketayotgan bo'lsa ham,
  // ichki holat allaqachon tugaganidan tugma yana bosiladigan bo'lib qolardi
  // (buttonLabel "Saqlanmoqda..." bo'lsa ham, DISABLED emas edi). Chaqiruvchi
  // shu prop orqali o'z holatini ham qo'shishi mumkin.
  disabled?: boolean;
}

type LiveStatus = { detected: boolean; size: number; score: number };

export default function FaceCapture({
  mode = "verify",
  onResult,
  onCancel,
  livenessThreshold = 0.5,
  buttonLabel,
  hint,
  autoStart = mode === "verify",
  disabled = false,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [modelsReady, setModelsReady] = useState(false);
  const [modelProgress, setModelProgress] = useState<{ loaded: number; total: number }>({
    loaded: 0,
    total: 3,
  });
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState("");
  const [live, setLive] = useState<LiveStatus>({ detected: false, size: 0, score: 0 });
  // Tiriklik sinovi (ko'z pirpiratish / og'iz ochish) real-vaqtli holati
  const [challenge, setChallenge] = useState<LivenessProgress | null>(null);
  // 4.2-band: model o'z serverimizdan (/models) yuklanadi — u ishlamay qolsa
  // ilgari ekran abadiy "yuklanmoqda..." bo'lib qolar, qayta urinish uchun
  // butun sahifani yangilash kerak edi. (Ilgari uchinchi tomon CDN'i edi.)
  const [modelLoadError, setModelLoadError] = useState("");

  // 2.4-band: capture() async davom etayotganda modal bekor qilinsa (yoki komponent
  // unmount bo'lsa), natija E'TIBORGA OLINMASLIGI kerak. Oldin "showFace" guardi
  // chaqiruvchi (CheckIn.tsx) tarafida edi, lekin u ESKI closure'ni ko'radi (render
  // paytidagi qiymat) — bekor qilingandan keyin ham "haqiqiy" bo'lib qolaverardi va
  // so'rov baribir ketardi. Bu ref esa unmount'da DARHOL yangilanadi.
  const cancelledRef = useRef(false);
  useEffect(() => {
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // HTTP (xavfsiz bo'lmagan) originda brauzer mediaDevices'ni umuman bermaydi
        if (!navigator.mediaDevices?.getUserMedia) {
          setError(
            "Bu sahifada kamera ishlamaydi — sayt HTTPS orqali ochilishi kerak. " +
              "Manzilni https:// bilan oching."
          );
          return;
        }
        const s = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        setStream(s);
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          await videoRef.current.play();
        }
      } catch (e: any) {
        setError("Kamera ruxsati berilmadi: " + (e.message || e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  function loadModelsNow() {
    setModelLoadError("");
    loadModels((loaded, total) => setModelProgress({ loaded, total }))
      .then(() => setModelsReady(true))
      .catch((e) =>
        setModelLoadError(
          "Yuz aniqlash modelini yuklab bo'lmadi (internet aloqasini tekshiring). " +
            (e?.message || e)
        )
      );
  }

  useEffect(() => {
    loadModelsNow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // REAL VAQTLI yuz aniqlash (har 800ms)
  useEffect(() => {
    if (!modelsReady || capturing) return;
    let alive = true;
    const interval = setInterval(async () => {
      if (!alive || !videoRef.current || videoRef.current.paused) return;
      try {
        const r = await captureFace(videoRef.current);
        if (!alive) return;
        if (r) {
          setLive({ detected: true, size: Math.min(r.box.w, r.box.h), score: r.score });
        } else {
          setLive({ detected: false, size: 0, score: 0 });
        }
      } catch {
        /* ignore */
      }
    }, 800);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [modelsReady, capturing]);

  // Tasdiqlash (check-in) uchun yuz KATTAROQ bo'lishi kerak — tiriklik
  // sinovida landmark shovqinining nisbiy zarari yuz o'lchamiga bog'liq
  // (`MIN_VERIFY_FACE_SIZE` izohiga qarang). Ro'yxatdan o'tishda esa
  // eski chegara (yuz bor/yo'q) yetarli — u yerda mimika o'lchanmaydi.
  // DIQQAT: avtomatik boshlash effekti shu qiymatga bog'liq, shuning uchun
  // u effektdan OLDIN hisoblanishi shart (aks holda TDZ xatosi).
  const requiredSize = mode === "verify" ? MIN_VERIFY_FACE_SIZE : MIN_FACE_SIZE;
  const sizeGood = live.size >= requiredSize;

  // Avtomatik boshlash (egasi so'rovi 2026-07-31): ilgari xodim «Keldim»ni
  // bosgach kamera ochilar, so'ng YANA bitta tugmani bosishi kerak edi —
  // ortiqcha qadam, telefonda ayniqsa noqulay. Endi yuz aniqlanib o'lchami
  // yetarli bo'lgan zahoti sinov o'zi boshlanadi.
  //
  // `armed` — bir martalik "tetik": sinov boshlangach o'chadi. Xato bo'lsa
  // (tiriklik tasdiqlanmadi) qayta YOQILMAYDI — aks holda cheksiz halqa
  // bo'lardi: xato → yuz hamon ko'rinib turibdi → darhol qayta boshlash →
  // xato. Xodim «Qayta urinish»ni bosganda qayta tetiklanadi.
  const [armed, setArmed] = useState(autoStart);
  useEffect(() => {
    if (!armed || capturing || disabled) return;
    if (!modelsReady || !live.detected || !sizeGood) return;
    setArmed(false);
    void capture();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [armed, capturing, disabled, modelsReady, live.detected, sizeGood]);

  function retry() {
    setError("");
    setChallenge(null);
    if (autoStart) setArmed(true);
    else void capture();
  }

  async function capture() {
    if (!videoRef.current) return;
    setCapturing(true);
    setError("");
    try {
      if (mode === "register") {
        const r = await captureForRegister(videoRef.current, 8);
        if (cancelledRef.current) return; // bekor qilindi — natija e'tiborga olinmaydi
        if ("error" in r) {
          setError(r.error);
          setCapturing(false);
          return;
        }
        onResult(r);
      } else {
        setChallenge(null);
        const r = await captureLiveFace(videoRef.current, {
          onProgress: (p) => {
            if (!cancelledRef.current) setChallenge(p);
          },
          shouldCancel: () => cancelledRef.current,
        });
        if (cancelledRef.current) return; // bekor qilindi — natija e'tiborga olinmaydi
        if (!r) {
          setError("Yuz aniqlanmadi. Iltimos kameraga to'g'ri tuting va yorug'roq joyda turing.");
          setCapturing(false);
          return;
        }
        if (r.liveness < livenessThreshold) {
          // Diagnostika raqamlari xabarga ATAYLAB kiritilgan: chegara jonli
          // qurilmalarda noto'g'ri ishlab qolsa, xodim aynan shu sonlarni
          // aytib bera oladi va sozlamani taxminga emas, faktga qarab
          // tuzatish mumkin (2026-07-27/30 da ikki marta shu kerak bo'ldi).
          setError(
            (r.unstablePose
              ? `Poza juda beqaror — telefonni barqaror ushlab, kameraga to'g'ri qarab turing.\n`
              : `Tiriklik tasdiqlanmadi — shu vaqt ichida pirpiratganingiz aniqlanmadi.\n`) +
              `Qayta urinib ko'ring: kameraga tik qarab bir necha soniya turing — ` +
              `o'tmasa, ko'zingizni ataylab bir marta pirpiratib qo'ying (yoki og'zingizni ochib yoping).\n` +
              `Tafsilot: ko'z ${(r.earDip * 100).toFixed(0)}% (pirpiratish uchun 60% dan past kerak), ` +
              `og'iz ${r.mouthDelta.toFixed(2)} (0.35 kerak), freym ${r.frames}, ` +
              `yuz ${r.faceSize.toFixed(0)}px.`
          );
          setCapturing(false);
          return;
        }
        onResult(r);
      }
    } catch (e: any) {
      if (cancelledRef.current) return;
      setError("Xato: " + (e.message || e));
    } finally {
      if (!cancelledRef.current) setCapturing(false);
    }
  }

  const defaultLabel = mode === "register" ? "Yuzimni ro'yxatdan o'tkazish" : "Yuzni tasdiqlash";
  const defaultHint =
    mode === "register"
      ? "8 freym ushlanadi, eng aniqi tanlanadi. Kameraga 40-60 sm masofada turing."
      : "Kameraga tik qarab turing — yuzingiz aniqlanishi bilan tasdiqlash O'ZI boshlanadi va tugagach avtomatik yuboriladi.";

  const statusColor = !live.detected ? "bg-rose-500" : !sizeGood ? "bg-amber-500" : "bg-emerald-500";
  const statusText = !live.detected
    ? "❌ Yuz aniqlanmadi"
    : !sizeGood
      ? `⚠️ Yaqinroq turing (${live.size.toFixed(0)}px → ${requiredSize}px kerak)`
      : `✅ Yuz aniq (${live.size.toFixed(0)}px, ${(live.score * 100).toFixed(0)}%)`;

  // Telefonda ishlatiladi — tugmalar kamida 48px balandlikda
  const btnPrimary =
    "px-4 py-3 min-h-[48px] rounded-md bg-indigo-600 text-white text-base font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed";
  const btnGhost = "px-4 py-3 min-h-[48px] rounded-md border border-slate-300 text-base hover:bg-slate-50";

  return (
    <div className="space-y-3">
      <div className="relative bg-black rounded-xl overflow-hidden aspect-[4/3] w-full max-w-md mx-auto">
        <video ref={videoRef} playsInline muted autoPlay className="w-full h-full object-cover transform scale-x-[-1]" />
        {!modelsReady && modelLoadError && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 text-white text-sm p-4">
            <div className="w-full max-w-[280px] text-center">
              <p className="mb-3">{modelLoadError}</p>
              <button
                onClick={loadModelsNow}
                className="rounded-md bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
              >
                Qayta urinish
              </button>
            </div>
          </div>
        )}
        {!modelsReady && !modelLoadError && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70 text-white text-sm">
            <div className="w-full max-w-[220px] text-center">
              <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <div>
                Model yuklanmoqda... {modelProgress.loaded}/{modelProgress.total}
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/20">
                <div
                  className="h-full rounded-full bg-white transition-all"
                  style={{ width: `${(modelProgress.loaded / modelProgress.total) * 100}%` }}
                />
              </div>
              <div className="mt-1 text-xs text-white/60">(birinchi marta ~10 soniya)</div>
            </div>
          </div>
        )}
        {capturing && modelsReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/55 text-white p-4">
            {mode === "verify" && challenge ? (
              // Tiriklik sinovi — xodim NIMA qilishi kerakligini va tizim uni
              // ko'rayotganini real vaqtda ko'rsatadi. Ilgari faqat "tahlil
              // qilinmoqda..." yozilardi: xodim nima qilish kerakligini
              // bilmasdi va sinov jimgina muvaffaqiyatsiz tugardi.
              <div className="w-full max-w-[260px] text-center">
                {challenge.blinkDetected || challenge.mouthDetected ? (
                  <div className="text-emerald-300">
                    <div className="text-3xl">✅</div>
                    <div className="mt-1 text-base font-semibold">Tiriklik tasdiqlandi</div>
                  </div>
                ) : (
                  <>
                    {/* Passiv-birinchi: xodimga "pirpirating" deb BUYURILMAYDI —
                        u kameraga qarab tursa, o'zi beixtiyor pirpiratadi va
                        sinov shu zahoti (avtomatik) tasdiqlanadi. Faqat kutish
                        NUDGE_AFTER_MS dan uzoqqa cho'zilsa (masalan diqqat
                        bilan tikilib kam pirpiratayotgan bo'lsa), yumshoq
                        eslatma ko'rsatiladi — fallback, boshlang'ich talab EMAS. */}
                    <div className="text-3xl animate-pulse">📷</div>
                    <div className="mt-1 text-base font-semibold">Kameraga qarab turing</div>
                    {challenge.elapsedMs >= NUDGE_AFTER_MS && (
                      <div className="mt-1 text-xs text-white/80">
                        Ko'zingizni pirpiratib qo'ysangiz tezroq o'tadi
                      </div>
                    )}
                    {!challenge.faceDetected ? (
                      <div className="mt-2 text-xs text-amber-300">
                        Yuz ko'rinmayapti — kameraga to'g'ri qarang
                      </div>
                    ) : challenge.unstablePose ? (
                      <div className="mt-2 text-xs text-amber-300">
                        Telefonni barqaror ushlang — bir joyda turing
                      </div>
                    ) : null}
                    <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/20">
                      <div
                        className="h-full rounded-full bg-white/80 transition-all"
                        style={{
                          width: `${Math.min(100, (challenge.elapsedMs / CHALLENGE_MAX_MS) * 100)}%`,
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="text-center text-sm">
                <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                Yuz tahlil qilinmoqda...
              </div>
            )}
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          {/* Kontur o'lchami videoga NISBATAN. Ilgari qat'iy `w-48 h-60`
              (192x240 px) edi, video esa `aspect-[4/3] w-full` — kichik
              ekranda kontur videodan chiqib ketardi: 320px ekranda 54px,
              360px da 24px (360px eng keng tarqalgan Android o'lchami).
              85% balandlik + aspect-[4/5] asl 192:240=0.8 nisbatini saqlaydi
              va har qanday ekranda video ichida qoladi. */}
          <div
            className={`h-[85%] aspect-[4/5] border-4 rounded-full transition-colors ${
              !modelsReady
                ? "border-white/30"
                : !live.detected
                  ? "border-rose-400/70"
                  : !sizeGood
                    ? "border-amber-400/70"
                    : "border-emerald-400/80"
            }`}
          />
        </div>
        {modelsReady && !capturing && (
          <div className="absolute top-3 left-3 right-3 flex justify-center">
            <div className={`${statusColor} text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg`}>
              {statusText}
            </div>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500 text-center whitespace-pre-line">{hint || defaultHint}</p>

      {/* Natija paneli (Tiriklik/Mimika/Aniqlik) ATAYLAB olib tashlandi:
          muvaffaqiyatda modal darhol yopiladi (ko'rinmasdi ham), xatoda esa
          aynan shu raqamlar xato matnida batafsilroq chiqadi — telefon
          ekranida ikki marta takrorlash ortiqcha shovqin edi. */}

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg px-3 py-2 text-xs whitespace-pre-wrap">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        {/* Avtomatik rejimda asosiy tugma UMUMAN yo'q — sinov o'zi boshlanadi.
            Tugma faqat xato bo'lgandan keyin («Qayta urinish») paydo bo'ladi. */}
        {!autoStart ? (
          <button
            onClick={capture}
            disabled={disabled || !modelsReady || capturing || !live.detected || !sizeGood}
            className={`${btnPrimary} flex-1`}
            title={!live.detected ? "Yuz aniqlanmadi" : !sizeGood ? "Yaqinroq turing" : ""}
          >
            {capturing ? "Tahlil qilinmoqda..." : buttonLabel || defaultLabel}
          </button>
        ) : (
          // Faqat kamera ISHLAYOTGAN bo'lsa ko'rsatiladi: oqim umuman
          // ochilmagan bo'lsa (ruxsat berilmagan) qayta urinish hech narsa
          // qilmasdi — `live.detected` hech qachon rost bo'lmaydi va tugma
          // xatoni jimgina tozalab, xodimni "nima bo'ldi?" holatida qoldirardi.
          // Bunday holatda faqat xato matni qoladi (u nima qilishni aytadi).
          error &&
          stream && (
            <button onClick={retry} disabled={disabled || capturing} className={`${btnPrimary} flex-1`}>
              Qayta urinish
            </button>
          )
        )}
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={disabled}
            className={`${btnGhost} ${autoStart && !(error && stream) ? "flex-1" : ""}`}
          >
            Bekor
          </button>
        )}
      </div>
    </div>
  );
}
