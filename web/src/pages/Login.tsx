import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const DEV_MODE = import.meta.env.VITE_DEBUG === "true";

type DeeplinkState =
  | { phase: "loading" }
  | { phase: "ready"; botUrl: string; code: string }
  | { phase: "error" };

export default function Login() {
  const { user, loginWithToken } = useAuth();
  const [deeplink, setDeeplink] = useState<DeeplinkState>({ phase: "loading" });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [devTelegramId, setDevTelegramId] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const startDeeplink = useCallback(async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setDeeplink({ phase: "loading" });
    try {
      const { code, bot_url } = await api.startTelegramDeeplink();
      setDeeplink({ phase: "ready", botUrl: bot_url, code });

      pollRef.current = setInterval(async () => {
        try {
          const res = await api.pollTelegramDeeplink(code);
          if (res.status === "ready" && res.access_token && res.user) {
            if (pollRef.current) clearInterval(pollRef.current);
            loginWithToken(res.access_token, res.user);
          } else if (res.status === "expired" || res.status === "used") {
            if (pollRef.current) clearInterval(pollRef.current);
            setDeeplink({ phase: "error" });
          } else if (res.status === "invalid_user") {
            if (pollRef.current) clearInterval(pollRef.current);
            toast.error("Bu Telegram akkaunt saytga kira olmaydi. Administratorga murojaat qiling.");
            setDeeplink({ phase: "error" });
          }
          // "pending" — kutishda davom etamiz
        } catch {
          // vaqtinchalik tarmoq xatosi — keyingi tikda qayta urinamiz
        }
      }, 2000);
    } catch {
      setDeeplink({ phase: "error" });
    }
  }, [loginWithToken]);

  useEffect(() => {
    startDeeplink();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [startDeeplink]);

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
          {deeplink.phase === "loading" && (
            <p className="mb-4 text-sm text-slate-500">Havola tayyorlanmoqda...</p>
          )}

          {deeplink.phase === "ready" && (
            <div className="mb-4 space-y-3">
              <p className="text-sm text-slate-600">
                Telegram botni oching va <b>Start</b> tugmasini bosing — sayt avtomatik kirishni kuting.
              </p>
              <Button asChild className="w-full" size="lg">
                <a href={deeplink.botUrl} target="_blank" rel="noreferrer">
                  <Send className="mr-2 h-4 w-4" />
                  Telegram botda ochish
                </a>
              </Button>
              <p className="animate-pulse text-xs text-slate-400">Tasdiqlash kutilmoqda...</p>
            </div>
          )}

          {deeplink.phase === "error" && (
            <div className="mb-4 space-y-2">
              <p className="text-sm text-rose-600">
                Havola muddati o'tdi yoki xatolik yuz berdi.
              </p>
              <Button variant="outline" className="w-full" onClick={startDeeplink}>
                Qaytadan urinish
              </Button>
            </div>
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
