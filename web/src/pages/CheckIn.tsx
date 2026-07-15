import { useEffect, useState } from "react";
import { api, Attendance } from "../lib/api";
import { useAuth } from "../lib/auth";
import FaceCapture from "../components/FaceCapture";
import { LiveResult } from "../lib/face";

type Status = "idle" | "loading" | "success" | "error";

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

// Backend naive-UTC qaytaradi — "Z" qo'shib mahalliy vaqtga o'giramiz.
function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const norm = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`;
  return new Date(norm).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
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

export default function CheckIn() {
  const { user, refreshUser } = useAuth();
  const [att, setAtt] = useState<Attendance | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [msg, setMsg] = useState("");
  const [time, setTime] = useState(new Date());
  const [showFace, setShowFace] = useState<null | "check-in" | "check-out">(null);
  const [position, setPosition] = useState<GeolocationPosition | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [registering, setRegistering] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    api
      .myAttendanceToday()
      .then(setAtt)
      .catch(() => setAtt(null));
    return () => clearInterval(t);
  }, []);

  async function startCheck(action: "check-in" | "check-out") {
    if (!user?.has_face) {
      setStatus("error");
      setMsg("Avval yuzingizni ro'yxatdan o'tkazing.");
      setShowRegister(true);
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

  async function onFaceCaptured(result: LiveResult | any) {
    if (!position || !showFace) return;
    const action = showFace;
    setShowFace(null);
    setStatus("loading");
    setMsg("Serverga yuborilmoqda...");
    try {
      const body = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        face_descriptor: result.descriptor,
        liveness: result.liveness ?? 1.0,
      };
      const updated = action === "check-in" ? await api.myCheckIn(body) : await api.myCheckOut(body);
      setAtt(updated);
      setStatus("success");
      setMsg(action === "check-in" ? "✅ Keldim deb qayd etildi!" : "✅ Ketdim deb qayd etildi!");
    } catch (e: any) {
      setStatus("error");
      setMsg("❌ " + (e.message || "Xato"));
    }
  }

  async function onFaceRegistered(result: any) {
    setRegistering(true);
    setMsg("Yuz saqlanmoqda...");
    try {
      await api.registerMyFace(result.descriptor);
      await refreshUser();
      setShowRegister(false);
      setStatus("success");
      setMsg("✅ Yuz muvaffaqiyatli ro'yxatdan o'tkazildi!");
    } catch (e: any) {
      setStatus("error");
      setMsg("❌ " + (e.message || "Xato"));
    } finally {
      setRegistering(false);
    }
  }

  const hasCheckIn = !!att?.check_in_time;
  const hasCheckOut = !!att?.check_out_time;

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Bugungi davomat</h2>
            <p className="text-sm text-slate-500">{fmtDateUz(time)}</p>
          </div>
          <div className="text-3xl font-bold text-indigo-600 tabular-nums">
            {time.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-5">
          <div className="bg-slate-50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">Keldim</div>
            <div className="text-xl font-semibold">{fmtTime(att?.check_in_time ?? null)}</div>
            {att && att.late_minutes > 0 && (
              <div className="text-xs text-rose-600 mt-1">Kechikish: {att.late_minutes} daq</div>
            )}
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">Ketdim</div>
            <div className="text-xl font-semibold">{fmtTime(att?.check_out_time ?? null)}</div>
            {att && att.early_leave_minutes > 0 && (
              <div className="text-xs text-amber-600 mt-1">Erta ketish: {att.early_leave_minutes} daq</div>
            )}
          </div>
        </div>

        {user && !user.has_face && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
            ⚠️ Check-in qilish uchun avval{" "}
            <button onClick={() => setShowRegister(true)} className="font-semibold underline">
              yuzingizni ro'yxatdan o'tkazing
            </button>
          </div>
        )}

        <div className="flex gap-3">
          <button
            className="flex-1 px-4 py-2.5 rounded-md bg-emerald-600 text-white font-medium hover:bg-emerald-700 disabled:opacity-50"
            disabled={hasCheckIn || status === "loading" || !user?.has_face}
            onClick={() => startCheck("check-in")}
          >
            🟢 Keldim
          </button>
          <button
            className="flex-1 px-4 py-2.5 rounded-md bg-rose-600 text-white font-medium hover:bg-rose-700 disabled:opacity-50"
            disabled={!hasCheckIn || hasCheckOut || status === "loading" || !user?.has_face}
            onClick={() => startCheck("check-out")}
          >
            🔴 Ketdim
          </button>
        </div>

        {msg && (
          <div
            className={`mt-4 rounded-lg px-3 py-2 text-sm ${
              status === "error"
                ? "bg-rose-50 text-rose-700 border border-rose-200"
                : status === "success"
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : "bg-blue-50 text-blue-700 border border-blue-200"
            }`}
          >
            {msg}
          </div>
        )}

        <div className="mt-4 text-xs text-slate-500 flex items-center gap-2">
          <span>🔒</span>
          <span>GPS + yuz tasdiqlash (Face ID) bilan tekshiriladi.</span>
        </div>
      </div>

      {user?.has_face && !showRegister && (
        <div className="text-center">
          <button onClick={() => setShowRegister(true)} className="text-sm text-indigo-600 hover:underline">
            Yuzni qayta ro'yxatdan o'tkazish
          </button>
        </div>
      )}

      {showRegister && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold">Yuzni ro'yxatdan o'tkazish</h3>
            <button onClick={() => setShowRegister(false)} className="text-slate-400 hover:text-slate-700 text-sm">
              Yopish
            </button>
          </div>
          <FaceCapture
            mode="register"
            onResult={onFaceRegistered}
            onCancel={() => setShowRegister(false)}
            buttonLabel={registering ? "Saqlanmoqda..." : "Yuzimni saqlash"}
          />
        </div>
      )}

      {showFace && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl p-5 w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">
                Yuz tasdiqlash ({showFace === "check-in" ? "Keldim" : "Ketdim"})
              </h3>
              <button
                onClick={() => {
                  setShowFace(null);
                  setStatus("idle");
                  setMsg("");
                }}
                className="text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <FaceCapture
              mode="verify"
              onResult={onFaceCaptured}
              onCancel={() => {
                setShowFace(null);
                setStatus("idle");
                setMsg("");
              }}
              buttonLabel={showFace === "check-in" ? "Keldim" : "Ketdim"}
            />
          </div>
        </div>
      )}
    </div>
  );
}
