"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { extractDescriptorFromFile, loadModels } from "@/lib/face";

export default function FaceRegisterPage() {
  const router = useRouter();
  const { me, refresh } = useMe();
  const [modelsReady, setModelsReady] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [descriptor, setDescriptor] = useState<number[] | null>(null);
  const [score, setScore] = useState(0);
  const [status, setStatus] = useState<"idle" | "analyzing" | "saving" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  // Modellarni yuklash
  useEffect(() => {
    loadModels().then(() => setModelsReady(true)).catch((e) => {
      setMsg("❌ Modellarni yuklab bo'lmadi: " + (e?.message || e));
      setStatus("error");
    });
  }, []);

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setDescriptor(null);
    setMsg("");
    setStatus("analyzing");

    const result = await extractDescriptorFromFile(f);
    if ("error" in result) {
      setStatus("error");
      setMsg("❌ " + result.error);
      setPreview(URL.createObjectURL(f));
      return;
    }
    setPreview(result.previewUrl);
    setDescriptor(result.descriptor);
    setScore(result.score);
    setStatus("idle");
    setMsg(`✅ Yuz aniqlandi (aniqlik: ${(result.score * 100).toFixed(0)}%). "Saqlash" tugmasini bosing.`);
  }

  async function save() {
    if (!file || !descriptor) return;
    setStatus("saving");
    setMsg("Saqlanmoqda...");
    try {
      const fd = new FormData();
      fd.append("face_descriptor", JSON.stringify(descriptor));
      fd.append("photo", file);
      await api.post("/accounts/users/register-face/", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setStatus("done");
      setMsg("✅ Yuz muvaffaqiyatli ro'yxatdan o'tkazildi!");
      await refresh();
      setTimeout(() => router.push("/dashboard"), 1500);
    } catch (e: any) {
      setStatus("error");
      setMsg("❌ " + (e.response?.data?.detail || e.message || "Xato"));
    }
  }

  function reset() {
    setFile(null);
    setPreview("");
    setDescriptor(null);
    setMsg("");
    setStatus("idle");
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold">Yuz rasmingizni yuklang</h1>
        <p className="text-slate-500 text-sm mt-1">
          {me?.has_face
            ? "Sizning yuzingiz allaqachon ro'yxatdan o'tgan. Yangilash uchun yangi rasm yuklang."
            : "Check-in qilish uchun yuz rasmingizni yuklang."}
        </p>
      </div>

      <div className="card bg-blue-50 border-blue-200 text-blue-900 text-sm">
        <p className="font-semibold mb-1">📌 Yaxshi rasm tanlash uchun:</p>
        <ul className="list-disc ml-5 space-y-0.5">
          <li>Yuz <b>aniq va to'liq</b> ko'rinishi kerak (peshana, ko'z, og'iz, iyak)</li>
          <li>Yorug' joyda olingan rasm</li>
          <li>Kameraga <b>to'g'ridan-to'g'ri</b> qaragan</li>
          <li>Qora ko'zoynak yoki niqobsiz</li>
          <li>JPG yoki PNG format</li>
        </ul>
      </div>

      {me?.face_photo_url && !preview && (
        <div className="card">
          <div className="text-sm font-medium text-slate-600 mb-2">Hozirgi rasm:</div>
          <img src={me.face_photo_url} alt="Hozirgi" className="w-32 h-32 object-cover rounded-lg mx-auto" />
        </div>
      )}

      <div className="card">
        {!preview && (
          <label className="block">
            <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center hover:border-primary-500 hover:bg-primary-50 transition cursor-pointer">
              <div className="text-5xl mb-3">📷</div>
              <div className="font-semibold text-slate-700">Rasm tanlang</div>
              <div className="text-xs text-slate-500 mt-1">
                Tugmani bosing yoki rasmni shu yerga torting
              </div>
              <div className="text-xs text-slate-400 mt-2">
                {modelsReady ? "Tayyor ✅" : "Modellar yuklanmoqda..."}
              </div>
            </div>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onFileChange}
              disabled={!modelsReady}
            />
          </label>
        )}

        {preview && (
          <div className="space-y-4">
            <div className="flex justify-center">
              <img
                src={preview}
                alt="Tanlangan"
                className="max-h-80 rounded-xl shadow"
              />
            </div>
            {status === "analyzing" && (
              <div className="text-center text-sm text-slate-600">
                <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                Yuz aniqlanmoqda...
              </div>
            )}
            {descriptor && (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-emerald-50 rounded-lg p-2 text-center">
                  <div className="text-slate-500">Yuz aniqlandi</div>
                  <div className="text-lg font-bold text-emerald-600">
                    {(score * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="bg-blue-50 rounded-lg p-2 text-center">
                  <div className="text-slate-500">Holat</div>
                  <div className="text-lg font-bold text-blue-600">
                    Saqlashga tayyor
                  </div>
                </div>
              </div>
            )}
            <div className="flex gap-2">
              <button
                onClick={save}
                disabled={!descriptor || status === "saving" || status === "done"}
                className="btn-primary flex-1"
              >
                {status === "saving" ? "Saqlanmoqda..." : "💾 Saqlash"}
              </button>
              <button onClick={reset} className="btn-ghost">
                Boshqa rasm
              </button>
            </div>
          </div>
        )}
      </div>

      {msg && (
        <div className={`card text-center text-sm ${
          status === "done" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : status === "error" ? "bg-rose-50 text-rose-700 border-rose-200"
          : "bg-blue-50 text-blue-700 border-blue-200"
        }`}>
          {msg}
        </div>
      )}
    </div>
  );
}
