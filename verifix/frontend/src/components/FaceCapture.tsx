"use client";
import { useEffect, useRef, useState } from "react";
import {
  loadModels, captureFace, captureLiveFace, captureForRegister,
  LiveResult, RegisterResult, MIN_FACE_SIZE,
} from "@/lib/face";

type Mode = "register" | "verify";

interface Props {
  mode?: Mode;
  onResult: (result: LiveResult | RegisterResult) => void;
  onCancel?: () => void;
  livenessThreshold?: number;
  buttonLabel?: string;
  hint?: string;
}

type LiveStatus = {
  detected: boolean;
  size: number;
  score: number;
};

export default function FaceCapture({
  mode = "verify",
  onResult, onCancel,
  livenessThreshold = 0.5,  // Backend bilan moslangan (settings.FACE_LIVENESS_THRESHOLD)
  buttonLabel,
  hint,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [modelsReady, setModelsReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<any>(null);
  const [live, setLive] = useState<LiveStatus>({ detected: false, size: 0, score: 0 });

  // Kameradan stream olamiz
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false,
        });
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
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

  // Modellarni yuklash
  useEffect(() => {
    loadModels().then(() => setModelsReady(true)).catch((e) => {
      setError("Modellarni yuklab bo'lmadi: " + (e?.message || e));
    });
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
          const size = Math.min(r.box.w, r.box.h);
          setLive({ detected: true, size, score: r.score });
        } else {
          setLive({ detected: false, size: 0, score: 0 });
        }
      } catch {}
    }, 800);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [modelsReady, capturing]);

  async function capture() {
    if (!videoRef.current) return;
    setCapturing(true);
    setError("");
    setLastResult(null);
    try {
      if (mode === "register") {
        const r = await captureForRegister(videoRef.current, 8);
        if ("error" in r) {
          setError(r.error);
          setCapturing(false);
          return;
        }
        setLastResult(r);
        onResult(r);
      } else {
        const r = await captureLiveFace(videoRef.current, 5);
        if (!r) {
          setError("Yuz aniqlanmadi. Iltimos kameraga to'g'ri tuting.");
          setCapturing(false);
          return;
        }
        setLastResult(r);
        if (r.liveness < livenessThreshold) {
          setError(
            `Tiriklik tekshiruvi muvaffaqiyatsiz (${r.liveness.toFixed(2)} < ${livenessThreshold}).\n` +
            `Qaytadan urinib ko'ring — yorug'roq joyda, biroz harakat qiling.`
          );
          setCapturing(false);
          return;
        }
        onResult(r);
      }
    } catch (e: any) {
      setError("Xato: " + (e.message || e));
    } finally {
      setCapturing(false);
    }
  }

  const defaultLabel = mode === "register"
    ? "Yuzimni ro'yxatdan o'tkazish"
    : "Yuzni tasdiqlash";
  const defaultHint = mode === "register"
    ? "8 freym ushlanadi va o'rtachalanadi. Kameraga 40-60 sm masofada turing."
    : "Yuzingizni kameraga to'g'rilang va biroz harakat qiling.";

  // Yuz holati - foydalanuvchiga ko'rsatish
  const sizeGood = live.size >= MIN_FACE_SIZE;
  const statusColor = !live.detected
    ? "bg-rose-500"
    : !sizeGood
      ? "bg-amber-500"
      : "bg-emerald-500";
  const statusText = !live.detected
    ? "❌ Yuz aniqlanmadi"
    : !sizeGood
      ? `⚠️ Yuz juda kichik (${live.size.toFixed(0)}px) — yaqinroq turing`
      : `✅ Yuz aniq (${live.size.toFixed(0)}px, ${(live.score * 100).toFixed(0)}%)`;

  return (
    <div className="space-y-3">
      <div className="relative bg-black rounded-xl overflow-hidden aspect-[4/3] w-full max-w-md mx-auto">
        <video
          ref={videoRef}
          playsInline muted autoPlay
          className="w-full h-full object-cover transform scale-x-[-1]"
        />
        {!modelsReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70 text-white text-sm">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              Aniq model yuklanmoqda... (birinchi marta ~10 soniya)
            </div>
          </div>
        )}
        {capturing && modelsReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 text-white text-sm">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              Yuz tahlil qilinmoqda...
            </div>
          </div>
        )}
        {/* Yo'naltiruvchi doira */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className={`w-48 h-60 border-4 rounded-full transition-colors ${
            !modelsReady ? "border-white/30"
            : !live.detected ? "border-rose-400/70"
            : !sizeGood ? "border-amber-400/70"
            : "border-emerald-400/80"
          }`} />
        </div>
        {/* Real-time status badge */}
        {modelsReady && !capturing && (
          <div className="absolute top-3 left-3 right-3 flex justify-center">
            <div className={`${statusColor} text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg`}>
              {statusText}
            </div>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500 text-center whitespace-pre-line">
        {hint || defaultHint}
      </p>

      {lastResult && mode === "register" && (
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-emerald-50 rounded-lg p-2 text-center">
            <div className="text-slate-500">Aniqlik</div>
            <div className="text-lg font-bold text-emerald-600">
              {(lastResult.avgScore * 100).toFixed(0)}%
            </div>
          </div>
          <div className="bg-blue-50 rounded-lg p-2 text-center">
            <div className="text-slate-500">Yuz</div>
            <div className="text-lg font-bold text-blue-600">
              {lastResult.faceSize?.toFixed(0)}px
            </div>
          </div>
          <div className="bg-slate-50 rounded-lg p-2 text-center">
            <div className="text-slate-500">Freym</div>
            <div className="text-lg font-bold text-slate-600">
              {lastResult.frames}
            </div>
          </div>
        </div>
      )}

      {lastResult && mode === "verify" && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-slate-50 rounded-lg p-2 text-center">
            <div className="text-slate-500">Tiriklik</div>
            <div className={`text-lg font-bold ${lastResult.liveness >= livenessThreshold ? "text-emerald-600" : "text-rose-600"}`}>
              {(lastResult.liveness * 100).toFixed(0)}%
            </div>
          </div>
          <div className="bg-slate-50 rounded-lg p-2 text-center">
            <div className="text-slate-500">Aniqlik</div>
            <div className="text-lg font-bold text-slate-700">
              {(lastResult.avgScore * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg px-3 py-2 text-xs whitespace-pre-wrap">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={capture}
          disabled={!modelsReady || capturing || !live.detected || !sizeGood}
          className="btn-primary flex-1"
          title={!live.detected ? "Yuz aniqlanmadi" : !sizeGood ? "Yaqinroq turing" : ""}
        >
          {capturing
            ? "Tahlil qilinmoqda..."
            : buttonLabel || defaultLabel}
        </button>
        {onCancel && (
          <button onClick={onCancel} className="btn-ghost">
            Bekor
          </button>
        )}
      </div>
    </div>
  );
}
