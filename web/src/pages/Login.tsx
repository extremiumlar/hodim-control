import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, string | number>) => void;
  }
}

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_LOGIN_BOT_USERNAME;
const DEV_MODE = import.meta.env.VITE_DEBUG === "true";

export default function Login() {
  const { user, loginWithToken } = useAuth();
  const widgetRef = useRef<HTMLDivElement>(null);
  const [devTelegramId, setDevTelegramId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!BOT_USERNAME || !widgetRef.current) return;

    window.onTelegramAuth = async (tgUser) => {
      try {
        const { access_token, user } = await api.telegramLogin(tgUser);
        loginWithToken(access_token, user);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Kirishda xatolik");
      }
    };

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    widgetRef.current.appendChild(script);
  }, [loginWithToken]);

  if (user) return <Navigate to="/" replace />;

  const handleDevLogin = async () => {
    setError(null);
    try {
      const { access_token, user } = await api.devLogin(Number(devTelegramId));
      loginWithToken(access_token, user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kirishda xatolik");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="bg-white shadow rounded-lg p-8 w-full max-w-sm text-center">
        <h1 className="text-xl font-semibold mb-6">Xodimlar KPI/Bonus tizimi</h1>

        {BOT_USERNAME ? (
          <div ref={widgetRef} className="flex justify-center mb-4" />
        ) : (
          <p className="text-sm text-slate-500 mb-4">
            TELEGRAM_LOGIN_BOT_USERNAME sozlanmagan — Telegram Login Widget ko'rsatilmayapti.
          </p>
        )}

        {DEV_MODE && (
          <div className="border-t pt-4 mt-4">
            <p className="text-xs text-amber-600 mb-2">
              Dev-login (faqat lokal sinov uchun, DEBUG=true bo'lganda ishlaydi)
            </p>
            <input
              type="text"
              placeholder="Telegram ID"
              value={devTelegramId}
              onChange={(e) => setDevTelegramId(e.target.value)}
              className="border rounded px-3 py-2 w-full mb-2 text-sm"
            />
            <button
              onClick={handleDevLogin}
              className="w-full bg-indigo-600 text-white rounded py-2 text-sm font-medium hover:bg-indigo-700"
            >
              Dev sifatida kirish
            </button>
          </div>
        )}

        {error && <p className="text-sm text-red-600 mt-4">{error}</p>}
      </div>
    </div>
  );
}
