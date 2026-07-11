"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      router.push("/dashboard");
    } catch (err: any) {
      // Tarmoq xatosi (server javob bermadi)
      if (!err.response) {
        setError(
          `Server bilan bog'lanib bo'lmadi.\n` +
          `API manzili: ${API_BASE}\n` +
          `Xato: ${err.message || "Network Error"}\n\n` +
          `Tekshiring:\n` +
          `1) Backend ishlayaptimi (python manage.py runserver 0.0.0.0:8000)\n` +
          `2) Telefon va kompyuter bir Wi-Fi tarmog'idamiz\n` +
          `3) Windows Firewall port 8000 ga ruxsat berilgan`
        );
      } else if (err.response.status === 401) {
        setError("Login yoki parol noto'g'ri.");
      } else {
        const detail = err.response.data?.detail || JSON.stringify(err.response.data);
        setError(`Xato (${err.response.status}): ${detail}`);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-600 to-primary-900 p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-primary-600 rounded-2xl mx-auto mb-4 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-9 w-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a3 3 0 015.36-1.84M15 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold">Hodim CRM</h1>
          <p className="text-slate-500 mt-1">Tizimga kirish</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="label">Foydalanuvchi nomi</label>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </div>
          <div>
            <label className="label">Parol</label>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && (
            <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg px-3 py-2 text-xs whitespace-pre-wrap font-mono">
              {error}
            </div>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "Kirilmoqda..." : "Kirish"}
          </button>
          <p className="text-xs text-center text-slate-400 mt-3">
            API: {API_BASE}
          </p>
        </form>
      </div>
    </div>
  );
}
