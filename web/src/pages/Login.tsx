import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

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
  const [loggingIn, setLoggingIn] = useState(false);

  useEffect(() => {
    if (!BOT_USERNAME || !widgetRef.current) return;

    window.onTelegramAuth = async (tgUser) => {
      try {
        const { access_token, user } = await api.telegramLogin(tgUser);
        loginWithToken(access_token, user);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Kirishda xatolik");
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
    setLoggingIn(true);
    try {
      const { access_token, user } = await api.devLogin(Number(devTelegramId));
      loginWithToken(access_token, user);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Kirishda xatolik");
    } finally {
      setLoggingIn(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Xodimlar KPI/Bonus tizimi</CardTitle>
        </CardHeader>
        <CardContent className="text-center">
          {BOT_USERNAME ? (
            <div ref={widgetRef} className="mb-4 flex justify-center" />
          ) : (
            <p className="mb-4 text-sm text-slate-500">
              TELEGRAM_LOGIN_BOT_USERNAME sozlanmagan — Telegram Login Widget ko'rsatilmayapti.
            </p>
          )}

          {DEV_MODE && (
            <>
              <Separator className="my-4" />
              <p className="mb-2 text-xs text-amber-600">
                Dev-login (faqat lokal sinov uchun, DEBUG=true bo'lganda ishlaydi)
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleDevLogin();
                }}
                className="space-y-2"
              >
                <Input
                  type="text"
                  placeholder="Telegram ID"
                  value={devTelegramId}
                  onChange={(e) => setDevTelegramId(e.target.value)}
                />
                <Button type="submit" disabled={loggingIn} className="w-full">
                  {loggingIn ? "Kirilmoqda..." : "Dev sifatida kirish"}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
