"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import Link from "next/link";

// FaceCapture faqat brauzerda yuklanadi (face-api Node.js'da ishlamaydi)
const FaceCapture = dynamic(() => import("@/components/FaceCapture"), { ssr: false });

type Status = "idle" | "loading" | "success" | "error";

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Brauzer geolokatsiyani qo'llab-quvvatlamaydi."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true, timeout: 10000, maximumAge: 0,
    });
  });
}

export default function CheckInCard() {
  const { me } = useMe();
  const [att, setAtt] = useState<any>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [msg, setMsg] = useState("");
  const [time, setTime] = useState(new Date());

  // Yuz tasdiqlash modali
  const [showFace, setShowFace] = useState<null | "check-in" | "check-out">(null);
  const [position, setPosition] = useState<GeolocationPosition | null>(null);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    fetchToday();
    return () => clearInterval(t);
  }, []);

  async function fetchToday() {
    try {
      const r = await api.get("/attendance/today/");
      setAtt(r.data);
    } catch {
      setAtt(null);
    }
  }

  /** 1-bosqich: GPS olamiz, keyin yuz modalini ochamiz */
  async function startCheck(action: "check-in" | "check-out") {
    if (!me?.has_face) {
      setStatus("error");
      setMsg("Avval yuzingizni ro'yxatdan o'tkazing.");
      return;
    }
    setStatus("loading");
    setMsg("Joylashuv aniqlanmoqda...");
    try {
      const pos = await getPosition();
      setPosition(pos);
      setShowFace(action);
      setMsg("Yuzingizni kameraga tuting...");
    } catch (e: any) {
      setStatus("error");
      setMsg("❌ GPS xato: " + (e.message || e));
    }
  }

  /** 2-bosqich: yuz olindi - hammasini serverga yuboramiz */
  async function onFaceCaptured(faceResult: any) {
    if (!position || !showFace) return;
    setShowFace(null);
    setStatus("loading");
    setMsg("Serverga yuborilmoqda...");
    try {
      const r = await api.post(`/attendance/${showFace}/`, {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        face_descriptor: faceResult.descriptor,
        liveness: faceResult.liveness ?? 1.0,
      });
      setAtt(r.data);
      setStatus("success");
      setMsg(showFace === "check-in"
        ? "✅ Keldim deb qayd etildi!"
        : "✅ Ketdim deb qayd etildi!");
    } catch (e: any) {
      setStatus("error");
      setMsg("❌ " + (e.response?.data?.detail || e.message || "Xato"));
    }
  }

  const hasCheckIn = !!att?.check_in_time;
  const hasCheckOut = !!att?.check_out_time;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">Bugungi davomat</h2>
          <p className="text-sm text-slate-500">
            {time.toLocaleDateString("uz-UZ", { weekday: "long", day: "numeric", month: "long" })}
          </p>
        </div>
        <div className="text-3xl font-bold text-primary-600 tabular-nums">
          {time.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-5">
        <div className="bg-slate-50 rounded-lg p-3">
          <div className="text-xs text-slate-500 mb-1">Keldim</div>
          <div className="text-xl font-semibold">{att?.check_in_time ? new Date(att.check_in_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</div>
          {att?.late_minutes > 0 && <div className="text-xs text-rose-600 mt-1">Kechikish: {att.late_minutes} daq</div>}
        </div>
        <div className="bg-slate-50 rounded-lg p-3">
          <div className="text-xs text-slate-500 mb-1">Ketdim</div>
          <div className="text-xl font-semibold">{att?.check_out_time ? new Date(att.check_out_time).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</div>
          {att?.early_leave_minutes > 0 && <div className="text-xs text-amber-600 mt-1">Erta ketish: {att.early_leave_minutes} daq</div>}
        </div>
      </div>

      {/* Agar yuz ro'yxatdan o'tmagan bo'lsa - ogohlantirish */}
      {me && !me.has_face && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          ⚠️ Check-in qilish uchun avval{" "}
          <Link href="/face-register" className="font-semibold underline">
            yuzingizni ro'yxatdan o'tkazing
          </Link>
        </div>
      )}

      <div className="flex gap-3">
        <button
          className="btn-success flex-1"
          disabled={hasCheckIn || status === "loading" || !me?.has_face}
          onClick={() => startCheck("check-in")}>
          🟢 Keldim
        </button>
        <button
          className="btn-danger flex-1"
          disabled={!hasCheckIn || hasCheckOut || status === "loading" || !me?.has_face}
          onClick={() => startCheck("check-out")}>
          🔴 Ketdim
        </button>
      </div>

      {msg && (
        <div className={`mt-4 rounded-lg px-3 py-2 text-sm ${
          status === "error" ? "bg-rose-50 text-rose-700 border border-rose-200"
          : status === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
          : "bg-blue-50 text-blue-700 border border-blue-200"
        }`}>{msg}</div>
      )}

      <div className="mt-4 text-xs text-slate-500 flex items-center gap-2">
        <span>🔒</span>
        <span>GPS + yuz tasdiqlash (Face ID) bilan tekshiriladi.</span>
      </div>

      {/* Face capture modali */}
      {showFace && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl p-5 w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">
                Yuz tasdiqlash ({showFace === "check-in" ? "Keldim" : "Ketdim"})
              </h3>
              <button onClick={() => { setShowFace(null); setStatus("idle"); setMsg(""); }} className="text-slate-400 hover:text-slate-700">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <FaceCapture
              onResult={onFaceCaptured}
              onCancel={() => { setShowFace(null); setStatus("idle"); setMsg(""); }}
              buttonLabel={showFace === "check-in" ? "Keldim" : "Ketdim"}
            />
          </div>
        </div>
      )}
    </div>
  );
}
